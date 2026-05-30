from __future__ import annotations

from .common import FlexibleSchema


class ProfileUpsertRequest(FlexibleSchema):
    id: str | None = None
    name: str | None = None
    authMode: str | None = None
    region: str | None = None
    tenantId: str | None = None
    clientId: str | None = None
    clientSecret: str | None = None
    refreshToken: str | None = None
    driveId: str | None = None
    siteId: str | None = None
    siteHostname: str | None = None
    sitePath: str | None = None
    libraryName: str | None = None
    rootPath: str | None = None
    capacityPoolId: str | None = None


class ProfileResponse(FlexibleSchema):
    profile: dict


class ProfileCapacityRequest(FlexibleSchema):
    capacityEnabled: bool


class ProfileCapacityPoolRequest(FlexibleSchema):
    capacityPoolId: str
