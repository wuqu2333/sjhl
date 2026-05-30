from __future__ import annotations

from .common import FlexibleSchema


class Pan115ApiDelayRequest(FlexibleSchema):
    globalMultiplier: float | int | str | None = None
    globalDelaySeconds: float | int | str | None = None
    listDelaySeconds: float | int | str | None = None
    renameDelaySeconds: float | int | str | None = None
    deleteDelaySeconds: float | int | str | None = None
    mutateDelaySeconds: float | int | str | None = None
    downDelaySeconds: float | int | str | None = None


class AppSettingsRequest(FlexibleSchema):
    dailyUploadLimitEnabled: bool | None = None
    dailyUploadLimitBytes: int | None = None
    transferConcurrency: int | str | None = None
    downloadDir: str | None = None
    minFreeSpaceGb: int | None = None
    pan115OpenApiDelay: Pan115ApiDelayRequest | None = None
    pan115CookieApiDelay: Pan115ApiDelayRequest | None = None
