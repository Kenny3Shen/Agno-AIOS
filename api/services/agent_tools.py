"""Built-in toolkits for specialist Agents (data analysis / deep research).

Security-operations keeps MCP + Local Skills; these helpers only attach
Agno-native toolkits with safe defaults suitable for a multi-tenant workbench.
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from loguru import logger


@lru_cache(maxsize=1)
def analysis_work_dir() -> Path:
    """Shared sandbox directory for analysis File/Python tools."""
    root = Path(tempfile.gettempdir()) / "tais-agent-python"
    root.mkdir(parents=True, exist_ok=True)
    return root


# Back-compat alias used by older tests/imports.
_analysis_work_dir = analysis_work_dir


def profile_uses_analysis_sandbox(profile: dict[str, Any] | None) -> bool:
    """True when profile mounts File/CSV/Python sandboxed toolkits."""
    if not profile:
        return False
    names = {str(n).strip().lower() for n in (profile.get("builtin_tools") or ())}
    return bool(names & {"file", "csv", "python", "sql"})


def stage_media_into_analysis_dir(files: Any) -> list[Path]:
    """Write Agno File media (or filepath-like objects) into the analysis sandbox.

    Returns staged absolute paths. Safe to call with empty/None. Filenames are
    basename-only; collisions get a numeric suffix.
    """
    if not files:
        return []
    base = analysis_work_dir()
    staged: list[Path] = []
    for media in files:
        if media is None:
            continue
        raw_name = (
            getattr(media, "filename", None)
            or getattr(media, "name", None)
            or "upload.bin"
        )
        safe = Path(str(raw_name)).name.strip() or "upload.bin"
        # Disallow path tricks and empty-looking names.
        if safe in {".", ".."} or "/" in safe or "\\" in safe:
            safe = "upload.bin"
        dest = base / safe
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            n = 1
            while dest.exists():
                dest = base / f"{stem}_{n}{suffix}"
                n += 1

        content = getattr(media, "content", None)
        if content is None:
            filepath = getattr(media, "filepath", None)
            if filepath:
                try:
                    content = Path(filepath).read_bytes()
                except OSError as exc:
                    logger.warning("Could not stage media from path {}: {}", filepath, exc)
                    continue
            else:
                logger.debug("Skip staging media without content/filepath: {}", safe)
                continue
        if isinstance(content, str):
            content = content.encode("utf-8")
        if not isinstance(content, (bytes, bytearray)):
            logger.debug("Skip staging media with non-bytes content: {}", safe)
            continue
        try:
            dest.write_bytes(bytes(content))
        except OSError as exc:
            logger.warning("Failed to stage {}: {}", safe, exc)
            continue
        staged.append(dest)
        logger.info("Staged analysis media -> {}", dest)
    return staged


def build_tools_for_profile(profile: dict[str, Any]) -> list[Any]:
    """Instantiate toolkit list declared on an agent profile."""
    tools: list[Any] = []
    for name in profile.get("builtin_tools") or ():
        key = str(name).strip().lower()
        builder = _BUILDERS.get(key)
        if builder is None:
            logger.warning("Unknown builtin tool toolkit: {}", key)
            continue
        try:
            toolkit = builder()
        except Exception as exc:  # noqa: BLE001 — soft-fail optional toolkits
            logger.warning("Failed to load toolkit {}: {}", key, exc)
            continue
        if toolkit is not None:
            tools.append(toolkit)
    # Agno rejects duplicate tool names on one Agent.
    names = {type(t).__name__ for t in tools}
    if "PythonTools" in names and "FileTools" in names:
        for toolkit in tools:
            if type(toolkit).__name__ == "PythonTools":
                _strip_python_tools(
                    toolkit,
                    {"pip_install_package", "uv_pip_install_package", "read_file", "list_files"},
                )
    else:
        for toolkit in tools:
            if type(toolkit).__name__ == "PythonTools":
                _strip_python_tools(
                    toolkit,
                    {"pip_install_package", "uv_pip_install_package"},
                )
    return tools


def _build_calculator() -> Any:
    from agno.tools.calculator import CalculatorTools

    return CalculatorTools()


def _build_reasoning() -> Any:
    from agno.tools.reasoning import ReasoningTools

    return ReasoningTools(
        enable_think=True,
        enable_analyze=True,
        add_instructions=True,
    )


def _build_website() -> Any:
    from agno.tools.website import WebsiteTools

    return WebsiteTools()


def _build_web_search() -> Any:
    """Optional DuckDuckGo/WebSearch toolkit (requires ``ddgs`` / duckduckgo-search).

    Soft-fails to None when the optional dependency is missing so deep-research
    still runs on Live Search + WebsiteTools alone.
    """
    try:
        from agno.tools.duckduckgo import DuckDuckGoTools
    except Exception as exc:  # noqa: BLE001
        logger.warning("DuckDuckGoTools unavailable: {}", exc)
        return None
    try:
        return DuckDuckGoTools(
            enable_search=True,
            enable_news=True,
            fixed_max_results=8,
            timeout=12,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("DuckDuckGoTools init failed: {}", exc)
        return None


def _build_file() -> Any:
    """Read/write analysis artifacts inside the shared sandbox (no delete)."""
    from agno.tools.file import FileTools

    return FileTools(
        base_dir=analysis_work_dir(),
        enable_save_file=True,
        enable_read_file=True,
        enable_delete_file=False,
        enable_list_files=True,
        enable_search_files=True,
        enable_read_file_chunk=True,
        enable_replace_file_chunk=False,
        enable_search_content=False,
        expose_base_directory=False,
    )


def _build_csv() -> Any:
    """CSV helpers over files already present in the analysis sandbox.

    SQL ``query_csv_file`` requires optional ``duckdb``; without it the toolkit
    still supports list/read/columns. Rebuilds the file list from the sandbox
    on each Agent/Team construction so Chat-staged uploads are visible.
    """
    from agno.tools.csv_toolkit import CsvTools

    base = analysis_work_dir()
    # Include nested uploads (if any) while staying inside the sandbox.
    csvs: list[Path] = sorted({*base.glob("*.csv"), *base.glob("**/*.csv")})
    # De-dupe by resolved path order-preserving.
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in csvs:
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return CsvTools(
        csvs=list(unique) if unique else None,
        row_limit=500,
        enable_read_csv_file=True,
        enable_list_csv_files=True,
        enable_get_columns=True,
        # Soft: enable only when duckdb importable (CsvTools handles ImportError).
        enable_query_csv_file=True,
    )


def _python_safe_globals() -> dict[str, Any]:
    safe_globals: dict[str, Any] = {
        "__builtins__": __builtins__,
        "Path": Path,
    }
    try:
        import polars as pl

        safe_globals["pl"] = pl
        safe_globals["polars"] = pl
    except Exception:  # noqa: BLE001
        logger.debug("polars unavailable for PythonTools safe globals")

    for mod_name in ("json", "math", "statistics", "csv", "re", "datetime", "collections"):
        try:
            safe_globals[mod_name] = __import__(mod_name)
        except Exception:  # noqa: BLE001
            pass
    return safe_globals


def _strip_python_tools(tools: Any, drop_names: set[str]) -> Any:
    """Remove selected PythonTools entrypoints in-place."""
    tool_list = getattr(tools, "tools", None)
    if isinstance(tool_list, list):
        tools.tools = [
            fn
            for fn in tool_list
            if getattr(fn, "__name__", "") not in drop_names
        ]
    functions = getattr(tools, "functions", None)
    if isinstance(functions, dict):
        for key in list(functions.keys()):
            entry = functions.get(key)
            name = getattr(entry, "name", None) or key
            entrypoint = getattr(entry, "entrypoint", None)
            entry_name = getattr(entrypoint, "__name__", "") if entrypoint else ""
            if str(name) in drop_names or entry_name in drop_names:
                functions.pop(key, None)
    return tools


def _build_python() -> Any:
    from agno.tools.python import PythonTools

    return PythonTools(
        base_dir=analysis_work_dir(),
        safe_globals=_python_safe_globals(),
        restrict_to_base_dir=True,
    )



def _build_sql() -> Any:
    """Optional read-only SQL toolkit (Agno data-agent pattern).

    Set ``TAIS_DATA_SQL_URL`` to a warehouse connection (prefer a DB role with
    SELECT-only grants). Soft-fails when unset so local CSV/Python analysis still works.
    """
    import os

    db_url = (os.getenv("TAIS_DATA_SQL_URL") or os.getenv("TAIS_ANALYTICS_DB_URL") or "").strip()
    if not db_url:
        logger.debug("SQLTools skipped: TAIS_DATA_SQL_URL not set")
        return None
    try:
        from agno.tools.sql import SQLTools
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQLTools import failed: {}", exc)
        return None
    try:
        return SQLTools(
            db_url=db_url,
            enable_list_tables=True,
            enable_describe_table=True,
            enable_run_sql_query=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQLTools init failed: {}", exc)
        return None


_BUILDERS = {
    "calculator": _build_calculator,
    "reasoning": _build_reasoning,
    "website": _build_website,
    "web_search": _build_web_search,
    "python": _build_python,
    "file": _build_file,
    "csv": _build_csv,
    "sql": _build_sql,
}
