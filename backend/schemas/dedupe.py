from __future__ import annotations

from .common import FlexibleSchema


class DedupeItem(FlexibleSchema):
    id: str
    algorithm: str
    hash: str
    size: int
    profile_id: str | None = ""
    remote_path: str | None = ""
