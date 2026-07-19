"""Built-in toolkits for specialist Agents (data analysis / deep research).

Analysis files are deliberately scoped to one live run.  A directory boundary
is useful for FileTools/CsvTools, but it is *not* a Python process sandbox:
Agno's local ``PythonTools`` can execute arbitrary Python.  Local Python is
therefore disabled by default and never enabled in production.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

from loguru import logger

from api.config import get_settings, is_production_environment


class AnalysisWorkspaceRequiredError(RuntimeError):
    """Raised when analysis tools are constructed outside a live run scope."""


@dataclass(frozen=True)
class AnalysisWorkspace:
    """Private, short-lived filesystem boundary for one analysis run.

    ``path`` is only a File/Csv path boundary.  It must not be described as a
    sandbox for arbitrary Python execution; see ``local_python_execution_enabled``.
    """

    path: Path
    run_id: str


_analysis_workspace: ContextVar[AnalysisWorkspace | None] = ContextVar(
    "tais_analysis_workspace", default=None
)
_ANALYSIS_TOOLKIT_NAMES = frozenset({"file", "csv", "python"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _safe_run_label(value: str | None) -> str:
    """Return a non-sensitive mkdtemp prefix component.

    The UUID still guarantees uniqueness; the label only helps operators match
    cleanup logs to a run without allowing a caller-controlled pathname.
    """
    raw = str(value or "run")
    label = "".join(char for char in raw if char.isascii() and char.isalnum())
    return (label[:24] or "run")


def create_analysis_workspace(run_id: str | None = None) -> AnalysisWorkspace:
    """Create an isolated 0700 workspace for a single live run.

    ``mkdtemp`` creates a unique directory below the system temporary root.
    Explicit chmod also makes the privacy guarantee independent of process umask.
    """
    resolved_run_id = str(run_id or uuid4())
    prefix = f"tais-analysis-{_safe_run_label(resolved_run_id)}-"
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        path.chmod(0o700)
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        shutil.rmtree(path, ignore_errors=True)
        raise RuntimeError("Could not secure analysis workspace permissions") from exc
    if mode != 0o700:
        shutil.rmtree(path, ignore_errors=True)
        raise RuntimeError(f"Analysis workspace must be mode 0700, got {mode:04o}")
    logger.debug("Created isolated analysis workspace for run={}", resolved_run_id)
    return AnalysisWorkspace(path=path, run_id=resolved_run_id)


def _make_workspace_entry_removable(
    operation: Callable[..., Any],
    path: str,
    _exc_info: tuple[type[BaseException], BaseException, object],
) -> None:
    """Best-effort rmtree repair for artifacts made readonly by tool code."""
    candidate = Path(path)
    try:
        # Never chmod through a symlink created by untrusted/local tool code.
        if candidate.is_symlink():
            candidate.unlink()
            return
        os.chmod(candidate, stat.S_IRWXU)
        operation(path)
    except OSError:
        # ``cleanup_analysis_workspace`` logs the unresolved root afterwards.
        return


def cleanup_analysis_workspace(workspace: AnalysisWorkspace) -> None:
    """Remove every staged upload and generated artifact for a completed run."""
    try:
        shutil.rmtree(workspace.path, onerror=_make_workspace_entry_removable)
    except FileNotFoundError:
        return
    except OSError as exc:
        # Do not leave an exception in a generator ``finally`` that masks the
        # original model/tool error.  A retryable operational log is safer.
        logger.warning(
            "Failed to remove isolated analysis workspace for run={}: {}",
            workspace.run_id,
            exc,
        )
    else:
        logger.debug("Removed isolated analysis workspace for run={}", workspace.run_id)


@contextmanager
def analysis_workspace_context(run_id: str | None = None) -> Iterator[AnalysisWorkspace]:
    """Bind one workspace to the current async task and always clean it up.

    Nested Chat/Team/Workflow helpers reuse the caller's workspace rather than
    creating a second directory.  ``ContextVar`` values propagate to child
    tasks, including Team's concurrent member runs.
    """
    current = _analysis_workspace.get()
    if current is not None:
        yield current
        return
    workspace = create_analysis_workspace(run_id)
    token: Token[AnalysisWorkspace | None] = _analysis_workspace.set(workspace)
    try:
        yield workspace
    finally:
        _analysis_workspace.reset(token)
        cleanup_analysis_workspace(workspace)


def current_analysis_workspace() -> AnalysisWorkspace | None:
    """Return the workspace bound to this run, if any."""
    return _analysis_workspace.get()


def _bound_workspace_path(expected: AnalysisWorkspace | None = None) -> Path:
    """Return the active workspace path and reject cross-context injection."""
    current = current_analysis_workspace()
    if current is None:
        raise AnalysisWorkspaceRequiredError(
            "Analysis File/Csv/Python tools require an active run workspace"
        )
    if expected is not None and expected != current:
        raise AnalysisWorkspaceRequiredError(
            "Analysis tools may only use the workspace bound to the current run"
        )
    return current.path


def analysis_work_dir() -> Path:
    """Return the current run's workspace, never a process-wide fallback."""
    return _bound_workspace_path()


def _analysis_tool_base_dir(base_dir: Path | None = None) -> Path:
    """Resolve a toolkit base dir without allowing a caller to escape a run."""
    current = _bound_workspace_path()
    if base_dir is not None and base_dir != current:
        raise AnalysisWorkspaceRequiredError(
            "Analysis tool base_dir must be the workspace bound to the current run"
        )
    return current


def _truthy_environment(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in _TRUE_VALUES


def local_python_execution_enabled() -> bool:
    """Whether the explicitly unsafe local Python escape hatch is allowed.

    A directory restriction does not stop ``PythonTools`` from reading host
    files, environment variables, or making network calls.  Production always
    fails closed; development/test requires a conscious opt-in via
    ``TAIS_ALLOW_UNSAFE_LOCAL_PYTHON=1``.  A real container/VM/E2B integration
    can be added separately, but must not silently fall back to local Python.
    """
    try:
        environment = str(get_settings().environment)
    except Exception:  # pragma: no cover - defensive for partial startup
        environment = os.getenv("ENVIRONMENT", "development")
    if is_production_environment(environment):
        return False
    return _truthy_environment("TAIS_ALLOW_UNSAFE_LOCAL_PYTHON")


def profile_uses_analysis_sandbox(profile: dict[str, Any] | None) -> bool:
    """True when profile mounts run-scoped File/CSV/Python toolkits."""
    if not profile:
        return False
    names = {str(n).strip().lower() for n in (profile.get("builtin_tools") or ())}
    return bool(names & _ANALYSIS_TOOLKIT_NAMES)


def stage_media_into_analysis_dir(
    files: Any,
    *,
    workspace: AnalysisWorkspace | None = None,
) -> list[Path]:
    """Write Agno media into this run's isolated analysis workspace.

    Returns staged absolute paths. Safe to call with empty/None. Filenames are
    basename-only; collisions get a numeric suffix.  Callers must either bind
    ``analysis_workspace_context`` (an explicit workspace must be the currently
    bound one), so uploads can never bleed into a subsequent user's run.
    """
    if not files:
        return []
    base = _bound_workspace_path(workspace)
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
        logger.debug("Staged analysis media into isolated workspace: {}", dest.name)
    return staged


def build_tools_for_profile(
    profile: dict[str, Any],
    *,
    workspace: AnalysisWorkspace | None = None,
) -> list[Any]:
    """Instantiate toolkit list declared on an agent profile.

    File/Csv/Python toolkits require a run-bound workspace.  The function
    intentionally raises outside one instead of recreating the former global
    directory.  Non-analysis toolkits remain usable in catalog/admin contexts.
    """
    tools: list[Any] = []
    for name in profile.get("builtin_tools") or ():
        key = str(name).strip().lower()
        builder = _BUILDERS.get(key)
        if builder is None:
            logger.warning("Unknown builtin tool toolkit: {}", key)
            continue
        try:
            if key in _ANALYSIS_TOOLKIT_NAMES:
                base = _bound_workspace_path(workspace)
                toolkit = builder(base)
            else:
                toolkit = builder()
        except AnalysisWorkspaceRequiredError:
            # This is a programming boundary, not an optional import failure.
            # Returning tools without a workspace would re-introduce cross-run
            # storage, so make callers bind a concrete run scope.
            raise
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
    # Prefer explicit backends that return results in constrained networks.
    # Default ``duckduckgo`` backend often yields empty text results; ``api``/``html``
    # are more reliable. Soft-fail entirely if none construct.
    last_exc: Exception | None = None
    for backend in ("api", "html", "lite", None):
        try:
            kwargs: dict[str, Any] = {
                "enable_search": True,
                "enable_news": True,
                "fixed_max_results": 8,
                "timeout": 15,
            }
            if backend is not None:
                kwargs["backend"] = backend
            return DuckDuckGoTools(**kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
    logger.warning("DuckDuckGoTools init failed: {}", last_exc)
    return None


def _build_file(base_dir: Path | None = None) -> Any:
    """Read/write artifacts in one run workspace (no delete)."""
    from agno.tools.file import FileTools

    workspace_dir = _analysis_tool_base_dir(base_dir)
    return FileTools(
        base_dir=workspace_dir,
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


def _build_csv(base_dir: Path | None = None) -> Any:
    """CSV helpers over files already present in this run workspace.

    List/read/columns only — SQL is provided by Agno ``SQLTools`` via
    ``TAIS_DATA_SQL_URL`` (no DuckDB). Rebuilds the file list from the sandbox
    on each Agent/Team construction so only this run's staged uploads are
    visible.
    """
    from agno.tools.csv_toolkit import CsvTools

    base = _analysis_tool_base_dir(base_dir)
    # Include nested uploads (if any) while staying inside the sandbox.
    csvs: list[Path] = sorted({*base.glob("*.csv"), *base.glob("**/*.csv")})
    # Agno CsvTools matches by stem only; keep one path per stem (prefer shallower
    # then newer mtime) so list/read stay consistent.
    by_stem: dict[str, Path] = {}
    for path in csvs:
        stem = path.stem
        prev = by_stem.get(stem)
        if prev is None:
            by_stem[stem] = path
            continue
        # Prefer files directly in sandbox root over nested duplicates.
        prev_depth = len(prev.relative_to(base).parts)
        cur_depth = len(path.relative_to(base).parts)
        if cur_depth < prev_depth:
            by_stem[stem] = path
        elif cur_depth == prev_depth:
            try:
                if path.stat().st_mtime >= prev.stat().st_mtime:
                    by_stem[stem] = path
            except OSError:
                by_stem[stem] = path
    unique = sorted(by_stem.values(), key=lambda p: p.name.lower())
    return CsvTools(
        csvs=list(unique) if unique else None,
        row_limit=500,
        enable_read_csv_file=True,
        enable_list_csv_files=True,
        enable_get_columns=True,
        # Warehouse SQL uses SQLTools (TAIS_DATA_SQL_URL), not DuckDB/CsvTools.
        enable_query_csv_file=False,
    )


def _unsafe_local_python_globals() -> dict[str, Any]:
    """Convenience globals for the explicitly opted-in local Python mode.

    This is intentionally not called ``safe``: Python's builtin import/open
    capabilities mean this cannot provide a security boundary.  It only keeps
    common dataframe utilities ergonomic for trusted development use.
    """
    globals_for_trusted_dev: dict[str, Any] = {
        "__builtins__": __builtins__,
        "Path": Path,
    }
    try:
        import polars as pl

        globals_for_trusted_dev["pl"] = pl
        globals_for_trusted_dev["polars"] = pl
    except Exception:  # noqa: BLE001
        logger.debug("polars unavailable for PythonTools safe globals")

    for mod_name in ("json", "math", "statistics", "csv", "re", "datetime", "collections"):
        try:
            globals_for_trusted_dev[mod_name] = __import__(mod_name)
        except Exception:  # noqa: BLE001
            pass
    return globals_for_trusted_dev


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


def _build_python(base_dir: Path | None = None) -> Any:
    """Build local Python only behind the explicit development escape hatch.

    ``restrict_to_base_dir`` confines PythonTools' helper file operations, not
    the executed Python process.  The production decision is intentionally
    evaluated here as a second fail-closed gate even if a caller invokes this
    private builder directly.
    """
    if not local_python_execution_enabled():
        logger.info(
            "Local PythonTools omitted (set TAIS_ALLOW_UNSAFE_LOCAL_PYTHON=1 "
            "only for trusted non-production development)"
        )
        return None
    from agno.tools.python import PythonTools

    logger.warning(
        "Enabling unsafe local PythonTools for trusted development; this is not "
        "a process sandbox"
    )
    workspace_dir = _analysis_tool_base_dir(base_dir)
    return PythonTools(
        base_dir=workspace_dir,
        safe_globals=_unsafe_local_python_globals(),
        restrict_to_base_dir=True,
    )



def _build_sql() -> Any:
    """Optional read-only warehouse SQL via Agno ``SQLTools`` (no DuckDB).

    Set ``TAIS_DATA_SQL_URL`` (or ``TAIS_ANALYTICS_DB_URL``) to a SQLAlchemy URL
    with SELECT-only grants. Soft-fails when unset so local CSV/Python analysis
    still works through File/Csv/Python tools.
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


_BUILDERS: dict[str, Callable[..., Any]] = {
    "calculator": _build_calculator,
    "reasoning": _build_reasoning,
    "website": _build_website,
    "web_search": _build_web_search,
    "python": _build_python,
    "file": _build_file,
    "csv": _build_csv,
    "sql": _build_sql,
}
