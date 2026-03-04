import os
from pathlib import Path

from dotenv import load_dotenv


_SETTINGS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _SETTINGS_FILE.parents[1]  # ig_scraper/
_WORKSPACE_ROOT = _SETTINGS_FILE.parents[2]  # Social lens/

# Load .env early so constants below read the intended values.
# Prefer explicit environment variables if already set in shell/service.
load_dotenv(_WORKSPACE_ROOT / ".env", override=False)
load_dotenv(_PROJECT_ROOT / ".env", override=False)

BASE_URL = "https://www.instagram.com"
HEADLESS = os.getenv("HEADLESS", "1").strip().lower() in {"1", "true", "yes"}

MIN_DELAY = 1.2
MAX_DELAY = 4.0

ACTION_LIMITS = {
	"scrolls": int(os.getenv("BUDGET_SCROLLS", "0") or "0"),
	"clicks": int(os.getenv("BUDGET_CLICKS", "0") or "0"),
	"opens": int(os.getenv("BUDGET_OPENS", "0") or "0")
}

ACTIVE_HOURS = (
	int(os.getenv("ACTIVE_HOURS_START", "9")),
	int(os.getenv("ACTIVE_HOURS_END", "24")),
)
MAX_WORKERS = max(1, int(os.getenv("MAX_WORKERS", "2")))
# If True, the scraper will attempt to load more comments by clicking
# "View all comments" / "Load more comments" buttons when scraping posts.
# Enabling deep comment loading increases runtime and interaction volume.
DEEP_COMMENT_LOADING = False

# Optional API writes currently disabled by default until backend endpoints are finalized.
ENABLE_BASELINE_WRITE = os.getenv("ENABLE_BASELINE_WRITE", "0").strip().lower() in {"1", "true", "yes"}
ENABLE_PROFILE_WRITE = os.getenv("ENABLE_PROFILE_WRITE", "0").strip().lower() in {"1", "true", "yes"}
ENABLE_POST_HISTORY_WRITE = os.getenv("ENABLE_POST_HISTORY_WRITE", "0").strip().lower() in {"1", "true", "yes"}

# Disable remote cooldown API calls by default because endpoint currently returns 404.
ENABLE_REMOTE_COOLDOWNS = os.getenv("ENABLE_REMOTE_COOLDOWNS", "0").strip().lower() in {"1", "true", "yes"}
