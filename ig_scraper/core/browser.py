from playwright.async_api import async_playwright
from config.settings import HEADLESS
import os


def _build_chromium_args() -> list[str]:
    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]

    force_no_sandbox = os.getenv("PW_NO_SANDBOX", "").strip().lower() in {"1", "true", "yes"}
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    if force_no_sandbox or is_root:
        args.extend(["--no-sandbox", "--disable-setuid-sandbox"])

    return args


async def start_browser(session_dir):
    # Ensure session_dir exists; Playwright will use it as user data dir
    os.makedirs(session_dir, exist_ok=True)
    storage_path = os.path.join(session_dir, "storage_state.json")

    pw = await async_playwright().start()
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    launch_kwargs = {
        "headless": HEADLESS,
        "viewport": {"width": 1280, "height": 800},
        "args": _build_chromium_args(),
        "user_agent": ua,
    }

    try:
        ctx = await pw.chromium.launch_persistent_context(session_dir, **launch_kwargs)
    except Exception as first_error:
        fallback_kwargs = dict(launch_kwargs)
        fallback_kwargs["channel"] = "chromium"
        try:
            ctx = await pw.chromium.launch_persistent_context(session_dir, **fallback_kwargs)
        except Exception as second_error:
            await pw.stop()
            raise RuntimeError(
                "Playwright could not start Chromium. On Ubuntu run: 'playwright install-deps chromium' and 'playwright install chromium'."
            ) from second_error

    page = await ctx.new_page()
    return pw, ctx, page
