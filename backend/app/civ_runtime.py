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

from . import civ_store
from .jsonutil import dumps

#: 1× is real time: one simulated second per real second, the clock in step
#: with Tashkent. The faster speeds are for watching generations pass.
SPEEDS = (0, 1, 10, 60, 100, 360, 1440)
BROADCAST_INTERVAL = 0.1
TICK_SECONDS = MINUTES_PER_TICK * 60.0
#: The 100× button is "a year a second": one game year (12 days) per real second.
YEAR_SECONDS = DAYS_PER_YEAR * 24 * 3600.0
#: Above this many simulated seconds per real second, people are moved once per
#: tick instead of continuously — at a year a second nobody can see the steps.
FAST_RATE = 3600.0


def sim_rate(speed: int) -> float:
    """Simulated seconds per real second for a speed button."""
    return YEAR_SECONDS if speed == 100 else float(speed)
TASHKENT = timezone(timedelta(hours=5))
#: Real seconds between saves. Frequent enough that a deploy or crash loses
#: at most a minute of history; the file is written atomically.
#: Free databases bill by awake time, so hosts set CIV_SAVE_EVERY higher there;
#: a shutdown or redeploy always saves regardless.
SAVE_EVERY_SECONDS = float(os.environ.get("CIV_SAVE_EVERY", "60"))
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
        self._last_buildings = 0.0
        self._signatures: dict[str, str] = {}
        #: Per browser: the newest unsent frame and a wake-up for its sender.
        self._outbox: dict[WebSocket, dict] = {}
        self._last_save_day = 0
        self._last_save_time = time.time()
        self._debt = 0.0
        self.tick_ms = 0.0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        try:
            data = self._read_saved()
            if data is not None:
                self.civ = Civilization.restore(data)
                where = "bazadan" if civ_store.enabled() else "fayldan"
                print(f"Tsivilizatsiya davom etadi ({where}): {self.civ.year}-yil, {len(self.civ.living)} kishi", flush=True)
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

    @staticmethod
    def _read_saved() -> dict | None:
        """The saved world: from the database when one is configured, else the file."""
        if civ_store.enabled():
            return civ_store.load()
        path = _save_path()
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

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
            if civ_store.enabled():
                civ_store.save(data)
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
            tmp.replace(path)

        try:
            await asyncio.to_thread(write)
        except Exception as error:  # a failed save is reported, never fatal
            print(f"Saqlash muvaffaqiyatsiz: {error}", flush=True)
            return {"saved": False, "error": str(error)}
        self._last_save_day = data["tick"] // TICKS_PER_DAY
        self._last_save_time = time.time()
        return {"saved": True, "year": self.civ.year}

    # -- loop --------------------------------------------------------------

    async def _loop(self) -> None:
        last = time.perf_counter()
        last_broadcast = 0.0
        try:
            while True:
                rate = sim_rate(self.speed)
                fast = rate > FAST_RATE
                # In year-a-second mode the loop runs almost flat out and only
                # broadcasts ten times a second.
                await asyncio.sleep(0.004 if fast else BROADCAST_INTERVAL)
                now = time.perf_counter()
                elapsed = now - last
                last = now
                async with self._lock:
                    civ = self.civ
                    self._debt += min(elapsed, 1.0) * rate
                    started = time.perf_counter()
                    steps = 0
                    if fast:
                        civ.auto_move = True
                        while self._debt >= TICK_SECONDS and time.perf_counter() - started < 0.09:
                            civ.step()
                            self._debt -= TICK_SECONDS
                            steps += 1
                        civ.auto_move = False
                        # If the machine cannot keep up, run as fast as it can
                        # rather than building an endless backlog.
                        self._debt = min(self._debt, rate * 0.5)
                    else:
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
                    due = now - last_broadcast >= BROADCAST_INTERVAL
                    payload = self._frame() if due else None
                if payload is not None:
                    last_broadcast = now
                    await self._broadcast(payload)
                if time.time() - self._last_save_time >= SAVE_EVERY_SECONDS:
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
            "petitions": civ.petitions_payload(),
            "customs": civ.customs_payload(),
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
        # Heavy lists go out only when they changed, and at most once a second:
        # at a year a second they change on every frame.
        if (changes and now - self._last_resources > 1.0) or now - self._last_resources > 6.0:
            payload["resources"] = civ.world.resource_payload()
            self._last_resources = now
        if civ.buildings_version != self._sent_buildings and now - self._last_buildings > 1.0:
            self._sent_buildings = civ.buildings_version
            self._last_buildings = now
            payload["buildings"] = civ.buildings_payload()
        for key, build in (
            ("chronicle", lambda: civ.chronicle_payload(60)),
            ("petitions", civ.petitions_payload),
            ("customs", civ.customs_payload),
        ):
            value = build()
            signature = dumps(value)
            if self._signatures.get(key) != signature:
                self._signatures[key] = signature
                payload[key] = value
        return payload

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        """
        Hands the frame to every browser's outbox.

        A slow browser never builds a backlog: if its previous frame has not
        gone out yet, the two are merged — incremental parts (terrain changes,
        new faces) are kept, everything else is simply the newer state.
        Without this a busy tab fell minutes behind and kept replaying the past.
        """
        for client in list(self._clients):
            box = self._outbox.get(client)
            if box is None:
                continue
            pending = box.get("payload")
            if pending is not None:
                merged = dict(payload)
                for key in ("terrain_changes", "looks"):
                    if key in pending:
                        merged[key] = pending[key] + payload.get(key, [])
                for key in ("buildings", "resources", "chronicle", "petitions", "customs", "world", "blueprints", "labels"):
                    if key in pending and key not in payload:
                        merged[key] = pending[key]
                if pending.get("kind") == "snapshot":
                    merged["kind"] = "snapshot"
                payload_to_send = merged
            else:
                payload_to_send = payload
            box["payload"] = payload_to_send
            box["event"].set()

    async def _sender(self, websocket: WebSocket, box: dict) -> None:
        try:
            while True:
                await box["event"].wait()
                box["event"].clear()
                payload = box.pop("payload", None)
                if payload is None:
                    continue
                await websocket.send_text(dumps(payload))
        except Exception:
            self._clients.discard(websocket)

    async def register(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            first = self.snapshot()
        box: dict = {"event": asyncio.Event(), "payload": first}
        box["event"].set()
        self._outbox[websocket] = box
        self._clients.add(websocket)
        sender = asyncio.create_task(self._sender(websocket, box))
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            self._clients.discard(websocket)
            self._outbox.pop(websocket, None)

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
            if action == "say":
                return civ.leader_says(
                    str(args["text"]),
                    petition_id=int(args["petition"]) if args.get("petition") else None,
                    person_id=int(args["id"]) if args.get("id") else None,
                )
        return {"reply": "Noma'lum buyruq"}

    async def reset(self) -> dict:
        async with self._lock:
            self._new_world()
            self._signatures.clear()
            payload = self.snapshot()
        await self._broadcast(payload)
        await self.save()
        return {"ok": True}


civ_runtime = CivRuntime()
