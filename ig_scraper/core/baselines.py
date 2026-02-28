import hashlib
import asyncio
from storage import api_client
from datetime import datetime
from config.settings import ENABLE_BASELINE_WRITE

def record(selector, html):
    if not ENABLE_BASELINE_WRITE:
        return

    h = hashlib.md5(html.encode()).hexdigest()
    try:
        # best-effort: schedule sending baseline to remote API (don't await)
        asyncio.create_task(api_client.record_baseline(selector, h, datetime.utcnow().isoformat()))
    except Exception:
        # fallback: just warn locally
        print("⚠ UI BASELINE (local):", selector)
    # keep local logging for immediate visibility
    # if remote detects change it can alert/flag
