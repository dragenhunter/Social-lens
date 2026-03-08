import asyncio, json
from core.runner import run_account
from config.settings import MAX_WORKERS, ACTIVE_HOURS
from storage import api_client
from datetime import datetime
import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Any


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
    """Check whether a source should be treated as Instagram.

    Primary signal is platform id (Instagram=4). URL host is used as an
    additional safety check when available.
    """
    url = (source.get("sourceUrl") or "").strip().lower()
    platform_value = source.get("platform")

    # Backend enum: Instagram = 4
    is_platform_instagram = str(platform_value).strip() == "4"

    # Some rows may have non-instagram URLs; only accept if URL is empty or instagram host.
    if url:
        try:
            host = (urlparse(url).netloc or "").lower()
        except Exception:
            host = ""
        is_instagram_host = "instagram.com" in host
    else:
        is_instagram_host = True

    return is_platform_instagram and is_instagram_host


def _resolve_env_placeholder(value: str) -> str:
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    if cleaned.startswith("${") and cleaned.endswith("}") and len(cleaned) > 3:
        env_name = cleaned[2:-1].strip()
        return os.getenv(env_name, "")
    return value


def _resolve_account_secrets(accounts: list[dict]) -> list[dict]:
    resolved: list[dict] = []
    for account in accounts:
        if not isinstance(account, dict):
            continue

        mapped = {
            key: _resolve_env_placeholder(value) if isinstance(value, str) else value
            for key, value in account.items()
        }

        if not mapped.get("username") or not mapped.get("password"):
            session = mapped.get("session", "unknown-session")
            print(f"Skipping account config for {session}: missing username/password after env resolution.")
            continue

        resolved.append(mapped)
    return resolved


async def load_instagram_targets() -> list[dict]:
    targets: list[dict] = []
    seen: set[str] = set()

    source_scan_limit = int(os.getenv("SOURCE_SCAN_LIMIT", "0") or "0")
    platform_ids = [
        x.strip()
        for x in os.getenv("INSTAGRAM_PLATFORM_IDS", "4").split(",")
        if x.strip()
    ]

    try:
        sources = []
        for platform_id in platform_ids:
            try:
                platform = int(platform_id)
            except Exception:
                print(f"Skipping invalid INSTAGRAM_PLATFORM_IDS value: {platform_id}")
                continue
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


def _load_run_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _save_run_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _select_rotated_account(eligible_accounts: list[dict], state_path: Path):
    if not eligible_accounts:
        return None

    state = _load_run_state(state_path)
    rotation = state.get("account_rotation") if isinstance(state, dict) else {}
    if not isinstance(rotation, dict):
        rotation = {}

    cursor = int(rotation.get("cursor", 0) or 0)
    normalized = max(0, cursor) % len(eligible_accounts)
    selected = eligible_accounts[normalized]

    rotation["cursor"] = (normalized + 1) % len(eligible_accounts)
    rotation["last_account"] = selected.get("username", "")
    state["account_rotation"] = rotation
    _save_run_state(state_path, state)
    return selected

def in_active_window():
    h = datetime.now().hour
    return ACTIVE_HOURS[0] <= h < ACTIVE_HOURS[1]

async def main():
    force_run = os.getenv("FORCE_RUN", "0").strip() in {"1", "true", "True", "yes", "YES"}
    strict_serial_accounts = os.getenv("STRICT_SERIAL_ACCOUNTS", "0").strip().lower() in {"1", "true", "yes"}
    rotate_single_account_per_run = os.getenv("ROTATE_SINGLE_ACCOUNT_PER_RUN", "1").strip().lower() in {"1", "true", "yes"}
    if not in_active_window() and not force_run:
        print(f"Outside ACTIVE_HOURS={ACTIVE_HOURS}. Set FORCE_RUN=1 to run manually now.")
        return

    project_root = Path(__file__).resolve().parent
    accounts_path = project_root / "config" / "accounts.json"

    with open(accounts_path, encoding="utf-8") as f:
        accounts = json.load(f)

    accounts = _resolve_account_secrets(accounts)

    if not accounts:
        print(f"No accounts found in {accounts_path}")
        return

    eligible_accounts = list(accounts)

    if not eligible_accounts:
        print("No eligible accounts to run.")
        return

    state_path = project_root / "storage" / "state.json"
    if rotate_single_account_per_run:
        selected = _select_rotated_account(eligible_accounts, state_path)
        if not selected:
            print("No eligible account selected for this run.")
            return
        print(f"Rotating accounts per run: selected {selected.get('username', 'unknown')}")
        eligible_accounts = [selected]

    targets = await load_instagram_targets()
    if not targets:
        print("No active Instagram sources found from API. Nothing to scrape.")
        return

    scrape_only_target = _normalize_username(os.getenv("SCRAPE_ONLY_TARGET", ""))
    if scrape_only_target:
        targets = [t for t in targets if _normalize_username(t.get("username", "")) == scrape_only_target]
        if not targets:
            print(f"No matching Instagram source found for SCRAPE_ONLY_TARGET={scrape_only_target}")
            return
        print(f"Applied SCRAPE_ONLY_TARGET={scrape_only_target}")

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
            try:
                return await run_account(acc, batch)
            except Exception as e:
                username = acc.get("username", "unknown")
                print(f"Account run failed for {username}: {e}")
                return e

    if strict_serial_accounts:
        print("STRICT_SERIAL_ACCOUNTS enabled: running account batches one-by-one")
        results = []
        for acc, batch in account_batches:
            results.append(await run_limited(acc, batch))
    else:
        results = await asyncio.gather(
            *[run_limited(acc, batch) for acc, batch in account_batches],
            return_exceptions=False,
        )

    failed = [r for r in results if isinstance(r, Exception)]
    if failed:
        print(f"Completed with {len(failed)} account-level failure(s).")

if __name__ == "__main__":
    asyncio.run(main())
