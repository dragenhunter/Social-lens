# ig_scraper

Instagram scraper with persistent Playwright session directories per account.

## Session model

The scraper is designed to reuse an account's browser session directory (`session`) across runs.

- On startup it launches Chromium with `launch_persistent_context(session_dir, ...)`, so Instagram cookies and local browser state are reused automatically.
- If valid Instagram auth cookies already exist, the scraper skips login and continues with the saved session.
- If cookies are missing or expired and manual login mode is enabled, the scraper keeps the browser open and waits for you to complete the Instagram login manually.
- After a successful login, it saves `storage_state.json` and the persistent Chromium profile under the same session directory so future runs reuse that session until Instagram expires it.

## Recommended env settings

For a manual-login-first setup, use these values in the workspace `.env`:

```env
HEADLESS=0
COOKIE_ONLY_AUTH=1
MANUAL_LOGIN_ONLY=1
MANUAL_LOGIN_SEED_ON_COOKIE_MISS=1
MANUAL_LOGIN_TIMEOUT_SECONDS=300
```

In this mode, account entries only need a `username` and `session` path. A password is optional and is not required for cookie reuse or manual session seeding.
