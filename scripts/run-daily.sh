#!/usr/bin/env bash
# Unattended daily wrapper — sources .env, resolves absolute paths, appends to log.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${FRIGATE_DATA_DIR:-$HOME/.local/share/frigate-scanner}"
LOG_DIR="${FRIGATE_LOG_DIR:-$HOME/Library/Logs/frigate-scanner}"
DB_PATH="$DATA_DIR/frigate.db"

# Ensure uv is on PATH for both Homebrew locations
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Load SHODAN_API_KEY and any other vars from .env if present
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_DIR/.env"
    set +a
fi

mkdir -p "$DATA_DIR" "$LOG_DIR"

{
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    uv run --project "$PROJECT_DIR" \
        "$PROJECT_DIR/src/backend/run.py" run \
        --db "$DB_PATH" \
        --out-dir "$DATA_DIR"
    echo
} >> "$LOG_DIR/scanner.log" 2>&1
