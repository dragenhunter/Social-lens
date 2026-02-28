import asyncio
import os
import httpx

API_BASE = os.getenv("API_BASE", "http://localhost:5000").rstrip("/")
PAYLOAD = {
    "password": os.getenv("API_PASS", ""),
    "userNameOrEmailAddress": os.getenv("API_USER", ""),
    "rememberMe": True,
}

async def main():
    if not PAYLOAD["userNameOrEmailAddress"] or not PAYLOAD["password"]:
        print("Set API_USER and API_PASS environment variables before running this script.")
        return
    async with httpx.AsyncClient(base_url=API_BASE, timeout=20.0) as c:
        r = await c.post('/api/account/login', json=PAYLOAD)
        print('status', r.status_code)
        try:
            data = r.json()
            print('r.json() ->', type(data), repr(data))
        except Exception as e:
            print('json error', e)
            print('text repr', repr(r.text))

asyncio.run(main())
