from __future__ import annotations

from fastapi import APIRouter, Depends

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.capacity import CapacityChoiceRequest


router = APIRouter(prefix="/capacity", tags=["capacity"])


@router.post("/choose")
def choose_capacity_target(body: CapacityChoiceRequest, container: AppContainer = Depends(get_container)):
    try:
        return {"ok": True, "profile": container.capacity.choose_profile(int(body.size or 0), body.poolId or "default")}
    except Exception as error:
        raise_bad_request(error)


@router.post("/refresh-all")
async def refresh_all_capacity(container: AppContainer = Depends(get_container)):
    results = []
    for profile in container.profiles.list(True):
        if not profile.get("driveId") or not profile.get("capacityEnabled", True):
            continue
        await container.capacity.refresh_quota(profile)
        results.append({"id": profile["id"], "name": profile["name"]})
    return {"ok": True, "refreshed": len(results)}
