"""Workflow definition mapping guard for the canonical 1.0 schema."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


# Kept as a strict validation rule until callers move the rule into the
# workflow compiler.  Unlike the removed migration, it never rewrites old
# workflow definitions into a supported form.
RETIRED_WORKFLOW_SKILL_NAMES = frozenset({"playbook-skill"})


def canonicalize_workflow_definition(value: object) -> dict[str, Any] | None:
    """Return a detached mapping without accepting legacy field aliases.

    Callers validate the returned definition through the canonical workflow
    compiler.  Old field names, missing ids, and retired skills are therefore
    rejected instead of being repaired on read or startup.
    """
    if not isinstance(value, Mapping):
        return None
    return {str(key): deepcopy(item) for key, item in value.items()}
