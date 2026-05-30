from __future__ import annotations

from fastapi import APIRouter, Depends

from core.container import AppContainer, get_container
from core.exceptions import raise_bad_request
from schemas.catalog import CatalogScanRequest
from task.catalog_scan import enqueue_catalog_scan


router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.post("/scan")
async def scan_catalog(body: CatalogScanRequest | None = None, container: AppContainer = Depends(get_container)):
    try:
        request = body.model_dump(exclude_none=True) if body else {}
        status = await container.catalog.scan_all(request.get("profileId") or "")
        return {"ok": True, "status": status}
    except Exception as error:
        raise_bad_request(error)
