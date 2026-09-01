"""
The president's day (specification section 6).

The routine decides *when* the president governs, not what it decides. Reports
are read in the morning, development planning happens in the afternoon, and
outside those windows the president is asleep, eating or with family — so the
city is not being re-planned at three in the morning.

A declared emergency replaces the routine entirely.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..clock import TimeOfDay


@dataclass(frozen=True, slots=True)
class ScheduleSlot:
    start_hour: int
    activity: str
    #: Whether the decision engine may run during this slot.
    governs: bool = False
    #: Where the president should be.
    location: str = "palace"


#: Ordered by start hour; the last slot whose hour has passed is the active one.
DAILY_ROUTINE: tuple[ScheduleSlot, ...] = (
    ScheduleSlot(0, "sleeping", location="palace"),
    ScheduleSlot(6, "waking_up", location="palace"),
    ScheduleSlot(7, "breakfast", location="palace"),
    ScheduleSlot(8, "government_office", governs=True, location="office"),
    ScheduleSlot(9, "reading_city_reports", governs=True, location="office"),
    ScheduleSlot(10, "meetings", governs=True, location="office"),
    ScheduleSlot(12, "lunch", location="office"),
    ScheduleSlot(13, "development_planning", governs=True, location="office"),
    ScheduleSlot(15, "inspections", governs=True, location="city"),
    ScheduleSlot(17, "citizen_meetings", governs=True, location="city"),
    ScheduleSlot(19, "family_time", location="palace"),
    ScheduleSlot(22, "sleeping", location="palace"),
)

#: What the president does during a crisis, at any hour.
EMERGENCY_ACTIVITY = "emergency_response"


def slot_for(now: TimeOfDay) -> ScheduleSlot:
    active = DAILY_ROUTINE[0]
    for slot in DAILY_ROUTINE:
        if now.hour >= slot.start_hour:
            active = slot
        else:
            break
    return active


def may_govern(now: TimeOfDay, *, in_emergency: bool) -> bool:
    """
    Whether the decision engine may run at this moment.

    During an emergency the answer is always yes: that is the whole point of
    declaring one.
    """
    if in_emergency:
        return True
    return slot_for(now).governs


def activity_for(now: TimeOfDay, *, in_emergency: bool) -> str:
    if in_emergency:
        return EMERGENCY_ACTIVITY
    return slot_for(now).activity


def location_for(now: TimeOfDay, *, in_emergency: bool) -> str:
    if in_emergency:
        return "city"
    return slot_for(now).location
