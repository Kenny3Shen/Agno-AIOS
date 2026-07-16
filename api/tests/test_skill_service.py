from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from api.services import skill_service


def test_resolve_enabled_skill_dirs_filters_and_empty():
    fake = [Path("/tmp/playbook-skill"), Path("/tmp/cve-intel-skill")]

    class Meta:
        def __init__(self, name: str):
            self.name = name

    with (
        patch.object(skill_service, "get_enabled_skill_dirs", return_value=fake),
        patch.object(
            skill_service,
            "parse_skill_metadata",
            side_effect=lambda d: Meta(d.name),
        ),
    ):
        assert skill_service.resolve_enabled_skill_dirs(None) == fake
        assert skill_service.resolve_enabled_skill_dirs([]) == []
        assert [p.name for p in skill_service.resolve_enabled_skill_dirs(["cve-intel-skill"])] == [
            "cve-intel-skill"
        ]
        assert skill_service.resolve_enabled_skill_dirs(["missing"]) == []

