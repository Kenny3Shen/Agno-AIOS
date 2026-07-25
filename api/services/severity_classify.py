"""Severity classification dialogue contract for the severity-router workflow.

Classify agent output is consumed by router CEL on the previous step text
(``input``). Keep tokens, offline eval classifier, and selector logic here so
tests pin the **shipped** contract (template + CEL), not a parallel product.
"""

from __future__ import annotations

import re
from typing import Literal

SeverityToken = Literal["critical", "high", "other"]
RoutePath = Literal["path_a", "path_b", "path_c"]

# Single source of truth for the Classify step instructions (template embeds this).
SEVERITY_CLASSIFY_INSTRUCTIONS = """\
You are a security severity classifier for an automated IR workflow.

Task: Read the operator alert / message and choose exactly one severity token.

Allowed tokens (lowercase English only):
- critical — active compromise, ransomware, data exfiltration in progress, domain admin takeover, or similar emergency requiring immediate containment.
- high — confirmed serious vulnerability exploitation, significant malware with limited blast radius, or urgent but not full emergency.
- other — medium/low/unknown, informational, insufficient evidence, or ambiguous cases.

Rules:
1. Do not invent IOCs, CVEs, hostnames, or impact not supported by the input.
2. If evidence is missing or ambiguous, choose **other** (never guess critical).
3. Prefer **other** over over-classifying when unsure.
4. Output format (strict):
   - Line 1 must be exactly: SEVERITY: <token>
     where <token> is one of: critical, high, other
   - Line 2 optional: one short rationale sentence (no new facts).
5. The first line is the only routing signal. Downstream CEL matches
   ^SEVERITY:\\s*critical|high$ (case-insensitive), not free-text words in the rationale.

Examples:
Input: "Ransomware encrypting file servers; domain admin sessions active."
Output:
SEVERITY: critical
Active ransomware with privileged sessions implies emergency containment.

Input: "Scanner found CVE-2024-xxxx on one internal host; no exploit evidence."
Output:
SEVERITY: high
Serious CVE reported but limited confirmed impact.

Input: "User reports slow laptop; no malware indicators."
Output:
SEVERITY: other
Insufficient security impact evidence.
"""

# Router CEL: match only the structured SEVERITY line (not rationale prose).
# Uses multiline (?m) + case-insensitive (?i) so "SEVERITY: CRITICAL" works and
# "SEVERITY: other\\n... critical ..." does NOT select path_a.
SEVERITY_ROUTER_SELECTOR_CEL = (
    'input.matches("(?im)^SEVERITY:\\\\s*critical\\\\s*$") ? "path_a" : '
    '(input.matches("(?im)^SEVERITY:\\\\s*high\\\\s*$") ? "path_b" : "path_c")'
)

_SEVERITY_LINE = re.compile(r"(?im)^\s*SEVERITY:\s*(critical|high|other)\s*$")

# Keyword cues aligned with SEVERITY_CLASSIFY_INSTRUCTIONS (offline / eval agent).
_CRITICAL_CUES = re.compile(
    r"(?i)\b("
    r"ransomware|encrypting|exfiltrat|domain\s+admin|active\s+compromise|"
    r"c2\s+beacon|lateral\s+movement\s+in\s+progress|wipe|wiper"
    r")\b"
)
_HIGH_CUES = re.compile(
    r"(?i)\b("
    r"cve-\d{4}|exploit|malware|ransomware|"  # cve often high if not emergency
    r"confirmed\s+exploit|high\s+severity|privilege\s+escalation"
    r")\b"
)


def _as_severity_token(value: str) -> SeverityToken | None:
    token = value.strip().lower()
    if token == "critical":
        return "critical"
    if token == "high":
        return "high"
    if token == "other":
        return "other"
    return None


def extract_severity_token(text: str) -> SeverityToken:
    """Parse classifier dialogue into a stable token (prefer SEVERITY: line)."""
    raw = str(text or "")
    match = _SEVERITY_LINE.search(raw)
    if match:
        parsed = _as_severity_token(match.group(1))
        if parsed is not None:
            return parsed
    return "other"


def classify_alert_severity(prompt: str) -> SeverityToken:
    """Deterministic offline Eval Agent for the Classify dialogue contract.

    Mirrors the instruction rules (critical > high > other / ambiguous→other)
    without calling a live LLM. Used by tests and offline eval runs of the
    severity-router Classify step.
    """
    text = str(prompt or "").strip()
    if not text:
        return "other"
    # Ambiguity / insufficient evidence → other (instruction rules 2–3)
    if re.search(
        r"(?i)\b(unclear|unknown|insufficient|no\s+malware|cannot\s+confirm|no\s+indicators)\b",
        text,
    ):
        if not _CRITICAL_CUES.search(text):
            return "other"
    if _CRITICAL_CUES.search(text):
        return "critical"
    if _HIGH_CUES.search(text):
        return "high"
    return "other"


def format_classify_reply(token: SeverityToken, rationale: str = "") -> str:
    """Build a router-compatible classifier reply (tests / offline agent)."""
    line = f"SEVERITY: {token}"
    note = str(rationale or "").strip()
    if note:
        return f"{line}\n{note}"
    return line


def run_classify_step(prompt: str) -> str:
    """Shipped offline path: Classify dialogue under SEVERITY_CLASSIFY_INSTRUCTIONS.

    Returns the full agent-style reply string that the router CEL consumes.
    """
    # Contract guard: instructions must document the SEVERITY line format.
    if "SEVERITY:" not in SEVERITY_CLASSIFY_INSTRUCTIONS:
        raise RuntimeError("Classify instructions missing SEVERITY: contract")
    token = classify_alert_severity(prompt)
    # Rationale may mention words like critical/high; CEL must ignore them.
    rationale = {
        "critical": "Emergency indicators present in the alert text.",
        "high": "Serious but non-emergency impact described in the alert.",
        "other": "Insufficient or non-critical security impact in the alert.",
    }[token]
    return format_classify_reply(token, rationale)


def select_severity_route(text: str) -> RoutePath:
    """Production routing: same CEL expression as the severity-router template."""
    return select_severity_route_cel(text)


def select_severity_route_cel(text: str) -> RoutePath:
    """Evaluate the shipped router CEL expression against ``input``."""
    import celpy
    from celpy.celtypes import StringType

    env = celpy.Environment()
    program = env.program(env.compile(SEVERITY_ROUTER_SELECTOR_CEL))
    activation: dict[str, StringType] = {"input": StringType(str(text or ""))}
    result = program.evaluate(activation)
    path = str(result)
    if path == "path_a":
        return "path_a"
    if path == "path_b":
        return "path_b"
    return "path_c"


def run_classify_and_route(prompt: str) -> tuple[str, SeverityToken, RoutePath]:
    """End-to-end offline: prompt → Classify reply → CEL route (template contract)."""
    reply = run_classify_step(prompt)
    token = extract_severity_token(reply)
    path = select_severity_route_cel(reply)
    return reply, token, path
