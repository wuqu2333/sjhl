from __future__ import annotations

from .common import FlexibleSchema


class CapacityChoiceRequest(FlexibleSchema):
    size: int | None = 0
    poolId: str | None = None
