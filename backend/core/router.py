from fastapi import APIRouter

from api import catalog, capacity, capacity_pools, dashboard, dedupe, files, oauth, pan115, profiles, settings, sync_jobs, tenants, transfers, worker


api_router = APIRouter(prefix="/api")
api_router.include_router(dashboard.router)
api_router.include_router(profiles.router)
api_router.include_router(tenants.router)
api_router.include_router(files.router)
api_router.include_router(capacity.router)
api_router.include_router(capacity_pools.router)
api_router.include_router(oauth.router)
api_router.include_router(transfers.router)
api_router.include_router(pan115.router)
api_router.include_router(dedupe.router)
api_router.include_router(catalog.router)
api_router.include_router(sync_jobs.router)
api_router.include_router(settings.router)
api_router.include_router(worker.router)
