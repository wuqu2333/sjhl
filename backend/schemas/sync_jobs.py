from __future__ import annotations

from .common import FlexibleSchema


class SyncJobRequest(FlexibleSchema):
    id: str | None = None
    name: str | None = None
    enabled: bool | None = False
    sourceType: str | None = "local"
    syncMode: str | None = "add"
    intervalMinutes: int | None = 0
    scheduleTime: str | None = ""
    profileId: str | None = None
    sourcePath: str | None = ""
    sourceCid: str | None = "0"
    cookie: str | None = ""
    pan115AccountId: str | None = ""
    userAgent: str | None = ""
    targetDir: str | None = ""
    recursive: bool | None = True
    dedupeScope: str | None = "global"
