"""Global + profile-scoped memory capture policy (P1 behaviour quality).

User memory is for **durable personal/operational preferences**, not for
incident artifacts.  Operational facts belong in Knowledge; ephemeral SOC
indicators of exposure (IOE) must not land in long-term user memory.
"""

from __future__ import annotations

from api.services.agent_catalog import DEFAULT_AGENT_ID

# Profiles that run security operations / HITL / MCP containment paths.
_SOC_AGENT_IDS = frozenset(
    {
        DEFAULT_AGENT_ID,
        "security-operations",
    }
)

_GLOBAL_CAPTURE = """\
Capture ONLY durable facts about the user that remain useful across many sessions.

DO store (brief third-person statements):
- Role, team, preferred language, time zone, escalation contacts
- Stable workflow preferences (report format, severity thresholds, notification channels)
- Explicit long-term goals or constraints the user asked you to remember
- Standing policies the user confirmed as permanent (e.g. "always prefer contain-then-notify")

DO NOT store:
- One-off tasks, temporary TODOs, or "this turn only" requests
- Single investigation artifacts: individual IPs, hostnames, case/ticket IDs, alert IDs,
  CVE numbers from a one-time lookup, sample hashes, or raw log lines
- Full tool/MCP outputs, blacklist dumps, vulnerability feed excerpts
- Secrets, tokens, passwords, API keys, webhook URLs
- Casual chatter, temporary emotional state, or speculative guesses
- Content that belongs in the Knowledge base (runbooks, asset inventories, org-wide facts)

If the same preference is restated, UPDATE the existing memory instead of adding a duplicate.
When unsure whether something is durable, do not create a memory.
"""

_TOOL_CAPTURE_APPENDIX = """\

When tool results are present in the input:
- Extract only durable preferences or standing policies the user confirmed after seeing results.
- Never copy raw tool dumps, multi-page feeds, bulk IP lists, or entire log files into memory.
- Prefer a short third-person summary of the user's decision, not the tool payload itself.
"""

_SOC_CAPTURE_APPENDIX = """\

SOC / security-operations constraints (STRICT):
- User memory is NOT an investigation notebook. Do not record indicators of exposure (IOE),
  victim IPs, malware hashes, alert timelines, containment ticket numbers, or case narratives.
- Prefer Knowledge for operational facts (playbooks, asset ownership tables, org policies).
- Allowed user-memory examples: "User is a SOC analyst", "User prefers Chinese incident reports",
  "User escalates P1 to on-call via Feishu", "User wants high-severity first".
- Forbidden examples: "User investigated 10.0.0.5", "Alert ABC-123 was a true positive",
  "Host db-prod had CVE-2024-xxxx", any single-run IOC list.
- If the user only discusses a live incident, usually create NO new memory.
"""

# Short agent instruction block injected when agentic memory is on for SOC agents.
SOC_AGENT_MEMORY_INSTRUCTIONS = (
    "Memory discipline: only update long-term user memory for durable preferences "
    "(language, report style, escalation contacts, standing playbook choices). "
    "Do not store investigation IOCs, temporary IPs, alert IDs, or one-off case details—"
    "put operational facts in Knowledge instead."
)


def is_soc_memory_profile(agent_id: str | None) -> bool:
    """True when the agent should apply the strict SOC capture whitelist."""
    aid = str(agent_id or "").strip()
    return aid in _SOC_AGENT_IDS or aid == DEFAULT_AGENT_ID


def memory_capture_instructions(
    *,
    tool_content_enabled: bool = False,
    agent_id: str | None = None,
) -> str:
    """Build MemoryManager ``memory_capture_instructions`` for this run."""
    parts = [_GLOBAL_CAPTURE.strip()]
    if tool_content_enabled:
        parts.append(_TOOL_CAPTURE_APPENDIX.strip())
    if is_soc_memory_profile(agent_id):
        parts.append(_SOC_CAPTURE_APPENDIX.strip())
    return "\n\n".join(parts)


def soc_memory_agent_instructions(agent_id: str | None) -> list[str]:
    """Extra Agent ``instructions`` lines when agentic memory is enabled for SOC."""
    if not is_soc_memory_profile(agent_id):
        return []
    return [SOC_AGENT_MEMORY_INSTRUCTIONS]


__all__ = [
    "SOC_AGENT_MEMORY_INSTRUCTIONS",
    "is_soc_memory_profile",
    "memory_capture_instructions",
    "soc_memory_agent_instructions",
]
