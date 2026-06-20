import asyncio
from datetime import datetime
from typing import Any

from fastapi.encoders import jsonable_encoder

from api.services.postgres_store import get_agno_postgres_db

# Keep a single DB wrapper instance.
_trace_db = get_agno_postgres_db()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Accept ISO8601 timestamps; allow trailing 'Z'.
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


async def list_traces(
    *,
    run_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
    team_id: str | None = None,
    workflow_id: str | None = None,
    status: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 20,
    page: int = 1,
) -> dict[str, Any]:
    """Return a paginated list of traces.

    Uses Agno `PostgresDb.get_traces()` convenience API.
    """
    if limit <= 0:
        limit = 20
    if limit > 200:
        limit = 200
    if page <= 0:
        page = 1

    st = _parse_dt(start_time)
    et = _parse_dt(end_time)

    traces, total_count = await asyncio.to_thread(
        _trace_db.get_traces,
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        agent_id=agent_id,
        team_id=team_id,
        workflow_id=workflow_id,
        status=status,
        start_time=st,
        end_time=et,
        limit=limit,
        page=page,
    )

    items = [jsonable_encoder(t.to_dict()) for t in traces]
    return {"items": items, "total_count": total_count, "page": page, "limit": limit}


def _build_span_tree(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a hierarchical span tree.

    Input spans are dicts with at least: span_id, parent_span_id.
    """
    by_id: dict[str, dict[str, Any]] = {}
    children_by_parent: dict[str | None, list[dict[str, Any]]] = {}

    for s in spans:
        span_id = str(s.get("span_id", ""))
        if not span_id:
            continue
        node = {"span": s, "children": []}
        by_id[span_id] = node
        parent = s.get("parent_span_id")
        children_by_parent.setdefault(parent, []).append(node)

    # attach children
    for span_id, node in by_id.items():
        parent_id = node["span"].get("parent_span_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(node)

    # root nodes = parent_span_id is None or missing parent
    roots: list[dict[str, Any]] = []
    for span_id, node in by_id.items():
        parent_id = node["span"].get("parent_span_id")
        if not parent_id or parent_id not in by_id:
            roots.append(node)

    # Sort roots/children by start_time if present.
    def _key(n: dict[str, Any]):
        st = n.get("span", {}).get("start_time")
        return st or ""

    def _sort_rec(nodes: list[dict[str, Any]]):
        nodes.sort(key=_key)
        for n in nodes:
            _sort_rec(n.get("children", []))

    _sort_rec(roots)
    return roots


async def get_trace_detail(trace_id: str) -> dict[str, Any] | None:
    trace = await asyncio.to_thread(_trace_db.get_trace, trace_id=trace_id)
    if not trace:
        return None

    spans = await asyncio.to_thread(_trace_db.get_spans, trace_id=trace_id)
    span_dicts = [jsonable_encoder(s.to_dict()) for s in spans]
    tree = _build_span_tree(span_dicts)

    return {
        "trace": jsonable_encoder(trace.to_dict()),
        "spans": span_dicts,
        "tree": tree,
    }
