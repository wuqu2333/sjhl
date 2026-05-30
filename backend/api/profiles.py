from __future__ import annotations

from fastapi import APIRouter, Depends

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.profiles import ProfileCapacityPoolRequest, ProfileCapacityRequest, ProfileUpsertRequest


router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("")
def save_profile(body: ProfileUpsertRequest, container: AppContainer = Depends(get_container)):
    try:
        return {"ok": True, "profile": container.profiles.upsert(body.model_dump(exclude_none=True))}
    except Exception as error:
        raise_bad_request(error)


@router.delete("/{profile_id}")
def remove_profile(profile_id: str, container: AppContainer = Depends(get_container)):
    container.profiles.remove(profile_id)
    return {"ok": True}


@router.patch("/{profile_id}/capacity")
def update_profile_capacity(profile_id: str, body: ProfileCapacityRequest, container: AppContainer = Depends(get_container)):
    try:
        return {
            "ok": True,
            "profile": container.profiles.set_capacity_enabled(profile_id, body.capacityEnabled),
        }
    except Exception as error:
        raise_bad_request(error)


@router.patch("/{profile_id}/capacity-pool")
def update_profile_capacity_pool(
    profile_id: str,
    body: ProfileCapacityPoolRequest,
    container: AppContainer = Depends(get_container),
):
    try:
        if not container.capacity_pools.get(body.capacityPoolId):
            raise ValueError("容量池不存在")
        return {
            "ok": True,
            "profile": container.profiles.set_capacity_pool(profile_id, body.capacityPoolId),
        }
    except Exception as error:
        raise_bad_request(error)
