from playwright.async_api import async_playwright
from config.settings import HEADLESS
import os


async def start_browser(session_dir):
    # Ensure session_dir exists; Playwright will use it as user data dir
    os.makedirs(session_dir, exist_ok=True)
    storage_path = os.path.join(session_dir, "storage_state.json")

    pw = await async_playwright().start()
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    ctx = await pw.chromium.launch_persistent_context(
        session_dir,
        headless=HEADLESS,
        viewport={"width": 1280, "height": 800},
        args=["--disable-blink-features=AutomationControlled"],
        user_agent=ua,
    )
    page = await ctx.new_page()
    return pw, ctx, page
