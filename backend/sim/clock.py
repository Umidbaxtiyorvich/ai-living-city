"""
Simulation time.

Simulation time is fully decoupled from wall-clock time: one tick is one
simulated minute, and the speed multiplier decides how many ticks the engine
tries to run per real second. Everything downstream reasons in simulated
minutes, so changing speed never changes behaviour — only how fast you watch it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY
DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = DAYS_PER_MONTH * MONTHS_PER_YEAR

#: Real milliseconds per sim-minute at 1× — one sim-minute per real second
#: (smooth clock; one sim-day ≈ 24 real minutes at 1×).
REAL_MS_PER_TICK_AT_1X = 1_000.0

#: Cap per frame so time advances smoothly instead of in visible jumps.
MAX_TICKS_PER_STEP = 12


class Speed(IntEnum):
    """Allowed speed multipliers, per specification section 35."""

    PAUSED = 0
    X1 = 1
    X2 = 2
    X5 = 5
    X10 = 10
    X50 = 50
    X100 = 100

    @classmethod
    def parse(cls, value: int) -> "Speed":
        try:
            return cls(value)
        except ValueError as error:
            allowed = ", ".join(str(int(s)) for s in cls)
            raise ValueError(f"speed {value} is not one of: {allowed}") from error


@dataclass(slots=True)
class TimeOfDay:
    """A calendar reading derived from the tick counter."""

    year: int
    month: int
    day_of_month: int
    hour: int
    minute: int
    total_days: int

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day_of_month:02d} {self.hour:02d}:{self.minute:02d}"

    @property
    def minutes_since_midnight(self) -> int:
        return self.hour * MINUTES_PER_HOUR + self.minute

    @property
    def is_night(self) -> bool:
        return self.hour < 6 or self.hour >= 22

    @property
    def is_working_hours(self) -> bool:
        return 8 <= self.hour < 18


class Clock:
    """Owns the tick counter and the speed setting."""

    def __init__(self, start_year: int = 1, speed: Speed = Speed.X1) -> None:
        self.tick: int = 0
        self.speed: Speed = speed
        self._start_year = start_year
        #: Real-time debt carried between steps, so fractional ticks are not lost.
        self._accumulator_ms: float = 0.0

    # -- advancing ---------------------------------------------------------

    def ticks_due(self, elapsed_real_ms: float) -> int:
        """
        How many ticks should run for the real time that has passed.

        Returns 0 while paused. Caps at `MAX_TICKS_PER_STEP` and drops the
        remaining debt: falling behind permanently is worse than losing time,
        because the backlog would only grow.
        """
        if self.speed == Speed.PAUSED:
            self._accumulator_ms = 0.0
            return 0

        self._accumulator_ms += elapsed_real_ms * int(self.speed)
        due = int(self._accumulator_ms // REAL_MS_PER_TICK_AT_1X)
        self._accumulator_ms -= due * REAL_MS_PER_TICK_AT_1X

        if due > MAX_TICKS_PER_STEP:
            self._accumulator_ms = 0.0
            return MAX_TICKS_PER_STEP
        return due

    def advance(self, ticks: int = 1) -> None:
        self.tick += ticks

    # -- reading -----------------------------------------------------------

    @property
    def total_days(self) -> int:
        return self.tick // MINUTES_PER_DAY

    @property
    def now(self) -> TimeOfDay:
        minute_of_day = self.tick % MINUTES_PER_DAY
        days = self.total_days
        return TimeOfDay(
            year=self._start_year + days // DAYS_PER_YEAR,
            month=(days % DAYS_PER_YEAR) // DAYS_PER_MONTH + 1,
            day_of_month=days % DAYS_PER_MONTH + 1,
            hour=minute_of_day // MINUTES_PER_HOUR,
            minute=minute_of_day % MINUTES_PER_HOUR,
            total_days=days,
        )

    def is_new_day(self) -> bool:
        """True on the tick that crosses midnight."""
        return self.tick % MINUTES_PER_DAY == 0

    def is_new_month(self) -> bool:
        return self.is_new_day() and self.total_days % DAYS_PER_MONTH == 0

    def is_new_year(self) -> bool:
        return self.is_new_day() and self.total_days % DAYS_PER_YEAR == 0

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> dict:
        return {"tick": self.tick, "speed": int(self.speed), "start_year": self._start_year}

    @classmethod
    def restore(cls, data: dict) -> "Clock":
        clock = cls(start_year=data.get("start_year", 1), speed=Speed.parse(data.get("speed", 1)))
        clock.tick = data.get("tick", 0)
        return clock
