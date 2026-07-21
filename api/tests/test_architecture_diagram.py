"""Structural checks for the shipped TAIS architecture diagram assets."""

from __future__ import annotations

import re
import struct
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SVG_PATH = REPO_ROOT / "docs" / "assets" / "tais-architecture.svg"
PNG_PATH = REPO_ROOT / "docs" / "assets" / "tais-architecture.png"

# Column bodies used for corridor collision checks (from SVG layout).
COLUMNS = (
    ("operator", 62, 364, 212, 674),
    ("presentation", 260, 215, 595, 875),
    ("api", 650, 215, 985, 875),
    ("runtime", 1040, 215, 1375, 875),
    ("data", 1430, 215, 1860, 875),
)


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    # IHDR is first chunk after signature
    length = struct.unpack(">I", data[8:12])[0]
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    assert length >= 13
    return width, height


def _parse_path_points(d: str) -> list[tuple[float, float]]:
    """Parse simple absolute SVG path commands used by the architecture arrows."""
    tokens = re.findall(r"[MmHhVvLl]|-?\d+(?:\.\d+)?", d)
    pts: list[tuple[float, float]] = []
    i = 0
    x = y = 0.0
    while i < len(tokens):
        t = tokens[i]
        if t in "MmLl":
            x, y = float(tokens[i + 1]), float(tokens[i + 2])
            pts.append((x, y))
            i += 3
        elif t == "H":
            x = float(tokens[i + 1])
            pts.append((x, y))
            i += 2
        elif t == "V":
            y = float(tokens[i + 1])
            pts.append((x, y))
            i += 2
        elif t == "h":
            x += float(tokens[i + 1])
            pts.append((x, y))
            i += 2
        elif t == "v":
            y += float(tokens[i + 1])
            pts.append((x, y))
            i += 2
        else:
            # numeric without command — treat as absolute L pair if after M
            if re.fullmatch(r"-?\d+(?:\.\d+)?", t):
                x, y = float(t), float(tokens[i + 1])
                pts.append((x, y))
                i += 2
            else:
                raise AssertionError(f"unsupported path token {t!r} in {d!r}")
    return pts


def _sample_polyline(pts: list[tuple[float, float]], step: float = 4.0) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        n = max(1, int(dist / step))
        for i in range(n + 1):
            t = i / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def _deep_interior_hits(
    pts: list[tuple[float, float]],
    *,
    margin: float = 14.0,
) -> list[tuple[float, float, str]]:
    hits: list[tuple[float, float, str]] = []
    for x, y in _sample_polyline(pts):
        for name, x0, y0, x1, y1 in COLUMNS:
            if x0 + margin < x < x1 - margin and y0 + margin < y < y1 - margin:
                hits.append((x, y, name))
                break
    return hits


@pytest.fixture(scope="module")
def svg_text() -> str:
    assert SVG_PATH.is_file(), f"missing diagram source {SVG_PATH}"
    return SVG_PATH.read_text(encoding="utf-8")


def test_architecture_assets_exist_and_png_is_1920x1080(svg_text: str) -> None:
    assert PNG_PATH.is_file(), f"missing diagram export {PNG_PATH}"
    width, height = _png_size(PNG_PATH)
    assert (width, height) == (1920, 1080)
    assert 'viewBox="0 0 1920 1080"' in svg_text
    assert 'width="1920"' in svg_text and 'height="1080"' in svg_text


def test_architecture_layer_labels_present(svg_text: str) -> None:
    required = [
        "安全运营人员",
        "PRESENTATION",
        "APPLICATION API",
        "AI ORCHESTRATION",
        "DATA &amp; INTEGRATIONS",
        "HTTPS",
        "JWT + SSE",
        "Jobs 队列",
        "会话 · Trace · 审批",
        "工具 / 检索",
    ]
    missing = [label for label in required if label not in svg_text]
    assert not missing, f"missing diagram labels: {missing}"


def test_architecture_arrow_markers_are_compact(svg_text: str) -> None:
    widths = [int(m) for m in re.findall(r'markerWidth="(\d+)"', svg_text)]
    heights = [int(m) for m in re.findall(r'markerHeight="(\d+)"', svg_text)]
    assert widths, "expected arrow markers"
    assert all(w <= 8 for w in widths), widths
    assert all(h <= 8 for h in heights), heights

    main_strokes = re.findall(
        r'stroke-width="([0-9.]+)"\s+marker-end="url\(#arrow(?:Cyan|Purple|Green)\)"',
        svg_text,
    )
    # Four main L→R connectors use stroke-width 2
    assert len(main_strokes) >= 4
    assert all(float(s) <= 2.0 for s in main_strokes), main_strokes


def test_architecture_secondary_paths_avoid_column_interiors(svg_text: str) -> None:
    # Jobs (amber) and observability (green) secondary corridors
    jobs_match = re.search(
        r'd="(M985[^"]+)"\s+[^>]*marker-end="url\(#arrowAmber\)"',
        svg_text,
    )
    obs_match = re.search(
        r'd="(M1645[^"]+)"\s+[^>]*marker-end="url\(#arrowGreen\)"',
        svg_text,
    )
    assert jobs_match, "Jobs amber path missing"
    assert obs_match, "Observability green path missing"

    jobs_hits = _deep_interior_hits(_parse_path_points(jobs_match.group(1)))
    obs_hits = _deep_interior_hits(_parse_path_points(obs_match.group(1)))
    assert not jobs_hits, f"Jobs path cuts through columns: {jobs_hits[:5]}"
    assert not obs_hits, f"Observability path cuts through columns: {obs_hits[:5]}"


def test_architecture_main_lane_is_mid_height(svg_text: str) -> None:
    mains = re.findall(r'd="(M\d+ 530H\d+)"\s+stroke="[^"]+"\s+stroke-width="2"', svg_text)
    assert len(mains) == 4, mains
    for d in mains:
        pts = _parse_path_points(d)
        assert all(abs(y - 530) < 0.01 for _, y in pts)
