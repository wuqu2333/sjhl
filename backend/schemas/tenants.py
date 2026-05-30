from __future__ import annotations

from .common import FlexibleSchema


class TenantConnectionRequest(FlexibleSchema):
    id: str | None = None
    name: str | None = None
    authMode: str | None = None
    region: str | None = None
    tenantId: str | None = None
    clientId: str | None = None
    clientSecret: str | None = None
    refreshToken: str | None = None
    defaultRootPath: str | None = None
    importDocumentsOnly: bool | None = None


class TenantDiscoverRequest(FlexibleSchema):
    search: str | None = None
    documentsOnly: bool | None = None
    rootPath: str | None = None


class TenantSharePointMountRequest(FlexibleSchema):
    siteUrl: str
    libraryName: str | None = None
    rootPath: str | None = None
    documentsOnly: bool | None = None
