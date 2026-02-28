#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRAPER_DIR="$PROJECT_ROOT/ig_scraper"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
LOG_DIR="$SCRAPER_DIR/logs"
LOG_FILE="$LOG_DIR/cron_scraper.log"

mkdir -p "$LOG_DIR"
cd "$PROJECT_ROOT"

export FORCE_RUN="${FORCE_RUN:-1}"
export HEADLESS="${HEADLESS:-1}"

if [[ -x "$VENV_PYTHON" ]]; then
  "$VENV_PYTHON" "$SCRAPER_DIR/main.py" >> "$LOG_FILE" 2>&1
else
  python3 "$SCRAPER_DIR/main.py" >> "$LOG_FILE" 2>&1
fi
