from storage import api_client
from datetime import datetime, timedelta
from config.settings import ENABLE_REMOTE_COOLDOWNS

async def is_on_cooldown(username):
    if not ENABLE_REMOTE_COOLDOWNS:
        return False

    try:
        res = await api_client.check_cooldown(username)
        # assume API returns { "until": "ISO_TIMESTAMP" } or similar
        until = None
        if isinstance(res, dict):
            until = res.get("until")
        elif isinstance(res, list) and res:
            until = res[0].get("until")
        if until:
            return datetime.utcnow() < datetime.fromisoformat(until)
    except Exception:
        # if API fails, default to not on cooldown
        return False
    return False

async def set_cooldown(username, hours=24):
    if not ENABLE_REMOTE_COOLDOWNS:
        return

    try:
        await api_client.set_cooldown_api(username, hours)
    except Exception:
        # best-effort: ignore remote failures
        pass
