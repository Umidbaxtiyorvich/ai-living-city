from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .runtime import runtime

# Frontend build output (Docker copies to /app/frontend/dist)
STATIC_ROOT = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Loading a large save blocks for several seconds — run off the event loop.
    await asyncio.to_thread(runtime.start)
    runtime._start_loop()
    try:
        yield
    finally:
        await runtime.stop()


app = FastAPI(title="AI Living City", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=512)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.websocket("/ws")
async def world_socket(websocket: WebSocket) -> None:
    await runtime.register(websocket)


def _mount_frontend() -> None:
    if not STATIC_ROOT.is_dir():
        return
    assets = STATIC_ROOT / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path == "ws":
            raise HTTPException(status_code=404)
        candidate = STATIC_ROOT / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = STATIC_ROOT / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404)


_mount_frontend()
