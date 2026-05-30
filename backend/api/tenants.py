from __future__ import annotations

from fastapi import APIRouter, Depends

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.tenants import TenantConnectionRequest, TenantDiscoverRequest, TenantSharePointMountRequest


router = APIRouter(prefix="/tenant-connections", tags=["tenants"])


@router.post("")
def save_tenant(body: TenantConnectionRequest, container: AppContainer = Depends(get_container)):
    try:
        return {"ok": True, "connection": container.tenants.upsert(body.model_dump(exclude_none=True))}
    except Exception as error:
        raise_bad_request(error)


@router.delete("/{connection_id}")
def remove_tenant(connection_id: str, container: AppContainer = Depends(get_container)):
    container.tenants.remove(connection_id)
    return {"ok": True}


@router.post("/{connection_id}/discover")
async def discover_tenant(connection_id: str, body: TenantDiscoverRequest | None = None, container: AppContainer = Depends(get_container)):
    try:
        options = body.model_dump(exclude_none=True) if body else {}
        return {"ok": True, "drives": await container.discovery.discover(connection_id, options)}
    except Exception as error:
        raise_bad_request(error)


@router.post("/{connection_id}/import")
async def import_tenant(connection_id: str, body: TenantDiscoverRequest | None = None, container: AppContainer = Depends(get_container)):
    try:
        options = body.model_dump(exclude_none=True) if body else {}
        result = await container.discovery.import_discovered(connection_id, options)
        return {"ok": True, **result}
    except Exception as error:
        raise_bad_request(error)


@router.post("/{connection_id}/mount-sharepoint")
async def mount_sharepoint_site(
    connection_id: str,
    body: TenantSharePointMountRequest,
    container: AppContainer = Depends(get_container),
):
    try:
        result = await container.discovery.mount_sharepoint_site(connection_id, body.model_dump(exclude_none=True))
        return {"ok": True, **result}
    except Exception as error:
        raise_bad_request(error)
