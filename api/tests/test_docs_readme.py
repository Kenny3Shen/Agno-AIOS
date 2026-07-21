"""Structural checks: README embeds architecture diagram; technical docs live under docs/."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
DOCS = REPO_ROOT / "docs"
ASSETS = DOCS / "assets"

TECH_DOCS = (
    "architecture.md",
    "agents.md",
    "hitl.md",
    "workflows.md",
    "operations.md",
    "security.md",
    "development.md",
    "glossary.md",
    "README.md",
)


def _md_local_targets(markdown: str, base_dir: Path) -> list[tuple[str, Path]]:
    """Collect relative markdown link/image targets (exclude http(s), mailto, anchors-only)."""
    found: list[tuple[str, Path]] = []
    for match in re.finditer(r"!?\[([^\]]*)\]\(([^)]+)\)", markdown):
        target = match.group(2).strip()
        # strip optional title
        target = target.split()[0].strip("\"'")
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if target.startswith("#"):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        resolved = (base_dir / path_part).resolve()
        found.append((target, resolved))
    return found


@pytest.fixture(scope="module")
def readme_text() -> str:
    assert README.is_file()
    return README.read_text(encoding="utf-8")


def test_diagram_assets_exist_and_nonempty() -> None:
    svg = ASSETS / "tais-architecture.svg"
    png = ASSETS / "tais-architecture.png"
    assert svg.is_file() and svg.stat().st_size > 1000
    assert png.is_file() and png.stat().st_size > 1000


def test_readme_embeds_architecture_diagram(readme_text: str) -> None:
    # Relative image under docs/assets naming the architecture diagram
    assert re.search(
        r"!\[[^\]]*\]\(\./docs/assets/tais-architecture\.(?:png|svg)\)",
        readme_text,
    ), "README must embed docs/assets/tais-architecture.png or .svg"


def test_technical_docs_exist_with_substance() -> None:
    missing = [name for name in TECH_DOCS if not (DOCS / name).is_file()]
    assert not missing, f"missing docs pages: {missing}"
    # Relocated deep dives must retain substance (not empty stubs)
    for name in ("hitl.md", "workflows.md", "operations.md", "architecture.md", "agents.md"):
        body = (DOCS / name).read_text(encoding="utf-8")
        assert len(body) > 500, f"{name} too short to hold moved technical content"
        assert body.lstrip().startswith("#"), f"{name} should be a markdown document"


def test_agents_doc_retains_agno_alignment_substance() -> None:
    """Moved Agents / Agno 对齐 prose must not be truncated away from the repo."""
    body = (DOCS / "agents.md").read_text(encoding="utf-8")
    required = (
        "deep-research-review",
        "csv-quick-analysis",
        "0700",
        "TAIS_ALLOW_UNSAFE_LOCAL_PYTHON",
        "TaskStateUpdated",
        "fail-closed",
        "TAIS_ENABLE_AGNO_TEAM",
        "research-analysis-team",
        "SQLTools",
        "Data Agents",
        "Deep Research",
    )
    missing = [token for token in required if token not in body]
    assert not missing, f"docs/agents.md missing relocated substance: {missing}"


def test_readme_links_to_docs_pages(readme_text: str) -> None:
    for name in (
        "docs/architecture.md",
        "docs/agents.md",
        "docs/hitl.md",
        "docs/workflows.md",
        "docs/operations.md",
        "docs/README.md",
    ):
        assert name in readme_text or f"./{name}" in readme_text, f"README should link {name}"


def test_readme_no_longer_hosts_hitl_or_workflow_deep_dive_headers(readme_text: str) -> None:
    # Deep-dive section titles should live under docs/, not as full ## sections in README
    assert "## 工作流编排技术架构" not in readme_text
    assert "### HITL 人机审批技术架构" not in readme_text
    assert "## 配置与运维" not in readme_text


def test_readme_and_docs_relative_links_resolve(readme_text: str) -> None:
    failures: list[str] = []
    for label, path in _md_local_targets(readme_text, REPO_ROOT):
        if not path.exists():
            failures.append(f"README -> {label} => missing {path}")
    for name in TECH_DOCS:
        text = (DOCS / name).read_text(encoding="utf-8")
        for label, path in _md_local_targets(text, DOCS):
            if not path.exists():
                failures.append(f"docs/{name} -> {label} => missing {path}")
    assert not failures, "broken relative links:\n" + "\n".join(failures)
