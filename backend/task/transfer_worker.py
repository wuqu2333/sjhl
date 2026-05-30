from __future__ import annotations

import asyncio


def enqueue_transfer_processing(job_queue) -> asyncio.Task:
    return asyncio.create_task(job_queue.process())
