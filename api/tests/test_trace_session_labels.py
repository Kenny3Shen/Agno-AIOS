"""Trace session display labels prefer chat titles over engine span names."""

from __future__ import annotations

import pytest

from api.services.chat_session_service import (
    TITLE_METADATA_KEY,
    is_technical_session_label,
    session_display_label_from_row,
)
from api.services.tracing_service import _fallback_trace_session_name


def test_is_technical_session_label_detects_arun() -> None:
    assert is_technical_session_label("安全运营助手.arun")
    assert is_technical_session_label("Agent.run")
    assert is_technical_session_label("")
    assert not is_technical_session_label("分析最新 CVE 影响")
    assert not is_technical_session_label("Renamed session")


def test_session_display_label_prefers_title_then_preview() -> None:
    row = {
        "session_id": "s1",
        "metadata": {TITLE_METADATA_KEY: "自定义标题"},
        "runs": [{"input": "第一句话"}],
    }
    assert session_display_label_from_row(row) == "自定义标题"

    row_preview = {
        "session_id": "s2",
        "metadata": {},
        "runs": [{"input": "请分析 10.0.0.1 的告警"}],
    }
    assert "10.0.0.1" in session_display_label_from_row(row_preview)


def test_fallback_strips_arun_suffix() -> None:
    assert (
        _fallback_trace_session_name(
            engine_name="安全运营助手.arun",
            agent_id="security-operations",
            team_id=None,
            workflow_id=None,
            session_id="sid",
        )
        == "security-operations"
    )
    assert (
        _fallback_trace_session_name(
            engine_name="安全运营助手.arun",
            agent_id=None,
            team_id=None,
            workflow_id=None,
            session_id="sid",
        )
        == "安全运营助手"
    )


@pytest.mark.asyncio
async def test_session_display_labels_empty_ids() -> None:
    from api.services import tracing_service as ts

    assert await ts._session_display_labels([]) == {}
