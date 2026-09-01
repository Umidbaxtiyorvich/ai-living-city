from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from sim.desks import UPLOAD_DIR, ensure_upload_dir
from sim.workshop import WORKSHOP_DIR

from ..runtime import (
    CameraBody,
    CommandBody,
    FollowBody,
    MoneyBody,
    RoleBody,
    SpawnBody,
    SpeedBody,
    runtime,
)
from ..jsonutil import jsonable

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.get("/snapshot")
def snapshot() -> dict:
    return jsonable(runtime.snapshot())


@router.get("/agent/{agent_id}")
async def agent_detail(agent_id: int) -> dict:
    payload = await runtime.agent_detail(agent_id)
    if payload.get("error"):
        raise HTTPException(status_code=404, detail="Agent topilmadi")
    return payload


@router.post("/speed")
async def set_speed(body: SpeedBody) -> dict:
    try:
        return await runtime.set_speed(body.value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/follow")
async def set_follow(body: FollowBody) -> dict:
    try:
        return await runtime.set_follow(body.target)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/camera")
async def set_camera(body: CameraBody) -> dict:
    return await runtime.set_camera(body.x, body.y)


@router.post("/admin/money")
async def add_money(body: MoneyBody) -> dict:
    return await runtime.add_money(body.amount)


@router.post("/admin/spawn")
async def spawn(body: SpawnBody) -> dict:
    return await runtime.spawn_people(body.count)


@router.post("/admin/emergency")
async def emergency() -> dict:
    return await runtime.declare_storm()


@router.post("/admin/reset")
async def reset_city() -> dict:
    return await runtime.reset_city()


@router.post("/command")
async def player_command(body: CommandBody) -> dict:
    return await runtime.player_command(body.text, agent_id=body.agent_id)


@router.post("/assignment")
async def assignment(
    text: str = Form(""),
    agent_id: int | None = Form(None),
    file: UploadFile | None = File(None),
) -> dict:
    upload_path = None
    filename = None
    if file is not None and file.filename:
        folder = ensure_upload_dir()
        safe = Path(file.filename).name
        dest = folder / f"in_{int(runtime.state.tick)}_{safe}"
        dest.write_bytes(await file.read())
        upload_path = str(dest)
        filename = safe
    if not (text or "").strip() and not filename:
        raise HTTPException(status_code=400, detail="Matn yoki fayl kerak")
    return await runtime.player_command(
        text or filename or "",
        agent_id=agent_id,
        upload_path=upload_path,
        filename=filename,
    )


@router.get("/files/{name}")
def download_file(name: str):
    folder = UPLOAD_DIR.resolve()
    path = (folder / Path(name).name).resolve()
    try:
        path.relative_to(folder)
    except ValueError:
        raise HTTPException(status_code=404, detail="Fayl topilmadi") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fayl topilmadi")
    return FileResponse(path)


@router.get("/workshop/{name}")
def workshop_file(name: str):
    folder = WORKSHOP_DIR.resolve()
    path = (folder / Path(name).name).resolve()
    try:
        path.relative_to(folder)
    except ValueError:
        raise HTTPException(status_code=404, detail="Fayl topilmadi") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fayl topilmadi")
    return FileResponse(path, media_type="text/plain; charset=utf-8")


@router.post("/role")
async def set_role(body: RoleBody) -> dict:
    result = await runtime.set_role(body.role)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/save")
async def save() -> dict:
    result = await runtime.save(reason="manual")
    if not result.get("saved"):
        raise HTTPException(status_code=503, detail=result.get("error", "Saqlash imkonsiz"))
    return result


@router.get("/history")
async def history(days: int = 365) -> dict:
    return await runtime.history(limit=max(1, min(days, 5_000)))
