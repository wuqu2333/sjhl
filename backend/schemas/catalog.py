from __future__ import annotations

from .common import FlexibleSchema


class CatalogScanRequest(FlexibleSchema):
    profileId: str | None = ""
