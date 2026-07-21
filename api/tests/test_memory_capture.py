"""P1 memory capture policy + memory_mode helpers."""

from __future__ import annotations

from api.persistence.chat_settings import (
    memory_flags_from_mode,
    memory_mode_from_flags,
    normalize_memory_mode,
)
from api.services.memory_capture import (
    is_soc_memory_profile,
    memory_capture_instructions,
    soc_memory_agent_instructions,
)


def test_normalize_memory_mode() -> None:
    assert normalize_memory_mode("agentic") == "agentic"
    assert normalize_memory_mode("OFF") == "off"
    assert normalize_memory_mode("garbage") == "automatic"


def test_memory_mode_flags_roundtrip() -> None:
    assert memory_flags_from_mode("off") == (False, False)
    assert memory_flags_from_mode("automatic") == (True, False)
    assert memory_flags_from_mode("agentic") == (True, True)
    assert memory_mode_from_flags(memory_enabled=False, enable_agentic_memory=True) == "off"
    assert (
        memory_mode_from_flags(memory_enabled=True, enable_agentic_memory=True) == "agentic"
    )
    assert (
        memory_mode_from_flags(memory_enabled=True, enable_agentic_memory=False)
        == "automatic"
    )


def test_global_capture_blocks_one_off_tasks() -> None:
    text = memory_capture_instructions(tool_content_enabled=False)
    assert "DO store" in text or "durable" in text.lower()
    assert "One-off" in text or "one-off" in text.lower()
    assert "IP" in text or "IOC" in text or "investigation" in text.lower()


def test_soc_appendix_and_agent_instructions() -> None:
    assert is_soc_memory_profile("security-operations")
    assert is_soc_memory_profile(None) is False or is_soc_memory_profile("") is False
    soc = memory_capture_instructions(
        tool_content_enabled=False, agent_id="security-operations"
    )
    assert "SOC" in soc or "IOE" in soc or "indicator" in soc.lower()
    assert "Knowledge" in soc
    general = memory_capture_instructions(
        tool_content_enabled=False, agent_id="data-analysis"
    )
    assert "SOC / security-operations" not in general
    assert soc_memory_agent_instructions("security-operations")
    assert not soc_memory_agent_instructions("data-analysis")


def test_tool_appendix_only_when_enabled() -> None:
    without = memory_capture_instructions(tool_content_enabled=False)
    with_tools = memory_capture_instructions(tool_content_enabled=True)
    assert "tool results" in with_tools.lower() or "When tool" in with_tools
    assert len(with_tools) > len(without)
