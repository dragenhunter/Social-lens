# Ubuntu VPS Deployment + Cron

## What this setup does
- Runs scraper with API auth and source-driven targets.
- Uses cron with `flock` so runs never overlap.
- Next run starts only after previous full cycle (all scraper accounts + assigned targets) has finished.
- Scrapes only **new** posts when `sourceId` is available.

## 1) Clone repo on VPS
```bash
git clone <your-repo-url> ~/social-lens
cd ~/social-lens
```

## 2) Run auto setup
```bash
chmod +x ig_scraper/deploy/ubuntu/setup_vps.sh
ig_scraper/deploy/ubuntu/setup_vps.sh ~/social-lens
```

This installs Python + Chromium, creates `.venv`, installs requirements, writes `.env`, and installs cron.

Update `.env` immediately after setup:
- Set real `API_BASE`, `API_USER`, and `API_PASS` values.
- Set Instagram accounts (`IG_ACCOUNT_*_USERNAME` / `IG_ACCOUNT_*_PASSWORD`) in `ig_scraper/config/accounts.json` or map placeholders via env.
- Ensure `INSTAGRAM_PLATFORM_IDS=4`.
- Keep `SCRAPE_LOOKBACK_HOURS=6` (or adjust as needed).
- Keep `.env` private (already ignored by git).

## 3) Verify cron
```bash
crontab -l
```
Expected entry:
```cron
*/20 * * * * /usr/bin/flock -n /tmp/ig_scraper.lock /home/<user>/social-lens/ig_scraper/scripts/run_scraper.sh
```

## 4) Watch logs
```bash
tail -f ~/social-lens/ig_scraper/logs/cron_scraper.log
```

Expected runtime behavior:
- Loads Instagram sources from API platform `4`.
- Scrapes profile posts and writes only posts from the last `SCRAPE_LOOKBACK_HOURS`.
- Skips already-existing posts via API duplicate check.

## 5) Optional: run manually once
```bash
cd ~/social-lens
FORCE_RUN=1 ./.venv/bin/python ig_scraper/main.py
```

## 6) Recommended production `.env` baseline
```dotenv
API_BASE=http://your-api-host:5000
API_USER=your_api_username
API_PASS=your_api_password
API_CLIENT_ID=Lens_App
API_SCOPE=Lens

FORCE_RUN=1
HEADLESS=1
MAX_WORKERS=2
STRICT_SERIAL_ACCOUNTS=1

INSTAGRAM_PLATFORM_IDS=4
SOURCE_SCAN_LIMIT=0
SCRAPE_TARGET_LIMIT=0
SCRAPE_LOOKBACK_HOURS=6
PROFILE_POST_IDLE_SCROLLS=3

BUDGET_SCROLLS=0
BUDGET_CLICKS=0
BUDGET_OPENS=0

ENABLE_BASELINE_WRITE=0
ENABLE_PROFILE_WRITE=0
ENABLE_POST_HISTORY_WRITE=0
ENABLE_REMOTE_COOLDOWNS=0
```

## Current disabled API writes (by design)
These are disabled by default until endpoints are finalized:
- `ENABLE_BASELINE_WRITE=0`
- `ENABLE_PROFILE_WRITE=0`
- `ENABLE_POST_HISTORY_WRITE=0`
- `ENABLE_REMOTE_COOLDOWNS=0`

Post persistence remains enabled via:
- `PUT /api/app/scraper/posts`
