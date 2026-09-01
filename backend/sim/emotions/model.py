"""
Emotions.

Eleven scalar feelings on a 0..100 scale (specification section 22). They are
not decoration: `decision_bias` turns the emotional state into concrete nudges
that the behaviour code reads when choosing what an agent does next.

Emotions decay toward a personal baseline rather than toward zero, so a naturally
anxious agent stays anxious and a cheerful one recovers quickly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: All tracked feelings, in a fixed order for serialisation.
EMOTION_NAMES: tuple[str, ...] = (
    "happiness",
    "sadness",
    "anger",
    "fear",
    "love",
    "stress",
    "pain",
    "loneliness",
    "excitement",
    "jealousy",
    "confidence",
)

#: Fraction of the gap to the baseline closed per simulated hour.
DECAY_PER_HOUR = 0.12


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


@dataclass(slots=True)
class Emotions:
    happiness: float = 60.0
    sadness: float = 15.0
    anger: float = 10.0
    fear: float = 10.0
    love: float = 20.0
    stress: float = 20.0
    pain: float = 0.0
    loneliness: float = 20.0
    excitement: float = 25.0
    jealousy: float = 5.0
    confidence: float = 50.0

    #: Personal set-point each feeling drifts back to.
    baseline: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.baseline:
            self.baseline = {name: getattr(self, name) for name in EMOTION_NAMES}

    # -- reading -----------------------------------------------------------

    def as_dict(self) -> dict[str, float]:
        return {name: round(getattr(self, name), 2) for name in EMOTION_NAMES}

    @property
    def wellbeing(self) -> float:
        """
        A single 0..100 summary used for city-wide happiness reporting.

        Positive feelings lift it, negative ones drag it down, weighted so that
        pain and stress hurt more than mild sadness.
        """
        positive = self.happiness * 0.45 + self.confidence * 0.2 + self.love * 0.15 + self.excitement * 0.1
        negative = (
            self.sadness * 0.2
            + self.stress * 0.28
            + self.pain * 0.3
            + self.loneliness * 0.2
            + self.anger * 0.15
            + self.fear * 0.15
            + self.jealousy * 0.08
        )
        return _clamp(positive * 1.1 - negative * 0.55 + 20.0)

    # -- writing -----------------------------------------------------------

    def adjust(self, **deltas: float) -> None:
        for name, delta in deltas.items():
            if name not in EMOTION_NAMES:
                raise KeyError(f"unknown emotion {name!r}")
            setattr(self, name, _clamp(getattr(self, name) + delta))

    def decay(self, hours: float) -> None:
        rate = min(1.0, DECAY_PER_HOUR * hours)
        for name in EMOTION_NAMES:
            current = getattr(self, name)
            target = self.baseline.get(name, current)
            setattr(self, name, _clamp(current + (target - current) * rate))

    # -- influence on behaviour -------------------------------------------

    def decision_bias(self) -> dict[str, float]:
        """
        Multipliers the behaviour code applies when scoring options.

        Each stays near 1.0 so emotions colour decisions without overriding
        physical needs — a starving agent still eats, however sad it is.
        """
        return {
            # Lonely agents seek company; content ones are happy alone.
            "socialise": 1.0 + (self.loneliness - 20.0) / 100.0,
            # Stress and low confidence make job-seeking less likely.
            "seek_job": 1.0 + (self.confidence - 50.0) / 120.0 - self.stress / 200.0,
            # Excitement drives leisure, sadness suppresses it.
            "leisure": 1.0 + (self.excitement - 25.0) / 90.0 - self.sadness / 160.0,
            # Pain and fear push toward medical care.
            "seek_healthcare": 1.0 + (self.pain + self.fear) / 90.0,
            # Stressed and angry agents work less willingly.
            "work": 1.0 - (self.stress + self.anger) / 320.0,
        }

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> dict:
        return {"values": self.as_dict(), "baseline": self.baseline}

    @classmethod
    def restore(cls, data: dict) -> "Emotions":
        emotions = cls(**data.get("values", {}))
        emotions.baseline = data.get("baseline") or emotions.baseline
        return emotions
