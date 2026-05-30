from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config.settings import CORS_ORIGINS, ENABLE_API_DOCS, FRONTEND_DIST_DIR
from core.container import get_container
from core.router import api_router
from task.sync_scheduler import start_sync_scheduler


app = FastAPI(
    title="SJHL SP Manager API",
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.include_router(api_router)

if FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")


@app.get("/{path:path}", include_in_schema=False)
async def frontend_spa(path: str):
    if path.startswith(("api/", "api", "docs", "redoc", "openapi.json")):
        raise HTTPException(status_code=404)
    index_file = FRONTEND_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404)


@app.on_event("startup")
async def startup() -> None:
    get_container().jobs.start_scheduler()
    start_sync_scheduler(get_container().sync_engine)
