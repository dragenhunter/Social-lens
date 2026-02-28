#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${1:-$HOME/social-lens}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"

echo "[1/6] Installing system packages"
sudo apt-get update -y
sudo apt-get install -y git curl wget jq cron build-essential "python${PYTHON_VERSION}" "python${PYTHON_VERSION}-venv" "python${PYTHON_VERSION}-dev"

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repo directory not found: $REPO_DIR"
  echo "Clone your repo first, then rerun: git clone <repo-url> $REPO_DIR"
  exit 1
fi

echo "[2/6] Creating venv"
cd "$REPO_DIR"
"python${PYTHON_VERSION}" -m venv .venv
source .venv/bin/activate

echo "[3/6] Installing Python deps"
pip install --upgrade pip
pip install -r ig_scraper/requirements.txt
playwright install chromium

echo "[4/6] Preparing env file"
if [[ ! -f "$REPO_DIR/.env" ]]; then
  cat > "$REPO_DIR/.env" <<EOF
API_BASE=http://your-api-host:5000
API_USER=your_api_username
API_PASS=your_api_password
API_CLIENT_ID=Lens_App
API_SCOPE=Lens
FORCE_RUN=1
HEADLESS=1
ENABLE_BASELINE_WRITE=0
ENABLE_PROFILE_WRITE=0
ENABLE_POST_HISTORY_WRITE=0
ENABLE_REMOTE_COOLDOWNS=0
EOF
  echo "Created $REPO_DIR/.env (replace placeholder API_* values before running)."
fi

echo "[5/6] Making run script executable"
chmod +x "$REPO_DIR/ig_scraper/scripts/run_scraper.sh"

echo "[6/6] Installing cron job"
CRON_LINE="*/20 * * * * /usr/bin/flock -n /tmp/ig_scraper.lock $REPO_DIR/ig_scraper/scripts/run_scraper.sh"
( crontab -l 2>/dev/null | grep -v 'ig_scraper/scripts/run_scraper.sh' ; echo "$CRON_LINE" ) | crontab -

sudo service cron restart || true

echo "Done. Cron installed:"
crontab -l | grep 'ig_scraper/scripts/run_scraper.sh' || true
