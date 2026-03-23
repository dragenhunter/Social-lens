import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.browser import start_browser
from core.runner import ensure_logged_in


def _resolve_env_placeholder(value: str) -> str:
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    if cleaned.startswith("${") and cleaned.endswith("}") and len(cleaned) > 3:
        env_name = cleaned[2:-1].strip()
        return os.getenv(env_name, "")
    return value


def load_accounts() -> list[dict]:
    accounts_path = Path("config") / "accounts.json"
    with accounts_path.open("r", encoding="utf-8") as f:
        accounts = json.load(f)

    resolved: list[dict] = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        mapped = {
            key: _resolve_env_placeholder(value) if isinstance(value, str) else value
            for key, value in account.items()
        }
        resolved.append(mapped)
    return resolved


async def check_login(account: dict) -> dict:
    username = account.get("username") or ""
    session_dir = account.get("session") or (f"sessions/{username}" if username else "")

    if not username:
        return {
            "username": username or "<missing>",
            "session": session_dir,
            "status": "skipped",
            "reason": "missing_username",
        }

    try:
        pw, ctx, page = await start_browser(session_dir)
    except Exception as e:
        return {
            "username": username,
            "session": session_dir,
            "status": "failed",
            "reason": f"browser_start_failed:{type(e).__name__}",
        }

    try:
        ok = await ensure_logged_in(page, account, max_retries=2)
        reason = account.get("_login_failure_reason") or ""
        return {
            "username": username,
            "session": session_dir,
            "status": "ok" if ok else "failed",
            "reason": reason or ("" if ok else "unknown"),
        }
    except Exception as e:
        return {
            "username": username,
            "session": session_dir,
            "status": "failed",
            "reason": f"exception:{type(e).__name__}",
        }
    finally:
        try:
            await ctx.close()
        except Exception:
            pass
        try:
            await pw.stop()
        except Exception:
            pass


async def main() -> None:
    accounts = load_accounts()
    print(f"Loaded {len(accounts)} configured account entries")

    results: list[dict] = []
    for idx, account in enumerate(accounts, start=1):
        username = account.get("username") or "<missing>"
        print(f"\n[{idx}/{len(accounts)}] Checking login for {username}")
        result = await check_login(account)
        results.append(result)
        print(result)

    ok = [r for r in results if r.get("status") == "ok"]
    failed = [r for r in results if r.get("status") == "failed"]
    skipped = [r for r in results if r.get("status") == "skipped"]

    print("\nSUMMARY")
    print({
        "total": len(results),
        "ok": len(ok),
        "failed": len(failed),
        "skipped": len(skipped),
    })

    by_reason: dict[str, int] = {}
    for row in failed + skipped:
        key = str(row.get("reason") or "unknown")
        by_reason[key] = by_reason.get(key, 0) + 1
    print("REASONS", by_reason)


if __name__ == "__main__":
    asyncio.run(main())
