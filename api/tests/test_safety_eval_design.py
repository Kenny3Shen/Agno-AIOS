"""Structural checks for the Safety Eval design doc (docs/safety-eval.md).

These tests gate the design deliverable: industry metrics, Agno API mapping,
Grok 4.5 (xAI) validation path, and phased roadmap — without loading harmful
packs or calling external model APIs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "safety-eval.md"
REGISTRY = REPO_ROOT / "eval_packs" / "registry.yaml"
PACKS_README = REPO_ROOT / "eval_packs" / "README.md"
DOCS_INDEX = REPO_ROOT / "docs" / "README.md"
ROOT_README = REPO_ROOT / "README.md"


@pytest.fixture(scope="module")
def design_text() -> str:
    assert DOC.is_file(), "docs/safety-eval.md must exist"
    text = DOC.read_text(encoding="utf-8")
    assert len(text) > 8000, "safety-eval design should be substantial"
    return text


def test_design_and_registry_artifacts_exist() -> None:
    assert DOC.is_file()
    assert REGISTRY.is_file()
    assert PACKS_README.is_file()
    assert "safety-eval.md" in DOCS_INDEX.read_text(encoding="utf-8")
    assert "safety-eval.md" in ROOT_README.read_text(encoding="utf-8")


def test_metrics_named_with_industry_benchmark_anchors(design_text: str) -> None:
    """Criterion: ASR, refusal, over-refusal + named benchmarks/papers."""
    body = design_text.lower()
    for metric in ("asr", "refusal", "over-refusal", "over_refusal"):
        assert metric in body or metric.replace("_", "-") in body or metric.replace("_", " ") in body

    # Explicit metric section + formulas / definitions
    assert re.search(r"Attack Success Rate|ASR", design_text)
    assert re.search(r"Refusal rate|Refusal", design_text)
    assert re.search(r"[Oo]ver-refusal|Over-refusal", design_text)

    # Named industry / paper anchors (not informal-only)
    for anchor in (
        "HarmBench",
        "StrongREJECT",
        "JailbreakBench",
        "Do-Not-Answer",
        "AdvBench",
    ):
        assert anchor in design_text, f"missing benchmark anchor: {anchor}"

    # Prefer a dedicated anchors subsection
    assert "业界与论文" in design_text or "6.0" in design_text


def test_agno_eval_surface_mapped_to_runner_and_api(design_text: str) -> None:
    """Criterion: Accuracy / AgentAsJudge / Reliability + suite/case/API."""
    for agno_type in (
        "AccuracyEval",
        "AgentAsJudgeEval",
        "ReliabilityEval",
    ):
        assert agno_type in design_text, f"missing Agno type: {agno_type}"

    for field in ("criteria", "threshold", "expected_tool_calls"):
        assert field in design_text

    assert "agent_eval_runner" in design_text
    assert "/api/agent-evals" in design_text
    assert "agno.eval" in design_text or "agno.eval.accuracy" in design_text

    # Runner-backed eval_types strings used by this repo
    for eval_type in ("accuracy", "agent_as_judge", "reliability"):
        assert eval_type in design_text


def test_admin_configured_subject_and_minimal_procedure(design_text: str) -> None:
    """Criterion: a configured subject + concrete validation procedure."""
    assert "Grok 4.5" in design_text
    assert "xAI" in design_text or "xai" in design_text
    assert "grok-4.5" in design_text
    assert "管理员" in design_text
    assert "Settings" in design_text
    assert "YOUR_GROK_CONFIG_ID" in design_text
    assert "xai-grok-4.5" not in design_text
    assert "DEFAULT_MODELS" not in design_text
    assert "工作台内置模型连接" not in design_text

    # Subject vs judge roles
    assert re.search(r"Subject|被测", design_text)
    assert re.search(r"Judge|判定", design_text)
    assert "eval_judge_model_id" in design_text
    assert "active_model_id" in design_text
    assert "Agno 进程默认" in design_text

    # Minimal procedure: suite/case/run path
    assert "design-validation" in design_text or "设计验证" in design_text
    assert "agent_as_judge" in design_text
    assert re.search(r"POST.*agent-evals|/api/agent-evals/suites", design_text)


def test_phased_development_path_recorded(design_text: str) -> None:
    """Criterion: design-only vs MVP vs later is scannable."""
    assert "Phase 0" in design_text or "设计-only" in design_text or "设计交付" in design_text
    assert "Phase 1" in design_text
    assert "Phase 2" in design_text
    # Development path summary table or section
    assert "发展路径" in design_text or "技术细节与发展路径" in design_text


def test_registry_lists_core_packs() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    for pack_id in ("do-not-answer", "strongreject", "soc-custom-v1"):
        assert pack_id in text, f"registry missing pack {pack_id}"
    assert "layer: L1" in text or "L1" in text
    assert "layer: L2" in text or "L2" in text
