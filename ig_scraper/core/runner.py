from core.browser import start_browser
from core.actions import pause
from core.budgets import Budget
from core.governor import Governor
from core.profiles import scrape_profile
from core.posts import scrape_posts
from core.baselines import record
from core.cooldowns import is_on_cooldown, set_cooldown
from core.quarantine import quarantine_account
from config.settings import BASE_URL, ACTION_LIMITS
import asyncio
import os
from pathlib import Path


async def ensure_logged_in(page, account, max_retries=2):
    username = account.get("username")
    password = account.get("password")
    # Try to detect logged-in state via the Home icon
    try:
        await page.goto(BASE_URL, wait_until="domcontentloaded")
        if "/accounts/login" not in page.url:
            logged_in_selectors = [
                'svg[aria-label="Home"]',
                'a[href="/"]',
                'a[href*="/direct/inbox/"]',
                'nav',
                'input[placeholder="Search"]',
            ]
            for selector in logged_in_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=2000)
                    return True
                except Exception:
                    continue

        # Navigate to explicit login page and submit credentials
        await page.goto(f"{BASE_URL}/accounts/login/", timeout=30000)
        await page.wait_for_load_state('networkidle')
        # try dismissing common cookie/privacy banners
        for banner in ('text=Accept All', 'text=Accept', 'text=Agree', 'button:has-text("Accept")'):
            try:
                await page.click(banner, timeout=1500)
                break
            except Exception:
                pass

        username_selectors = [
            'input[name="username"]',
            'input[aria-label="Phone number, username, or email"]',
            'input[type="text"]',
        ]
        password_selectors = [
            'input[name="password"]',
            'input[type="password"]',
        ]

        for attempt in range(max_retries):
            print(f"Login attempt {attempt+1}/{max_retries} for {username}")
            # fill username
            filled_user = False
            for us in username_selectors:
                try:
                    el = await page.query_selector(us)
                    print("username selector check:", us, "->", bool(el))
                    if not el:
                        continue
                    await el.click()
                    await el.fill(username)
                    # ensure frameworks see the change
                    try:
                        await page.evaluate("(s,v)=>{const e=document.querySelector(s); if(e){e.focus(); e.value=v; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true}));}}", us, username)
                    except Exception:
                        pass
                    filled_user = True
                    break
                except Exception:
                    continue

            # fill password
            filled_pass = False
            for ps in password_selectors:
                try:
                    el = await page.query_selector(ps)
                    print("password selector check:", ps, "->", bool(el))
                    if not el:
                        continue
                    await el.click()
                    await el.fill(password)
                    try:
                        await page.evaluate("(s,v)=>{const e=document.querySelector(s); if(e){e.focus(); e.value=v; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true}));}}", ps, password)
                    except Exception:
                        pass
                    filled_pass = True
                    break
                except Exception:
                    continue

            if not (filled_user and filled_pass):
                await asyncio.sleep(1)
                continue

            # submit: try several ways to trigger the login
            submit_attempted = False
            submit_selectors = [
                'div[aria-label="Log In"]',
                'div[aria-label="Log in"]',
                'button[type="submit"]',
                'button:has-text("Log In")',
                'text=Log In',
                'button:has-text("Log in")',
                'form button[type="submit"]'
            ]
            for s in submit_selectors:
                try:
                    btn = await page.query_selector(s)
                    print('submit selector check:', s, '->', bool(btn))
                    if not btn:
                        continue
                    try:
                        await btn.click()
                        print('Clicked submit element for selector:', s)
                    except Exception:
                        # fallback to JS click
                        try:
                            await page.evaluate("(sel)=>{const b=document.querySelector(sel); if(b) b.click();}", s)
                            print('Evaluated click via JS for selector:', s)
                        except Exception as e:
                            print('Failed to click or eval-click for', s, e)
                            continue

                    submit_attempted = True
                    break
                except Exception as e:
                    print('submit selector error for', s, e)
                    continue

            if not submit_attempted:
                # try pressing Enter while focused on password input
                try:
                    for ps in password_selectors:
                        try:
                            el = await page.query_selector(ps)
                            if el:
                                await el.press('Enter')
                                print('Pressed Enter on', ps)
                                submit_attempted = True
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            if not submit_attempted:
                # fallback: call form.submit() via JS
                try:
                    await page.evaluate("() => { const f = document.querySelector('form'); if(f) f.submit(); }")
                    print('Called form.submit() via JS')
                    submit_attempted = True
                except Exception:
                    pass

            try:
                await page.wait_for_selector('svg[aria-label="Home"]', timeout=15000)
                return True
            except Exception:
                # save debug artifacts to inspect why login didn't complete
                try:
                    await page.screenshot(path="run_e2e_login_debug.png", full_page=True)
                    html = await page.content()
                    with open("run_e2e_login_debug.html", "w", encoding="utf-8") as fh:
                        fh.write(html)
                    print("Saved run_e2e_login_debug.png and run_e2e_login_debug.html")
                except Exception as e:
                    print("Failed to save debug artifacts:", e)
                await asyncio.sleep(2)
        return False
    except Exception:
        return False

async def run_account(account, targets):
    if await is_on_cooldown(account["username"]):
        return

    gov = Governor()
    budget = Budget(ACTION_LIMITS)

    pw, ctx, page = await start_browser(account["session"])
    # ensure we are logged into Instagram (use session if present, otherwise perform login)
    logged = await ensure_logged_in(page, account)
    if not logged:
        username = account.get("username")
        print("Login failed for", username)
        quarantine_account(username, reason="login_failed")
        print("Quarantined account", username, "due to repeated login failure")
        await set_cooldown(account["username"], 48)
        await ctx.close()
        await pw.stop()
        return
    # On successful login, persist storage state so future runs reuse the session
    try:
        sess = account.get("session") or f"sessions/{account.get('username')}"
        os.makedirs(sess, exist_ok=True)
        storage_path = Path(sess) / "storage_state.json"
        await ctx.storage_state(path=str(storage_path))
        print("Saved storage_state to", storage_path)
    except Exception as e:
        print("Failed to save storage state:", e)
    try:
        for target in targets:
            try:
                if isinstance(target, dict):
                    u = target.get("username", "")
                    source_id = target.get("source_id", "")
                else:
                    u = str(target)
                    source_id = ""

                if not u:
                    continue

                await page.goto(f"{BASE_URL}/{u}/", wait_until="domcontentloaded")
                await pause(gov.mult)

                for overlay in (
                    'button:has-text("Not Now")',
                    'button:has-text("Accept")',
                    'button:has-text("Accept all")',
                    'button:has-text("Allow all cookies")',
                    'text=Accept All',
                ):
                    try:
                        await page.click(overlay, timeout=1200)
                        break
                    except Exception:
                        pass

                if "/accounts/login" in page.url:
                    relogged = await ensure_logged_in(page, account, max_retries=1)
                    if not relogged:
                        print(f"Skipping {u}: redirected to login and relogin failed")
                        continue
                    await page.goto(f"{BASE_URL}/{u}/", wait_until="domcontentloaded")
                    await pause(gov.mult)

                html = await page.inner_html("main")
                record("article", html)

                await scrape_profile(page, u)
                await scrape_posts(page, u, budget, gov, source_id=source_id)
            except Exception as profile_error:
                print(f"Error scraping {u}: {profile_error}")
                continue
    except Exception as e:
        print("Hard error:", e)
        quarantine_account(account.get("username"), reason=f"hard_error:{type(e).__name__}")
        await set_cooldown(account["username"], 48)
    finally:
        await ctx.close()
        await pw.stop()
