from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlparse

from config.settings import BASE_URL
from core.actions import pause
from core.comments import list_comments
from core.confidence import score
from core.diffing import record_post_diff
from storage import api_client


def _normalize_external_post_id(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    return cleaned.rstrip("/")


async def _visible_profile_post_urls(page) -> list[str]:
    urls = await page.evaluate(
        r"""
        () => {
            const urls = [];
            for (const a of document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"], a[data-testid="user-post-item"]')) {
                const href = a.href || a.getAttribute('href');
                if (!href) continue;
                const raw = href.split('?')[0].replace(/\/$/, '');
                if (raw) urls.push(raw);
            }
            return urls;
        }
        """
    )
    return urls if isinstance(urls, list) else []


def _parse_iso_utc(value: str):
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _scrape_and_write_open_post(page, username, gov, source_id: str, external_post_id: str):

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

            const timeEl = document.querySelector('time[datetime]');

            return {
                post_id: location.pathname.replace(/\/$/, ''),
                caption: text(captionEl),
                likes: numberFrom(text(likesEl)),
                comments: document.querySelectorAll('ul ul li, article ul ul li').length,
                published_at: timeEl ? (timeEl.getAttribute('datetime') || '') : '',
            };
        }
        """
    )

    if not post.get("post_id"):
        post["post_id"] = external_post_id

    published_at_dt = _parse_iso_utc(post.get("published_at", ""))

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
            "postDate": (published_at_dt.isoformat() if published_at_dt else datetime.utcnow().isoformat()),
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
    except Exception as e:
        print(f"Failed to write post for {username} ({post.get('post_id')}): {e}")

    await pause(gov.mult)

    return published_at_dt


async def scrape_posts(page, username, budget, gov, source_id=""):
    if not source_id:
        print(f"Skipping {username}: missing source_id for API duplicate checks")
        return

    lookback_hours = max(1, int(os.getenv("SCRAPE_LOOKBACK_HOURS", "6") or "6"))
    cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    profile_url = page.url

    try:
        recent_ids = await api_client.get_recent_post_ids(source_id, limit=200)
    except Exception:
        recent_ids = set()

    seen_urls: set[str] = set()
    idle_scrolls = 0
    max_idle_scrolls = max(1, int(os.getenv("PROFILE_POST_IDLE_SCROLLS", "3") or "3"))
    wrote_new_posts = 0
    older_post_boundary_hit = False
    saw_any_post_links = False

    while idle_scrolls < max_idle_scrolls:
        urls = await _visible_profile_post_urls(page)

        new_visible_urls = [u for u in urls if u not in seen_urls]
        for u in new_visible_urls:
            seen_urls.add(u)
        if new_visible_urls:
            saw_any_post_links = True

        if not new_visible_urls:
            idle_scrolls += 1
            budget.consume("scrolls")
            await page.mouse.wheel(0, 2200)
            await pause(gov.mult)
            continue

        idle_scrolls = 0

        for post_url in new_visible_urls:
            path = urlparse(post_url).path.rstrip("/")
            external_post_id = _normalize_external_post_id(path)
            if not external_post_id:
                continue

            budget.consume("opens")
            try:
                await page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                try:
                    await page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
                    await pause(gov.mult)
                except Exception:
                    pass
                continue

            await pause(gov.mult)

            published_at_raw = await page.evaluate(
                r"""
                () => {
                    const timeEl = document.querySelector('time[datetime]');
                    return timeEl ? (timeEl.getAttribute('datetime') || '') : '';
                }
                """
            )
            published_at_dt = _parse_iso_utc(published_at_raw)
            if published_at_dt and published_at_dt < cutoff_utc:
                print(f"Reached {lookback_hours}h lookback boundary for {username} at {external_post_id}; stopping further scan.")
                older_post_boundary_hit = True
                break

            exists = external_post_id in recent_ids
            if not exists:
                try:
                    exists = await api_client.post_exists(source_id, external_post_id)
                except Exception:
                    exists = False

            if exists:
                try:
                    await page.go_back(wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    try:
                        await page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
                    except Exception:
                        pass
                await pause(gov.mult)
                continue

            await _scrape_and_write_open_post(page, username, gov, source_id, external_post_id)
            recent_ids.add(external_post_id)
            wrote_new_posts += 1

            try:
                await page.go_back(wait_until="domcontentloaded", timeout=60000)
            except Exception:
                try:
                    await page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
            await pause(gov.mult)

        if older_post_boundary_hit:
            break

        budget.consume("scrolls")
        await page.mouse.wheel(0, 2200)
        await pause(gov.mult)

    if wrote_new_posts == 0:
        if older_post_boundary_hit:
            print(f"No new posts in the last {lookback_hours} hours for {username}.")
        elif saw_any_post_links:
            print(f"No new posts for {username}; skipping.")
        else:
            print(f"No post links found for {username}")
