#!/usr/bin/env bash
# Wrapper script for updating CVE database safely from cron
# Usage: run_update_cve.sh [args passed to update_cve.py]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure logs directory exists
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/cron_cve.log"
LOCK_FILE="$SCRIPT_DIR/.run_update_cve.lock"

# Use a lock to prevent concurrent runs
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date -Iseconds) - Another update_cve process is already running, exiting" >> "$LOG_FILE"
  exit 0
fi

# Load environment file if present (export variables)
if [ -f "$SCRIPT_DIR/.env" ]; then
  # Export variables defined in .env
  set -a
  # shellcheck disable=SC1090
  source "$SCRIPT_DIR/.env"
  set +a
fi

# Try runtime options in this order:
# 1) .venv/bin/uv
# 2) .venv/bin/python
# 3) system uv
# 4) system python
VENV_UV="$SCRIPT_DIR/.venv/bin/uv"
VENV_PY="$SCRIPT_DIR/.venv/bin/python"
RUN_CMD=()
if [ -x "$VENV_UV" ]; then
  RUN_CMD=("$VENV_UV" "run" "update_cve.py")
elif [ -x "$VENV_PY" ]; then
  RUN_CMD=("$VENV_PY" "update_cve.py")
elif command -v uv >/dev/null 2>&1; then
  RUN_CMD=("uv" "run" "update_cve.py")
elif command -v python >/dev/null 2>&1; then
  RUN_CMD=("python" "update_cve.py")
else
  echo "$(date -Iseconds) - ERROR: Neither 'uv' nor 'python' found. Please install one or ensure .venv is set up." >> "$LOG_FILE"
  exit 1
fi

# Log start
echo "$(date -Iseconds) - Starting update_cve.py ($*)" >> "$LOG_FILE"

# Run the update script. We pass any provided args through.
# Redirect output to LOG_FILE. When executed by cron there's no interactive shell so avoid relying on shell defaults.
echo "$(date -Iseconds) - Will run: ${RUN_CMD[*]} $*" >> "$LOG_FILE"
"${RUN_CMD[@]}" "$@" >> "$LOG_FILE" 2>&1 || {
  echo "$(date -Iseconds) - update_cve.py exited with non-zero status" >> "$LOG_FILE"
  exit 1
}

# Log completion
echo "$(date -Iseconds) - Completed update_cve.py" >> "$LOG_FILE"

# Close the flockfd (file descriptor 9) by exiting - the lock will be released automatically
exit 0
