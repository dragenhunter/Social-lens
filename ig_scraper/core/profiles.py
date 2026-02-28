from storage import api_client
from datetime import datetime
from config.settings import ENABLE_PROFILE_WRITE

async def scrape_profile(page, username):
    if not ENABLE_PROFILE_WRITE:
        return

    data = await page.evaluate("""
    () => ({
        bio: document.querySelector("header section div span")?.innerText || "",
        followers: Number(document.querySelector("a[href$='/followers/'] span")?.innerText.replace(/,/g,'')) || 0,
        following: Number(document.querySelector("a[href$='/following/'] span")?.innerText.replace(/,/g,'')) || 0
    })
    """)

    payload = {
        "username": username,
        "bio": data["bio"],
        "followers": data["followers"],
        "following": data["following"],
        "last_scraped": datetime.utcnow().isoformat()
    }

    try:
        await api_client.write_profile(payload)
    except Exception:
        # best-effort: do not raise if remote API fails
        pass
