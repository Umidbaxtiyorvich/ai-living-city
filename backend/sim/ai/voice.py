"""
The citizens' voice.

Each mind forms wishes about the city (`sim.ai.mind`). Individually they are
opinions; aggregated they are a mandate. This module turns thousands of private
wishes into a handful of numbers the president can rank against its own
indicators — the channel through which what people think changes what gets
built.

Kept separate from the president so the same pulse feeds the dashboard and so
the brain stays free of per-agent loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .mind import WISH_FLOOR, WISH_TEXT, Wish


@dataclass(slots=True)
class SocietyPulse:
    """A daily summary of the collective mind."""

    #: Wish → strength 0..1: mean urgency weighted by how many share it.
    voice: dict[str, float] = field(default_factory=dict)
    awareness: float = 0.0
    wisdom: float = 0.0
    achievements: int = 0
    studying_share: float = 0.0
    goals_active: int = 0
    #: A few representative thoughts, for the HUD ticker.
    thoughts: list[dict] = field(default_factory=list)

    def top_wish(self) -> tuple[Wish, float] | None:
        if not self.voice:
            return None
        key = max(self.voice, key=lambda name: self.voice[name])
        return Wish(key), self.voice[key]

    def as_dict(self) -> dict:
        return {
            "voice": [
                {"wish": key, "text": WISH_TEXT[Wish(key)], "strength": round(value, 3)}
                for key, value in sorted(self.voice.items(), key=lambda kv: -kv[1])
            ],
            "awareness": round(self.awareness, 1),
            "wisdom": round(self.wisdom, 1),
            "achievements": self.achievements,
            "studying_share": round(self.studying_share, 3),
            "goals_active": self.goals_active,
            "thoughts": self.thoughts,
        }


def listen(agents: Iterable) -> SocietyPulse:
    """Aggregates every living mind. Linear in population, run once a day."""
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    awareness = wisdom = 0.0
    achievements = goals = studying = 0
    population = 0
    thinkers: list = []

    for agent in agents:
        if not agent.alive:
            continue
        population += 1
        mind = agent.mind
        awareness += mind.awareness
        wisdom += mind.wisdom
        achievements += mind.achievements
        goals += len(mind.active_goals)
        if any(goal.kind.value == "education" for goal in mind.active_goals):
            studying += 1
        for wish, value in mind.wishes.items():
            if value < WISH_FLOOR:
                continue
            totals[wish] = totals.get(wish, 0.0) + value
            counts[wish] = counts.get(wish, 0) + 1
        if mind.thought and agent.is_adult:
            thinkers.append(agent)

    pulse = SocietyPulse()
    if population == 0:
        return pulse

    for wish, total in totals.items():
        share = counts[wish] / population
        mean = total / counts[wish]
        # A wish shared by a fifth of the city at full urgency reads as ~0.6.
        pulse.voice[wish] = round(min(1.0, mean * min(1.0, share * 3.0)), 3)

    pulse.awareness = awareness / population
    pulse.wisdom = wisdom / population
    pulse.achievements = achievements
    pulse.goals_active = goals
    pulse.studying_share = studying / population

    # The most self-aware voices are the ones worth showing.
    thinkers.sort(key=lambda agent: (-agent.mind.awareness, agent.id))
    pulse.thoughts = [
        {"id": agent.id, "name": agent.name, "thought": agent.mind.thought}
        for agent in thinkers[:6]
    ]
    return pulse
