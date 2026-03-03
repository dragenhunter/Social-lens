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
import re
from pathlib import Path


async def ensure_logged_in(page, account, max_retries=2):
    username = account.get("username")
    password = account.get("password")
    # Try to detect logged-in state via the Home icon
    try:
        await page.goto(BASE_URL, wait_until="domcontentloaded")

        def _looks_logged_in(url: str) -> bool:
            lower = (url or "").lower()
            return (
                "instagram.com" in lower
                and "/accounts/login" not in lower
                and "/challenge/" not in lower
                and "/checkpoint/" not in lower
            )

        if _looks_logged_in(page.url):
            logged_in_selectors = [
                'svg[aria-label="Home"]',
                'a[href="/"]',
                'a[href*="/direct/inbox/"]',
                'nav',
                'input[placeholder="Search"]',
                'a[href*="/accounts/edit/"]',
            ]
            for selector in logged_in_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=2500)
                    return True
                except Exception:
                    continue
            # URL-based success fallback for UI variants where selectors drift.
            return True

        # Navigate to explicit login page and submit credentials
        await page.goto(f"{BASE_URL}/accounts/login/", timeout=30000)
        await page.wait_for_load_state('domcontentloaded')
        # try dismissing common cookie/privacy banners
        for banner in ('text=Accept All', 'text=Accept', 'text=Agree', 'button:has-text("Accept")'):
            try:
                await page.click(banner, timeout=1500)
                break
            except Exception:
                pass

        # wait for any known login input to appear; IG can serve multiple form variants
        try:
            await page.wait_for_selector(
                'input[name="username"], input[name="email"], input[autocomplete="username"], input[type="password"], input[name="pass"], input[name="password"]',
                timeout=12000,
            )
        except Exception:
            print("Login form did not render in time. url=", page.url)

        username_selectors = [
            'input[name="username"]',
            'input[name="email"]',
            'input[autocomplete="username"]',
            'input[aria-label="Phone number, username, or email"]',
            'input[type="text"]',
        ]
        password_selectors = [
            'input[name="password"]',
            'input[name="pass"]',
            'input[autocomplete="current-password"]',
            'input[type="password"]',
        ]

        async def _detect_login_error_reason() -> str:
            error_selectors = [
                'text=The login information you entered is incorrect',
                'text=Sorry, your password was incorrect',
                'text=Find your account and log in',
                'text=We detected an unusual login attempt',
                'text=checkpoint',
                'text=challenge',
            ]
            for sel in error_selectors:
                try:
                    if await page.query_selector(sel):
                        normalized = sel.lower()
                        if "incorrect" in normalized or "password" in normalized:
                            return "invalid_credentials"
                        if "checkpoint" in normalized or "challenge" in normalized or "unusual login" in normalized:
                            return "challenge_required"
                except Exception:
                    continue

            try:
                body_text = (await page.inner_text("body")).lower()
                if "login information you entered is incorrect" in body_text or "your password was incorrect" in body_text:
                    return "invalid_credentials"
                if "challenge" in body_text or "unusual login attempt" in body_text or "checkpoint" in body_text:
                    return "challenge_required"
            except Exception:
                pass

            return ""

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
                try:
                    print("Could not find login inputs on url:", page.url)
                except Exception:
                    pass
                await asyncio.sleep(1)
                continue

            # submit: try several ways to trigger the login
            submit_attempted = False
            submit_selectors = [
                'div[aria-label="Log In"]',
                'div[aria-label="Log in"]',
                'button[name="login"]',
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
                success_selectors = [
                    'svg[aria-label="Home"]',
                    'a[href="/"]',
                    'a[href*="/direct/inbox/"]',
                    'a[href*="/accounts/edit/"]',
                    'nav',
                ]
                for success_selector in success_selectors:
                    try:
                        await page.wait_for_selector(success_selector, timeout=4000)
                        return True
                    except Exception:
                        continue

                await page.wait_for_load_state("domcontentloaded")
                if _looks_logged_in(page.url):
                    return True
            except Exception:
                pass

            failure_reason = await _detect_login_error_reason()
            if failure_reason:
                account["_login_failure_reason"] = failure_reason
                print(f"Detected login failure reason for {username}: {failure_reason}")
                if failure_reason == "invalid_credentials":
                    return False

            # save debug artifacts to inspect why login didn't complete
            try:
                await page.screenshot(path="run_e2e_login_debug.png", full_page=True)
                html = await page.content()
                html = re.sub(r'(<input[^>]+type="password"[^>]*value=")([^"]*)(")', r'\1***\3', html, flags=re.IGNORECASE)
                html = re.sub(r'(<input[^>]+name="(?:email|username)"[^>]*value=")([^"]*)(")', r'\1***\3', html, flags=re.IGNORECASE)
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

    try:
        pw, ctx, page = await start_browser(account["session"])
    except Exception as e:
        username = account.get("username")
        print(f"Browser startup failed for {username}: {e}")
        await set_cooldown(account["username"], 6)
        return
    # ensure we are logged into Instagram (use session if present, otherwise perform login)
    logged = await ensure_logged_in(page, account)
    if not logged:
        username = account.get("username")
        login_reason = account.get("_login_failure_reason") or "login_failed"
        print("Login failed for", username)
        quarantine_account(username, reason=login_reason)
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

                if "/challenge/" in page.url or "/checkpoint/" in page.url:
                    print(f"Skipping {u}: challenge/checkpoint page encountered ({page.url})")
                    continue

                html = ""
                try:
                    await page.wait_for_selector("main", timeout=8000)
                    html = await page.inner_html("main", timeout=5000)
                except Exception:
                    try:
                        html = await page.inner_html("body", timeout=5000)
                        print(f"Using body fallback for {u}: 'main' not found on {page.url}")
                    except Exception:
                        html = await page.content()
                        print(f"Using page.content fallback for {u}: body/main unavailable on {page.url}")

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
