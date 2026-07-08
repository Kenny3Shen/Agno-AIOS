from __future__ import annotations

import importlib
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_aiomysql_dependency_and_deprecated_mysql_skills_are_removed() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]

    assert not any(dep.partition(">=")[0] == "aiomysql" for dep in dependencies)
    assert not any(dep.partition(">=")[0] == "orjson" for dep in dependencies)
    assert not (ROOT / "api/agent/skills/darknet-trace-skill").exists()
    assert not (ROOT / "api/agent/skills/threat-trace-skill").exists()


def test_response_layer_uses_fastapi_default_pydantic_serialization() -> None:
    main_source = (ROOT / "api/main.py").read_text(encoding="utf-8")

    assert "default_response_class" not in main_source
    assert "JsonResponse" not in main_source
    assert not (ROOT / "api/utils/json_response.py").exists()


def test_knowledge_source_snapshot_helpers_live_in_focused_service() -> None:
    knowledge_service = importlib.import_module("api.services.knowledge_service")
    source_service = importlib.import_module("api.services.knowledge_source_service")

    for helper_name in (
        "source_digest",
        "source_ref",
        "metadata_with_source_ref",
        "text_source_snapshot",
        "path_source_snapshot",
        "ainsert_source_snapshot_async",
    ):
        assert hasattr(source_service, helper_name)
        assert not hasattr(knowledge_service, f"_{helper_name}")
