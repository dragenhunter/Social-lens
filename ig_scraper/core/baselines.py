import hashlib
from storage import api_client
from datetime import datetime
from config.settings import ENABLE_BASELINE_WRITE
from core.background import create_logged_task

def record(selector, html):
    if not ENABLE_BASELINE_WRITE:
        return

    h = hashlib.md5(html.encode()).hexdigest()
    try:
        create_logged_task(
            api_client.record_baseline(selector, h, datetime.utcnow().isoformat()),
            f"record baseline for {selector}",
        )
    except RuntimeError:
        # fallback: just warn locally
        print("UI BASELINE (local):", selector)
    # keep local logging for immediate visibility
    # if remote detects change it can alert/flag
