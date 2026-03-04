from datetime import datetime
import os
from urllib.parse import urlparse

from config.settings import BASE_URL
from core.actions import pause
from core.comments import list_comments
from core.confidence import score
from core.diffing import record_post_diff
from storage import api_client


async def _collect_profile_post_urls(page, budget, gov, max_urls: int, max_scrolls: int):
    collected = []
    seen = set()

    for _ in range(max_scrolls + 1):
        urls = await page.evaluate(
            r"""
            () => {
                const urls = [];
                for (const a of document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]')) {
                    const raw = a.href ? a.href.split('?')[0].replace(/\/$/, '') : null;
                    if (raw) urls.push(raw);
                }
                return urls;
            }
            """
        )

        for post_url in urls:
            if post_url in seen:
                continue
            seen.add(post_url)
            collected.append(post_url)
            if len(collected) >= max_urls:
                return collected

        budget.consume("scrolls")
        await page.mouse.wheel(0, 2200)
        await pause(gov.mult)

    return collected


async def scrape_posts(page, username, budget, gov, source_id=""):
    max_scan_urls = max(1, int(os.getenv("PROFILE_POST_SCAN_LIMIT", "30") or "30"))
    max_scan_scrolls = max(0, int(os.getenv("PROFILE_POST_SCAN_SCROLLS", "8") or "8"))
    stop_on_existing = os.getenv("SCRAPE_UNTIL_EXISTING_URL", "0").strip().lower() in {"1", "true", "yes"}

    post_urls = await _collect_profile_post_urls(
        page=page,
        budget=budget,
        gov=gov,
        max_urls=max_scan_urls,
        max_scrolls=max_scan_scrolls,
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
        existing_boundary_hit = False
        for post_url, external_post_id in post_candidates:
            exists = external_post_id in recent_ids
            if not exists:
                try:
                    exists = await api_client.post_exists(source_id, external_post_id)
                except Exception:
                    exists = False

            if exists:
                if stop_on_existing:
                    print(f"Found existing post URL for {username} ({external_post_id}); stopping further scan.")
                    existing_boundary_hit = True
                    break
                continue

            if not exists:
                new_candidates.append((post_url, external_post_id))

        if not new_candidates:
            if existing_boundary_hit:
                print(f"Reached existing-post boundary for {username}; no new posts before boundary.")
                return
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
            r"""
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
