import asyncio, json
from core.runner import run_account
from core.quarantine import is_quarantined
from config.settings import MAX_WORKERS, ACTIVE_HOURS
from storage import api_client
from datetime import datetime
import os
from pathlib import Path
from urllib.parse import urlparse


def _normalize_username(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if value.startswith("@"):
        value = value[1:]
    return value.strip("/").lower()


def _extract_username_from_url(source_url: str) -> str:
    if not source_url:
        return ""
    try:
        parsed = urlparse(source_url)
        host = (parsed.netloc or "").lower()
        if "instagram.com" not in host:
            return ""
        parts = [p for p in (parsed.path or "").split("/") if p]
        if not parts:
            return ""
        if parts[0].lower() in {"p", "reel", "explore", "stories", "accounts"}:
            return ""
        return _normalize_username(parts[0])
    except Exception:
        return ""


def _is_instagram_source(source: dict) -> bool:
    url = (source.get("sourceUrl") or "").lower()
    if "instagram.com" in url:
        return True

    platform = source.get("platform")
    platform_ids = {
        x.strip()
        for x in os.getenv("INSTAGRAM_PLATFORM_IDS", "2").split(",")
        if x.strip()
    }
    return str(platform) in platform_ids


async def load_instagram_targets() -> list[dict]:
    targets: list[dict] = []
    seen: set[str] = set()

    source_scan_limit = int(os.getenv("SOURCE_SCAN_LIMIT", "0") or "0")
    platform_ids = [
        x.strip()
        for x in os.getenv("INSTAGRAM_PLATFORM_IDS", "2").split(",")
        if x.strip()
    ]

    try:
        sources = []
        for platform_id in platform_ids:
            platform = int(platform_id)
            platform_sources = await api_client.fetch_sources(
                platform=platform,
                is_active=True,
                max_result_count=200,
                total_limit=source_scan_limit if source_scan_limit > 0 else None,
            )
            sources.extend(platform_sources)

        if not sources:
            sources = await api_client.fetch_sources(
                is_active=True,
                max_result_count=200,
                total_limit=source_scan_limit if source_scan_limit > 0 else None,
            )
    except Exception as e:
        print(f"Failed to fetch source accounts from API: {e}")
        return []

    for source in sources:
        if not isinstance(source, dict):
            continue
        if not _is_instagram_source(source):
            continue

        username = _extract_username_from_url(source.get("sourceUrl", ""))
        if not username:
            username = _normalize_username(source.get("sourceHandle", ""))
        if not username or username in seen:
            continue

        seen.add(username)
        targets.append({
            "username": username,
            "source_id": source.get("id", ""),
            "source_url": source.get("sourceUrl", ""),
        })

    return targets

def in_active_window():
    h = datetime.now().hour
    return ACTIVE_HOURS[0] <= h < ACTIVE_HOURS[1]

async def main():
    force_run = os.getenv("FORCE_RUN", "0").strip() in {"1", "true", "True", "yes", "YES"}
    if not in_active_window() and not force_run:
        print(f"Outside ACTIVE_HOURS={ACTIVE_HOURS}. Set FORCE_RUN=1 to run manually now.")
        return

    project_root = Path(__file__).resolve().parent
    accounts_path = project_root / "config" / "accounts.json"

    with open(accounts_path, encoding="utf-8") as f:
        accounts = json.load(f)

    if not accounts:
        print(f"No accounts found in {accounts_path}")
        return

    include_quarantined = os.getenv("FORCE_INCLUDE_QUARANTINED", "0").strip() in {"1", "true", "True", "yes", "YES"}
    eligible_accounts = []
    quarantined_count = 0
    for acc in accounts:
        username = acc.get("username")
        quarantined, info = is_quarantined(username)
        if quarantined and not include_quarantined:
            quarantined_count += 1
            reason = info.get("reason", "unknown")
            since = info.get("since", "unknown")
            print(f"Skipping quarantined account {username} (since={since}, reason={reason})")
            continue
        eligible_accounts.append(acc)

    if quarantined_count:
        print(f"Skipped {quarantined_count} quarantined account(s).")

    if not eligible_accounts:
        print("No eligible accounts to run. Re-enable accounts or set FORCE_INCLUDE_QUARANTINED=1.")
        return

    targets = await load_instagram_targets()
    if not targets:
        print("No active Instagram sources found from API. Nothing to scrape.")
        return

    target_limit = int(os.getenv("SCRAPE_TARGET_LIMIT", "0") or "0")
    if target_limit > 0:
        targets = targets[:target_limit]
        print(f"Applied SCRAPE_TARGET_LIMIT={target_limit}")

    print(f"Loaded {len(targets)} Instagram targets from API source list.")
    batches = [targets[i::len(eligible_accounts)] for i in range(len(eligible_accounts))]
    account_batches = [(acc, batch) for acc, batch in zip(eligible_accounts, batches) if batch]

    if not account_batches:
        print("No non-empty account batches to run.")
        return

    semaphore = asyncio.Semaphore(max(1, MAX_WORKERS))

    async def run_limited(acc, batch):
        async with semaphore:
            return await run_account(acc, batch)

    await asyncio.gather(
        *[run_limited(acc, batch) for acc, batch in account_batches]
    )

if __name__ == "__main__":
    asyncio.run(main())
