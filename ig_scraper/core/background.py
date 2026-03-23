import asyncio
import logging
from typing import Any


logger = logging.getLogger("ig_scraper.background")


def create_logged_task(coro: Any, description: str) -> asyncio.Task:
    task = asyncio.create_task(coro)

    def _log_failure(completed_task: asyncio.Task) -> None:
        try:
            completed_task.result()
        except asyncio.CancelledError:
            logger.info("Background task cancelled: %s", description)
        except Exception:
            logger.exception("Background task failed: %s", description)

    task.add_done_callback(_log_failure)
    return task