"""
City events and the emergency system (specification sections 26 and 27).

The event log is the city's history. It is append-only and persisted
immediately, unlike the world snapshot, because the story of who was born, who
married and what burned down is the part a player cares about keeping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..codec import decode_dataclass, encode


class EventType(StrEnum):
    # Life
    BIRTH = "birth"
    DEATH = "death"
    WEDDING = "wedding"
    BIRTHDAY = "birthday"
    GRADUATION = "graduation"
    HIRED = "hired"
    DISMISSED = "dismissed"
    MOVED_HOME = "moved_home"
    ARRIVED = "arrived"
    # City
    FESTIVAL = "festival"
    HOLIDAY = "holiday"
    BUILDING_STARTED = "building_started"
    BUILDING_COMPLETE = "building_complete"
    DISTRICT_OPENED = "district_opened"
    MAP_EXPANDED = "map_expanded"
    CITY_LEVEL_UP = "city_level_up"
    # Government
    PLAYER_COMMAND = "player_command"
    PRESIDENT_DECISION = "president_decision"
    POLICY_CHANGE = "policy_change"
    DECISION_REVIEWED = "decision_reviewed"
    # Trouble
    ROAD_ACCIDENT = "road_accident"
    FIRE = "fire"
    FLOOD = "flood"
    STORM = "storm"
    POWER_FAILURE = "power_failure"
    EPIDEMIC = "epidemic"
    ECONOMIC_CRISIS = "economic_crisis"
    FOOD_SHORTAGE = "food_shortage"
    HOUSING_SHORTAGE = "housing_shortage"
    JOB_SHORTAGE = "job_shortage"
    EMERGENCY_DECLARED = "emergency_declared"
    EMERGENCY_ENDED = "emergency_ended"


class Severity(StrEnum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


#: Events that put the city into emergency mode.
CRISIS_EVENTS = frozenset(
    {
        EventType.FIRE,
        EventType.FLOOD,
        EventType.EPIDEMIC,
        EventType.POWER_FAILURE,
        EventType.ECONOMIC_CRISIS,
    }
)


@dataclass(slots=True)
class Event:
    id: int
    tick: int
    day: int
    type: EventType
    severity: Severity
    text: str
    agent_ids: list[int] = field(default_factory=list)
    building_ids: list[int] = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "tick": self.tick,
            "day": self.day,
            "type": self.type,
            "severity": self.severity,
            "text": self.text,
            "agent_ids": list(self.agent_ids),
            "building_ids": list(self.building_ids),
            "data": self.data,
        }


class EventLog:
    """
    Append-only log with a bounded in-memory tail.

    Older entries are expected to have been persisted already; keeping the whole
    history in RAM would grow without limit over simulated decades.
    """

    def __init__(self, memory_limit: int = 2_000) -> None:
        self._events: list[Event] = []
        self._next_id = 1
        self.memory_limit = memory_limit
        #: Events added since the last drain, for streaming to clients.
        self._pending: list[Event] = []

    def record(
        self,
        tick: int,
        day: int,
        event_type: EventType,
        text: str,
        *,
        severity: Severity = Severity.INFO,
        agent_ids: list[int] | None = None,
        building_ids: list[int] | None = None,
        **data,
    ) -> Event:
        event = Event(
            id=self._next_id,
            tick=tick,
            day=day,
            type=event_type,
            severity=severity,
            text=text,
            agent_ids=agent_ids or [],
            building_ids=building_ids or [],
            data=data,
        )
        self._next_id += 1
        self._events.append(event)
        self._pending.append(event)

        if len(self._events) > self.memory_limit:
            del self._events[: len(self._events) - self.memory_limit]

        return event

    def drain_pending(self) -> list[Event]:
        """Returns and clears events not yet sent to clients."""
        pending = self._pending
        self._pending = []
        return pending

    def recent(self, count: int = 50, *, min_severity: Severity | None = None) -> list[Event]:
        events = self._events
        if min_severity is not None:
            order = list(Severity)
            floor = order.index(min_severity)
            events = [e for e in events if order.index(e.severity) >= floor]
        return events[-count:]

    def of_type(self, event_type: EventType, count: int = 50) -> list[Event]:
        return [e for e in self._events if e.type is event_type][-count:]

    @property
    def total(self) -> int:
        return self._next_id - 1

    def sync_next_id(self, value: int) -> None:
        self._next_id = max(self._next_id, value)

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> dict:
        """
        The retained tail of the log.

        Events older than `memory_limit` are already written to their own table
        by the repository, so a snapshot only needs what is still in memory —
        enough for the client's event feed to look continuous after a reload.
        """
        return {
            "next_id": self._next_id,
            "memory_limit": self.memory_limit,
            "events": [encode(event) for event in self._events],
        }

    @classmethod
    def restore(cls, data: dict) -> "EventLog":
        log = cls(memory_limit=int(data.get("memory_limit", 2_000)))
        log._events = [decode_dataclass(Event, item) for item in data.get("events", [])]
        log._next_id = int(data.get("next_id", len(log._events) + 1))
        return log


@dataclass(slots=True)
class Emergency:
    """An active crisis."""

    type: EventType
    declared_tick: int
    #: Simulated minutes the response is expected to take.
    duration_minutes: int
    text: str

    def expired(self, tick: int) -> bool:
        return tick - self.declared_tick >= self.duration_minutes

    def as_dict(self) -> dict:
        return {
            "type": self.type,
            "declared_tick": self.declared_tick,
            "duration_minutes": self.duration_minutes,
            "text": self.text,
        }


#: Responders each crisis calls out, and how long it lasts in simulated minutes.
EMERGENCY_RESPONSE: dict[EventType, tuple[tuple[str, ...], int]] = {
    EventType.FIRE: (("firefighter", "police", "doctor"), 240),
    EventType.FLOOD: (("firefighter", "police", "builder"), 1_440),
    EventType.EPIDEMIC: (("doctor", "nurse"), 4_320),
    EventType.POWER_FAILURE: (("electrician", "engineer"), 480),
    EventType.ECONOMIC_CRISIS: (("accountant", "manager"), 7_200),
}
