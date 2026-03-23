from storage import api_client
from datetime import datetime
from config.settings import ENABLE_POST_HISTORY_WRITE
from core.background import create_logged_task

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
        create_logged_task(
            api_client.record_post_history(entry),
            f"record post history for {post.get('post_id', '<unknown>')}",
        )
    except RuntimeError:
        # No active event loop: keep best-effort behavior without crashing scrape flow.
        pass
