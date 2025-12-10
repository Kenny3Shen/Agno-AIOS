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

# Make sure we use the uv binary inside the virtualenv if available
VENV_UV="$SCRIPT_DIR/.venv/bin/uv"
if [ -x "$VENV_UV" ]; then
  UV_CMD="$VENV_UV"
else
  # fallback to global uv if present
  if command -v uv >/dev/null 2>&1; then
    UV_CMD="uv"
  else
    echo "$(date -Iseconds) - ERROR: 'uv' not found. Please install uv or create a venv with uv present." >> "$LOG_FILE"
    exit 1
  fi
fi

# Log start
echo "$(date -Iseconds) - Starting update_cve.py ($*)" >> "$LOG_FILE"

# Run the update script. We pass any provided args through.
# Redirect output to LOG_FILE. Use bash -lc to ensure environment variables and `uv` are interpreted properly.
# When executed by cron there's no interactive shell, so we avoid relying on shell defaults.
$UV_CMD run update_cve.py "$@" >> "$LOG_FILE" 2>&1 || {
  echo "$(date -Iseconds) - update_cve.py exited with non-zero status" >> "$LOG_FILE"
  exit 1
}

# Log completion
echo "$(date -Iseconds) - Completed update_cve.py" >> "$LOG_FILE"

# Close the flockfd (file descriptor 9) by exiting - the lock will be released automatically
exit 0
