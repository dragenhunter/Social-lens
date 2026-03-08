from core.browser import start_browser
from core.actions import pause
from core.budgets import Budget
from core.governor import Governor
from core.profiles import scrape_profile
from core.posts import scrape_posts
from core.baselines import record
from core.cooldowns import is_on_cooldown, set_cooldown
from config.settings import BASE_URL, ACTION_LIMITS
import asyncio
import os
import re
from pathlib import Path


async def ensure_logged_in(page, account, max_retries=2):
    username = account.get("username")
    password = account.get("password")
    cookie_only_auth = os.getenv("COOKIE_ONLY_AUTH", "0").strip().lower() in {"1", "true", "yes"}
    auto_switch_profile_on_picker = os.getenv("AUTO_SWITCH_PROFILE_ON_PICKER", "0").strip().lower() in {"1", "true", "yes"}
    manual_login_seed_on_cookie_miss = os.getenv("MANUAL_LOGIN_SEED_ON_COOKIE_MISS", "1").strip().lower() in {"1", "true", "yes"}
    headless_mode = os.getenv("HEADLESS", "1").strip().lower() in {"1", "true", "yes"}
    account["_login_failure_reason"] = ""

    def _is_challenge_like_url(url: str) -> bool:
        lower = (url or "").lower()
        return (
            "/challenge/" in lower
            or "/checkpoint/" in lower
            or "/auth_platform/codeentry" in lower
            or "two_factor" in lower
        )

    async def _has_auth_cookies() -> bool:
        try:
            cookies = await page.context.cookies([BASE_URL])
        except Exception:
            try:
                cookies = await page.context.cookies()
            except Exception:
                return False

        cookie_names = {str(cookie.get("name", "")).lower() for cookie in cookies}
        return "sessionid" in cookie_names and "ds_user_id" in cookie_names

    async def _save_login_debug_artifacts(tag: str) -> None:
        try:
            safe_tag = re.sub(r"[^a-zA-Z0-9_-]", "_", (tag or "debug"))
            png_path = f"run_e2e_login_debug_{safe_tag}.png"
            html_path = f"run_e2e_login_debug_{safe_tag}.html"
            await page.screenshot(path=png_path, full_page=True)
            html = await page.content()
            html = re.sub(r'(<input[^>]+type="password"[^>]*value=")([^"]*)(")', r'\1***\3', html, flags=re.IGNORECASE)
            html = re.sub(r'(<input[^>]+name="(?:email|username)"[^>]*value=")([^"]*)(")', r'\1***\3', html, flags=re.IGNORECASE)
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            print(f"Saved {png_path} and {html_path}")
        except Exception as e:
            print("Failed to save debug artifacts:", e)

    async def _dismiss_common_banners() -> None:
        for banner in (
            'text=Accept All',
            'text=Accept',
            'text=Agree',
            'button:has-text("Accept")',
            'button:has-text("Allow all cookies")',
            'button:has-text("Allow essential and optional cookies")',
            'button:has-text("Only allow essential cookies")',
            'button:has-text("Not Now")',
        ):
            try:
                await page.click(banner, timeout=1200)
                break
            except Exception:
                pass

    async def _click_text_option(options: list[str], tag: str) -> bool:
        for option in options:
            if not option:
                continue
            try:
                loc = page.locator(f'text={option}').first
                if await loc.count() > 0:
                    await loc.click(timeout=3000)
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    print(f"Clicked account picker option via locator ({tag}): {option}")
                    return True
            except Exception:
                pass

        try:
            clicked = await page.evaluate(
                r"""
                (labels) => {
                    const normalized = labels.map(x => String(x || '').toLowerCase().trim()).filter(Boolean);
                    const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], div, span'));
                    for (const node of nodes) {
                        const text = (node.innerText || node.textContent || '').toLowerCase().replace(/\s+/g, ' ').trim();
                        if (!text) continue;
                        if (normalized.some(label => text === label || text.includes(label))) {
                            node.click();
                            return true;
                        }
                    }
                    return false;
                }
                """,
                options,
            )
            if clicked:
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                print(f"Clicked account picker option via JS ({tag})")
                return True
        except Exception:
            pass

        return False

    async def _switch_picker_to_manual_login() -> bool:
        switch_profile_texts = [
            "Use another profile",
            "Switch accounts",
            "Use another account",
        ]
        switched = await _click_text_option(switch_profile_texts, "switch_profile")
        if switched:
            print(f"Switched to manual login form for {username} via account picker")
        return switched

    async def _wait_for_session_after_picker_continue() -> bool:
        wait_seconds = max(2, int(os.getenv("PICKER_CONTINUE_WAIT_SECONDS", "8") or "8"))
        checks = wait_seconds * 2
        for _ in range(checks):
            try:
                current_url = (page.url or "").lower()
            except Exception:
                current_url = ""

            if current_url and "instagram.com" in current_url and "/accounts/login" not in current_url and "/challenge/" not in current_url and "/checkpoint/" not in current_url:
                return True
            if await _has_auth_cookies():
                return True
            await asyncio.sleep(0.5)
        return False

    async def _wait_for_manual_login_seed() -> bool:
        timeout_seconds = max(30, int(os.getenv("MANUAL_LOGIN_TIMEOUT_SECONDS", "300") or "300"))
        print(
            f"Manual login required for {username}. Complete Instagram login in the open browser window "
            f"within {timeout_seconds}s to seed cookies."
        )
        checks = timeout_seconds * 2
        for _ in range(checks):
            if await _handle_account_picker():
                return True
            try:
                if _looks_logged_in(page.url) and await _has_auth_cookies():
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

    async def _handle_account_picker() -> bool:
        try:
            body_text = (await page.inner_text("body")).lower()
        except Exception:
            body_text = ""

        looks_like_picker = (
            "use another profile" in body_text
            or "continue" in body_text
            or "continue as" in body_text
        )
        if not looks_like_picker:
            return False

        handle_hint = (username or "").split("@", 1)[0].strip().lower()

        continue_texts = [
            f"Continue as {username}" if username else "",
            f"Continue as {handle_hint}" if handle_hint else "",
            "Continue",
        ]

        if await _click_text_option(continue_texts, "continue"):
            if await _wait_for_session_after_picker_continue():
                try:
                    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    pass
                if "instagram.com" in (page.url or "").lower() and "/accounts/login" not in (page.url or "").lower():
                    print(f"Used account picker continue for {username} (cookie-confirmed)")
                    return True
                if await _has_auth_cookies():
                    print(f"Used account picker continue for {username} (session detected)")
                    return True
            print(f"Account picker continue did not establish session for {username}; keeping current picker state")
            return False

        if auto_switch_profile_on_picker and await _switch_picker_to_manual_login():
            return False

        return False

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

        if _looks_logged_in(page.url) and await _has_auth_cookies():
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
            # Cookie-based success fallback for UI variants where selectors drift.
            if await _has_auth_cookies():
                return True

        if cookie_only_auth:
            # In cookie-only mode we never submit credentials.
            await page.goto(f"{BASE_URL}/accounts/login/", timeout=30000)
            await page.wait_for_load_state('domcontentloaded')

            if await _handle_account_picker():
                return True

            if _looks_logged_in(page.url) and await _has_auth_cookies():
                return True

            if manual_login_seed_on_cookie_miss:
                if headless_mode:
                    print(
                        f"Cookie-only auth: manual seeding requested for {username}, but HEADLESS=1. "
                        "Set HEADLESS=0 to complete first-time login and save cookies."
                    )
                else:
                    seeded = await _wait_for_manual_login_seed()
                    if seeded:
                        print(f"Manual login seed complete for {username}; cookies are now available.")
                        return True
                    print(f"Manual login seed timed out for {username}.")

            account["_login_failure_reason"] = "cookie_session_missing"
            print(f"Cookie-only auth enabled: no valid IG session cookies for {username}")
            return False

        # Navigate to explicit login page and submit credentials
        await page.goto(f"{BASE_URL}/accounts/login/", timeout=30000)
        await page.wait_for_load_state('domcontentloaded')

        if await _handle_account_picker():
            return True

        if _is_challenge_like_url(page.url):
            account["_login_failure_reason"] = "challenge_required"
            return False

        # try dismissing common cookie/privacy banners
        await _dismiss_common_banners()

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
            'input[type="email"]',
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
                if "please wait a few minutes" in body_text or "try again later" in body_text:
                    return "rate_limited"
            except Exception:
                pass

            return ""

        for attempt in range(max_retries):
            print(f"Login attempt {attempt+1}/{max_retries} for {username}")

            await _dismiss_common_banners()

            if attempt > 0:
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=45000)
                    await _dismiss_common_banners()
                    if await _handle_account_picker():
                        return True
                except Exception:
                    pass

            async def _find_login_scope_and_fields():
                scopes = [page, *list(page.frames)]

                # Include any additional tabs/pages created by Instagram auth flows.
                try:
                    for other_page in page.context.pages:
                        if other_page is page:
                            continue
                        scopes.append(other_page)
                        scopes.extend(list(other_page.frames))
                except Exception:
                    pass

                # De-duplicate scope objects while preserving order.
                deduped_scopes = []
                seen_scope_ids = set()
                for scope in scopes:
                    sid = id(scope)
                    if sid in seen_scope_ids:
                        continue
                    seen_scope_ids.add(sid)
                    deduped_scopes.append(scope)

                # 1) Preferred: username+password form.
                for scope in deduped_scopes:
                    for us in username_selectors:
                        try:
                            user_el = await scope.query_selector(us)
                        except Exception:
                            user_el = None
                        if not user_el:
                            continue
                        for ps in password_selectors:
                            try:
                                pass_el = await scope.query_selector(ps)
                            except Exception:
                                pass_el = None
                            if pass_el:
                                return scope, us, ps, False

                # 2) Fallback: password-only re-auth form.
                for scope in deduped_scopes:
                    for ps in password_selectors:
                        try:
                            pass_el = await scope.query_selector(ps)
                        except Exception:
                            pass_el = None
                        if pass_el:
                            return scope, "", ps, True

                for scope in scopes:
                    for us in username_selectors:
                        try:
                            user_el = await scope.query_selector(us)
                        except Exception:
                            user_el = None
                        if not user_el:
                            continue
                        for ps in password_selectors:
                            try:
                                pass_el = await scope.query_selector(ps)
                            except Exception:
                                pass_el = None
                            if pass_el:
                                return scope, us, ps, False
                return None, "", "", False

            if _is_challenge_like_url(page.url):
                account["_login_failure_reason"] = "challenge_required"
                print(f"Challenge/checkpoint flow detected for {username}: {page.url}")
                return False

            login_scope, user_selector, pass_selector, password_only_form = await _find_login_scope_and_fields()
            if not login_scope:
                try:
                    print("Could not find login inputs on url:", page.url)
                    body_preview = (await page.inner_text("body"))[:220].replace("\n", " ")
                    print("Login page body preview:", body_preview)
                except Exception:
                    pass

                if await _handle_account_picker():
                    return True

                if not cookie_only_auth:
                    switched = await _switch_picker_to_manual_login()
                    if switched:
                        await asyncio.sleep(0.5)
                        continue

                failure_reason = await _detect_login_error_reason()
                if failure_reason:
                    account["_login_failure_reason"] = failure_reason
                await _save_login_debug_artifacts(f"no_inputs_attempt_{attempt+1}")
                await asyncio.sleep(1)
                continue

            if user_selector:
                print("username selector check:", user_selector, "->", True)
            else:
                print("username selector check: <not required for password-only re-auth form>")
            print("password selector check:", pass_selector, "->", True)

            filled_user = False
            if password_only_form:
                filled_user = True
            else:
                try:
                    user_el = await login_scope.query_selector(user_selector)
                    if user_el:
                        await user_el.click()
                        await user_el.fill(username)
                        filled_user = True
                except Exception:
                    filled_user = False

            filled_pass = False
            try:
                pass_el = await login_scope.query_selector(pass_selector)
                if pass_el:
                    await pass_el.click()
                    await pass_el.fill(password)
                    filled_pass = True
            except Exception:
                filled_pass = False

            if not (filled_user and filled_pass):
                print("Found login fields but failed to fill one or both fields")
                await _save_login_debug_artifacts(f"fill_failed_attempt_{attempt+1}")
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
                'form button[type="submit"]',
                'button:has-text("Continue")',
                'text=Continue',
            ]
            for s in submit_selectors:
                try:
                    btn = await login_scope.query_selector(s)
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
                            el = await login_scope.query_selector(ps)
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
                if _looks_logged_in(page.url) and await _has_auth_cookies():
                    return True
            except Exception:
                pass

            failure_reason = await _detect_login_error_reason()
            if failure_reason:
                account["_login_failure_reason"] = failure_reason
                print(f"Detected login failure reason for {username}: {failure_reason}")
                if failure_reason in {"invalid_credentials", "challenge_required"}:
                    return False

            # save debug artifacts to inspect why login didn't complete
            await _save_login_debug_artifacts(f"post_submit_attempt_{attempt+1}")
            await asyncio.sleep(2)
        if not account.get("_login_failure_reason"):
            account["_login_failure_reason"] = "login_failed"
        return False
    except Exception:
        if not account.get("_login_failure_reason"):
            account["_login_failure_reason"] = "login_failed"
        return False

async def run_account(account, targets):
    username = account.get("username")
    if not username:
        print("Skipping account with missing username")
        return "skipped_missing_username"

    if await is_on_cooldown(username):
        return "skipped_cooldown"

    gov = Governor()
    budget = Budget(ACTION_LIMITS)
    total_targets = len(targets) if isinstance(targets, list) else 0
    processed_targets = 0
    target_errors = 0
    skipped_empty_username = 0
    skipped_relogin_failed = 0
    skipped_challenge = 0

    session_dir = account.get("session") or f"sessions/{username}"

    try:
        pw, ctx, page = await start_browser(session_dir)
    except Exception as e:
        print(f"Browser startup failed for {username}: {e}")
        await set_cooldown(username, 6)
        return "browser_start_failed"
    # ensure we are logged into Instagram (use session if present, otherwise perform login)
    logged = await ensure_logged_in(page, account)
    if not logged:
        login_reason = account.get("_login_failure_reason") or "login_failed"
        print("Login failed for", username)
        if login_reason == "invalid_credentials":
            print("Invalid credentials detected for", username)
            await set_cooldown(username, 48)
        elif login_reason == "cookie_session_missing":
            print("Cookie-only auth: session missing/expired for", username, "- skipping credential login")
            await set_cooldown(username, 1)
        elif login_reason == "challenge_required":
            print("Challenge required for", username, "- skipping without quarantine")
            await set_cooldown(username, 6)
        else:
            print("Transient login failure for", username, "- skipping without quarantine")
            await set_cooldown(username, 6)
        await ctx.close()
        await pw.stop()
        return login_reason
    # On successful login, persist storage state so future runs reuse the session
    try:
        os.makedirs(session_dir, exist_ok=True)
        storage_path = Path(session_dir) / "storage_state.json"
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
                    skipped_empty_username += 1
                    continue

                await page.goto(f"{BASE_URL}/{u}/", wait_until="domcontentloaded", timeout=60000)
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
                        skipped_relogin_failed += 1
                        continue
                    await page.goto(f"{BASE_URL}/{u}/", wait_until="domcontentloaded", timeout=60000)
                    await pause(gov.mult)

                if "/challenge/" in page.url or "/checkpoint/" in page.url:
                    print(f"Skipping {u}: challenge/checkpoint page encountered ({page.url})")
                    skipped_challenge += 1
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
                processed_targets += 1
            except Exception as profile_error:
                print(f"Error scraping {u}: {profile_error}")
                target_errors += 1
                continue
    except Exception as e:
        print("Hard error:", e)
        await set_cooldown(username, 48)
        return f"hard_error:{type(e).__name__}"
    finally:
        await ctx.close()
        await pw.stop()

    print(
        f"Account summary {username}: total={total_targets}, processed={processed_targets}, "
        f"target_errors={target_errors}, skipped_empty_username={skipped_empty_username}, "
        f"skipped_relogin_failed={skipped_relogin_failed}, skipped_challenge={skipped_challenge}"
    )

    return "ok"
