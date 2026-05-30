from __future__ import annotations

from .common import FlexibleSchema


class DriveFileItem(FlexibleSchema):
    id: str | None = None
    name: str = ""
    path: str = ""
    type: str = "file"
    size: int = 0
    childCount: int = 0
    mimeType: str = ""
    sha1: str = ""
    sha256: str = ""
    quickXorHash: str = ""
    lastModifiedDateTime: str = ""
    webUrl: str = ""
    downloadUrl: str = ""


class CreateFolderRequest(FlexibleSchema):
    path: str = ""
    name: str
    conflictBehavior: str = "rename"
