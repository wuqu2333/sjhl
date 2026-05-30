from __future__ import annotations

from .common import FlexibleSchema


class WorkerProgressRequest(FlexibleSchema):
    downloaded: int = 0
    uploaded: int = 0
    total: int = 0
    percent: int = 0
    speed: int = 0


class WorkerFailedRequest(FlexibleSchema):
    error: str = ""
