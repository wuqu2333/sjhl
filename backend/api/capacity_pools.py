from __future__ import annotations

from fastapi import APIRouter, Depends

from app.stores import DEFAULT_CAPACITY_POOL_ID
from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.capacity_pools import CapacityPoolSaveRequest


router = APIRouter(prefix="/capacity-pools", tags=["capacity-pools"])


@router.get("")
def list_capacity_pools(container: AppContainer = Depends(get_container)):
    return {"ok": True, "pools": container.capacity_pools.list()}


@router.post("")
def save_capacity_pool(body: CapacityPoolSaveRequest, container: AppContainer = Depends(get_container)):
    try:
        return {"ok": True, "pool": container.capacity_pools.upsert(body.model_dump(exclude_none=True))}
    except Exception as error:
        raise_bad_request(error)


@router.delete("/{pool_id}")
def remove_capacity_pool(pool_id: str, container: AppContainer = Depends(get_container)):
    try:
        if pool_id == DEFAULT_CAPACITY_POOL_ID:
            raise ValueError("默认容量池不能删除")
        in_use = [
            profile
            for profile in container.profiles.list()
            if profile.get("capacityPoolId") == pool_id
        ]
        if in_use:
            raise ValueError("容量池仍有关联的 SP，请先把这些 SP 移动到其他容量池")
        container.capacity_pools.remove(pool_id)
        return {"ok": True}
    except Exception as error:
        raise_bad_request(error)
