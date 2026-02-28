import asyncio
from storage import api_client

async def main():
    try:
        print("Logging into Lens API...")
        await api_client.client.login()
        print("Logged in. Fetching sources...")
        sources = await api_client.fetch_sources()
        print("Fetched sources (type):", type(sources))
        # print a small summary
        if isinstance(sources, dict) and "items" in sources:
            print("Items count:", len(sources.get("items", [])))
        else:
            try:
                print("Length:", len(sources))
            except Exception:
                print(sources)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Smoke test failed:", e)

if __name__ == '__main__':
    asyncio.run(main())
