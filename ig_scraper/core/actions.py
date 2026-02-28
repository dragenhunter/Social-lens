import asyncio, random
from config.settings import MIN_DELAY, MAX_DELAY

async def pause(mult=1.0):
    await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY) * mult)

async def scroll(page, steps=2):
    for _ in range(steps):
        await page.mouse.wheel(0, random.randint(800, 1400))
        await pause()
