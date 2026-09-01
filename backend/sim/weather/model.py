"""
Weather.

Kept simple but consequential: weather shifts how willing agents are to be
outdoors and nudges mood, and a storm can trigger a city event. Conditions
change on a daily cycle with seasonal temperature, which is enough to make the
city feel like it has a climate without simulating one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..clock import DAYS_PER_YEAR
from ..rng import Rng


class Condition(StrEnum):
    CLEAR = "clear"
    CLOUDY = "cloudy"
    RAIN = "rain"
    STORM = "storm"
    SNOW = "snow"
    FOG = "fog"
    HEAT = "heat"


#: How much each condition discourages being outside, 0..1.
OUTDOOR_PENALTY: dict[Condition, float] = {
    Condition.CLEAR: 0.0,
    Condition.CLOUDY: 0.05,
    Condition.FOG: 0.2,
    Condition.RAIN: 0.4,
    Condition.SNOW: 0.5,
    Condition.HEAT: 0.35,
    Condition.STORM: 0.8,
}

#: Mood effect per simulated hour of exposure.
MOOD_EFFECT: dict[Condition, dict[str, float]] = {
    Condition.CLEAR: {"happiness": 0.6, "excitement": 0.3},
    Condition.CLOUDY: {},
    Condition.FOG: {"sadness": 0.2},
    Condition.RAIN: {"sadness": 0.4, "happiness": -0.3},
    Condition.SNOW: {"excitement": 0.3, "happiness": -0.1},
    Condition.HEAT: {"stress": 0.5, "anger": 0.2},
    Condition.STORM: {"fear": 0.8, "stress": 0.6, "happiness": -0.5},
}


@dataclass(slots=True)
class Weather:
    condition: Condition = Condition.CLEAR
    #: Degrees Celsius.
    temperature: float = 20.0
    #: 0..1.
    wind: float = 0.2
    day_generated: int = -1

    @property
    def outdoor_penalty(self) -> float:
        return OUTDOOR_PENALTY[self.condition]

    @property
    def mood_effect(self) -> dict[str, float]:
        return MOOD_EFFECT[self.condition]

    def as_dict(self) -> dict:
        return {
            "condition": self.condition,
            "temperature": round(self.temperature, 1),
            "wind": round(self.wind, 2),
            "outdoor_penalty": round(self.outdoor_penalty, 2),
        }


def seasonal_temperature(day: int, rng: Rng) -> float:
    """
    Mean temperature for the day, following a yearly sine.

    Calibrated to a continental climate — hot summers, cold winters — which
    matches the setting and makes both HEAT and SNOW reachable.
    """
    import math

    phase = (day % DAYS_PER_YEAR) / DAYS_PER_YEAR
    # Peak in the middle of the year, trough at the ends.
    seasonal = math.sin((phase - 0.25) * 2 * math.pi)
    return 16.0 + seasonal * 18.0 + rng.number(-4.0, 4.0)


def roll_weather(day: int, rng: Rng) -> Weather:
    """
    Picks the day's weather, weighted by temperature.

    Snow is impossible above freezing and heat impossible below 30, so the
    condition is always consistent with the reading on the thermometer.
    """
    temperature = seasonal_temperature(day, rng)

    options: list[tuple[Condition, float]] = [
        (Condition.CLEAR, 5.0),
        (Condition.CLOUDY, 3.0),
        (Condition.RAIN, 2.0),
        (Condition.FOG, 0.8),
        (Condition.STORM, 0.4),
    ]
    if temperature <= 1.0:
        options.append((Condition.SNOW, 4.0))
    if temperature >= 30.0:
        options.append((Condition.HEAT, 4.0))

    condition = rng.weighted(options)
    return Weather(
        condition=condition,
        temperature=temperature,
        wind=round(rng.number(0.0, 0.6) + (0.4 if condition is Condition.STORM else 0.0), 2),
        day_generated=day,
    )
