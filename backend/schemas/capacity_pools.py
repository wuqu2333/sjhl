from __future__ import annotations

from .common import FlexibleSchema


class CapacityPoolSaveRequest(FlexibleSchema):
    id: str | None = None
    name: str
