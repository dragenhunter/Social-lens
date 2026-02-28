import asyncio
import os
import sys

# Ensure project root is importable when run from run_in_terminal
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from storage import api_client


def make_sample_post():
    return [
        {
            "externalId": "smoke-test-0001",
            "content": "Smoke test post - do not act on this",
            "postedAt": None,
            "platform": 3,
            "username": "smoke_test_user",
            "url": "http://example.com/smoke",
        }
    ]


async def main():
    print("Logging in and sending sample post to API...")
    await api_client.client.login()
    posts = make_sample_post()
    resp = await api_client.write_posts(posts)
    print("API response:", type(resp))
    print(resp)


if __name__ == "__main__":
    asyncio.run(main())
