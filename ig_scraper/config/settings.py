import os

BASE_URL = "https://www.instagram.com"
HEADLESS = os.getenv("HEADLESS", "1").strip().lower() in {"1", "true", "yes"}

MIN_DELAY = 1.2
MAX_DELAY = 4.0

ACTION_LIMITS = {
	"scrolls": 40,
	"clicks": 25,
	"opens": 15
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
