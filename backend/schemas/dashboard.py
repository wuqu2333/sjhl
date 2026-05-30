from __future__ import annotations

from .common import FlexibleSchema


class AppInfo(FlexibleSchema):
    name: str
    dataDir: str
    graphBaseUrl: str
    authBaseUrl: str
