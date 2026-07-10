#!/usr/bin/env bash
# Wrapper script for updating CVE database safely from cron
# Usage: scripts/run_update_cve.sh [args passed to update-cve]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Ensure logs directory exists
LOG_DIR="$PROJECT_DIR/.logs"
RUNTIME_DIR="$PROJECT_DIR/tmp"
mkdir -p "$LOG_DIR" "$RUNTIME_DIR"
LOG_FILE="$LOG_DIR/cron_cve.log"
LOCK_FILE="$RUNTIME_DIR/run_update_cve.lock"

# Use a lock to prevent concurrent runs
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date -Iseconds) - Another update-cve process is already running, exiting" >> "$LOG_FILE"
  exit 0
fi

# Load environment file if present (export variables)
if [ -f "$PROJECT_DIR/.env" ]; then
  # Export variables defined in .env
  set -a
  # shellcheck disable=SC1090
  source "$PROJECT_DIR/.env"
  set +a
fi

# Try runtime options in this order:
# 1) project console script in .venv
# 2) uv project script
# 3) .venv python module execution
# 4) system python module execution
VENV_BIN="$PROJECT_DIR/.venv/bin"
VENV_PY="$VENV_BIN/python"
RUN_CMD=()
if [ -x "$VENV_BIN/update-cve" ]; then
  RUN_CMD=("$VENV_BIN/update-cve")
elif command -v uv >/dev/null 2>&1; then
  RUN_CMD=("uv" "run" "update-cve")
elif [ -x "$VENV_PY" ]; then
  RUN_CMD=("$VENV_PY" "-m" "api.tasks.update_cve")
elif command -v python3 >/dev/null 2>&1; then
  RUN_CMD=("python3" "-m" "api.tasks.update_cve")
elif command -v python >/dev/null 2>&1; then
  RUN_CMD=("python" "-m" "api.tasks.update_cve")
else
  echo "$(date -Iseconds) - ERROR: Neither 'uv' nor 'python' found. Please install one or ensure .venv is set up." >> "$LOG_FILE"
  exit 1
fi

# Log start
echo "$(date -Iseconds) - Starting update-cve ($*)" >> "$LOG_FILE"

# Run the update script. We pass any provided args through.
# Redirect output to LOG_FILE. When executed by cron there's no interactive shell so avoid relying on shell defaults.
echo "$(date -Iseconds) - Will run: ${RUN_CMD[*]} $*" >> "$LOG_FILE"
export AGNO_CVE_UPDATE_LOCK_HELD=1
"${RUN_CMD[@]}" "$@" >> "$LOG_FILE" 2>&1 || {
  echo "$(date -Iseconds) - update-cve exited with non-zero status" >> "$LOG_FILE"
  exit 1
}

# Log completion
echo "$(date -Iseconds) - Completed update-cve" >> "$LOG_FILE"

# Close the flockfd (file descriptor 9) by exiting - the lock will be released automatically
exit 0
