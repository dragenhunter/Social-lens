"""Lightweight async worker pool.

Provides a simple concurrency primitive for scheduling coroutines with
bounded concurrency. Intended for small-scale use in the scraper where
an executor-like interface is helpful.
"""

import asyncio
from typing import Callable, Any


class AsyncWorkerPool:
    def __init__(self, size: int):
        self._size = max(1, int(size))
        self._sema = asyncio.Semaphore(self._size)
        self._tasks = set()
        self._closed = False

    async def _run_task(self, coro):
        async with self._sema:
            try:
                return await coro
            except Exception:
                raise

    def submit(self, coro) -> asyncio.Task:
        """Schedule a coroutine for execution under the pool's concurrency.

        Returns an asyncio.Task object that can be awaited.
        """
        if self._closed:
            raise RuntimeError("pool is closed")
        task = asyncio.create_task(self._run_task(coro))
        self._tasks.add(task)

        def _on_done(t):
            self._tasks.discard(t)

        task.add_done_callback(_on_done)
        return task

    async def shutdown(self, wait: bool = True):
        """Close the pool. If `wait` is True, await remaining tasks."""
        self._closed = True
        if wait and self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


def create_pool(size: int):
    return AsyncWorkerPool(size)

