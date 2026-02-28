import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.runner import run_account

async def main():
    with open('config/accounts.json') as f:
        accounts = json.load(f)
    if not accounts:
        print('No accounts in config/accounts.json')
        return
    acc = accounts[0]
    usernames = ['instagram']
    print(f"Running E2E scrape for account: {acc['username']} -> {usernames}")
    await run_account(acc, usernames)

if __name__ == '__main__':
    asyncio.run(main())
