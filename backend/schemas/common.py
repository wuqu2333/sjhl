from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlexibleSchema(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class OkResponse(FlexibleSchema):
    ok: bool = True


class ErrorResponse(FlexibleSchema):
    detail: str


class IdResponse(OkResponse):
    id: str


class EmptyBody(FlexibleSchema):
    pass


class ProfileSelector(FlexibleSchema):
    profile_id: str | None = Field(default=None, alias="profileId")


JsonDict = dict[str, Any]
