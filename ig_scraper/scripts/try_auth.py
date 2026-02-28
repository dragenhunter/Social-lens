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
    for path in ['/api/TokenAuth/Authenticate', '/api/token-auth/authenticate', '/api/account/login', '/api/account/check-password', '/api/account/my-profile']:
        try:
            print('\nTrying', path)
            r = c.post(path, json={'userNameOrEmailAddress': API_USER, 'password': API_PASS, 'rememberMe': True})
            print('status', r.status_code)
            print('text', r.text[:1000])
        except Exception as e:
            print('error', e)
