from storage import api_client
from datetime import datetime
import asyncio
from config.settings import ENABLE_POST_HISTORY_WRITE

def record_post_diff(post):
    if not ENABLE_POST_HISTORY_WRITE:
        return

    try:
        # Attempt to send the historical record to remote API
        entry = {
            "postId": post["post_id"],
            "caption": post.get("caption"),
            "likes": post.get("likes"),
            "comments": post.get("comments"),
            "scrapedAt": datetime.utcnow().isoformat()
        }
        asyncio.create_task(api_client.record_post_history(entry))
    except Exception:
        # best-effort: ignore failures
        pass
