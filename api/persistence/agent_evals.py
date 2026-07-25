from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from api.utils.async_once import AsyncOnce

from sqlalchemy import (
    BigInteger,
    Boolean,
    case,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    Table,
    and_,
    delete,
    Text,
    desc,
    false,
    func,
    insert,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from api.config import get_settings
from api.persistence import durable_jobs as durable_job_store
from api.persistence.database import get_async_control_plane_engine
from api.persistence.durable_jobs import DurableJob, JobKind, JobState
from api.persistence.migrations import ensure_control_plane_schema_current

SUITES_TABLE = "agent_eval_suites"
CASES_TABLE = "agent_eval_cases"
SUITE_RUNS_TABLE = "agent_eval_suite_runs"
CASE_RUNS_TABLE = "agent_eval_case_runs"

_agent_eval_tables_once = AsyncOnce()


class ActiveEvalSuiteRunError(ValueError):
    """Raised when a Suite already has a queued or executing run."""


def _app_schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_app_schema())


def agent_eval_suites_table() -> Table:
    table = Table(
        SUITES_TABLE,
        _metadata(),
        Column("id", Text, primary_key=True),
        Column("name", Text, nullable=False),
        Column("description", Text, nullable=False, server_default=""),
        # One Suite maps to one concrete Agno Agent or Team.  Do not store a
        # free-form "agent id" on individual Cases: that allowed a visible
        # target selection to diverge from the component actually evaluated.
        Column("target_kind", Text, nullable=False),
        Column("target_id", Text, nullable=False),
        Column("enabled", Boolean, nullable=False, server_default=text("true")),
        Column("tags", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
        Column("created_by", Text, nullable=False, server_default=""),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )
    Index("idx_agent_eval_suites_updated", desc(table.c.updated_at))
    return table


def agent_eval_cases_table() -> Table:
    table = Table(
        CASES_TABLE,
        _metadata(),
        Column("id", Text, primary_key=True),
        Column("suite_id", Text, nullable=False),
        Column("name", Text, nullable=False),
        Column("description", Text, nullable=False, server_default=""),
        Column("input", Text, nullable=False),
        Column("expected_output", Text, nullable=False, server_default=""),
        Column("criteria", Text, nullable=False, server_default=""),
        # Agno's Suite ``Case.judge_mode`` is part of the evaluation contract.
        # Keep it out of opaque metadata so a binary/numeric verdict can be
        # reproduced and filtered without interpreting an arbitrary blob.
        Column(
            "judge_mode",
            Text,
            nullable=False,
            server_default=text("'binary'"),
        ),
        # Agno AccuracyEval and AgentAsJudgeEval both accept an ordered list of
        # extra instructions beyond the primary criterion. Keep them as a
        # first-class, versioned Case property rather than opaque metadata.
        Column(
            "additional_guidelines",
            JSONB,
            nullable=False,
            server_default=text("'[]'::jsonb"),
        ),
        Column("threshold", Integer, nullable=False, server_default=text("7")),
        Column(
            "eval_types",
            JSONB,
            nullable=False,
        ),
        Column(
            "expected_tool_calls",
            JSONB,
            nullable=False,
            server_default=text("'[]'::jsonb"),
        ),
        Column(
            "expected_tool_call_arguments",
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        Column(
            "allow_additional_tool_calls",
            Boolean,
            nullable=False,
            # Match Agno Case / ReliabilityEval: a normal regression Case
            # asserts required tool calls without rejecting unrelated useful
            # calls. Safety packs opt into the stricter false value per Case.
            server_default=text("true"),
        ),
        Column(
            "performance_config",
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        # Agno ``Case.timeout_seconds``: null deliberately means use the
        # Suite runner's ``default_timeout`` instead of an implicit database
        # value that would be difficult to audit later.
        Column("timeout_seconds", Integer, nullable=True),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("tags", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
        Column("enabled", Boolean, nullable=False, server_default=text("true")),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )
    Index("idx_agent_eval_cases_suite", table.c.suite_id, desc(table.c.updated_at))
    Index("idx_agent_eval_cases_enabled", table.c.enabled)
    Index("idx_agent_eval_cases_tags", table.c.tags, postgresql_using="gin")
    return table


def agent_eval_suite_runs_table() -> Table:
    table = Table(
        SUITE_RUNS_TABLE,
        _metadata(),
        Column("id", Text, primary_key=True),
        Column("suite_id", Text, nullable=False),
        Column("status", Text, nullable=False),
        Column("started_by", Text, nullable=False, server_default=""),
        Column("error_summary", Text, nullable=False, server_default=""),
        Column("summary", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        # Private immutable Suite-level execution metadata (target and worker
        # manifest). Ordered Case definitions live only on CaseRun work items;
        # public SuiteRun projections intentionally expose only ``summary``.
        Column(
            "execution_snapshot",
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        # Private durable-worker fence.  A SuiteRun may outlive a worker
        # lease, so status alone is not proof that a writer still owns the
        # execution.  The worker job id and monotonically increasing epoch
        # make stale progress and terminal writes rejectable in SQL.
        Column("active_job_id", Text, nullable=False, server_default=""),
        Column(
            "active_lease_epoch",
            BigInteger,
            nullable=False,
            server_default=text("0"),
        ),
        Column(
            "started_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column("completed_at", DateTime(timezone=True), nullable=True),
    )
    Index("idx_agent_eval_suite_runs_suite", table.c.suite_id, desc(table.c.started_at))
    Index("idx_agent_eval_suite_runs_status", table.c.status)
    return table


def agent_eval_case_runs_table() -> Table:
    table = Table(
        CASE_RUNS_TABLE,
        _metadata(),
        Column("id", Text, primary_key=True),
        Column("suite_run_id", Text, nullable=False),
        Column("case_id", Text, nullable=False),
        # A non-null index marks a CaseRun as a pre-created Suite work item.
        # Historical/direct CaseRuns keep this null, so they cannot be claimed
        # by a durable Suite worker.
        Column("work_item_index", Integer, nullable=True),
        Column("status", Text, nullable=False),
        Column("agent_run_id", Text, nullable=False, server_default=""),
        Column("session_id", Text, nullable=False, server_default=""),
        Column("trace_id", Text, nullable=False, server_default=""),
        Column(
            "agno_eval_run_ids",
            JSONB,
            nullable=False,
            server_default=text("'[]'::jsonb"),
        ),
        Column("error_type", Text, nullable=False, server_default=""),
        Column("error_summary", Text, nullable=False, server_default=""),
        Column("replay_of_case_run_id", Text, nullable=False, server_default=""),
        # Definition evidence can contain prompts and expected output. Keep it
        # in an intentionally private JSONB column, never the public CaseRun
        # projection. Execution provenance follows the same boundary.
        Column(
            "definition_snapshot",
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        Column(
            "execution_provenance",
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        # Private, write-once terminal evidence for crash-safe SuiteRun
        # recovery.  It is deliberately separate from immutable execution
        # provenance: the latter describes how a CaseRun was started, while
        # this compact JSON document records its completed evaluator result.
        Column(
            "terminal_checkpoint",
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        # A fenced Suite execution owns exactly one logical CaseRun for each
        # frozen Case.  The fields stay private: they are coordination data,
        # not evaluator output or user-visible run metadata.
        Column("lease_job_id", Text, nullable=False, server_default=""),
        Column(
            "lease_epoch",
            BigInteger,
            nullable=False,
            server_default=text("0"),
        ),
        Column(
            "started_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column("completed_at", DateTime(timezone=True), nullable=True),
    )
    Index(
        "idx_agent_eval_case_runs_suite_run",
        table.c.suite_run_id,
        desc(table.c.started_at),
    )
    Index("idx_agent_eval_case_runs_case", table.c.case_id, desc(table.c.started_at))
    Index("idx_agent_eval_case_runs_status", table.c.status)
    Index(
        "uq_agent_eval_case_runs_work_item_order",
        table.c.suite_run_id,
        table.c.work_item_index,
        unique=True,
        postgresql_where=table.c.work_item_index.is_not(None),
    )
    Index(
        "uq_agent_eval_case_runs_work_item_case",
        table.c.suite_run_id,
        table.c.case_id,
        unique=True,
        postgresql_where=table.c.work_item_index.is_not(None),
    )
    Index(
        "uq_agent_eval_case_runs_fenced_suite_case",
        table.c.suite_run_id,
        table.c.case_id,
        unique=True,
        postgresql_where=and_(
            table.c.suite_run_id != "",
            table.c.lease_epoch > 0,
        ),
    )
    return table


async def ensure_agent_eval_tables_async() -> None:
    await _agent_eval_tables_once.run(_create_agent_eval_tables_async)


async def _create_agent_eval_tables_async() -> None:
    await ensure_control_plane_schema_current()


def _row_dict(row: Any) -> dict[str, Any]:
    mapping = getattr(row, "_mapping", row)
    return dict(mapping)


def _eval_run_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        eval_run_id = str(value).strip()
        if eval_run_id and eval_run_id not in seen:
            seen.add(eval_run_id)
            normalized.append(eval_run_id)
    return normalized


async def _create_row_async(table: Table, values: dict[str, Any]) -> dict[str, Any]:
    await ensure_agent_eval_tables_async()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(insert(table).values(values).returning(table))
        row = result.mappings().one()
    return _row_dict(row)


async def _create_child_row_async(
    table: Table,
    values: dict[str, Any],
    *,
    parent_table: Table,
    parent_id_key: str,
    parent_name: str,
) -> dict[str, Any]:
    """Insert a dependent row while holding its parent against deletion.

    Eval definitions deliberately have no database foreign keys: deleting one
    editable Case keeps its immutable CaseRun evidence.  The explicit suite
    tree deletion therefore needs a matching write-side lock.  ``FOR KEY
    SHARE`` serializes a child insert with the delete path's ``FOR UPDATE``
    lock on the parent, without needlessly blocking a non-key parent update.
    """
    parent_id = str(values.get(parent_id_key) or "").strip()
    if not parent_id:
        raise ValueError(f"{parent_id_key} is required")

    await ensure_agent_eval_tables_async()
    async with get_async_control_plane_engine().begin() as conn:
        parent = (
            await conn.execute(
                select(parent_table.c.id)
                .where(parent_table.c.id == parent_id)
                .with_for_update(read=True, key_share=True)
            )
        ).scalar_one_or_none()
        if parent is None:
            raise ValueError(f"{parent_name} not found")
        result = await conn.execute(insert(table).values(values).returning(table))
        row = result.mappings().one()
    return _row_dict(row)


async def _list_rows_async(
    table: Table,
    filters: list[Any],
    order_by: list[Any],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    await ensure_agent_eval_tables_async()
    stmt = select(table)
    if filters:
        stmt = stmt.where(and_(*filters))
    if order_by:
        stmt = stmt.order_by(*order_by)
    if limit is not None:
        stmt = stmt.limit(max(1, min(int(limit), 500)))
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [_row_dict(row) for row in rows]


async def _list_rows_page_async(
    table: Table,
    filters: list[Any],
    order_by: list[Any],
    *,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """SQL page + total for growing history tables."""
    await ensure_agent_eval_tables_async()
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 50), 100))
    count_stmt = select(func.count()).select_from(table)
    list_stmt = select(table)
    if filters:
        condition = and_(*filters)
        count_stmt = count_stmt.where(condition)
        list_stmt = list_stmt.where(condition)
    if order_by:
        list_stmt = list_stmt.order_by(*order_by)
    list_stmt = list_stmt.limit(safe_limit).offset((safe_page - 1) * safe_limit)
    async with get_async_control_plane_engine().begin() as conn:
        total = int((await conn.execute(count_stmt)).scalar_one())
        rows = (await conn.execute(list_stmt)).mappings().all()
    return [_row_dict(row) for row in rows], total


async def _get_row_async(table: Table, row_id: str) -> dict[str, Any] | None:
    await ensure_agent_eval_tables_async()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (await conn.execute(select(table).where(table.c.id == row_id)))
            .mappings()
            .one_or_none()
        )
    return _row_dict(row) if row is not None else None


async def _update_row_async(
    table: Table, row_id: str, values: dict[str, Any]
) -> dict[str, Any] | None:
    await ensure_agent_eval_tables_async()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    update(table)
                    .where(table.c.id == row_id)
                    .values(values)
                    .returning(table)
                )
            )
            .mappings()
            .one_or_none()
        )
    return _row_dict(row) if row is not None else None


async def create_suite_row_async(values: dict[str, Any]) -> dict[str, Any]:
    return await _create_row_async(agent_eval_suites_table(), values)


async def list_suite_rows_async(
    enabled: bool | None = None,
    *,
    limit: int = 500,
) -> list[dict[str, Any]]:
    table = agent_eval_suites_table()
    filters = [table.c.enabled == enabled] if enabled is not None else []
    return await _list_rows_async(
        table,
        filters,
        [desc(table.c.updated_at), table.c.name],
        limit=limit,
    )


async def get_suite_row_async(suite_id: str) -> dict[str, Any] | None:
    return await _get_row_async(agent_eval_suites_table(), suite_id)


async def update_suite_row_async(
    suite_id: str, values: dict[str, Any]
) -> dict[str, Any] | None:
    return await _update_row_async(agent_eval_suites_table(), suite_id, values)


async def create_case_row_async(values: dict[str, Any]) -> dict[str, Any]:
    return await _create_child_row_async(
        agent_eval_cases_table(),
        values,
        parent_table=agent_eval_suites_table(),
        parent_id_key="suite_id",
        parent_name="Eval suite",
    )


async def list_case_rows_async(
    suite_id: str | None = None,
    enabled: bool | None = None,
    tag: str | None = None,
    name: str | None = None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return all matching Case rows for trusted internal work.

    Eval execution and Pack import must never inherit the browser-facing page
    size. Their caller is responsible for bounded concurrency; this function
    intentionally has no arbitrary row cap.
    """
    table = agent_eval_cases_table()
    filters = []
    if suite_id is not None:
        filters.append(table.c.suite_id == suite_id)
    if enabled is not None:
        filters.append(table.c.enabled == enabled)
    if tag is not None:
        filters.append(table.c.tags.contains([tag]))
    if name is not None:
        filters.append(table.c.name == name)
    return await _list_rows_async(
        table,
        filters,
        [table.c.suite_id, desc(table.c.updated_at), table.c.name],
        limit=limit,
    )


async def list_case_rows_page_async(
    suite_id: str | None = None,
    enabled: bool | None = None,
    tag: str | None = None,
    name: str | None = None,
    *,
    page: int = 1,
    limit: int = 100,
) -> tuple[list[dict[str, Any]], int]:
    """Return one browser/API page of Case definitions with an exact total."""
    table = agent_eval_cases_table()
    filters = []
    if suite_id is not None:
        filters.append(table.c.suite_id == suite_id)
    if enabled is not None:
        filters.append(table.c.enabled == enabled)
    if tag is not None:
        filters.append(table.c.tags.contains([tag]))
    if name is not None:
        filters.append(table.c.name == name)
    return await _list_rows_page_async(
        table,
        filters,
        [table.c.suite_id, desc(table.c.updated_at), table.c.name],
        page=page,
        limit=limit,
    )


async def get_case_row_async(case_id: str) -> dict[str, Any] | None:
    return await _get_row_async(agent_eval_cases_table(), case_id)


async def update_case_row_async(
    case_id: str, values: dict[str, Any]
) -> dict[str, Any] | None:
    return await _update_row_async(agent_eval_cases_table(), case_id, values)


def _case_pack_keys(row: Mapping[str, Any]) -> tuple[str, str] | None:
    metadata = row.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    pack_id = str(metadata.get("pack_id") or "").strip()
    external_id = str(metadata.get("external_id") or "").strip()
    if not pack_id or not external_id:
        return None
    return pack_id, external_id


def _assert_pack_artifact_hash_matches(
    rows: Sequence[Mapping[str, Any]],
    *,
    pack_id: str,
    pack_version: str,
    artifact_hash: str,
) -> None:
    if not artifact_hash:
        return
    mismatched_case_ids: list[str] = []
    for row in rows:
        metadata = row.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        if (
            str(metadata.get("pack_id") or "").strip() != pack_id
            or str(metadata.get("pack_version") or "").strip() != pack_version
        ):
            continue
        existing_hash = str(metadata.get("pack_cases_sha256") or "").strip()
        if existing_hash and existing_hash != artifact_hash:
            mismatched_case_ids.append(str(row.get("id") or ""))
    if mismatched_case_ids:
        raise ValueError(
            "Imported eval pack version already exists with a different cases "
            "artifact hash; bump pack_version or remove the imported Pack version"
        )


async def _lock_imported_pack_identity(
    conn: Any,
    *,
    pack_id: str,
    pack_version: str,
) -> None:
    if conn.dialect.name != "postgresql":
        return
    lock_key = f"agent-eval-pack:{pack_id}@{pack_version}"
    await conn.execute(select(func.pg_advisory_xact_lock(func.hashtext(lock_key))))


async def import_pack_rows_async(
    *,
    pack_id: str,
    pack_version: str,
    artifact_hash: str,
    suite_values: dict[str, Any],
    case_values: list[dict[str, Any]],
) -> dict[str, Any]:
    """Atomically import one exact Pack version as a Suite plus Cases."""
    normalized_pack_id = str(pack_id or "").strip()
    normalized_pack_version = str(pack_version or "").strip()
    if not normalized_pack_id:
        raise ValueError("pack_id is required")
    if not normalized_pack_version:
        raise ValueError("pack_version is required")

    await ensure_agent_eval_tables_async()
    suites = agent_eval_suites_table()
    cases = agent_eval_cases_table()
    tagged_suite_filter = and_(
        suites.c.tags.contains([f"pack:{normalized_pack_id}"]),
        suites.c.tags.contains([f"pack_version:{normalized_pack_version}"]),
    )

    async with get_async_control_plane_engine().begin() as conn:
        await _lock_imported_pack_identity(
            conn,
            pack_id=normalized_pack_id,
            pack_version=normalized_pack_version,
        )
        candidate_suite_rows = (
            (
                await conn.execute(
                    select(suites).where(tagged_suite_filter).with_for_update()
                )
            )
            .mappings()
            .all()
        )
        suite_rows = [
            _row_dict(row)
            for row in candidate_suite_rows
            if _matches_exact_imported_pack_tags(
                row.get("tags"),
                pack_id=normalized_pack_id,
                pack_version=normalized_pack_version,
            )
        ]
        created_suite = not suite_rows
        if len(suite_rows) > 1:
            raise ValueError(
                "Imported eval pack version has multiple Suites; remove the "
                "Pack version and import it again"
            )
        if created_suite:
            suite_row = (
                (
                    await conn.execute(
                        insert(suites).values(suite_values).returning(suites)
                    )
                )
                .mappings()
                .one()
            )
            suite = _row_dict(suite_row)
            existing_case_rows: list[dict[str, Any]] = []
        else:
            existing_suite = suite_rows[0]
            if (
                str(existing_suite.get("target_kind") or "").strip()
                != str(suite_values.get("target_kind") or "").strip()
                or str(existing_suite.get("target_id") or "").strip()
                != str(suite_values.get("target_id") or "").strip()
            ):
                raise ValueError(
                    "Imported Eval Pack target differs from its existing Suite; "
                    "remove the Pack version and import it again"
                )
            suite_id = str(existing_suite["id"])
            existing_case_rows = [
                _row_dict(row)
                for row in (
                    (
                        await conn.execute(
                            select(cases)
                            .where(cases.c.suite_id == suite_id)
                            .with_for_update()
                        )
                    )
                    .mappings()
                    .all()
                )
            ]
            _assert_pack_artifact_hash_matches(
                existing_case_rows,
                pack_id=normalized_pack_id,
                pack_version=normalized_pack_version,
                artifact_hash=str(artifact_hash or "").strip(),
            )
            suite_row = (
                (
                    await conn.execute(
                        update(suites)
                        .where(suites.c.id == suite_id)
                        .values(
                            {
                                key: value
                                for key, value in suite_values.items()
                                if key not in {"id", "created_by"}
                            }
                        )
                        .returning(suites)
                    )
                )
                .mappings()
                .one()
            )
            suite = _row_dict(suite_row)

        suite_id = str(suite["id"])
        by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for row in existing_case_rows:
            key = _case_pack_keys(row)
            if key is not None:
                by_key[key] = row

        created = 0
        updated = 0
        for values in case_values:
            metadata = values.get("metadata")
            if not isinstance(metadata, Mapping):
                raise ValueError("Imported eval case metadata is required")
            key = (
                normalized_pack_id,
                str(metadata.get("external_id") or "").strip(),
            )
            if not key[1]:
                raise ValueError("Imported eval case external_id is required")
            write_values = {**values, "suite_id": suite_id}
            existing = by_key.get(key)
            if existing is None:
                row = (
                    (
                        await conn.execute(
                            insert(cases).values(write_values).returning(cases)
                        )
                    )
                    .mappings()
                    .one()
                )
                by_key[key] = _row_dict(row)
                created += 1
            else:
                case_id = str(existing["id"])
                row = (
                    (
                        await conn.execute(
                            update(cases)
                            .where(cases.c.id == case_id)
                            .values({key: value for key, value in write_values.items() if key != "id"})
                            .returning(cases)
                        )
                    )
                    .mappings()
                    .one()
                )
                by_key[key] = _row_dict(row)
                updated += 1

    return {
        "suite": suite,
        "created_suite": created_suite,
        "cases_created": created,
        "cases_updated": updated,
        "cases_in_suite": len(by_key),
    }


async def delete_case_row_async(case_id: str) -> dict[str, Any] | None:
    """Delete one Case definition while retaining immutable run evidence.

    Case-run rows are historical observations and Suite summaries deliberately
    retain their CaseResult-lite snapshots.  Unlike a whole Suite removal, a
    single Case deletion therefore only removes the editable definition (which
    contains the raw prompt) and leaves the historical result artifacts intact.
    """
    await ensure_agent_eval_tables_async()
    table = agent_eval_cases_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    delete(table).where(table.c.id == case_id).returning(table)
                )
            )
            .mappings()
            .one_or_none()
        )
    return _row_dict(row) if row is not None else None


def _validate_suite_run_work_items(
    *,
    suite_run_id: str,
    case_run_values: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate the one-to-one pre-created CaseRun work-item plan."""
    if isinstance(case_run_values, (str, bytes)):
        raise ValueError("SuiteRun CaseRun work items must be a sequence")
    if not case_run_values:
        raise ValueError("SuiteRun requires at least one pre-created CaseRun")

    normalized: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    work_item_ids: set[str] = set()
    for expected_index, raw_values in enumerate(case_run_values):
        values = dict(raw_values)
        work_item_id = str(values.get("id") or "").strip()
        case_id = str(values.get("case_id") or "").strip()
        row_suite_run_id = str(values.get("suite_run_id") or "").strip()
        work_item_index = values.get("work_item_index")
        if not work_item_id or not case_id or row_suite_run_id != suite_run_id:
            raise ValueError("CaseRun work item must belong to its SuiteRun and Case")
        if (
            isinstance(work_item_index, bool)
            or not isinstance(work_item_index, int)
            or work_item_index != expected_index
        ):
            raise ValueError("CaseRun work item indexes must be contiguous and ordered")
        if values.get("status") != "queued":
            raise ValueError("pre-created CaseRun work items must start queued")
        if work_item_id in work_item_ids or case_id in case_ids:
            raise ValueError("SuiteRun CaseRun work items must be unique")
        if not isinstance(values.get("definition_snapshot"), Mapping) or not values.get(
            "definition_snapshot"
        ):
            raise ValueError("CaseRun work item requires definition_snapshot")
        if not isinstance(values.get("execution_provenance"), Mapping) or not values.get(
            "execution_provenance"
        ):
            raise ValueError("CaseRun work item requires execution_provenance")
        if str(values.get("lease_job_id") or "") or int(values.get("lease_epoch") or 0):
            raise ValueError("pre-created CaseRun work item must not own a lease")
        work_item_ids.add(work_item_id)
        case_ids.add(case_id)
        normalized.append(values)
    return normalized


def _validate_eval_suite_job_contract(
    *,
    suite_run_id: str,
    kind: JobKind | str,
    payload: Mapping[str, Any],
    idempotency_key: str,
) -> None:
    """Keep durable job identity tied to the SuiteRun inserted beside it."""
    normalized_kind = kind.value if isinstance(kind, JobKind) else str(kind)
    if normalized_kind != JobKind.EVAL_SUITE_RUN.value:
        raise ValueError("SuiteRun work items require an eval_suite_run durable job")
    if dict(payload) != {"suite_run_id": suite_run_id}:
        raise ValueError("Eval Suite durable job payload must contain only its suite_run_id")
    if idempotency_key != f"eval-suite-run:{suite_run_id}":
        raise ValueError("Eval Suite durable job idempotency key must match its SuiteRun")


async def create_suite_run_with_case_runs_and_enqueue_job_async(
    values: dict[str, Any],
    *,
    case_run_values: Sequence[Mapping[str, Any]],
    kind: JobKind | str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    max_attempts: int = 5,
    priority: int = 0,
) -> tuple[dict[str, Any], DurableJob]:
    """Atomically create a queued SuiteRun, all CaseRuns, and its worker job.

    A standalone API process can die at any instruction boundary.  Keeping the
    SuiteRun, CaseRun work-item, and durable-job inserts in one transaction
    prevents an orphaned ``queued`` run or a worker with no immutable work.
    """
    suite_run_id = str(values.get("id") or "").strip()
    suite_id = str(values.get("suite_id") or "").strip()
    if not suite_run_id:
        raise ValueError("suite run id is required")
    if not suite_id:
        raise ValueError("suite_id is required")
    snapshot = values.get("execution_snapshot")
    manifest = snapshot.get("run_manifest") if isinstance(snapshot, Mapping) else None
    actor = manifest.get("actor") if isinstance(manifest, Mapping) else None
    if not isinstance(actor, Mapping) or str(actor.get("id") or "").strip() != str(
        values.get("started_by") or ""
    ).strip():
        raise ValueError("SuiteRun started_by must match its immutable execution manifest")
    work_items = _validate_suite_run_work_items(
        suite_run_id=suite_run_id,
        case_run_values=case_run_values,
    )
    _validate_eval_suite_job_contract(
        suite_run_id=suite_run_id,
        kind=kind,
        payload=payload,
        idempotency_key=idempotency_key,
    )

    await ensure_agent_eval_tables_async()
    suites = agent_eval_suites_table()
    suite_runs = agent_eval_suite_runs_table()
    case_runs = agent_eval_case_runs_table()
    async with get_async_control_plane_engine().begin() as conn:
        parent = (
            await conn.execute(
                select(suites.c.id)
                .where(suites.c.id == suite_id)
                # A key-share lock protects against deletion, but permits two
                # producers to observe "no active run" concurrently.  Take a
                # short parent update lock so this check and insert serialize.
                .with_for_update()
            )
        ).scalar_one_or_none()
        if parent is None:
            raise ValueError("Eval suite not found")
        active_run = (
            await conn.execute(
                select(suite_runs.c.id)
                .where(
                    and_(
                        suite_runs.c.suite_id == suite_id,
                        suite_runs.c.status.in_(("queued", "running", "cancelling")),
                    )
                )
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if active_run is not None:
            raise ActiveEvalSuiteRunError(
                f"Eval suite already has an active run: {active_run}"
            )
        row = (
            (
                await conn.execute(
                    insert(suite_runs).values(values).returning(suite_runs)
                )
            )
            .mappings()
            .one()
        )
        await conn.execute(insert(case_runs).values(work_items))
        job = await durable_job_store.enqueue_job_in_transaction(
            conn,
            kind=kind,
            payload=payload,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
            priority=priority,
        )
    return _row_dict(row), job


async def list_suite_run_rows_async(
    suite_id: str | None = None,
    status: str | None = None,
    *,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Paginated suite runs (newest first). Returns ``(rows, total_count)``."""
    table = agent_eval_suite_runs_table()
    filters = []
    if suite_id is not None:
        filters.append(table.c.suite_id == suite_id)
    if status is not None:
        filters.append(table.c.status == status)
    return await _list_rows_page_async(
        table,
        filters,
        [desc(table.c.started_at), table.c.id],
        page=page,
        limit=limit,
    )


async def get_suite_run_row_async(suite_run_id: str) -> dict[str, Any] | None:
    return await _get_row_async(agent_eval_suite_runs_table(), suite_run_id)


async def request_suite_run_cancel_row_async(
    suite_run_id: str,
    *,
    cancel_requested_at: str,
) -> dict[str, Any] | None:
    """Atomically mark an active SuiteRun as cancelling without losing progress.

    A worker may persist a partial ``summary`` while an operator asks to cancel.
    Locking the row before reading its current JSON lets the cancellation marker
    merge with that latest progress instead of restoring a stale snapshot.
    """
    normalized_suite_run_id = str(suite_run_id or "").strip()
    if not normalized_suite_run_id:
        return None

    await ensure_agent_eval_tables_async()
    table = agent_eval_suite_runs_table()
    active_statuses = {"queued", "running", "cancelling"}
    terminal_statuses = {"passed", "failed", "error", "cancelled", "completed"}
    async with get_async_control_plane_engine().begin() as conn:
        locked_row = (
            (
                await conn.execute(
                    select(table)
                    .where(table.c.id == normalized_suite_run_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if locked_row is None:
            return None

        current = _row_dict(locked_row)
        status = str(current.get("status") or "")
        if status in terminal_statuses or status not in active_statuses:
            return current

        raw_summary = current.get("summary")
        summary = dict(raw_summary) if isinstance(raw_summary, Mapping) else {}
        summary["cancel_requested"] = True
        summary["cancel_requested_at"] = cancel_requested_at
        updated_row = (
            (
                await conn.execute(
                    update(table)
                    .where(table.c.id == normalized_suite_run_id)
                    .values(
                        status="cancelling",
                        summary=summary,
                        error_summary="Eval suite cancellation requested",
                    )
                    .returning(table)
                )
            )
            .mappings()
            .one_or_none()
        )
    return _row_dict(updated_row) if updated_row is not None else current


async def update_suite_run_row_async(
    suite_run_id: str, values: dict[str, Any]
) -> dict[str, Any] | None:
    if "execution_snapshot" in values:
        raise ValueError("SuiteRun execution_snapshot is immutable")
    return await _update_row_async(agent_eval_suite_runs_table(), suite_run_id, values)


async def update_suite_run_row_if_status_async(
    suite_run_id: str,
    *,
    expected_statuses: Sequence[str],
    values: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Compare-and-set one SuiteRun lifecycle transition.

    A queued eval can be claimed by the durable worker while an operator asks
    to cancel it.  Keep the state transition in SQL so a stale worker cannot
    overwrite ``cancelling`` with ``running`` (or a terminal cancellation with
    a successful result) after that request wins.
    """
    statuses = tuple(
        value.strip() for value in expected_statuses if isinstance(value, str) and value.strip()
    )
    if not statuses:
        raise ValueError("expected_statuses is required")
    if "execution_snapshot" in values:
        raise ValueError("SuiteRun execution_snapshot is immutable")
    await ensure_agent_eval_tables_async()
    table = agent_eval_suite_runs_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    update(table)
                    .where(
                        and_(
                            table.c.id == suite_run_id,
                            table.c.status.in_(statuses),
                        )
                    )
                    .values(dict(values))
                    .returning(table)
                )
            )
            .mappings()
            .one_or_none()
        )
    return _row_dict(row) if row is not None else None


def _normalise_execution_lease(
    *,
    job_id: str,
    lease_epoch: int,
) -> tuple[str, int]:
    """Validate the private durable-job fence used by Eval execution writes."""
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        raise ValueError("execution lease job_id is required")
    if isinstance(lease_epoch, bool):
        raise ValueError("execution lease epoch must be a positive integer")
    try:
        normalized_epoch = int(lease_epoch)
    except (TypeError, ValueError) as exc:
        raise ValueError("execution lease epoch must be a positive integer") from exc
    if normalized_epoch < 1:
        raise ValueError("execution lease epoch must be a positive integer")
    return normalized_job_id, normalized_epoch


async def _lock_current_eval_suite_job_async(
    conn: Any,
    *,
    job_id: str,
    lease_epoch: int,
    suite_run_id: str | None = None,
) -> str | None:
    """Lock and validate a live Eval Suite durable lease.

    The SuiteRun's copied fence is not sufficient on its own: a durable worker
    can claim a newer epoch before it has begun the runner and updated that
    copied fence.  Every fenced Eval mutation therefore locks the durable row
    first and proves that the exact Eval Suite lease is still running, current,
    unexpired, and belongs to the same SuiteRun payload.
    """
    durable_jobs = durable_job_store.durable_jobs_table()
    payload_suite_run_id = durable_jobs.c.payload["suite_run_id"].astext
    conditions = [
        durable_jobs.c.id == job_id,
        durable_jobs.c.kind == JobKind.EVAL_SUITE_RUN.value,
        durable_jobs.c.state == JobState.RUNNING.value,
        durable_jobs.c.lease_epoch == lease_epoch,
        durable_jobs.c.lease_expires_at > func.clock_timestamp(),
    ]
    if suite_run_id is not None:
        conditions.append(payload_suite_run_id == suite_run_id)
    locked_payload_suite_run_id = (
        await conn.execute(
            select(payload_suite_run_id)
            .where(and_(*conditions))
            .with_for_update(of=durable_jobs)
        )
    ).scalar_one_or_none()
    normalized_payload_suite_run_id = str(locked_payload_suite_run_id or "").strip()
    return normalized_payload_suite_run_id or None


async def _lock_current_suite_run_execution_for_case_write_async(
    conn: Any,
    *,
    case_run_id: str,
    job_id: str,
    lease_epoch: int,
    suite_run_id: str,
) -> str | None:
    """Lock a CaseRun's parent SuiteRun while its fence is still current.

    Callers hold the durable-job row first; this helper then acquires the
    parent SuiteRun lock before its CaseRun row. A correlated ``EXISTS``
    predicate alone observes a statement snapshot, so a concurrent SuiteRun
    takeover could otherwise commit between that observation and the CaseRun
    update. Locking the SuiteRun makes the takeover and CaseRun write serialize
    in the same durable job -> SuiteRun -> CaseRun order used by
    :func:`claim_suite_case_run_row_async`.
    """
    suite_runs = agent_eval_suite_runs_table()
    case_runs = agent_eval_case_runs_table()
    locked_suite_run_id = (
        await conn.execute(
            select(suite_runs.c.id)
            .select_from(
                suite_runs.join(
                    case_runs,
                    suite_runs.c.id == case_runs.c.suite_run_id,
                )
            )
            .where(
                and_(
                    case_runs.c.id == case_run_id,
                    suite_runs.c.id == suite_run_id,
                    suite_runs.c.active_job_id == job_id,
                    suite_runs.c.active_lease_epoch == lease_epoch,
                )
            )
            .with_for_update(of=suite_runs)
        )
    ).scalar_one_or_none()
    return str(locked_suite_run_id) if locked_suite_run_id is not None else None


async def claim_suite_run_execution_row_async(
    suite_run_id: str,
    *,
    job_id: str,
    lease_epoch: int,
) -> dict[str, Any] | None:
    """Fence and claim a durable SuiteRun execution atomically.

    The durable job lease can be recovered while an old process is still
    scheduled.  The newer job epoch wins this compare-and-set; every later
    Eval write has to carry the same pair.  A different durable job is never
    allowed to attach to an already-bound SuiteRun.
    """
    normalized_suite_run_id = str(suite_run_id or "").strip()
    if not normalized_suite_run_id:
        return None
    normalized_job_id, normalized_epoch = _normalise_execution_lease(
        job_id=job_id,
        lease_epoch=lease_epoch,
    )
    await ensure_agent_eval_tables_async()
    table = agent_eval_suite_runs_table()
    claimable_statuses = ("queued", "running", "cancelling")
    async with get_async_control_plane_engine().begin() as conn:
        if (
            await _lock_current_eval_suite_job_async(
                conn,
                job_id=normalized_job_id,
                lease_epoch=normalized_epoch,
                suite_run_id=normalized_suite_run_id,
            )
            is None
        ):
            return None
        row = (
            (
                await conn.execute(
                    update(table)
                    .where(
                        and_(
                            table.c.id == normalized_suite_run_id,
                            table.c.status.in_(claimable_statuses),
                            or_(
                                table.c.active_job_id == "",
                                and_(
                                    table.c.active_job_id == normalized_job_id,
                                    table.c.active_lease_epoch < normalized_epoch,
                                ),
                            ),
                        )
                    )
                    .values(
                        status=case(
                            (table.c.status == "queued", "running"),
                            else_=table.c.status,
                        ),
                        active_job_id=normalized_job_id,
                        active_lease_epoch=normalized_epoch,
                    )
                    .returning(table)
                )
            )
            .mappings()
            .one_or_none()
        )
    return _row_dict(row) if row is not None else None


async def update_suite_run_row_if_execution_lease_async(
    suite_run_id: str,
    *,
    expected_statuses: Sequence[str],
    job_id: str,
    lease_epoch: int,
    values: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Write a SuiteRun only while its exact durable fence is current."""
    statuses = tuple(
        value.strip()
        for value in expected_statuses
        if isinstance(value, str) and value.strip()
    )
    if not statuses:
        raise ValueError("expected_statuses is required")
    if "execution_snapshot" in values:
        raise ValueError("SuiteRun execution_snapshot is immutable")
    normalized_job_id, normalized_epoch = _normalise_execution_lease(
        job_id=job_id,
        lease_epoch=lease_epoch,
    )
    await ensure_agent_eval_tables_async()
    table = agent_eval_suite_runs_table()
    async with get_async_control_plane_engine().begin() as conn:
        if (
            await _lock_current_eval_suite_job_async(
                conn,
                job_id=normalized_job_id,
                lease_epoch=normalized_epoch,
                suite_run_id=str(suite_run_id or "").strip(),
            )
            is None
        ):
            return None
        row = (
            (
                await conn.execute(
                    update(table)
                    .where(
                        and_(
                            table.c.id == str(suite_run_id or "").strip(),
                            table.c.status.in_(statuses),
                            table.c.active_job_id == normalized_job_id,
                            table.c.active_lease_epoch == normalized_epoch,
                        )
                    )
                    .values(dict(values))
                    .returning(table)
                )
            )
            .mappings()
            .one_or_none()
        )
    return _row_dict(row) if row is not None else None


async def _create_replay_case_run_from_snapshot_row_async(
    values: dict[str, Any],
    *,
    replay_source_case_run_id: str,
) -> dict[str, Any]:
    """Insert a replay row after locking and verifying its immutable source.

    A normal direct CaseRun locks the live Case to serialize with deletion.
    Replays are different: their source Case may have been deleted, while its
    historical CaseRun (and definition snapshot) remains valid evidence. Lock
    that source run instead and require an exact snapshot match, so this path
    cannot create arbitrary dangling CaseRun rows.
    """
    source_id = str(replay_source_case_run_id or "").strip()
    replay_of_case_run_id = str(values.get("replay_of_case_run_id") or "").strip()
    if not source_id or replay_of_case_run_id != source_id:
        raise ValueError("replay_source_case_run_id must match replay_of_case_run_id")

    requested_snapshot = values.get("definition_snapshot")
    if not isinstance(requested_snapshot, Mapping) or not requested_snapshot:
        raise ValueError("Replay CaseRun requires a non-empty definition_snapshot")

    await ensure_agent_eval_tables_async()
    case_runs = agent_eval_case_runs_table()
    suite_runs = agent_eval_suite_runs_table()
    suite_run_id = str(values.get("suite_run_id") or "").strip()
    async with get_async_control_plane_engine().begin() as conn:
        # Lock in the same SuiteRun -> CaseRun order used by suite-tree
        # deletion. This avoids a replay/deletion deadlock for a replay that
        # is attached to an existing SuiteRun.
        if suite_run_id:
            suite_run = (
                await conn.execute(
                    select(suite_runs.c.id)
                    .where(suite_runs.c.id == suite_run_id)
                    .with_for_update(read=True, key_share=True)
                )
            ).scalar_one_or_none()
            if suite_run is None:
                raise ValueError("Eval suite run not found")

        source_row = (
            (
                await conn.execute(
                    select(case_runs)
                    .where(case_runs.c.id == source_id)
                    .with_for_update(read=True, key_share=True)
                )
            )
            .mappings()
            .one_or_none()
        )
        if source_row is None:
            raise ValueError("Replay source Eval case run not found")
        source = _row_dict(source_row)
        source_snapshot = source.get("definition_snapshot")
        if not isinstance(source_snapshot, Mapping) or not source_snapshot:
            raise ValueError("Replay source Eval case run has no definition_snapshot")
        if dict(source_snapshot) != dict(requested_snapshot):
            raise ValueError("Replay definition_snapshot must match its source CaseRun")
        if str(source.get("case_id") or "").strip() != str(
            values.get("case_id") or ""
        ).strip():
            raise ValueError("Replay CaseRun must retain its source case_id")

        result = await conn.execute(insert(case_runs).values(values).returning(case_runs))
        row = result.mappings().one()
    return _row_dict(row)


async def create_case_run_row_async(
    values: dict[str, Any],
    *,
    replay_source_case_run_id: str | None = None,
) -> dict[str, Any]:
    # A Suite execution always has a SuiteRun parent. A normal direct Case run
    # locks its live Case; snapshot-backed replays are handled above and lock
    # their source CaseRun because the editable Case may no longer exist.
    if replay_source_case_run_id is not None:
        return await _create_replay_case_run_from_snapshot_row_async(
            values,
            replay_source_case_run_id=replay_source_case_run_id,
        )
    suite_run_id = str(values.get("suite_run_id") or "").strip()
    if not suite_run_id:
        return await _create_child_row_async(
            agent_eval_case_runs_table(),
            values,
            parent_table=agent_eval_cases_table(),
            parent_id_key="case_id",
            parent_name="Eval case",
        )
    return await _create_child_row_async(
        agent_eval_case_runs_table(),
        values,
        parent_table=agent_eval_suite_runs_table(),
        parent_id_key="suite_run_id",
        parent_name="Eval suite run",
    )


async def claim_suite_case_run_row_async(
    values: Mapping[str, Any],
    *,
    job_id: str,
    lease_epoch: int,
) -> tuple[dict[str, Any], bool] | None:
    """Claim or take over one pre-created fenced CaseRun work item.

    The locked SuiteRun check gives the operation a single linearization point
    with a SuiteRun takeover.  A missing work item is an invariant failure:
    workers must never create rows while executing. ``True`` means the caller
    owns a non-terminal CaseRun and may invoke the target; ``False`` returns a
    terminal or already-owned row which must not produce another invocation.
    """
    normalized_job_id, normalized_epoch = _normalise_execution_lease(
        job_id=job_id,
        lease_epoch=lease_epoch,
    )
    suite_run_id = str(values.get("suite_run_id") or "").strip()
    case_id = str(values.get("case_id") or "").strip()
    if not suite_run_id or not case_id:
        raise ValueError("fenced CaseRun requires suite_run_id and case_id")

    await ensure_agent_eval_tables_async()
    suite_runs = agent_eval_suite_runs_table()
    case_runs = agent_eval_case_runs_table()
    terminal_statuses = ("passed", "failed", "error", "cancelled", "skipped")
    active_statuses = ("queued", "running")
    async with get_async_control_plane_engine().begin() as conn:
        if (
            await _lock_current_eval_suite_job_async(
                conn,
                job_id=normalized_job_id,
                lease_epoch=normalized_epoch,
                suite_run_id=suite_run_id,
            )
            is None
        ):
            return None
        suite_row = (
            (
                await conn.execute(
                    select(suite_runs)
                    .where(suite_runs.c.id == suite_run_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if suite_row is None:
            return None
        suite = _row_dict(suite_row)
        if (
            str(suite.get("active_job_id") or "") != normalized_job_id
            or int(suite.get("active_lease_epoch") or 0) != normalized_epoch
            or str(suite.get("status") or "")
            not in {"running", "cancelling"}
        ):
            return None

        existing_row = (
            (
                await conn.execute(
                    select(case_runs)
                    .where(
                        and_(
                            case_runs.c.suite_run_id == suite_run_id,
                            case_runs.c.case_id == case_id,
                            case_runs.c.work_item_index.is_not(None),
                        )
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing_row is None:
            return None

        existing = _row_dict(existing_row)
        existing_status = str(existing.get("status") or "")
        if existing_status in terminal_statuses:
            return existing, False

        existing_epoch = int(existing.get("lease_epoch") or 0)
        existing_job_id = str(existing.get("lease_job_id") or "")
        if existing_epoch > normalized_epoch:
            return None
        if existing_epoch == normalized_epoch:
            if existing_job_id != normalized_job_id:
                return None
            return existing, False
        if existing_status not in active_statuses or existing.get("terminal_checkpoint") not in (
            {},
            None,
        ):
            return None
        row = (
            (
                await conn.execute(
                    update(case_runs)
                    .where(
                        and_(
                            case_runs.c.id == str(existing.get("id") or ""),
                            case_runs.c.lease_epoch == existing_epoch,
                            case_runs.c.status.in_(active_statuses),
                            case_runs.c.terminal_checkpoint == {},
                        )
                    )
                    .values(
                        status="running",
                        lease_job_id=normalized_job_id,
                        lease_epoch=normalized_epoch,
                    )
                    .returning(case_runs)
                )
            )
            .mappings()
            .one_or_none()
        )
        return (_row_dict(row), True) if row is not None else None


async def list_case_run_rows_async(
    suite_run_id: str | None = None,
    case_id: str | None = None,
    status: str | None = None,
    *,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Paginated case runs (newest first). Returns ``(rows, total_count)``."""
    table = agent_eval_case_runs_table()
    filters = []
    if suite_run_id is not None:
        filters.append(table.c.suite_run_id == suite_run_id)
    if case_id is not None:
        filters.append(table.c.case_id == case_id)
    if status is not None:
        filters.append(table.c.status == status)
    return await _list_rows_page_async(
        table,
        filters,
        [desc(table.c.started_at), table.c.id],
        page=page,
        limit=limit,
    )


async def list_suite_run_case_work_item_rows_async(
    suite_run_id: str,
) -> list[dict[str, Any]]:
    """Return only pre-created SuiteRun CaseRun work items in frozen order.

    A Suite may have historical direct CaseRuns as well as its durable work
    items.  Worker recovery and Suite reports must never use those historical
    rows as an alternate source of selected case definitions, so this query is
    deliberately restricted to non-null ``work_item_index`` rows.
    """
    normalized_suite_run_id = str(suite_run_id or "").strip()
    if not normalized_suite_run_id:
        return []

    await ensure_agent_eval_tables_async()
    table = agent_eval_case_runs_table()
    async with get_async_control_plane_engine().begin() as conn:
        rows = (
            (
                await conn.execute(
                    select(table)
                    .where(
                        and_(
                            table.c.suite_run_id == normalized_suite_run_id,
                            table.c.work_item_index.is_not(None),
                        )
                    )
                    .order_by(table.c.work_item_index.asc(), table.c.id)
                )
            )
            .mappings()
            .all()
        )
    return [_row_dict(row) for row in rows]


async def get_case_run_row_async(case_run_id: str) -> dict[str, Any] | None:
    return await _get_row_async(agent_eval_case_runs_table(), case_run_id)


def case_runs_by_agno_eval_run_ids_statement(eval_run_ids: list[str]) -> Any:
    table = agent_eval_case_runs_table()
    filters = [
        table.c.agno_eval_run_ids.contains([eval_run_id])
        for eval_run_id in _eval_run_ids(eval_run_ids)
    ]
    condition = or_(*filters) if filters else false()
    return select(table).where(condition).order_by(desc(table.c.started_at), table.c.id)


async def list_case_runs_by_agno_eval_run_ids_rows_async(
    eval_run_ids: list[str],
) -> list[dict[str, Any]]:
    eval_run_keys = _eval_run_ids(eval_run_ids)
    if not eval_run_keys:
        return []
    await ensure_agent_eval_tables_async()
    async with get_async_control_plane_engine().begin() as conn:
        rows = (
            (
                await conn.execute(
                    case_runs_by_agno_eval_run_ids_statement(eval_run_keys)
                )
            )
            .mappings()
            .all()
        )
    return [_row_dict(row) for row in rows]


async def update_case_run_row_async(
    case_run_id: str, values: dict[str, Any]
) -> dict[str, Any] | None:
    immutable_keys = {
        "suite_run_id",
        "case_id",
        "work_item_index",
        "definition_snapshot",
        "execution_provenance",
        "terminal_checkpoint",
    }
    if immutable_keys.intersection(values):
        raise ValueError(
            "CaseRun definition_snapshot, execution_provenance, and "
            "terminal_checkpoint are immutable"
        )
    return await _update_row_async(agent_eval_case_runs_table(), case_run_id, values)


async def update_case_run_row_if_execution_lease_async(
    case_run_id: str,
    *,
    job_id: str,
    lease_epoch: int,
    values: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Update a fenced CaseRun only while its SuiteRun fence remains current."""
    immutable_keys = {
        "suite_run_id",
        "case_id",
        "work_item_index",
        "definition_snapshot",
        "execution_provenance",
        "terminal_checkpoint",
    }
    if immutable_keys.intersection(values):
        raise ValueError("CaseRun private evidence is immutable")
    normalized_job_id, normalized_epoch = _normalise_execution_lease(
        job_id=job_id,
        lease_epoch=lease_epoch,
    )
    normalized_case_run_id = str(case_run_id or "").strip()
    if not normalized_case_run_id:
        return None
    await ensure_agent_eval_tables_async()
    case_runs = agent_eval_case_runs_table()
    async with get_async_control_plane_engine().begin() as conn:
        durable_suite_run_id = await _lock_current_eval_suite_job_async(
            conn,
            job_id=normalized_job_id,
            lease_epoch=normalized_epoch,
        )
        if durable_suite_run_id is None:
            return None
        locked_suite_run_id = await _lock_current_suite_run_execution_for_case_write_async(
            conn,
            case_run_id=normalized_case_run_id,
            job_id=normalized_job_id,
            lease_epoch=normalized_epoch,
            suite_run_id=durable_suite_run_id,
        )
        if locked_suite_run_id is None:
            return None
        row = (
            (
                await conn.execute(
                    update(case_runs)
                    .where(
                        and_(
                            case_runs.c.id == normalized_case_run_id,
                            case_runs.c.suite_run_id == locked_suite_run_id,
                            case_runs.c.lease_job_id == normalized_job_id,
                            case_runs.c.lease_epoch == normalized_epoch,
                        )
                    )
                    .values(dict(values))
                    .returning(case_runs)
                )
            )
            .mappings()
            .one_or_none()
        )
    return _row_dict(row) if row is not None else None


async def complete_case_run_row_if_queued_async(
    case_run_id: str,
    *,
    values: Mapping[str, Any],
    terminal_checkpoint: Mapping[str, Any],
    job_id: str | None = None,
    lease_epoch: int | None = None,
) -> dict[str, Any] | None:
    """Atomically complete one queued CaseRun and write its private evidence.

    A worker can die after it has evaluated a Case but before it has persisted
    the enclosing SuiteRun progress row.  The terminal checkpoint must commit
    with the CaseRun state itself, not in a follow-up update.  The conditional
    transition also makes the checkpoint write-once: a stale worker cannot
    replace a completed result after another writer wins.
    """
    normalized_case_run_id = str(case_run_id or "").strip()
    if not normalized_case_run_id:
        return None
    if not isinstance(terminal_checkpoint, Mapping):
        raise ValueError("terminal_checkpoint must be an object")
    if {"definition_snapshot", "execution_provenance", "terminal_checkpoint"}.intersection(
        values
    ):
        raise ValueError("CaseRun private evidence can only be written at creation/completion")

    if (job_id is None) != (lease_epoch is None):
        raise ValueError("execution lease requires both job_id and lease_epoch")

    await ensure_agent_eval_tables_async()
    table = agent_eval_case_runs_table()
    update_values = {
        **dict(values),
        "terminal_checkpoint": dict(terminal_checkpoint),
    }
    conditions = [
        table.c.id == normalized_case_run_id,
        table.c.status.in_(("queued", "running")),
        table.c.terminal_checkpoint == {},
    ]
    normalized_job_id: str | None = None
    normalized_epoch: int | None = None
    if job_id is not None and lease_epoch is not None:
        normalized_job_id, normalized_epoch = _normalise_execution_lease(
            job_id=job_id,
            lease_epoch=lease_epoch,
        )
        conditions.extend(
            (
                table.c.lease_job_id == normalized_job_id,
                table.c.lease_epoch == normalized_epoch,
            )
        )
    async with get_async_control_plane_engine().begin() as conn:
        if normalized_job_id is not None and normalized_epoch is not None:
            durable_suite_run_id = await _lock_current_eval_suite_job_async(
                conn,
                job_id=normalized_job_id,
                lease_epoch=normalized_epoch,
            )
            if durable_suite_run_id is None:
                return None
            locked_suite_run_id = (
                await _lock_current_suite_run_execution_for_case_write_async(
                    conn,
                    case_run_id=normalized_case_run_id,
                    job_id=normalized_job_id,
                    lease_epoch=normalized_epoch,
                    suite_run_id=durable_suite_run_id,
                )
            )
            if locked_suite_run_id is None:
                return None
            conditions.append(table.c.suite_run_id == locked_suite_run_id)
        row = (
            (
                await conn.execute(
                    update(table)
                    .where(and_(*conditions))
                    .values(update_values)
                    .returning(table)
                )
            )
            .mappings()
            .one_or_none()
        )
    return _row_dict(row) if row is not None else None


def _matches_exact_imported_pack_tags(
    tags: Any,
    *,
    pack_id: str,
    pack_version: str,
) -> bool:
    """Accept only one unambiguous pack/version identity pair."""
    if not isinstance(tags, list):
        return False
    pack_ids: set[str] = set()
    pack_versions: set[str] = set()
    for tag in tags:
        text = str(tag).strip()
        if text.startswith("pack:"):
            value = text.split(":", 1)[1].strip()
            if value:
                pack_ids.add(value)
        elif text.startswith("pack_version:"):
            value = text.split(":", 1)[1].strip()
            if value:
                pack_versions.add(value)
    return pack_ids == {pack_id} and pack_versions == {pack_version}


async def _delete_suite_tree_in_transaction(
    conn: Any,
    *,
    suite_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Delete Suite definitions and every dependent workbench artifact.

    The eval tables intentionally do not use database foreign keys because
    Agno's own result store is independent.  Keep the explicit order here
    (CaseRun → SuiteRun → Case → Suite) in one transaction so a failed delete
    cannot leave an incomplete workbench tree behind.
    """
    suites = agent_eval_suites_table()
    cases = agent_eval_cases_table()
    suite_runs = agent_eval_suite_runs_table()
    case_runs = agent_eval_case_runs_table()
    suite_ids = [str(row["id"]) for row in suite_rows]
    case_rows = (
        (
            await conn.execute(
                select(cases).where(cases.c.suite_id.in_(suite_ids)).with_for_update()
            )
        )
        .mappings()
        .all()
    )
    case_ids = [str(row["id"]) for row in case_rows]
    suite_run_rows = (
        (
            await conn.execute(
                select(suite_runs.c.id, suite_runs.c.status)
                .where(suite_runs.c.suite_id.in_(suite_ids))
                .with_for_update()
            )
        )
        .mappings()
        .all()
    )
    suite_run_ids = [str(row["id"]) for row in suite_run_rows]
    active_suite_run_ids = [
        str(row["id"])
        for row in suite_run_rows
        if str(row.get("status") or "") in {"queued", "running", "cancelling"}
    ]
    if active_suite_run_ids:
        raise ActiveEvalSuiteRunError(
            "Eval suite cannot be removed while it has active run(s): "
            + ", ".join(active_suite_run_ids)
        )

    case_run_filters = []
    if case_ids:
        case_run_filters.append(case_runs.c.case_id.in_(case_ids))
    if suite_run_ids:
        case_run_filters.append(case_runs.c.suite_run_id.in_(suite_run_ids))
    case_run_ids: list[str] = []
    if case_run_filters:
        case_run_rows = (
            (
                await conn.execute(
                    select(case_runs.c.id)
                    .where(or_(*case_run_filters))
                    .with_for_update()
                )
            )
            .mappings()
            .all()
        )
        case_run_ids = [str(row["id"]) for row in case_run_rows]

    # An Eval SuiteRun and its durable job are created atomically but do not
    # have a database FK (the generic job table intentionally knows no Eval
    # schema). Remove terminal jobs in this same transaction so a pack/suite
    # delete cannot leave a later worker retrying an orphaned payload.
    durable_jobs = durable_job_store.durable_jobs_table()
    durable_job_ids: list[str] = []
    if suite_run_ids:
        job_idempotency_keys = [f"eval-suite-run:{run_id}" for run_id in suite_run_ids]
        durable_job_rows = (
            (
                await conn.execute(
                    select(durable_jobs.c.id)
                    .where(
                        and_(
                            durable_jobs.c.kind == JobKind.EVAL_SUITE_RUN.value,
                            or_(
                                durable_jobs.c.idempotency_key.in_(job_idempotency_keys),
                                durable_jobs.c.payload["suite_run_id"].astext.in_(
                                    suite_run_ids
                                ),
                            ),
                        )
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .all()
        )
        durable_job_ids = [str(row["id"]) for row in durable_job_rows]

    if durable_job_ids:
        await conn.execute(
            delete(durable_jobs).where(durable_jobs.c.id.in_(durable_job_ids))
        )
    if case_run_ids:
        await conn.execute(delete(case_runs).where(case_runs.c.id.in_(case_run_ids)))
    if suite_run_ids:
        await conn.execute(delete(suite_runs).where(suite_runs.c.id.in_(suite_run_ids)))
    if case_ids:
        await conn.execute(delete(cases).where(cases.c.id.in_(case_ids)))
    await conn.execute(delete(suites).where(suites.c.id.in_(suite_ids)))

    return {
        "suite_ids": suite_ids,
        "suites_deleted": len(suite_ids),
        "cases_deleted": len(case_ids),
        "suite_runs_deleted": len(suite_run_ids),
        "case_runs_deleted": len(case_run_ids),
        "durable_jobs_deleted": len(durable_job_ids),
    }


async def delete_suite_rows_async(suite_id: str) -> dict[str, Any] | None:
    """Permanently delete one Suite and all of its workbench run history.

    The caller owns the policy decision about whether the Suite is mutable;
    this lower layer only gives the delete operation atomic graph semantics.
    """
    normalized_suite_id = str(suite_id or "").strip()
    if not normalized_suite_id:
        raise ValueError("suite_id is required")

    await ensure_agent_eval_tables_async()
    suites = agent_eval_suites_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    select(suites)
                    .where(suites.c.id == normalized_suite_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return await _delete_suite_tree_in_transaction(
            conn,
            suite_rows=[_row_dict(row)],
        )


async def remove_imported_pack_rows_async(
    pack_id: str,
    *,
    pack_version: str,
) -> dict[str, Any]:
    """Permanently purge one exact imported pack version in one transaction."""
    normalized_pack_id = str(pack_id or "").strip()
    normalized_pack_version = str(pack_version or "").strip()
    if not normalized_pack_id:
        raise ValueError("pack_id is required")
    if not normalized_pack_version:
        raise ValueError("pack_version is required")

    await ensure_agent_eval_tables_async()
    suites = agent_eval_suites_table()
    tagged_suite_filter = and_(
        suites.c.tags.contains([f"pack:{normalized_pack_id}"]),
        suites.c.tags.contains([f"pack_version:{normalized_pack_version}"]),
    )

    async with get_async_control_plane_engine().begin() as conn:
        candidate_suite_rows = (
            (
                await conn.execute(
                    select(suites).where(tagged_suite_filter).with_for_update()
                )
            )
            .mappings()
            .all()
        )
        suite_rows = [
            row
            for row in candidate_suite_rows
            if _matches_exact_imported_pack_tags(
                row.get("tags"),
                pack_id=normalized_pack_id,
                pack_version=normalized_pack_version,
            )
        ]
        if not suite_rows:
            raise ValueError(
                "Imported eval pack version not found: "
                f"{normalized_pack_id}@{normalized_pack_version}"
            )

        deleted = await _delete_suite_tree_in_transaction(
            conn,
            suite_rows=[_row_dict(row) for row in suite_rows],
        )

    return {
        "pack_id": normalized_pack_id,
        "pack_version": normalized_pack_version,
        **deleted,
    }
