from __future__ import annotations

import asyncio


def enqueue_catalog_scan(catalog_service, profile_id: str = "") -> asyncio.Task:
    return asyncio.create_task(catalog_service.scan_all(profile_id))
