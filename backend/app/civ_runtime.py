"""
Runs the civilization in real time and streams it to browsers.

Separate from the city runtime: only one of the two runs, chosen by
`WORLD_MODE`, so a deployment never pays for a simulation nobody watches.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from datetime import datetime, timedelta, timezone

from civ.catalog import BLUEPRINTS
from civ.engine import TASK_LABELS, Civilization
from civ.models import DAYS_PER_YEAR, MINUTES_PER_TICK, TICKS_PER_DAY

from .jsonutil import dumps

#: 1× is real time: one simulated second per real second, the clock in step
#: with Tashkent. The faster speeds are for watching generations pass.
SPEEDS = (0, 1, 10, 60, 360, 1440)
BROADCAST_INTERVAL = 0.1
TICK_SECONDS = MINUTES_PER_TICK * 60.0
TASHKENT = timezone(timedelta(hours=5))
#: How much missed time a restarted server catches up on.
MAX_CATCH_UP_SECONDS = 2 * 24 * 3600


def tashkent_minutes() -> int:
    now = datetime.now(TASHKENT)
    return now.hour * 60 + now.minute


def _save_path() -> Path:
    configured = os.environ.get("CIV_SAVE_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "civ_world.json"


class CivRuntime:
    def __init__(self) -> None:
        self.civ: Civilization | None = None
        self.speed = int(os.environ.get("DEFAULT_SPEED", "1") or 1)
        self._clients: set[WebSocket] = set()
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._sent_buildings = -1
        self._last_resources = 0.0
        self._last_save_day = 0
        self._debt = 0.0
        self.tick_ms = 0.0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        path = _save_path()
        if path.is_file():
            try:
                self.civ = Civilization.restore(json.loads(path.read_text(encoding="utf-8")))
                print(f"Tsivilizatsiya davom etadi: {self.civ.year}-yil, {len(self.civ.living)} kishi", flush=True)
            except Exception as error:  # a broken save must not stop the server
                print(f"Saqlangan dunyo o'qilmadi ({error}); yangi dunyo.", flush=True)
                self.civ = None
        if self.civ is None:
            self._new_world()
        else:
            self.civ.ensure_player()
            self._catch_up()
        self.civ.auto_move = False
        self._last_save_day = self.civ.day

    def _catch_up(self) -> None:
        """Life went on while the server slept: replay the missed hours, up to two days."""
        saved_at = getattr(self.civ, "saved_at", None)
        if not saved_at:
            return
        missed = min(MAX_CATCH_UP_SECONDS, max(0.0, time.time() - saved_at))
        ticks = int(missed // TICK_SECONDS)
        self.civ.auto_move = True
        for _ in range(ticks):
            self.civ.step()
        if ticks:
            print(f"Server uxlagan paytdagi {ticks * MINUTES_PER_TICK // 60} soat hayot tiklandi", flush=True)

    def _new_world(self, seed: int | None = None) -> None:
        seed = seed if seed is not None else int(os.environ.get("WORLD_SEED", "0") or 0) or int(time.time()) % 100000
        self.civ = Civilization(seed=seed, size=int(os.environ.get("CIV_MAP_SIZE", "96")))
        self.civ.genesis(start_minutes=tashkent_minutes())
        self.civ.auto_move = False
        print(f"Yangi dunyo yaratildi (urug' {seed}): 10 kishi", flush=True)

    def start_loop(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="civ-loop")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.save()

    async def save(self) -> dict:
        if self.civ is None:
            return {"saved": False}
        async with self._lock:
            data = self.civ.snapshot()
            data["saved_at"] = time.time()
        path = _save_path()

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
            tmp.replace(path)

        try:
            await asyncio.to_thread(write)
        except OSError as error:
            return {"saved": False, "error": str(error)}
        self._last_save_day = data["tick"] // TICKS_PER_DAY
        return {"saved": True, "year": self.civ.year}

    # -- loop --------------------------------------------------------------

    async def _loop(self) -> None:
        last = time.perf_counter()
        try:
            while True:
                await asyncio.sleep(BROADCAST_INTERVAL)
                now = time.perf_counter()
                elapsed = now - last
                last = now
                async with self._lock:
                    civ = self.civ
                    self._debt += min(elapsed, 1.0) * self.speed
                    started = time.perf_counter()
                    steps = 0
                    # Walk continuously; run a tick each time ten minutes have passed.
                    while self._debt > 0 and time.perf_counter() - started < 0.07:
                        to_tick = TICK_SECONDS - civ.subsecond
                        chunk = min(self._debt, to_tick, 120.0)
                        civ.move(chunk)
                        self._debt -= chunk
                        if chunk >= to_tick - 1e-6:
                            civ.step()
                            steps += 1
                    if self._debt > TICK_SECONDS * 4:
                        self._debt = 0.0
                    if steps:
                        self.tick_ms = (time.perf_counter() - started) * 1000 / steps
                    payload = self._frame()
                await self._broadcast(payload)
                if self.civ.day - self._last_save_day >= DAYS_PER_YEAR:
                    await self.save()
        except asyncio.CancelledError:
            return

    # -- payloads ----------------------------------------------------------

    def _common(self) -> dict[str, Any]:
        civ = self.civ
        return {
            "time": civ.time_payload(),
            "speed": self.speed,
            "people": [p.compact() for p in civ.people.values() if p.alive],
            "stats": {**civ.stats(), "tick_ms": round(self.tick_ms, 2)},
            "settlements": civ.settlements_payload(),
            "animals": [a.compact() for a in civ.animals.values()],
            "player_id": civ.player_id,
            "player_auto": bool(civ.player.auto) if civ.player else False,
        }

    def snapshot(self) -> dict[str, Any]:
        civ = self.civ
        civ.take_new_looks()
        civ.world.take_changes()
        self._sent_buildings = civ.buildings_version
        return {
            "kind": "snapshot",
            **self._common(),
            "world": {"width": civ.world.width, "height": civ.world.height, "terrain": civ.world.terrain_string()},
            "resources": civ.world.resource_payload(),
            "buildings": civ.buildings_payload(),
            "looks": [p.looks() for p in civ.people.values() if p.alive],
            "chronicle": civ.chronicle_payload(60),
            "labels": TASK_LABELS,
            "blueprints": [
                {
                    "kind": bp.kind, "name": bp.name, "wood": bp.wood, "stone": bp.stone,
                    "w": bp.width, "h": bp.height, "category": bp.category,
                    "known": all(r in civ.known for r in bp.requires),
                }
                for bp in BLUEPRINTS
            ],
        }

    def _frame(self) -> dict[str, Any]:
        civ = self.civ
        payload: dict[str, Any] = {"kind": "frame", **self._common()}
        looks = civ.take_new_looks()
        if looks:
            payload["looks"] = looks
        changes = civ.world.take_changes()
        if changes:
            payload["terrain_changes"] = changes
        now = time.perf_counter()
        if changes or now - self._last_resources > 2.0:
            if changes or now - self._last_resources > 6.0:
                payload["resources"] = civ.world.resource_payload()
                self._last_resources = now
        if civ.buildings_version != self._sent_buildings:
            self._sent_buildings = civ.buildings_version
            payload["buildings"] = civ.buildings_payload()
        payload["chronicle"] = civ.chronicle_payload(60)
        return payload

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        if not self._clients:
            return
        message = dumps(payload)
        dead = []
        for client in list(self._clients):
            try:
                await client.send_text(message)
            except Exception:
                dead.append(client)
        for client in dead:
            self._clients.discard(client)

    async def register(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            first = dumps(self.snapshot())
        self._clients.add(websocket)
        await websocket.send_text(first)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            self._clients.discard(websocket)

    # -- commands ----------------------------------------------------------

    async def set_speed(self, value: int) -> dict:
        self.speed = min(SPEEDS, key=lambda s: abs(s - value))
        return {"speed": self.speed}

    async def person(self, person_id: int) -> dict:
        person = self.civ.people.get(person_id)
        if person is None:
            return {"error": "not_found"}
        detail = person.detail()
        detail["task_label"] = TASK_LABELS.get(person.task, person.task)
        partner = self.civ.people.get(person.partner_id) if person.partner_id else None
        detail["partner"] = f"{partner.name} {partner.surname}" if partner else None
        settlement = self.civ.settlements.get(person.settlement_id) if person.settlement_id else None
        detail["settlement"] = settlement.name if settlement else None
        home = self.civ.buildings.get(person.home_id) if person.home_id else None
        detail["home"] = home.blueprint.name if home else None
        detail["alive"] = person.alive
        return detail

    async def player(self, action: str, **args: Any) -> dict:
        async with self._lock:
            civ = self.civ
            if action == "goto":
                return {"reply": civ.player_goto(float(args["x"]), float(args["y"]))}
            if action == "do":
                return {"reply": civ.player_do(str(args["what"]))}
            if action == "build":
                return civ.player_build(str(args["kind"]), int(args["x"]), int(args["y"]), bool(args.get("creative")))
            if action == "talk":
                return {"reply": civ.player_talk(int(args["id"]))}
            if action == "propose":
                return {"reply": civ.player_propose(int(args["id"]))}
        return {"reply": "Noma'lum buyruq"}

    async def reset(self) -> dict:
        async with self._lock:
            self._new_world()
            payload = self.snapshot()
        await self._broadcast(payload)
        await self.save()
        return {"ok": True}


civ_runtime = CivRuntime()
