import httpx
import os
from dotenv import load_dotenv
load_dotenv()
API_BASE = os.getenv('API_BASE','http://localhost:5000').rstrip('/')
API_USER = os.getenv('API_USER','')
API_PASS = os.getenv('API_PASS','')

if not API_USER or not API_PASS:
    raise SystemExit('Set API_USER and API_PASS environment variables before running this script.')

with httpx.Client(base_url=API_BASE, timeout=20.0) as c:
    r = c.post('/api/account/login', json={
        'userNameOrEmailAddress': API_USER,
        'password': API_PASS,
        'rememberMe': True
    })
    print('status', r.status_code)
    print('text:', r.text[:2000])
    try:
        print('json:', r.json())
    except Exception as e:
        print('json parse error', e)
    # use same client (cookies) to fetch sources
    try:
        print('\nFetching sources via /api/app/scraper/sources')
        s = c.get('/api/app/scraper/sources')
        if s.status_code == 404:
            s = c.get('/api/app/sources', params={'IsActive': 'True'})
        print('sources status', s.status_code)
        try:
            print('sources json:', s.json())
        except Exception:
            print('sources text:', s.text[:1000])
    except Exception as e:
        print('fetch sources error', e)
