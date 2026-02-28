import sys
import json
import os
from urllib import request, parse

BASE = os.getenv('API_BASE', 'http://localhost:5000').rstrip('/')
API_USER = os.getenv('API_USER', '')
API_PASS = os.getenv('API_PASS', '')
API_CLIENT_ID = os.getenv('API_CLIENT_ID', 'Lens_App')
API_SCOPE = os.getenv('API_SCOPE', 'Lens')

if not API_USER or not API_PASS:
    print('Set API_USER and API_PASS environment variables before running this script.')
    sys.exit(1)
# Try using httpx/requests if available, else urllib

try:
    import httpx
    client = httpx.Client()
    r = client.post(BASE + '/connect/token', data={'grant_type':'password','username':API_USER,'password':API_PASS,'client_id':API_CLIENT_ID,'scope':API_SCOPE}, headers={'Content-Type':'application/x-www-form-urlencoded'})
    try:
        j = r.json()
    except Exception:
        print('Token response text:', r.text)
        sys.exit(1)
    token = j.get('access_token')
    print('access_token received:', bool(token))
    if token:
        h = {'Authorization': f'Bearer {token}'}
        g = client.get(BASE + '/api/app/source?IsActive=True', headers=h)
        print('GET /api/app/source status:', g.status_code)
        try:
            print('body:', g.json())
        except Exception:
            print('body text:', g.text[:1000])
    client.close()
    sys.exit(0)
except Exception as e:
    pass

try:
    import requests
    r = requests.post(BASE + '/connect/token', data={'grant_type':'password','username':API_USER,'password':API_PASS,'client_id':API_CLIENT_ID,'scope':API_SCOPE}, headers={'Content-Type':'application/x-www-form-urlencoded'})
    try:
        j = r.json()
    except Exception:
        print('Token response text:', r.text)
        sys.exit(1)
    token = j.get('access_token')
    print('access_token received:', bool(token))
    if token:
        h = {'Authorization': f'Bearer {token}'}
        g = requests.get(BASE + '/api/app/source?IsActive=True', headers=h)
        print('GET /api/app/source status:', g.status_code)
        try:
            print('body:', g.json())
        except Exception:
            print('body text:', g.text[:1000])
    sys.exit(0)
except Exception as e:
    pass

# Fallback to urllib
try:
    data = parse.urlencode({'grant_type':'password','username':API_USER,'password':API_PASS,'client_id':API_CLIENT_ID,'scope':API_SCOPE}).encode()
    req = request.Request(BASE + '/connect/token', data=data, headers={'Content-Type':'application/x-www-form-urlencoded'})
    with request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode()
        try:
            j = json.loads(body)
        except Exception:
            print('Token response text:', body)
            sys.exit(1)
        token = j.get('access_token')
        print('access_token received:', bool(token))
    if token:
        req2 = request.Request(BASE + '/api/app/source?IsActive=True', headers={'Authorization': f'Bearer {token}'})
        with request.urlopen(req2, timeout=20) as g:
            body2 = g.read().decode()
            print('GET /api/app/source status: 200')
            try:
                print('body:', json.loads(body2))
            except Exception:
                print('body text:', body2[:1000])
except Exception as e:
    print('urllib failed:', e)
    sys.exit(1)
