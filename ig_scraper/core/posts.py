from datetime import datetime
from urllib.parse import urlparse

from config.settings import BASE_URL
from core.actions import pause
from core.comments import list_comments
from core.confidence import score
from core.diffing import record_post_diff
from storage import api_client


async def scrape_posts(page, username, budget, gov, source_id=""):
    post_urls = await page.evaluate(
        """
        () => {
            const urls = Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'))
                .map(a => a.href ? a.href.split('?')[0].replace(/\/$/, '') : null)
                .filter(Boolean);
            return Array.from(new Set(urls)).slice(0, 5);
        }
        """
    )

    if not post_urls:
        print(f"No post links found for {username}")
        return

    post_candidates = []
    for post_url in post_urls:
        path = urlparse(post_url).path.rstrip("/")
        if path:
            post_candidates.append((post_url, path))

    if source_id:
        try:
            recent_ids = await api_client.get_recent_post_ids(source_id, limit=50)
        except Exception:
            recent_ids = set()

        new_candidates = []
        for post_url, external_post_id in post_candidates:
            exists = external_post_id in recent_ids
            if not exists:
                try:
                    exists = await api_client.post_exists(source_id, external_post_id)
                except Exception:
                    exists = False
            if not exists:
                new_candidates.append((post_url, external_post_id))

        if not new_candidates:
            print(f"No new posts for {username}; skipping.")
            return

        post_candidates = new_candidates

    for post_url, external_post_id in post_candidates:
        budget.consume("opens")
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            continue

        await pause(gov.mult)

        post = await page.evaluate(
            """
            () => {
                const text = (el) => (el && el.innerText ? el.innerText : "").trim();
                const numberFrom = (raw) => {
                    if (!raw) return 0;
                    const cleaned = raw.replace(/,/g, '').trim();
                    if (/^\d+(\.\d+)?[kKmMbB]$/.test(cleaned)) {
                        const n = parseFloat(cleaned.slice(0, -1));
                        const u = cleaned.slice(-1).toLowerCase();
                        if (u === 'k') return Math.round(n * 1000);
                        if (u === 'm') return Math.round(n * 1000000);
                        if (u === 'b') return Math.round(n * 1000000000);
                    }
                    const n = Number(cleaned.replace(/[^0-9.]/g, ''));
                    return Number.isFinite(n) ? n : 0;
                };

                const captionEl =
                    document.querySelector('h1') ||
                    document.querySelector('article ul li span') ||
                    document.querySelector('article div[role="button"] span');

                const likesEl =
                    document.querySelector('section a[href*="liked_by"] span') ||
                    document.querySelector('section span[title]') ||
                    document.querySelector('section span');

                return {
                    post_id: location.pathname.replace(/\/$/, ''),
                    caption: text(captionEl),
                    likes: numberFrom(text(likesEl)),
                    comments: document.querySelectorAll('ul ul li, article ul ul li').length,
                };
            }
            """
        )

        if not post.get("post_id"):
            post["post_id"] = external_post_id

        post["confidence"] = score(post)
        record_post_diff(post)

        comments_data = []
        try:
            from config.settings import DEEP_COMMENT_LOADING

            comments_data = await list_comments(page, deep=DEEP_COMMENT_LOADING, max_comments=50)
        except Exception:
            comments_data = []

        try:
            payload = {
                "sourceId": source_id or "",
                "externalPostId": post["post_id"],
                "postDate": datetime.utcnow().isoformat(),
                "postUrl": f"{BASE_URL}{post['post_id']}",
                "content": post["caption"],
                "keywords": "",
                "keywordMatchedCount": 0,
                "isSummarized": False,
                "sentimentScore": int(post.get("confidence", 0) * 1000),
                "commentCount": len(comments_data),
                "comments": comments_data,
            }
            await api_client.write_posts([payload])
        except Exception:
            pass

        await pause(gov.mult)
