"""
Owns the live city and the real-time loop.

The engine stays synchronous and deterministic. This module is the only place
that talks to the clock in wall time and to WebSocket clients.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from sim.clock import Speed
from sim.engine import Engine
from sim.events.model import EventType
from sim.state import SimulationConfig, WorldState

from .config import settings
from .db.repository import (
    capture,
    get_or_create_world,
    load_latest,
    metrics_series,
    write_capture,
)
from .db.schema import upgrade_to_head
from .db.session import session_scope
from .jsonutil import dumps, jsonable


class SpeedBody(BaseModel):
    value: int


class FollowBody(BaseModel):
    target: str | None = None


class CameraBody(BaseModel):
    x: float
    y: float


class MoneyBody(BaseModel):
    amount: float = Field(..., ge=-50_000_000, le=50_000_000)


class SpawnBody(BaseModel):
    count: int = Field(1, ge=1, le=40)


class CommandBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    agent_id: int | None = None


class RoleBody(BaseModel):
    role: str


class Runtime:
    def __init__(self) -> None:
        self.engine: Engine | None = None
        self._clients: set[WebSocket] = set()
        self._task: asyncio.Task[None] | None = None
        self._last_map_version = 0
        self._broadcast_counter = 0
        self.follow_president = False
        self._lock = asyncio.Lock()
        #: Simulated day of the last successful save.
        self._last_save_day = 0
        #: Set when persistence is unavailable, so the loop stops retrying and
        #: the failure is visible instead of silently dropping saves.
        self.persistence_error: str | None = None

    @property
    def state(self) -> WorldState:
        if self.engine is None:
            raise RuntimeError("simulation is not running")
        return self.engine.state

    def start(self, *, resume: bool = True) -> None:
        """
        Brings the city up, continuing the saved one when there is one.

        Does not start the async loop — call `_start_loop()` from the event
        loop thread after this returns.
        """
        state = self._resume() if resume else None
        if state is not None:
            engine = Engine(state)
            self._activate(engine, resumed=True, start_loop=False)
            return

        config = SimulationConfig(
            seed=settings.world_seed,
            map_size=settings.map_size,
            founding_population=settings.founding_population,
            starting_budget=settings.starting_budget,
            speed=Speed.parse(settings.default_speed),
        )
        state = WorldState.create(config)
        engine = Engine(state)
        engine.found_city()
        self._activate(engine, resumed=False, start_loop=False)

    def _activate(self, engine: Engine, *, resumed: bool, start_loop: bool = True) -> None:
        state = engine.state
        state.camera_focus = (state.grid.width / 2, state.grid.height / 2)
        # Only agents near the camera get full pathfinding — not the entire map.
        w = float(state.grid.width)
        state.config.full_detail_radius = min(55.0, max(28.0, w * 0.18))
        state.config.reduced_detail_radius = min(110.0, max(50.0, w * 0.34))
        state.clock.speed = Speed.parse(settings.default_speed)

        self.engine = engine
        engine.ensure_player_identity()
        self._last_map_version = state.map_version
        self._last_save_day = state.day
        if start_loop:
            self._start_loop()

        verb = "davom etadi" if resumed else "tayyor"
        print(
            f"Shahar {verb}: {state.day}-kun, {state.population} aholi, "
            f"{len(state.buildings)} bino, prezident {state.president.name if state.president else '-'}",
            flush=True,
        )

    def _start_loop(self) -> None:
        """Ensure exactly one simulation loop task is running."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            self._task = None
        self._task = asyncio.create_task(self._loop(), name="city-loop")

    async def _stop_loop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def _resume(self) -> WorldState | None:
        """The saved city, or None if this database has never held one."""
        upgrade_to_head()
        with session_scope() as session:
            return load_latest(session, settings.world_name)

    async def stop(self) -> None:
        await self._stop_loop()
        if self.engine is not None:
            # The world continues where it left off next time it is started.
            await self.save(reason="shutdown")

    # -- payloads ----------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        state = self.state
        return {
            "kind": "snapshot",
            "tiles": state.tile_payload(),
            "buildings": state.building_payload(),
            "agents": state.agent_payload(),
            "president": state.president.public_state() if state.president else None,
            "dashboard": state.dashboard_payload(),
        }

    def tick_payload(self, *, include_tiles: bool, include_buildings: bool) -> dict[str, Any]:
        state = self.state
        payload: dict[str, Any] = {
            "kind": "tick",
            "agents": state.agent_payload(),
            "president": state.president.public_state() if state.president else None,
            "dashboard": state.dashboard_payload(),
        }
        if include_buildings:
            payload["buildings"] = state.building_payload()
        if include_tiles:
            payload["tiles"] = state.tile_payload()
        return payload

    # -- loop --------------------------------------------------------------

    def _apply_follow(self) -> None:
        state = self.state
        if self.follow_president and state.president is not None:
            state.camera_focus = state.president.position
            return
        if state.followed_agent_id is None:
            return
        agent = state.agents.get(state.followed_agent_id)
        if agent is not None and agent.alive:
            state.camera_focus = agent.position

    async def _loop(self) -> None:
        last = time.perf_counter()
        try:
            while True:
                # ~30 FPS loop — smooth clock and responsive UI.
                await asyncio.sleep(0.033)
                now = time.perf_counter()
                elapsed_ms = (now - last) * 1000.0
                last = now

                async with self._lock:
                    self._apply_follow()
                    due = self.state.clock.ticks_due(elapsed_ms)
                    if due <= 0:
                        continue
                    speed = int(self.state.clock.speed)
                    # Small batches keep time flowing evenly instead of stuttering.
                    per_frame = 2 if speed <= 2 else 4 if speed <= 10 else 8
                    batch = min(due, per_frame)
                    deadline = time.perf_counter() + 0.028
                    for _ in range(batch):
                        self.engine.tick()
                        if time.perf_counter() >= deadline:
                            break
                    include_tiles = self.state.map_version != self._last_map_version
                    if include_tiles:
                        self._last_map_version = self.state.map_version
                    self._broadcast_counter += 1
                    include_buildings = include_tiles or self._broadcast_counter % 4 == 0
                    payload = self.tick_payload(
                        include_tiles=include_tiles,
                        include_buildings=include_buildings,
                    )

                await self.broadcast(payload)
                await self._autosave_if_due()
        except asyncio.CancelledError:
            return

    async def _autosave_if_due(self) -> None:
        if self.persistence_error is not None or settings.autosave_days <= 0:
            return
        if self.state.day - self._last_save_day < settings.autosave_days:
            return
        await self.save(reason="autosave")

    async def broadcast(self, payload: dict[str, Any]) -> None:
        if not self._clients:
            return
        message = dumps(payload)
        dead: list[WebSocket] = []
        for client in list(self._clients):
            try:
                await client.send_text(message)
            except Exception:
                dead.append(client)
        for client in dead:
            self._clients.discard(client)

    async def register(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        await websocket.send_text(dumps(self.snapshot()))
        try:
            while True:
                # Client messages are optional; the loop is server-driven.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            self._clients.discard(websocket)

    # -- persistence -------------------------------------------------------

    async def save(self, *, reason: str = "manual") -> dict[str, Any]:
        """
        Writes the city to the database.

        The snapshot is taken under the lock so it cannot capture a half-applied
        tick, but the write itself runs in a worker thread: a large city takes
        long enough to serialise that doing it inline would stall the loop and
        every connected client with it.
        """
        async with self._lock:
            data = capture(self.state)

        def write() -> int:
            with session_scope() as session:
                snapshot = write_capture(
                    session,
                    data,
                    name=settings.world_name,
                    reason=reason,
                    history_limit=settings.snapshot_history,
                )
                return snapshot.id

        try:
            snapshot_id = await asyncio.to_thread(write)
        except Exception as error:  # pragma: no cover - depends on the backend
            self.persistence_error = f"{type(error).__name__}: {error}"
            print(f"Saqlash muvaffaqiyatsiz: {self.persistence_error}", flush=True)
            return {"saved": False, "error": self.persistence_error}

        self._last_save_day = data.day
        self.persistence_error = None
        return {
            "saved": True,
            "snapshot_id": snapshot_id,
            "day": data.day,
            "tick": data.tick,
            "reason": reason,
        }

    async def history(self, limit: int = 365) -> dict[str, Any]:
        """Daily indicators from the database, for the dashboard's charts."""

        def read() -> list[dict]:
            with session_scope() as session:
                world = get_or_create_world(
                    session, settings.world_name, self.state.config.seed
                )
                return metrics_series(session, world.id, limit=limit)

        return {"metrics": await asyncio.to_thread(read)}

    # -- commands ----------------------------------------------------------

    async def set_speed(self, value: int) -> dict[str, Any]:
        async with self._lock:
            self.state.clock.speed = Speed.parse(value)
        return {"speed": int(self.state.clock.speed)}

    async def set_follow(self, target: str | None) -> dict[str, Any]:
        async with self._lock:
            self.follow_president = False
            self.state.followed_agent_id = None
            if target in (None, "", "none"):
                pass
            elif target == "president":
                self.follow_president = True
                if self.state.president is not None:
                    self.state.camera_focus = self.state.president.position
            else:
                agent_id = int(target)
                self.state.followed_agent_id = agent_id
                agent = self.state.agents.get(agent_id)
                if agent is not None:
                    self.state.camera_focus = agent.position
        return {
            "follow_president": self.follow_president,
            "followed_agent_id": self.state.followed_agent_id,
        }

    async def set_camera(self, x: float, y: float) -> dict[str, Any]:
        async with self._lock:
            self.state.camera_focus = (x, y)
        return {"camera": {"x": x, "y": y}}

    async def agent_detail(self, agent_id: int) -> dict[str, Any]:
        agent = self.state.agents.get(agent_id)
        if agent is None or not agent.alive:
            return {"error": "agent_not_found"}
        return jsonable(agent.detail_state())

    async def add_money(self, amount: float) -> dict[str, Any]:
        async with self._lock:
            self.state.economy.budget += amount
        return {"budget": self.state.economy.budget}

    async def spawn_people(self, count: int) -> dict[str, Any]:
        async with self._lock:
            names: list[str] = []
            for _ in range(count):
                agent = self.state.spawn_citizen()
                names.append(agent.name)
        return {"spawned": names, "population": self.state.population}

    async def declare_storm(self) -> dict[str, Any]:
        async with self._lock:
            self.engine.declare_emergency(
                EventType.STORM,
                "Favqulodda holat: kuchli bo'ron",
                duration_minutes=180,
            )
        return {"emergency": True}

    async def reset_city(self) -> dict[str, Any]:
        """Found a fresh city with the Egregoria-inspired road network."""
        await self._stop_loop()
        async with self._lock:
            config = SimulationConfig(
                seed=settings.world_seed,
                map_size=settings.map_size,
                founding_population=settings.founding_population,
                starting_budget=settings.starting_budget,
                speed=Speed.parse(settings.default_speed),
            )
            state = WorldState.create(config)
            engine = Engine(state)
            engine.found_city()
            self.engine = engine
            engine.ensure_player_identity()
            self._last_map_version = state.map_version
            self._last_save_day = 0
            state.clock.speed = Speed.parse(settings.default_speed)
            payload = self.snapshot()
        self._start_loop()
        await self.broadcast(payload)
        save_result = await self.save(reason="reset")
        return {
            "ok": True,
            "reply": "Yangi shahar yaratildi — organik yo'l tarmog'i bilan.",
            "population": self.state.population,
            "saved": save_result.get("saved", False),
        }

    async def player_command(
        self,
        text: str,
        agent_id: int | None = None,
        upload_path: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            return self.engine.handle_player_command(
                text, agent_id=agent_id, upload_path=upload_path, filename=filename,
            )

    async def set_role(self, role: str) -> dict[str, Any]:
        async with self._lock:
            try:
                player = self.engine.set_player_role(role)
            except ValueError as error:
                return {"error": str(error)}
        return {"player": player}


runtime = Runtime()
