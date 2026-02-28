import httpx
import os

API_BASE = os.getenv("API_BASE", "http://localhost:5000").rstrip("/")
PAYLOAD = {
    "password": os.getenv("API_PASS", ""),
    "userNameOrEmailAddress": os.getenv("API_USER", ""),
    "rememberMe": True,
}

with httpx.Client(base_url=API_BASE, timeout=20.0) as c:
    if not PAYLOAD["userNameOrEmailAddress"] or not PAYLOAD["password"]:
        raise SystemExit("Set API_USER and API_PASS environment variables before running this script.")

    print('POST /api/account/login -> user set:', bool(PAYLOAD["userNameOrEmailAddress"]))
    r = c.post('/api/account/login', json=PAYLOAD)
    print('status:', r.status_code)
    print('headers:', dict(r.headers))
    try:
        print('json:', r.json())
    except Exception:
        print('text:', r.text)
    print('cookies:', c.cookies.jar)

    # Try sources without following redirects
    print('\nGET /api/app/scraper/sources (no redirects)')
    s = c.get('/api/app/scraper/sources', follow_redirects=False)
    print('status:', s.status_code)
    print('headers:', dict(s.headers))
    print('location:', s.headers.get('location'))
    print('history length:', len(s.history))

    # Try sources with redirects to follow
    print('\nGET /api/app/scraper/sources (follow redirects)')
    s2 = c.get('/api/app/scraper/sources', follow_redirects=True)
    print('final status:', s2.status_code)
    print('final url:', s2.url)
    print('history len:', len(s2.history))
    if s2.status_code == 200:
        try:
            print('json len or sample:', (len(s2.json()) if isinstance(s2.json(), list) else 'obj'))
        except Exception:
            print('text sample:', s2.text[:500])
    else:
        print('text sample:', s2.text[:500])
