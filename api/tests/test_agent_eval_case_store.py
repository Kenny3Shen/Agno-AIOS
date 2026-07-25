import json
from hashlib import sha256
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from api.services import agent_eval_case_store as store
from api.services import agent_eval_suite_queue as suite_queue


def actor():
    return SimpleNamespace(
        id="user-1", email="operator@example.com", role="admin", is_superuser=False
    )


def mutable_suite(suite_id: str = "suite-1") -> dict[str, object]:
    return {"id": suite_id, "name": "Regression", "tags": ["release"]}


def snapshot_case(
    case_id: str = "case-1",
    *,
    prompt: str = "private prompt",
) -> dict[str, object]:
    """A complete Case contract suitable for a frozen run snapshot."""
    return {
        "id": case_id,
        "suite_id": "suite-1",
        "name": f"Case {case_id}",
        "description": "",
        "input": prompt,
        "expected_output": "private expected output",
        "criteria": "",
        "judge_mode": "binary",
        "additional_guidelines": [],
        "threshold": 7,
        "eval_types": ["accuracy"],
        "expected_tool_calls": [],
        "expected_tool_call_arguments": {},
        "allow_additional_tool_calls": True,
        "performance_config": {
            "warmup_runs": 1,
            "num_iterations": 3,
            "measure_runtime": True,
            "measure_memory": False,
        },
        "timeout_seconds": None,
        "metadata": {},
        "tags": [],
        "enabled": True,
    }


def terminal_checkpoint(**overrides: object) -> dict[str, object]:
    """A complete, privacy-safe terminal checkpoint fixture."""
    return {
        "version": 1,
        "status": "passed",
        "duration_seconds": 1.23456,
        "timeout_seconds": 120,
        "timed_out": False,
        "accuracy_passed": True,
        "accuracy_score": 9.5,
        "judge_passed": True,
        "judge_score": 9,
        "reliability_passed": True,
        "reliability_evidence": {"failed_tool_calls": ["unapproved_tool"]},
        "performance": {
            "warmup_runs": 1,
            "num_iterations": 3,
            "runtime_seconds": {"avg": 0.1254321, "median": 0.1, "p95": 0.2},
        },
        "judge_id": "agent_as_judge:refusal-v1@1.0.0+model:judge-a",
        "eval_profile": "tools_off",
        **overrides,
    }


def test_performance_config_is_canonical_bounded_and_non_noop() -> None:
    assert store.normalize_performance_config(None) == {
        "warmup_runs": 1,
        "num_iterations": 3,
        "measure_runtime": True,
        "measure_memory": False,
    }
    assert store.normalize_performance_config(
        {
            "warmup_runs": 0,
            "num_iterations": 100,
            "measure_runtime": False,
            "measure_memory": True,
        }
    ) == {
        "warmup_runs": 0,
        "num_iterations": 100,
        "measure_runtime": False,
        "measure_memory": True,
    }


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("not-an-object", "must be an object"),
        ({"unknown": True}, "unsupported fields"),
        ({"warmup_runs": -1}, "warmup_runs"),
        ({"num_iterations": 101}, "num_iterations"),
        ({"num_iterations": True}, "num_iterations"),
        ({"measure_runtime": "yes"}, "measure_runtime"),
        (
            {"measure_runtime": False, "measure_memory": False},
            "must enable measure_runtime",
        ),
    ],
)
def test_performance_config_rejects_unbounded_or_non_executable_values(
    value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        store.normalize_performance_config(value)


@pytest.mark.asyncio
async def test_create_case_rejects_unknown_eval_type():
    with pytest.raises(ValueError, match="Unsupported eval type"):
        await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "bad",
                "input": "x",
                "eval_types": ["made_up"],
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "suite_id": "suite-1",
                "name": "No checks",
                "input": "probe",
                "eval_types": [],
            },
            "eval_types",
        ),
        (
            {
                "suite_id": "suite-1",
                "name": "Judge without criteria",
                "input": "probe",
                "eval_types": ["agent_as_judge"],
            },
            "criteria",
        ),
        (
            {
                "suite_id": "suite-1",
                "name": "Accuracy without reference",
                "input": "probe",
                "eval_types": ["accuracy"],
            },
            "expected_output",
        ),
        (
            {
                "suite_id": "suite-1",
                "name": "Reliability without tools",
                "input": "probe",
                "eval_types": ["reliability"],
            },
            "expected_tool_calls",
        ),
        (
            {
                "suite_id": "suite-1",
                "name": "Argument contract for another tool",
                "input": "probe",
                "eval_types": ["reliability"],
                "expected_tool_calls": ["search_docs"],
                "expected_tool_call_arguments": {"notify": {"message": "x"}},
            },
            "expected_tool_call_arguments keys",
        ),
    ],
)
async def test_create_case_rejects_incomplete_eval_contract(
    payload: dict[str, object], message: str
) -> None:
    with (
        patch.object(store, "get_suite", new=AsyncMock(return_value=mutable_suite())),
        pytest.raises(ValueError, match=message),
    ):
        await store.create_case(payload)


@pytest.mark.asyncio
async def test_create_case_persists_explicit_agno_judge_mode() -> None:
    row = {
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "Numeric judge",
        "input": "probe",
        "criteria": "Must be helpful.",
        "judge_mode": "numeric",
        "threshold": 8,
        "eval_types": ["agent_as_judge"],
        "expected_tool_calls": [],
        "expected_tool_call_arguments": {},
    }
    with (
        patch.object(store, "get_suite", new=AsyncMock(return_value=mutable_suite())),
        patch.object(store, "create_case_row_async", new=AsyncMock(return_value=row)) as create_mock,
    ):
        result = await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "Numeric judge",
                "input": "probe",
                "criteria": "Must be helpful.",
                "judge_mode": "numeric",
                "threshold": 8,
                "eval_types": ["agent_as_judge"],
            }
        )

    assert result["judge_mode"] == "numeric"
    assert create_mock.await_args is not None
    assert create_mock.await_args.kwargs["values"]["judge_mode"] == "numeric"


@pytest.mark.asyncio
async def test_update_case_revalidates_the_complete_eval_contract() -> None:
    existing = {
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "Accuracy case",
        "input": "probe",
        "expected_output": "safe result",
        "criteria": "",
        "judge_mode": "binary",
        "eval_types": ["accuracy"],
        "expected_tool_calls": [],
        "expected_tool_call_arguments": {},
    }
    with (
        patch.object(store, "get_suite", new=AsyncMock(return_value=mutable_suite())),
        patch.object(store, "get_case", new=AsyncMock(return_value=existing)),
        pytest.raises(ValueError, match="expected_output"),
    ):
        await store.update_case("case-1", {"expected_output": ""})


@pytest.mark.asyncio
async def test_create_suite_derives_created_by_from_actor():
    with patch.object(
        store,
        "create_suite_row_async",
        new=AsyncMock(
            return_value={
                "id": "suite-1",
                "name": "Security Regression",
                "description": "",
                "target_kind": "agent",
                "target_id": "security-operations",
                "enabled": True,
                "tags": ["security"],
                "created_by": "user-1",
                "created_at": "2026-07-06T00:00:00Z",
                "updated_at": "2026-07-06T00:00:00Z",
            }
        ),
    ) as create_mock:
        result = await store.create_suite(
            {
                "name": "Security Regression",
                "target": {"kind": "agent", "id": "security-operations"},
                "tags": ["security"],
            },
            actor(),
        )

    assert result["id"] == "suite-1"
    create_call = create_mock.await_args
    assert create_call is not None
    assert create_call.kwargs["values"]["created_by"] == "user-1"


@pytest.mark.asyncio
async def test_create_suite_rejects_unknown_target_without_a_default_fallback():
    with pytest.raises(ValueError, match="Unknown Eval Agent target"):
        await store.create_suite(
            {
                "name": "Unknown target regression",
                "target": {"kind": "agent", "id": "does-not-exist"},
            },
            actor(),
        )


@pytest.mark.asyncio
async def test_cases_reject_their_own_target_fields():
    with pytest.raises(ValueError, match="inherited from its Suite"):
        await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "Target must be inherited",
                "input": "probe",
                "target": {"kind": "agent", "id": "security-operations"},
            }
        )


@pytest.mark.asyncio
async def test_suite_target_is_immutable_after_creation():
    with patch.object(store, "get_suite", new=AsyncMock(return_value=mutable_suite())):
        with pytest.raises(ValueError, match="target is immutable"):
            await store.update_suite(
                "suite-1",
                {"target": {"kind": "agent", "id": "data-analysis"}},
            )


@pytest.mark.asyncio
async def test_create_case_sets_defaults_and_preserves_reliability_config():
    with (
        patch.object(store, "get_suite", new=AsyncMock(return_value=mutable_suite())),
        patch.object(
            store,
            "create_case_row_async",
            new=AsyncMock(
                return_value={
                    "id": "case-1",
                    "suite_id": "suite-1",
                    "name": "Feishu notification calls MCP",
                    "description": "",
                    "input": "Send a Feishu notification about the incident",
                    "expected_output": "",
                    "criteria": "",
                    "additional_guidelines": [
                        "Do not claim the notification was sent without the tool call."
                    ],
                    "threshold": 7,
                    "eval_types": ["reliability"],
                    "expected_tool_calls": ["basic_send_feishu_notify"],
                    "expected_tool_call_arguments": {
                        "basic_send_feishu_notify": {
                            "title": "Incident notification",
                            "content_md": "Please investigate the incident.",
                        }
                    },
                    "allow_additional_tool_calls": True,
                    "performance_config": {},
                    "metadata": {},
                    "enabled": True,
                    "created_at": "2026-07-06T00:00:00Z",
                    "updated_at": "2026-07-06T00:00:00Z",
                }
            ),
        ) as create_mock,
    ):
        result = await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "Feishu notification calls MCP",
                "input": "Send a Feishu notification about the incident",
                "eval_types": ["reliability"],
                "expected_tool_calls": ["basic_send_feishu_notify"],
                "expected_tool_call_arguments": {
                    "basic_send_feishu_notify": {
                        "title": "Incident notification",
                        "content_md": "Please investigate the incident.",
                    }
                },
                "additional_guidelines": [
                    " Do not claim the notification was sent without the tool call. ",
                    "Do not claim the notification was sent without the tool call.",
                ],
            }
        )

    assert result["eval_types"] == ["reliability"]
    assert result["expected_tool_calls"] == ["basic_send_feishu_notify"]
    create_call = create_mock.await_args
    assert create_call is not None
    assert create_call.kwargs["values"]["allow_additional_tool_calls"] is True
    assert create_call.kwargs["values"]["timeout_seconds"] is None
    assert create_call.kwargs["values"]["tags"] == []
    assert create_call.kwargs["values"]["performance_config"] == {
        "warmup_runs": 1,
        "num_iterations": 3,
        "measure_runtime": True,
        "measure_memory": False,
    }
    assert create_call.kwargs["values"]["additional_guidelines"] == [
        "Do not claim the notification was sent without the tool call."
    ]


def test_reliability_argument_contract_uses_agno_object_or_object_list_shape() -> None:
    contract = store.normalize_expected_tool_call_arguments(
        {
            " search_docs ": {"query": "security advisory", "limit": 3},
            "notify": [
                {"channel": "security"},
                {"channel": "incident-response"},
            ],
        }
    )

    assert contract == {
        "search_docs": {"query": "security advisory", "limit": 3},
        "notify": [
            {"channel": "security"},
            {"channel": "incident-response"},
        ],
    }


@pytest.mark.parametrize(
    "contract",
    [
        "not-an-object",
        {"": {}},
        {"search": []},
        {"search": "not-an-object"},
        {"search": [{"query": "advisory"}, "not-an-object"]},
        {"search": {"score": float("nan")}},
    ],
)
def test_reliability_argument_contract_rejects_malformed_values(contract: object) -> None:
    with pytest.raises(ValueError, match="expected_tool_call_arguments"):
        store.normalize_expected_tool_call_arguments(contract)


@pytest.mark.asyncio
async def test_case_writes_reject_malformed_reliability_argument_contracts() -> None:
    with pytest.raises(ValueError, match="expected_tool_call_arguments"):
        await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "Malformed reliability contract",
                "input": "Look up a security advisory.",
                "eval_types": ["reliability"],
                "expected_tool_call_arguments": {"search_docs": []},
            }
        )

    existing = {
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "Valid reliability contract",
        "input": "Look up a security advisory.",
        "eval_types": ["reliability"],
        "expected_tool_call_arguments": {"search_docs": {"query": "advisory"}},
    }
    with patch.object(store, "get_case", new=AsyncMock(return_value=existing)):
        with pytest.raises(ValueError, match="expected_tool_call_arguments"):
            await store.update_case(
                "case-1",
                {"expected_tool_call_arguments": {"search_docs": ["bad"]}},
            )


@pytest.mark.asyncio
async def test_case_additional_guidelines_can_be_updated_or_cleared() -> None:
    case_row = {
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "Guided check",
        "input": "check",
        "expected_output": "expected check",
        "eval_types": ["accuracy"],
        "expected_tool_calls": [],
        "expected_tool_call_arguments": {},
        "additional_guidelines": ["Use a strict safety standard."],
    }
    with (
        patch.object(store, "get_suite", new=AsyncMock(return_value=mutable_suite())),
        patch.object(store, "get_case", new=AsyncMock(return_value=case_row)),
        patch.object(
            store,
            "update_case_row_async",
            new=AsyncMock(return_value={**case_row, "additional_guidelines": []}),
        ) as update_mock,
    ):
        updated = await store.update_case(
            "case-1",
            {
                "additional_guidelines": [
                    " Use a strict safety standard. ",
                    "Use a strict safety standard.",
                ]
            },
        )
        cleared = await store.update_case("case-1", {"additional_guidelines": None})

    assert updated is not None
    assert updated["additional_guidelines"] == []
    assert cleared is not None
    assert update_mock.await_args_list[0].args == (
        "case-1",
        {"additional_guidelines": ["Use a strict safety standard."]},
    )
    assert update_mock.await_args_list[1].args == (
        "case-1",
        {"additional_guidelines": []},
    )


@pytest.mark.asyncio
async def test_case_additional_guidelines_reject_malformed_or_oversized_input() -> None:
    with pytest.raises(ValueError, match="additional_guidelines"):
        await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "Bad guidance",
                "input": "check",
                "additional_guidelines": "not a list",
            }
        )
    with pytest.raises(ValueError, match="additional_guidelines"):
        await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "Too many guidance rows",
                "input": "check",
                "additional_guidelines": ["x"] * 21,
            }
        )


@pytest.mark.asyncio
async def test_case_timeout_is_persisted_and_can_be_cleared() -> None:
    case_row = {
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "Slow live check",
        "input": "check",
        "expected_output": "expected check",
        "eval_types": ["accuracy"],
        "expected_tool_calls": [],
        "expected_tool_call_arguments": {},
        "timeout_seconds": 45,
    }
    with (
        patch.object(store, "get_suite", new=AsyncMock(return_value=mutable_suite())),
        patch.object(
            store,
            "get_case",
            new=AsyncMock(return_value=case_row),
        ),
        patch.object(
            store,
            "create_case_row_async",
            new=AsyncMock(return_value=case_row),
        ) as create_mock,
        patch.object(
            store,
            "update_case_row_async",
            new=AsyncMock(return_value={**case_row, "timeout_seconds": None}),
        ) as update_mock,
    ):
        created = await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "Slow live check",
                "input": "check",
                "expected_output": "expected check",
                "eval_types": ["accuracy"],
                "timeout_seconds": 45,
            }
        )
        updated = await store.update_case("case-1", {"timeout_seconds": None})

    assert created["timeout_seconds"] == 45
    assert create_mock.await_args is not None
    assert create_mock.await_args.kwargs["values"]["timeout_seconds"] == 45
    assert updated is not None
    assert updated["timeout_seconds"] is None
    update_mock.assert_awaited_once_with("case-1", {"timeout_seconds": None})


@pytest.mark.asyncio
async def test_case_timeout_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "Bad timeout",
                "input": "check",
                "eval_types": ["agent_as_judge"],
                "timeout_seconds": 0,
            }
        )


@pytest.mark.asyncio
async def test_case_tags_are_normalized_on_create_update_and_filter() -> None:
    case_row = {
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "Smoke check",
        "input": "check",
        "expected_output": "expected check",
        "eval_types": ["accuracy"],
        "expected_tool_calls": [],
        "expected_tool_call_arguments": {},
        "tags": ["smoke", "release"],
    }
    with (
        patch.object(store, "get_suite", new=AsyncMock(return_value=mutable_suite())),
        patch.object(
            store,
            "get_case",
            new=AsyncMock(return_value=case_row),
        ),
        patch.object(
            store,
            "create_case_row_async",
            new=AsyncMock(return_value=case_row),
        ) as create_mock,
        patch.object(
            store,
            "update_case_row_async",
            new=AsyncMock(return_value=case_row),
        ) as update_mock,
        patch.object(
            store,
            "list_case_rows_async",
            new=AsyncMock(return_value=[case_row]),
        ) as list_mock,
    ):
        created = await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "Smoke check",
                "input": "check",
                "expected_output": "expected check",
                "eval_types": ["accuracy"],
                "tags": [" smoke ", "release", "smoke", ""],
            }
        )
        updated = await store.update_case(
            "case-1", {"tags": [" release ", "smoke", "release"]}
        )
        listed = await store.list_cases(suite_id="suite-1", tag=" smoke ")

    assert created["tags"] == ["smoke", "release"]
    assert updated is not None
    assert updated["tags"] == ["smoke", "release"]
    assert listed["data"][0]["tags"] == ["smoke", "release"]
    assert create_mock.await_args is not None
    assert create_mock.await_args.kwargs["values"]["tags"] == ["smoke", "release"]
    assert update_mock.await_args is not None
    assert update_mock.await_args.args == ("case-1", {"tags": ["release", "smoke"]})
    assert list_mock.await_args is not None
    assert list_mock.await_args.kwargs == {
        "suite_id": "suite-1",
        "enabled": None,
        "tag": "smoke",
        "name": None,
    }


@pytest.mark.asyncio
async def test_list_cases_rejects_a_blank_tag_selector() -> None:
    with pytest.raises(ValueError, match="tag must not be blank"):
        await store.list_cases(suite_id="suite-1", tag="  ")


@pytest.mark.asyncio
async def test_list_cases_forwards_the_exact_name_selector() -> None:
    with patch.object(
        store, "list_case_rows_async", new=AsyncMock(return_value=[])
    ) as list_mock:
        result = await store.list_cases(suite_id="suite-1", name=" Smoke check ")

    assert result["data"] == []
    list_mock.assert_awaited_once_with(
        suite_id="suite-1",
        enabled=None,
        tag=None,
        name="Smoke check",
    )


@pytest.mark.asyncio
async def test_list_cases_rejects_a_blank_name_selector() -> None:
    with pytest.raises(ValueError, match="name must not be blank"):
        await store.list_cases(suite_id="suite-1", name="  ")


@pytest.mark.asyncio
async def test_internal_case_listing_is_not_capped_by_the_browser_page_size():
    rows = [
        {
            "id": f"case-{index}",
            "suite_id": "suite-1",
            "name": f"Case {index}",
            "input": "probe",
            "eval_types": ["agent_as_judge"],
        }
        for index in range(501)
    ]
    with patch.object(
        store,
        "list_case_rows_async",
        new=AsyncMock(return_value=rows),
    ) as list_mock:
        result = await store.list_cases(suite_id="suite-1")

    assert len(result["data"]) == 501
    list_mock.assert_awaited_once_with(
        suite_id="suite-1",
        enabled=None,
        tag=None,
        name=None,
    )


@pytest.mark.asyncio
async def test_case_page_uses_a_bounded_page_query_and_exact_total():
    row = {
        "id": "case-51",
        "suite_id": "suite-1",
        "name": "Case 51",
        "input": "probe",
        "eval_types": ["agent_as_judge"],
    }
    with patch.object(
        store,
        "list_case_rows_page_async",
        new=AsyncMock(return_value=([row], 501)),
    ) as list_mock:
        result = await store.list_cases_page(
            suite_id="suite-1",
            page=2,
            limit=50,
        )

    assert result["data"][0]["id"] == "case-51"
    assert result["meta"]["total_count"] == 501
    assert result["meta"]["page"] == 2
    list_mock.assert_awaited_once_with(
        suite_id="suite-1",
        enabled=None,
        tag=None,
        name=None,
        page=2,
        limit=50,
    )


@pytest.mark.asyncio
async def test_update_suite_filters_unknown_fields():
    with (
        patch.object(store, "get_suite", new=AsyncMock(return_value=mutable_suite())),
        patch.object(
            store,
            "update_suite_row_async",
            new=AsyncMock(
                return_value={
                    "id": "suite-1",
                    "name": "Updated",
                    "description": "new",
                    "target_kind": "agent",
                    "target_id": "security-operations",
                    "enabled": False,
                    "tags": ["nightly"],
                    "created_by": "user-1",
                    "created_at": "2026-07-06T00:00:00Z",
                    "updated_at": "2026-07-06T01:00:00Z",
                }
            ),
        ) as update_mock,
    ):
        result = await store.update_suite(
            "suite-1", {"name": "Updated", "enabled": False, "bogus": "x"}
        )

    assert result is not None
    assert result["name"] == "Updated"
    update_call = update_mock.await_args
    assert update_call is not None
    assert update_call.args == ("suite-1", {"name": "Updated", "enabled": False})


@pytest.mark.asyncio
async def test_manual_suites_cannot_claim_reserved_imported_pack_tags() -> None:
    with pytest.raises(ValueError, match="reserved for imported eval packs"):
        await store.create_suite(
            {
                "name": "Pretend imported suite",
                "tags": ["pack:harmbench", "pack_version:2026.07.1"],
            },
            actor(),
        )


@pytest.mark.asyncio
async def test_imported_pack_suite_and_cases_are_immutable_to_manual_writes() -> None:
    imported_suite = {
        "id": "suite-pack",
        "name": "safety-harmbench@2026.07.1",
        "tags": ["safety", "pack:harmbench", "pack_version:2026.07.1"],
    }
    imported_case = {
        "id": "case-pack",
        "suite_id": "suite-pack",
        "name": "Imported case",
        "input": "probe",
        "expected_output": "expected response",
        "eval_types": ["accuracy"],
        "expected_tool_calls": [],
        "expected_tool_call_arguments": {},
    }
    with (
        patch.object(store, "get_suite", new=AsyncMock(return_value=imported_suite)),
        patch.object(store, "get_case", new=AsyncMock(return_value=imported_case)),
    ):
        with pytest.raises(ValueError, match="immutable"):
            await store.update_suite("suite-pack", {"name": "Edited"})
        with pytest.raises(ValueError, match="immutable"):
            await store.create_case(
                {
                    "suite_id": "suite-pack",
                    "name": "Manual case",
                    "input": "manual probe",
                    "expected_output": "expected response",
                    "eval_types": ["accuracy"],
                }
            )
        with pytest.raises(ValueError, match="immutable"):
            await store.update_case("case-pack", {"name": "Edited"})


@pytest.mark.asyncio
async def test_manual_case_cannot_be_moved_into_an_imported_pack_suite() -> None:
    imported_suite = {
        "id": "suite-pack",
        "name": "safety-harmbench@2026.07.1",
        "tags": ["safety", "pack:harmbench", "pack_version:2026.07.1"],
    }
    manual_case = {
        "id": "case-manual",
        "suite_id": "suite-manual",
        "name": "Manual case",
        "input": "probe",
        "expected_output": "expected response",
        "eval_types": ["accuracy"],
        "expected_tool_calls": [],
        "expected_tool_call_arguments": {},
    }
    with (
        patch.object(
            store,
            "get_case",
            new=AsyncMock(return_value=manual_case),
        ),
        patch.object(
            store,
            "get_suite",
            new=AsyncMock(side_effect=[mutable_suite("suite-manual"), imported_suite]),
        ),
    ):
        with pytest.raises(ValueError, match="immutable"):
            await store.update_case("case-manual", {"suite_id": "suite-pack"})


@pytest.mark.asyncio
async def test_import_pack_rejects_duplicate_external_ids_before_persistence() -> None:
    import_rows = AsyncMock()
    payload = {
        "suite_id": "suite-pending",
        "name": "Imported case",
        "input": "probe",
        "expected_output": "safe answer",
        "eval_types": ["accuracy"],
        "metadata": {"pack_id": "fixture", "external_id": "same"},
    }

    with patch.object(store, "import_pack_rows_async", new=import_rows):
        with pytest.raises(ValueError, match="duplicate external_id"):
            await store.import_pack(
                pack_id="fixture",
                pack_version="v1",
                artifact_hash="abc",
                suite_payload={
                    "name": "Safety fixture",
                    "target": {"kind": "agent", "id": "security-operations"},
                    "tags": ["safety", "pack:fixture", "pack_version:v1"],
                },
                case_payloads=[payload, {**payload, "name": "Imported case 2"}],
                actor=actor(),
            )

    import_rows.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_imported_pack_requires_and_forwards_exact_version():
    removed = {
        "pack_id": "fixture-synthetic",
        "suite_ids": ["suite-1"],
        "suites_deleted": 1,
        "cases_deleted": 4,
        "suite_runs_deleted": 1,
        "case_runs_deleted": 4,
    }
    with patch.object(
        store,
        "remove_imported_pack_rows_async",
        new=AsyncMock(return_value=removed),
    ) as remove_mock:
        result = await store.remove_imported_pack(
            " fixture-synthetic ",
            pack_version=" 2026.07.1 ",
        )

    assert result == removed
    remove_mock.assert_awaited_once_with(
        "fixture-synthetic",
        pack_version="2026.07.1",
    )


@pytest.mark.asyncio
async def test_remove_imported_pack_requires_version():
    with pytest.raises(ValueError, match="pack_version"):
        await store.remove_imported_pack("fixture-synthetic", pack_version=" ")


@pytest.mark.asyncio
async def test_delete_manual_suite_cascades_its_workbench_tree():
    removed = {
        "suite_ids": ["suite-manual"],
        "suites_deleted": 1,
        "cases_deleted": 3,
        "suite_runs_deleted": 2,
        "case_runs_deleted": 6,
    }
    with (
        patch.object(
            store,
            "get_suite",
            new=AsyncMock(return_value=mutable_suite("suite-manual")),
        ),
        patch.object(
            store,
            "delete_suite_rows_async",
            new=AsyncMock(return_value=removed),
        ) as delete_mock,
    ):
        result = await store.delete_suite(" suite-manual ")

    assert result == removed
    delete_mock.assert_awaited_once_with("suite-manual")


@pytest.mark.asyncio
async def test_delete_suite_rejects_imported_pack_artifacts():
    imported_suite = {
        "id": "suite-pack",
        "tags": ["safety", "pack:harmbench", "pack_version:2026.07.1"],
    }
    with patch.object(
        store,
        "get_suite",
        new=AsyncMock(return_value=imported_suite),
    ):
        with pytest.raises(ValueError, match="immutable"):
            await store.delete_suite("suite-pack")


@pytest.mark.asyncio
async def test_delete_case_removes_only_manual_definition_and_retains_history():
    case_row = {
        "id": "case-manual",
        "suite_id": "suite-manual",
        "name": "Release check",
        "input": "check",
        "eval_types": ["agent_as_judge"],
    }
    with (
        patch.object(store, "get_case", new=AsyncMock(return_value=case_row)),
        patch.object(
            store,
            "get_suite",
            new=AsyncMock(return_value=mutable_suite("suite-manual")),
        ),
        patch.object(
            store,
            "delete_case_row_async",
            new=AsyncMock(return_value=case_row),
        ) as delete_mock,
    ):
        result = await store.delete_case("case-manual")

    assert result is not None
    assert result["id"] == "case-manual"
    assert result["suite_id"] == "suite-manual"
    delete_mock.assert_awaited_once_with("case-manual")


@pytest.mark.asyncio
async def test_delete_case_rejects_imported_pack_artifacts():
    imported_suite = {
        "id": "suite-pack",
        "tags": ["safety", "pack:harmbench", "pack_version:2026.07.1"],
    }
    with (
        patch.object(
            store,
            "get_case",
            new=AsyncMock(
                return_value={
                    "id": "case-pack",
                    "suite_id": "suite-pack",
                    "name": "Imported case",
                    "input": "probe",
                }
            ),
        ),
        patch.object(store, "get_suite", new=AsyncMock(return_value=imported_suite)),
    ):
        with pytest.raises(ValueError, match="immutable"):
            await store.delete_case("case-pack")


@pytest.mark.asyncio
async def test_update_case_revalidates_eval_types_and_rejects_empty_patch():
    with pytest.raises(ValueError, match="Unsupported eval type"):
        await store.update_case("case-1", {"eval_types": ["unknown"]})

    with pytest.raises(ValueError, match="No supported fields to update"):
        await store.update_case("case-1", {"bogus": "x"})


@pytest.mark.asyncio
async def test_enqueue_suite_run_derives_started_by_from_actor_atomically():
    persisted_row = {
        "id": "suite-run-1",
        "suite_id": "suite-1",
        "status": "queued",
        "started_by": "user-1",
        "error_summary": "",
        "summary": {"total": 1, "completed_cases": 0},
        "started_at": "2026-07-06T00:00:00Z",
        "completed_at": None,
    }
    plan = {
        "suite_id": "suite-1",
        "_suite": {
            "id": "suite-1",
            "name": "Regression",
            "target": {"kind": "agent", "id": "security-operations"},
            "tags": ["release"],
        },
        "_cases": [snapshot_case()],
        "case_ids": ["case-1"],
        "selected_tag": None,
        "selected_name": None,
        "default_timeout": 120,
    }
    with (
        patch.object(
            suite_queue,
            "uuid4",
            return_value=SimpleNamespace(hex="suite-run-1"),
        ),
        patch.object(
            suite_queue,
            "get_eval_judge_model_id",
            new=AsyncMock(return_value=""),
        ),
        patch.object(
            suite_queue,
            "create_suite_run_with_case_runs_and_enqueue_job_async",
            new=AsyncMock(
                return_value=(persisted_row, SimpleNamespace(id="job-1"))
            ),
        ) as enqueue_mock,
    ):
        result, job_id = await suite_queue.enqueue_suite_run(
            suite_id="suite-1",
            actor=actor(),
            plan=plan,
            summary={"total": 1, "completed_cases": 0},
        )

    assert result["status"] == "queued"
    assert job_id == "job-1"
    enqueue_call = enqueue_mock.await_args
    assert enqueue_call is not None
    values = enqueue_call.args[0]
    assert values["started_by"] == "user-1"
    assert enqueue_call.kwargs["payload"] == {"suite_run_id": "suite-run-1"}
    assert [
        work_item["case_id"] for work_item in enqueue_call.kwargs["case_run_values"]
    ] == ["case-1"]


@pytest.mark.asyncio
async def test_suite_run_execution_snapshot_is_private_and_case_definitions_live_in_work_items():
    first = snapshot_case("case-1", prompt="private prompt one")
    second = snapshot_case("case-2", prompt="private prompt two")
    execution_snapshot = store.build_suite_run_execution_snapshot(
        {
            "id": "suite-1",
            "target_kind": "agent",
            "target_id": "security-operations",
        },
        run_manifest={
            "version": store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
            "actor": {"id": "operator-1", "role": "user", "is_superuser": False},
            "selected_tag": None,
            "selected_name": None,
            "case_count": 2,
            "default_timeout": 120,
            "judge_model_config_id": "",
        },
    )
    work_items = store.build_suite_run_case_work_items(
        "suite-run-1", execution_snapshot, [first, second]
    )
    row = {
        "id": "suite-run-1",
        "suite_id": "suite-1",
        "status": "queued",
        "started_by": "operator-1",
        "error_summary": "",
        "summary": {"total_cases": 2},
        "execution_snapshot": execution_snapshot,
        "started_at": "2026-07-06T00:00:00Z",
        "completed_at": None,
    }
    with patch.object(
        store,
        "get_suite_run_row_async",
        new=AsyncMock(return_value=row),
    ):
        public_loaded = await store.get_suite_run("suite-run-1")
        private_loaded = await store.get_suite_run_private("suite-run-1")

    assert "cases" not in execution_snapshot
    assert "private prompt one" not in json.dumps(execution_snapshot)
    assert "private prompt two" not in json.dumps(execution_snapshot)
    assert [work_item["case_id"] for work_item in work_items] == [
        "case-1",
        "case-2",
    ]
    assert [work_item["work_item_index"] for work_item in work_items] == [0, 1]
    assert work_items[0]["definition_snapshot"]["input"] == "private prompt one"
    assert work_items[1]["definition_snapshot"]["input"] == "private prompt two"
    assert public_loaded is not None
    assert "execution_snapshot" not in public_loaded
    assert "private prompt one" not in json.dumps(public_loaded)
    assert private_loaded is not None
    assert private_loaded["execution_snapshot"] == execution_snapshot


def test_suite_execution_manifest_freezes_worker_actor_and_selection() -> None:
    first = snapshot_case("case-1")
    snapshot = store.build_suite_run_execution_snapshot(
        {
            "id": "suite-1",
            "target_kind": "agent",
            "target_id": "security-operations",
        },
        run_manifest={
            "version": store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
            "actor": {"id": "operator-1", "role": "user", "is_superuser": False},
            "selected_tag": "smoke",
            "selected_name": None,
            "case_count": 1,
            "default_timeout": 75,
            "judge_model_config_id": "judge-model-1",
        },
    )

    assert store.suite_run_execution_manifest(snapshot) == snapshot["run_manifest"]
    work_items = store.build_suite_run_case_work_items("suite-run-1", snapshot, [first])
    assert len(work_items) == 1
    assert work_items[0]["suite_run_id"] == "suite-run-1"
    assert work_items[0]["case_id"] == "case-1"
    assert work_items[0]["work_item_index"] == 0
    assert work_items[0]["status"] == "queued"
    assert work_items[0]["execution_provenance"] == {
        "version": 1,
        "definition_source": "suite_case_work_item",
        "target": {"kind": "agent", "id": "security-operations"},
        "actor": {"role": "user", "is_superuser": False},
        "default_timeout_seconds": 75,
        "timeout_seconds": 75,
        "eval_profile": "full",
        "judge_model_config_id": "judge-model-1",
    }


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        (
            {
                "version": store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
                "actor": {"id": "", "role": "user", "is_superuser": False},
                "selected_tag": None,
                "selected_name": None,
                "case_count": 1,
                "default_timeout": 120,
                "judge_model_config_id": "",
            },
            "actor.id must be a non-empty string",
        ),
        (
            {
                "version": store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
                "actor": {"id": "operator-1", "role": "user", "is_superuser": False},
                "selected_tag": "tag",
                "selected_name": "name",
                "case_count": 1,
                "default_timeout": 120,
                "judge_model_config_id": "",
            },
            "selected_tag or selected_name",
        ),
        (
            {
                "version": store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
                "actor": {"id": "operator-1", "role": "user", "is_superuser": False},
                "selected_tag": None,
                "selected_name": None,
                "case_count": 0,
                "default_timeout": 120,
                "judge_model_config_id": "",
            },
            "case_count",
        ),
    ],
)
def test_suite_execution_manifest_rejects_invalid_worker_contracts(
    manifest: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        store.normalize_suite_run_execution_manifest(manifest)


def test_suite_execution_manifest_normalizes_retired_actor_role():
    manifest = {
        "version": store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
        "actor": {"id": "operator-1", "role": "author", "is_superuser": False},
        "selected_tag": None,
        "selected_name": None,
        "case_count": 1,
        "default_timeout": 120,
        "judge_model_config_id": "",
    }

    normalized = store.normalize_suite_run_execution_manifest(manifest)

    assert normalized["actor"]["role"] == "user"


def test_case_run_execution_provenance_canonicalizes_actor_snapshot():
    normalized = store.normalize_case_run_execution_provenance(
        {"actor": {"role": "author", "is_superuser": True}}
    )

    assert normalized["actor"] == {"role": "admin", "is_superuser": True}


def test_suite_execution_manifest_canonicalizes_superuser_actor_role():
    manifest = {
        "version": store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
        "actor": {"id": "operator-1", "role": "user", "is_superuser": True},
        "selected_tag": None,
        "selected_name": None,
        "case_count": 1,
        "default_timeout": 120,
        "judge_model_config_id": "",
    }

    normalized = store.normalize_suite_run_execution_manifest(manifest)

    assert normalized["actor"]["role"] == "admin"
    assert normalized["actor"]["is_superuser"] is True


def test_suite_execution_snapshot_v2_rejects_invalid_or_embedded_case_contracts():
    snapshot = store.build_suite_run_execution_snapshot(
        {
            "id": "suite-1",
            "target_kind": "agent",
            "target_id": "security-operations",
        },
        run_manifest={
            "version": store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
            "actor": {"id": "operator-1", "role": "user", "is_superuser": False},
            "selected_tag": None,
            "selected_name": None,
            "case_count": 1,
            "default_timeout": 120,
            "judge_model_config_id": "",
        },
    )
    bad_case = snapshot_case()
    bad_case["expected_output"] = ""
    with pytest.raises(ValueError, match="expected_output"):
        store.build_suite_run_case_work_items("suite-run-1", snapshot, [bad_case])

    divergent = snapshot_case()
    divergent["suite_id"] = "other-suite"
    with pytest.raises(ValueError, match="must belong to the frozen Suite"):
        store.build_suite_run_case_work_items("suite-run-1", snapshot, [divergent])

    with pytest.raises(ValueError, match="unsupported fields: cases"):
        store.normalize_suite_run_execution_snapshot({**snapshot, "cases": [snapshot_case()]})


@pytest.mark.asyncio
async def test_request_suite_run_cancel_uses_the_atomic_latest_summary_update():
    latest_row = {
        "id": "suite-run-1",
        "suite_id": "suite-1",
        "status": "cancelling",
        "started_by": "user-1",
        "error_summary": "Eval suite cancellation requested",
        # This is progress the worker wrote after the old implementation's
        # pre-read and before cancellation obtained its row lock.
        "summary": {
            "completed_cases": 2,
            "total": 4,
            "passed": 2,
            "failed": 0,
            "errored": 0,
            "skipped": 0,
            "cancelled": 0,
            "cancel_requested": True,
            "cancel_requested_at": "2026-07-25T00:00:00+00:00",
        },
        "started_at": "2026-07-25T00:00:00+00:00",
        "completed_at": None,
    }
    with (
        patch.object(
            store,
            "request_suite_run_cancel_row_async",
            new=AsyncMock(return_value=latest_row),
        ) as cancel_mock,
        patch.object(store, "get_suite_run", new=AsyncMock()) as get_mock,
    ):
        result = await store.request_suite_run_cancel("suite-run-1")

    assert result is not None
    assert result["status"] == "cancelling"
    assert result["summary"]["completed_cases"] == 2
    assert "cases" not in result["summary"]
    cancel_call = cancel_mock.await_args
    assert cancel_call is not None
    assert cancel_call.args == ("suite-run-1",)
    assert isinstance(cancel_call.kwargs["cancel_requested_at"], str)
    get_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_case_run_filters_values_and_sets_status():
    with patch.object(
        store,
        "update_case_run_row_async",
        new=AsyncMock(
            return_value={
                "id": "case-run-1",
                "suite_run_id": "suite-run-1",
                "case_id": "case-1",
                "status": "passed",
                "agent_run_id": "agent-run-1",
                "session_id": "",
                "trace_id": "trace-1",
                "agno_eval_run_ids": ["eval-1"],
                "error_type": "",
                "error_summary": "",
                "replay_of_case_run_id": "",
                "started_at": "2026-07-06T00:00:00Z",
                "completed_at": "2026-07-06T00:01:00Z",
            }
        ),
    ) as update_mock:
        result = await store.mark_case_run(
            "case-run-1",
            "passed",
            {
                "agent_run_id": "agent-run-1",
                "trace_id": "trace-1",
                "agno_eval_run_ids": ["eval-1"],
                "bogus": "x",
            },
        )

    assert result is not None
    assert result["agno_eval_run_ids"] == ["eval-1"]
    update_call = update_mock.await_args
    assert update_call is not None
    sent_values = update_call.args[1]
    assert sent_values["status"] == "passed"
    assert sent_values["agent_run_id"] == "agent-run-1"
    assert "bogus" not in sent_values


@pytest.mark.asyncio
async def test_complete_case_run_writes_a_validated_private_checkpoint_once():
    checkpoint = terminal_checkpoint(status="failed")
    persisted_row = {
        "id": "case-run-1",
        "suite_run_id": "suite-run-1",
        "case_id": "case-1",
        "status": "failed",
        "agent_run_id": "agent-run-1",
        "session_id": "eval_case-run-1",
        "trace_id": "trace-1",
        "agno_eval_run_ids": ["accuracy-1"],
        "error_type": "AccuracyFailed",
        "error_summary": "private detail retained on the CaseRun",
        "replay_of_case_run_id": "",
        "definition_snapshot": {},
        "execution_provenance": {},
        "terminal_checkpoint": checkpoint,
        "started_at": "2026-07-06T00:00:00Z",
        "completed_at": "2026-07-06T00:01:00Z",
    }
    with patch.object(
        store,
        "complete_case_run_row_if_queued_async",
        new=AsyncMock(return_value=persisted_row),
    ) as complete_mock:
        result = await store.complete_case_run(
            "case-run-1",
            "failed",
            {
                "agent_run_id": "agent-run-1",
                "session_id": "eval_case-run-1",
                "trace_id": "trace-1",
                "agno_eval_run_ids": ["accuracy-1"],
                "error_type": "AccuracyFailed",
                "error_summary": "private detail retained on the CaseRun",
                "ignored": "must not persist",
            },
            terminal_checkpoint=checkpoint,
        )

    assert result is not None
    assert result["status"] == "failed"
    assert "terminal_checkpoint" not in result
    call = complete_mock.await_args
    assert call is not None
    assert call.args == ("case-run-1",)
    assert call.kwargs["values"]["status"] == "failed"
    assert call.kwargs["values"]["error_type"] == "AccuracyFailed"
    assert "ignored" not in call.kwargs["values"]
    assert call.kwargs["terminal_checkpoint"] == store.normalize_case_run_terminal_checkpoint(
        checkpoint
    )


@pytest.mark.asyncio
async def test_complete_case_run_forwards_the_private_execution_fence() -> None:
    checkpoint = terminal_checkpoint(status="passed")
    lease = store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=4)
    with patch.object(
        store,
        "complete_case_run_row_if_queued_async",
        new=AsyncMock(return_value=None),
    ) as complete_mock:
        result = await store.complete_case_run(
            "case-run-1",
            "passed",
            {},
            terminal_checkpoint=checkpoint,
            execution_lease=lease,
        )

    assert result is None
    complete_mock.assert_awaited_once()
    complete_call = complete_mock.await_args
    assert complete_call is not None
    assert complete_call.kwargs["job_id"] == "job-1"
    assert complete_call.kwargs["lease_epoch"] == 4


@pytest.mark.asyncio
async def test_claim_suite_case_run_creates_private_fenced_evidence() -> None:
    lease = store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=4)
    definition = snapshot_case()
    provenance = {"target": {"kind": "agent", "id": "security-operations"}}

    async def echo_claim(values, *, job_id, lease_epoch):
        assert job_id == "job-1"
        assert lease_epoch == 4
        return {
            **values,
            "lease_job_id": job_id,
            "lease_epoch": lease_epoch,
            "terminal_checkpoint": {},
        }, True

    with patch.object(
        store,
        "claim_suite_case_run_row_async",
        new=AsyncMock(side_effect=echo_claim),
    ):
        claim = await store.claim_suite_case_run(
            "case-1",
            suite_run_id="suite-run-1",
            definition_snapshot=definition,
            execution_provenance=provenance,
            execution_lease=lease,
        )

    assert claim is not None
    assert claim.acquired is True
    assert claim.case_run["status"] == "running"
    assert claim.case_run["lease_job_id"] == "job-1"
    assert claim.case_run["lease_epoch"] == 4
    assert "definition_snapshot" in claim.case_run


@pytest.mark.asyncio
async def test_claim_suite_case_run_rejects_a_mismatched_frozen_definition() -> None:
    lease = store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=4)
    definition = snapshot_case()
    provenance = {"target": {"kind": "agent", "id": "security-operations"}}
    with patch.object(
        store,
        "claim_suite_case_run_row_async",
        new=AsyncMock(
            return_value=(
                {
                    "id": "case-run-1",
                    "suite_run_id": "suite-run-1",
                    "case_id": "case-1",
                    "status": "running",
                    "definition_snapshot": snapshot_case(prompt="tampered"),
                    "execution_provenance": provenance,
                    "terminal_checkpoint": {},
                    "lease_job_id": "job-1",
                    "lease_epoch": 4,
                },
                True,
            )
        ),
    ):
        with pytest.raises(ValueError, match="definition does not match"):
            await store.claim_suite_case_run(
                "case-1",
                suite_run_id="suite-run-1",
                definition_snapshot=definition,
                execution_provenance=provenance,
                execution_lease=lease,
            )


@pytest.mark.asyncio
async def test_fenced_suite_progress_uses_the_execution_lease_cas() -> None:
    lease = store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=4)
    marked_row = {
        "id": "suite-run-1",
        "suite_id": "suite-1",
        "status": "passed",
        "started_by": "user-1",
        "error_summary": "",
        "summary": {"completed_cases": 1},
        "started_at": "2026-07-06T00:00:00Z",
        "completed_at": "2026-07-06T00:01:00Z",
    }
    with patch.object(
        store,
        "update_suite_run_row_if_execution_lease_async",
        new=AsyncMock(side_effect=[None, marked_row]),
    ) as update_mock:
        result = await store.update_suite_run_progress(
            "suite-run-1",
            summary={"completed_cases": 1},
            execution_lease=lease,
        )
        assert result is None
        marked = await store.mark_suite_run(
            "suite-run-1",
            "passed",
            {},
            expected_statuses=("running",),
            execution_lease=lease,
        )

    assert marked is not None
    assert marked["status"] == "passed"
    progress_call, terminal_call = update_mock.await_args_list
    assert progress_call.args == ("suite-run-1",)
    assert progress_call.kwargs == {
        "expected_statuses": ("running",),
        "job_id": "job-1",
        "lease_epoch": 4,
        "values": {"summary": {"completed_cases": 1}},
    }
    assert terminal_call.args == ("suite-run-1",)
    assert terminal_call.kwargs["expected_statuses"] == ("running",)
    assert terminal_call.kwargs["job_id"] == "job-1"
    assert terminal_call.kwargs["lease_epoch"] == 4
    assert terminal_call.kwargs["values"]["status"] == "passed"
    assert terminal_call.kwargs["values"]["summary"] == {}

    with pytest.raises(TypeError, match="execution_lease"):
        await cast(Any, store.mark_suite_run)(
            "suite-run-1",
            "passed",
            {},
            expected_statuses=("running",),
        )


@pytest.mark.asyncio
async def test_complete_case_run_rejects_empty_or_status_mismatched_checkpoint():
    with patch.object(
        store,
        "complete_case_run_row_if_queued_async",
        new=AsyncMock(),
    ) as complete_mock:
        with pytest.raises(ValueError, match="missing required fields"):
            await store.complete_case_run(
                "case-run-1",
                "passed",
                {},
                terminal_checkpoint={},
            )
        with pytest.raises(ValueError, match="must match CaseRun status"):
            await store.complete_case_run(
                "case-run-1",
                "passed",
                {},
                terminal_checkpoint=terminal_checkpoint(status="failed"),
            )

    complete_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_case_run_routes_terminal_checkpoint_to_one_way_completion():
    checkpoint = terminal_checkpoint(status="passed")
    with (
        patch.object(
            store,
            "complete_case_run",
            new=AsyncMock(return_value={"id": "case-run-1", "status": "passed"}),
        ) as complete_mock,
        patch.object(store, "update_case_run_row_async", new=AsyncMock()) as update_mock,
    ):
        result = await store.mark_case_run(
            "case-run-1",
            "passed",
            {
                "session_id": "eval_case-run-1",
                "terminal_checkpoint": checkpoint,
            },
        )

    assert result == {"id": "case-run-1", "status": "passed"}
    complete_mock.assert_awaited_once_with(
        "case-run-1",
        "passed",
        {"session_id": "eval_case-run-1"},
        terminal_checkpoint=checkpoint,
    )
    update_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_case_run_sets_defaults_and_replay_link():
    with patch.object(
        store,
        "create_case_run_row_async",
        new=AsyncMock(
            return_value={
                "id": "case-run-1",
                "suite_run_id": "",
                "case_id": "case-1",
                "status": "queued",
                "agent_run_id": "",
                "session_id": "",
                "trace_id": "",
                "agno_eval_run_ids": [],
                "error_type": "",
                "error_summary": "",
                "replay_of_case_run_id": "case-run-0",
                "started_at": "2026-07-06T00:00:00Z",
                "completed_at": None,
            }
        ),
    ) as create_mock:
        result = await store.create_case_run(
            "case-1", replay_of_case_run_id="case-run-0"
        )

    assert result["status"] == "queued"
    assert result["replay_of_case_run_id"] == "case-run-0"
    create_call = create_mock.await_args
    assert create_call is not None
    assert create_call.kwargs["values"]["suite_run_id"] == ""


@pytest.mark.asyncio
async def test_case_run_snapshots_are_private_and_have_a_stable_public_hash():
    definition = {
        "expected_output": "private expected output",
        "input": "private prompt",
        "nested": {"criterion": "private criterion"},
    }
    provenance = {
        "target": {"kind": "agent", "id": "security-operations"},
        "model_config_id": "private-model-config",
    }

    async def echo_created_row(*, values):
        return values

    with patch.object(
        store,
        "create_case_run_row_async",
        new=AsyncMock(side_effect=echo_created_row),
    ) as create_mock:
        public_created = await store.create_case_run(
            "case-1",
            definition_snapshot=definition,
            execution_provenance=provenance,
        )

    expected_hash = sha256(
        json.dumps(
            definition,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    create_call = create_mock.await_args
    assert create_call is not None
    sent_values = create_call.kwargs["values"]
    assert sent_values["definition_snapshot"] == definition
    assert sent_values["execution_provenance"] == provenance
    assert public_created["definition_snapshot_sha256"] == expected_hash
    assert "definition_snapshot" not in public_created
    assert "execution_provenance" not in public_created
    assert "terminal_checkpoint" not in public_created
    assert "private prompt" not in json.dumps(public_created)
    assert "private-model-config" not in json.dumps(public_created)


@pytest.mark.asyncio
async def test_private_case_run_accessor_retains_snapshot_for_replay():
    definition = snapshot_case(prompt="prompt retained only in the snapshot")
    row = {
        "id": "case-run-1",
        "suite_run_id": "",
        "case_id": "case-1",
        "status": "failed",
        "agent_run_id": "",
        "session_id": "",
        "trace_id": "",
        "agno_eval_run_ids": [],
        "error_type": "",
        "error_summary": "",
        "replay_of_case_run_id": "",
        "definition_snapshot": definition,
        "execution_provenance": {"target": {"id": "security-operations"}},
        "terminal_checkpoint": terminal_checkpoint(status="failed"),
        "started_at": "2026-07-06T00:00:00Z",
        "completed_at": None,
    }
    with patch.object(
        store,
        "get_case_run_row_async",
        new=AsyncMock(return_value=row),
    ):
        public = await store.get_case_run("case-run-1")
        private = await store.get_case_run_private("case-run-1")

    assert public is not None
    assert private is not None
    assert "definition_snapshot" not in public
    assert "execution_provenance" not in public
    assert "terminal_checkpoint" not in public
    assert "prompt retained" not in json.dumps(public)
    assert private["definition_snapshot"] == store.build_case_run_definition_snapshot(
        definition
    )
    assert private["execution_provenance"] == row["execution_provenance"]
    assert private["terminal_checkpoint"] == store.normalize_case_run_terminal_checkpoint(
        terminal_checkpoint(status="failed")
    )
    assert public["result"] == {
        "name": "Case case-1",
        "case_id": "case-1",
        "case_run_id": "case-run-1",
        "session_id": "",
        "duration_seconds": 1.235,
        "timeout_seconds": 120,
        "status": "failed",
        "passed": False,
        "timed_out": False,
        "skipped": False,
        "error_type": "",
        "error": "",
        "accuracy_passed": True,
        "accuracy_reason": None,
        "accuracy_score": 9.5,
        "judge_passed": True,
        "judge_reason": None,
        "judge_score": 9,
        "reliability_passed": True,
        "judge_id": "agent_as_judge:refusal-v1@1.0.0+model:judge-a",
        "eval_profile": "tools_off",
        "reliability_evidence": {"failed_tool_calls": ["unapproved_tool"]},
        "performance": {
            "warmup_runs": 1,
            "num_iterations": 3,
            "runtime_seconds": {"avg": 0.125432, "median": 0.1, "p95": 0.2},
        },
    }
    assert "prompt retained" not in json.dumps(public["result"])


@pytest.mark.asyncio
async def test_list_suite_run_case_result_lites_uses_frozen_case_order() -> None:
    first = snapshot_case("case-1")
    second = snapshot_case("case-2")
    second_row = {
        "id": "case-run-2",
        "suite_run_id": "suite-run-1",
        "case_id": "case-2",
        "work_item_index": 1,
        "status": "passed",
        "session_id": "eval_case-run-2",
        "definition_snapshot": second,
        "execution_provenance": {"timeout_seconds": 120, "eval_profile": "full"},
        "terminal_checkpoint": terminal_checkpoint(),
    }
    first_row = {
        "id": "case-run-1",
        "suite_run_id": "suite-run-1",
        "case_id": "case-1",
        "work_item_index": 0,
        "status": "failed",
        "session_id": "eval_case-run-1",
        "error_type": "JudgeFailed",
        "error_summary": "bounded failure",
        "definition_snapshot": first,
        "execution_provenance": {"timeout_seconds": 120, "eval_profile": "full"},
        "terminal_checkpoint": terminal_checkpoint(status="failed"),
    }
    with patch.object(
        store,
        "list_suite_run_case_work_items_private",
        new=AsyncMock(return_value=[first_row, second_row]),
    ) as list_work_items:
        results = await store.list_suite_run_case_result_lites("suite-run-1")

    assert [result["case_id"] for result in results] == ["case-1", "case-2"]
    assert results[0]["error"] == "bounded failure"
    assert results[1]["status"] == "passed"
    list_work_items.assert_awaited_once_with("suite-run-1")


@pytest.mark.asyncio
async def test_replay_from_snapshot_uses_the_verified_source_insert_path():
    definition = snapshot_case()

    async def echo_created_row(*, values, replay_source_case_run_id):
        assert replay_source_case_run_id == "case-run-source"
        return values

    with patch.object(
        store,
        "create_case_run_row_async",
        new=AsyncMock(side_effect=echo_created_row),
    ) as create_mock:
        result = await store.create_case_run(
            "case-1",
            replay_of_case_run_id="case-run-source",
            definition_snapshot=definition,
            replay_from_snapshot=True,
        )

    assert result["replay_of_case_run_id"] == "case-run-source"
    create_call = create_mock.await_args
    assert create_call is not None
    assert create_call.kwargs["replay_source_case_run_id"] == "case-run-source"
    assert "definition_snapshot" not in result


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("not-an-object", "must be an object"),
        ({"number": float("nan")}, "finite JSON numbers"),
        ({1: "not a JSON object key"}, "keys must be strings"),
        ({"unsupported": {"set"}}, "JSON-safe values"),
        (
            {"prompt": "x" * (store.MAX_CASE_RUN_DEFINITION_SNAPSHOT_BYTES + 1)},
            "at most",
        ),
    ],
)
def test_case_run_definition_snapshot_is_json_safe_and_bounded(
    value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        store.normalize_case_run_definition_snapshot(value)


def test_execution_provenance_is_bounded_separately_from_definition_snapshot() -> None:
    with pytest.raises(ValueError, match="at most"):
        store.normalize_case_run_execution_provenance(
            {"provenance": "x" * (store.MAX_CASE_RUN_EXECUTION_PROVENANCE_BYTES + 1)}
        )


def test_terminal_checkpoint_is_strict_private_and_normalized() -> None:
    checkpoint = terminal_checkpoint()

    normalized = store.normalize_case_run_terminal_checkpoint(checkpoint)

    assert normalized["duration_seconds"] == 1.235
    assert normalized["accuracy_score"] == 9.5
    assert normalized["judge_score"] == 9
    assert normalized["reliability_evidence"] == {
        "failed_tool_calls": ["unapproved_tool"]
    }
    assert normalized["performance"] == {
        "warmup_runs": 1,
        "num_iterations": 3,
        "runtime_seconds": {"avg": 0.125432, "median": 0.1, "p95": 0.2},
    }
    assert "judge_reason" not in normalized
    assert "accuracy_reason" not in normalized
    assert "model_output" not in normalized


@pytest.mark.parametrize(
    ("checkpoint", "message"),
    [
        ({}, "missing required fields"),
        (
            terminal_checkpoint(judge_reason="private judge rationale"),
            "unsupported fields: judge_reason",
        ),
        (
            terminal_checkpoint(model_output="private model output"),
            "unsupported fields: model_output",
        ),
    ],
)
def test_terminal_checkpoint_rejects_empty_and_free_text_fields(
    checkpoint: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        store.normalize_case_run_terminal_checkpoint(checkpoint)


@pytest.mark.asyncio
async def test_list_case_runs_by_agno_eval_run_ids_maps_each_eval_id():
    with patch.object(
        store,
        "list_case_runs_by_agno_eval_run_ids_rows_async",
        new=AsyncMock(
            return_value=[
                {
                    "id": "case-run-1",
                    "suite_run_id": "suite-run-1",
                    "case_id": "case-1",
                    "status": "failed",
                    "agent_run_id": "agent-run-1",
                    "session_id": "",
                    "trace_id": "",
                    "agno_eval_run_ids": ["eval-1", "eval-2"],
                    "error_type": "assertion",
                    "error_summary": "Missing tool call",
                    "replay_of_case_run_id": "",
                    "started_at": "2026-07-06T00:00:00Z",
                    "completed_at": "2026-07-06T00:01:00Z",
                }
            ]
        ),
    ) as list_mock:
        result = await store.list_case_runs_by_agno_eval_run_ids(
            ["eval-2", "eval-1", "eval-2", ""]
        )

    assert result["eval-1"]["id"] == "case-run-1"
    assert result["eval-2"]["id"] == "case-run-1"
    list_call = list_mock.await_args
    assert list_call is not None
    assert list_call.args == (["eval-2", "eval-1"],)


@pytest.mark.asyncio
async def test_mark_direct_case_run_allows_status_only_updates():
    case_run_row = {
        "id": "case-run-1",
        "suite_run_id": "suite-run-1",
        "case_id": "case-1",
        "status": "running",
        "agent_run_id": "",
        "session_id": "",
        "trace_id": "",
        "agno_eval_run_ids": [],
        "error_type": "",
        "error_summary": "",
        "replay_of_case_run_id": "",
        "started_at": "2026-07-06T00:00:00Z",
        "completed_at": None,
    }
    with patch.object(
        store, "update_case_run_row_async", new=AsyncMock(return_value=case_run_row)
    ) as case_update:
        case_result = await store.mark_case_run("case-run-1", "running", {})

    assert case_result is not None
    assert case_result["status"] == "running"
    case_call = case_update.await_args
    assert case_call is not None
    assert case_call.args[1] == {"status": "running"}


@pytest.mark.asyncio
async def test_list_and_get_helpers_normalize_rows():
    suite_row = {
        "id": "suite-1",
        "name": "Security",
        "description": "",
        "target_kind": "agent",
        "target_id": "security-operations",
        "enabled": True,
        "tags": ["security"],
        "created_by": "user-1",
        "created_at": "2026-07-06T00:00:00Z",
        "updated_at": "2026-07-06T00:00:00Z",
    }
    with (
        patch.object(
            store, "list_suite_rows_async", new=AsyncMock(return_value=[suite_row])
        ) as list_mock,
        patch.object(
            store, "get_suite_row_async", new=AsyncMock(return_value=suite_row)
        ) as get_mock,
    ):
        listed = await store.list_suites(enabled=True)
        fetched = await store.get_suite("suite-1")

    assert listed["data"] == [fetched]
    assert listed["meta"]["total_count"] == 1
    list_call = list_mock.await_args
    get_call = get_mock.await_args
    assert list_call is not None
    assert get_call is not None
    assert list_call.kwargs["enabled"] is True
    assert get_call.args == ("suite-1",)


@pytest.mark.asyncio
async def test_list_suite_and_case_runs_return_data_meta():
    suite_row = {
        "id": "sr-1",
        "suite_id": "s1",
        "status": "completed",
        "started_by": "user-1",
        "error_summary": "",
        "summary": {},
        "started_at": "2026-07-06T00:00:00Z",
        "finished_at": "2026-07-06T00:01:00Z",
    }
    case_row = {
        "id": "cr-1",
        "suite_run_id": "",
        "case_id": "c1",
        "status": "failed",
        "agent_run_id": "",
        "session_id": "",
        "trace_id": "",
        "agno_eval_run_ids": [],
        "error_type": "",
        "error_summary": "boom",
        "replay_of_case_run_id": "",
        "started_at": "2026-07-06T00:00:00Z",
        "finished_at": "2026-07-06T00:01:00Z",
    }
    with (
        patch.object(
            store,
            "list_suite_run_rows_async",
            new=AsyncMock(return_value=([suite_row], 3)),
        ) as suite_list,
        patch.object(
            store,
            "list_case_run_rows_async",
            new=AsyncMock(return_value=([case_row], 2)),
        ) as case_list,
    ):
        suite_payload = await store.list_suite_runs(
            suite_id="s1", status="completed", page=2, limit=10
        )
        case_payload = await store.list_case_runs(
            case_id="c1", status="failed", page=1, limit=25
        )

    assert suite_list.await_args is not None
    assert suite_list.await_args.kwargs == {
        "suite_id": "s1",
        "status": "completed",
        "page": 2,
        "limit": 10,
    }
    assert set(suite_payload.keys()) == {"data", "meta"}
    assert suite_payload["meta"]["page"] == 2
    assert suite_payload["meta"]["limit"] == 10
    assert suite_payload["meta"]["total_count"] == 3
    assert suite_payload["data"][0]["id"] == "sr-1"

    assert case_list.await_args is not None
    assert case_list.await_args.kwargs["page"] == 1
    assert case_list.await_args.kwargs["limit"] == 25
    assert case_payload["meta"]["total_count"] == 2
    assert case_payload["data"][0]["id"] == "cr-1"
