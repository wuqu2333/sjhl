from __future__ import annotations

import asyncio


async def sync_scheduler_loop(sync_engine, interval_seconds: int = 30) -> None:
    while True:
        await sync_engine.tick()
        await asyncio.sleep(interval_seconds)


def start_sync_scheduler(sync_engine, interval_seconds: int = 30) -> asyncio.Task:
    return asyncio.create_task(sync_scheduler_loop(sync_engine, interval_seconds))
