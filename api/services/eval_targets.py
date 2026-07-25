"""Strict, executable target catalog for Agno Eval Suites.

An Eval Suite is a regression contract for one concrete runtime target.  Unlike
Chat's permissive selector (which deliberately falls back to the default Agent
for an unknown user preference), Eval authoring must never substitute a target:
an unknown or unavailable target is an authoring/runtime error.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from api.services.agent_catalog import AGENT_PROFILES
from api.services.team_runtime import TEAM_PROFILES, team_feature_enabled

EvalTargetKind = Literal["agent", "team"]
_TARGET_KINDS = frozenset({"agent", "team"})


@dataclass(frozen=True)
class EvalTarget:
    """One concrete Agno component that an Eval Suite executes."""

    kind: EvalTargetKind
    id: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.id}


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Eval target {field} is required")
    return text


def _target_profile(kind: EvalTargetKind, target_id: str) -> Mapping[str, Any]:
    if kind == "agent":
        profile = AGENT_PROFILES.get(target_id)
        if profile is None or not bool(profile.get("chat_selectable", False)):
            raise ValueError(f"Unknown Eval Agent target: {target_id}")
        return profile

    profile = TEAM_PROFILES.get(target_id)
    if profile is None or not bool(profile.get("chat_selectable", False)):
        raise ValueError(f"Unknown Eval Team target: {target_id}")
    return profile


def parse_eval_target(
    value: object,
    *,
    require_available: bool = True,
) -> EvalTarget:
    """Validate an explicit ``{kind, id}`` Eval target without any fallback."""
    if not isinstance(value, Mapping):
        raise ValueError("Eval target must be an object with kind and id")
    kind_text = _required_text(value.get("kind"), "kind")
    if kind_text not in _TARGET_KINDS:
        raise ValueError("Eval target kind must be 'agent' or 'team'")
    kind: EvalTargetKind = "agent" if kind_text == "agent" else "team"
    target_id = _required_text(value.get("id"), "id")
    _target_profile(kind, target_id)
    if kind == "team" and require_available and not team_feature_enabled():
        raise ValueError(
            "Eval Team target is disabled; set TAIS_ENABLE_AGNO_TEAM=1 before authoring or running it"
        )
    return EvalTarget(kind=kind, id=target_id)


def target_from_suite(
    suite: Mapping[str, Any],
    *,
    require_available: bool = True,
) -> EvalTarget:
    """Read and strictly validate the persisted target for a Suite."""
    return parse_eval_target(suite.get("target"), require_available=require_available)


def list_eval_targets() -> list[dict[str, Any]]:
    """Return selectable targets with Team availability made explicit to the UI."""
    rows: list[dict[str, Any]] = []
    for target_id, profile in AGENT_PROFILES.items():
        if not bool(profile.get("chat_selectable", False)):
            continue
        rows.append(
            {
                "kind": "agent",
                "id": target_id,
                "name": str(profile.get("name") or target_id),
                "description": str(profile.get("description") or ""),
                "available": True,
            }
        )

    teams_available = team_feature_enabled()
    for target_id, profile in TEAM_PROFILES.items():
        if not bool(profile.get("chat_selectable", False)):
            continue
        rows.append(
            {
                "kind": "team",
                "id": target_id,
                "name": str(profile.get("name") or target_id),
                "description": str(profile.get("description") or ""),
                "available": teams_available,
                "unavailable_reason": (
                    "TAIS_ENABLE_AGNO_TEAM=1 is required" if not teams_available else ""
                ),
            }
        )
    return rows
