"""
The citizen's mind — a local, deterministic "artificial consciousness".

Needs and emotions describe how an agent *feels*; the mind is what it *makes of
it*. Every citizen carries one, and it does four things no rule table did
before:

1. **Learns from experience.** Free time is no longer a fixed reflex. Each
   leisure choice is scored by how much happier the agent actually became, and
   the running estimate (a tiny temporal-difference learner) steers the next
   choice. Two agents with the same personality drift apart because they lived
   different lives.
2. **Wants things.** Goals — a career, a degree, savings, a family, friends,
   a home, health, mastery of a craft — are formed from personality and
   circumstance, tracked against the agent's real state, and replaced once
   achieved or abandoned.
3. **Improves itself.** Skills grow with practice at work; an agent whose
   ambitions outrun its schooling chooses to study, and enough study hours earn
   the next education level. Better education opens better jobs, which is how
   the population upgrades itself without anybody ordering it to.
4. **Reflects.** Once a day the agent looks back: notices how the day went,
   promotes what mattered to long-term memory, updates its goals, forms a wish
   about the city, and puts one line of inner monologue into words. Awareness —
   how much of this the agent can do — grows with reflection and lived memory.

The wishes are the bridge to the city: `sim.ai.voice` aggregates them and the
president reads the result as a concern of its own, so what citizens think
literally reshapes the map.

No LLM is involved. Everything here is cheap arithmetic seeded from the agent
itself, so a city of thousands reflects every day at 100x speed and a replay
reproduces the same thoughts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from ..jobs.professions import PROFESSIONS, Education
from ..memory.model import MemoryKind

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from ..agents.models import Agent

#: Activities the mind chooses between in free time. Kept as plain strings so
#: this module does not import the agent model it is a part of.
FREE_TIME_CHOICES: tuple[str, ...] = ("leisure", "socialising", "shopping", "studying")

#: Learning rate of the free-time value estimates.
LEARNING_RATE = 0.18

#: Ceiling for awareness and wisdom.
MAX_AWARENESS = 100.0

#: Study hours required to reach each education level from the one below it.
STUDY_HOURS_FOR: dict[Education, float] = {
    Education.SCHOOL: 120.0,
    Education.VOCATIONAL: 260.0,
    Education.UNIVERSITY: 520.0,
    Education.POSTGRADUATE: 900.0,
}

#: Skill points gained per hour of practice at work, before diminishing returns.
PRACTICE_RATE = 0.12

#: Skill points gained per hour of study.
STUDY_RATE = 0.2

#: Wishes below this urgency are not voiced to the city.
WISH_FLOOR = 0.15


class GoalKind(StrEnum):
    CAREER = "career"
    EDUCATION = "education"
    WEALTH = "wealth"
    FAMILY = "family"
    FRIENDSHIP = "friendship"
    HOME = "home"
    HEALTH = "health"
    MASTERY = "mastery"


GOAL_TEXT: dict[GoalKind, str] = {
    GoalKind.CAREER: "yaxshi ish topish",
    GoalKind.EDUCATION: "o'qib, yangi daraja olish",
    GoalKind.WEALTH: "pul jamg'arish",
    GoalKind.FAMILY: "oila qurish",
    GoalKind.FRIENDSHIP: "yaqin do'stlar orttirish",
    GoalKind.HOME: "o'z uyimga ega bo'lish",
    GoalKind.HEALTH: "sog'lig'imni tiklash",
    GoalKind.MASTERY: "kasbimda usta bo'lish",
}


class Wish(StrEnum):
    """What a citizen would like the city to provide."""

    HOUSING = "housing"
    JOBS = "jobs"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    PARKS = "parks"
    SHOPS = "shops"
    CULTURE = "culture"


WISH_TEXT: dict[Wish, str] = {
    Wish.HOUSING: "ko'proq uy-joy",
    Wish.JOBS: "yangi ish o'rinlari",
    Wish.HEALTHCARE: "yaqinroq shifoxona",
    Wish.EDUCATION: "ko'proq maktab va universitet",
    Wish.PARKS: "ko'proq park va dam olish joyi",
    Wish.SHOPS: "ko'proq do'kon",
    Wish.CULTURE: "kinoteatr va sport markazi",
}


@dataclass(slots=True)
class Goal:
    kind: GoalKind
    #: Numeric target whose meaning depends on the kind (money, skill, level...).
    target: float = 0.0
    progress: float = 0.0
    created_day: int = 0
    achieved_day: int | None = None
    abandoned: bool = False

    @property
    def active(self) -> bool:
        return self.achieved_day is None and not self.abandoned

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "text": GOAL_TEXT[self.kind],
            "target": round(self.target, 1),
            "progress": round(self.progress, 3),
            "created_day": self.created_day,
            "achieved_day": self.achieved_day,
            "abandoned": self.abandoned,
        }


def _default_preferences() -> dict[str, float]:
    return {choice: 0.0 for choice in FREE_TIME_CHOICES}


@dataclass(slots=True)
class Mind:
    #: 0..100. How much the agent understands itself; gates how well it plans.
    awareness: float = 8.0
    #: Lessons drawn from achieved and failed goals.
    wisdom: float = 0.0
    #: Learned value of each free-time activity, in happiness points per hour.
    preferences: dict[str, float] = field(default_factory=_default_preferences)
    goals: list[Goal] = field(default_factory=list)
    #: Latest inner monologue line, in Uzbek.
    thought: str = ""
    #: Study hours since the last education level.
    study_hours: float = 0.0
    #: Whole lifetime of study, for the inspector.
    total_study_hours: float = 0.0
    achievements: int = 0
    #: Wish → urgency 0..1, smoothed over days.
    wishes: dict[str, float] = field(default_factory=dict)
    #: Happiness at the last reflection, to judge the day.
    last_happiness: float = 60.0
    last_reflection_day: int = -1
    #: Days in a row the agent has been unemployed, for goal adaptation.
    idle_days: int = 0

    # -- reading -----------------------------------------------------------

    @property
    def active_goals(self) -> list[Goal]:
        return [goal for goal in self.goals if goal.active]

    def wants(self, kind: GoalKind) -> bool:
        return any(goal.kind is kind for goal in self.active_goals)

    def as_dict(self) -> dict:
        return {
            "awareness": round(self.awareness, 1),
            "wisdom": round(self.wisdom, 1),
            "thought": self.thought,
            "preferences": {k: round(v, 2) for k, v in self.preferences.items()},
            "goals": [goal.as_dict() for goal in self.active_goals],
            "achieved": [goal.as_dict() for goal in self.goals if goal.achieved_day is not None][-5:],
            "achievements": self.achievements,
            "study_hours": round(self.total_study_hours, 1),
            "wishes": {
                k: round(v, 2) for k, v in sorted(self.wishes.items(), key=lambda kv: -kv[1])
                if v >= WISH_FLOOR
            },
        }


# -- determinism -------------------------------------------------------------


def _noise(*parts: int) -> float:
    """Deterministic 0..1 from integers — no shared RNG stream to disturb."""
    value = 2166136261
    for part in parts:
        value ^= part & 0xFFFFFFFF
        value = (value * 16777619) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 2246822519) & 0xFFFFFFFF
    value ^= value >> 13
    return value / 0xFFFFFFFF


def _trait(agent: "Agent", name: str) -> float:
    return agent.personality.get(name, 0.5)


# -- 1. choosing -------------------------------------------------------------


def choose_free_time(
    agent: "Agent",
    *,
    bias: dict[str, float],
    stamp: int,
    can_study: bool,
) -> str:
    """
    Picks a free-time activity from emotion, learned value and goals.

    Exploration shrinks as awareness grows: a young mind tries things, a
    reflective one does what it has learned works — but never stops trying
    entirely, or a bad early experience would be final.
    """
    mind = agent.mind
    explore = max(0.05, 0.35 - mind.awareness / 300.0)

    scores: dict[str, float] = {}
    for choice in FREE_TIME_CHOICES:
        if choice == "studying" and not can_study:
            continue
        score = mind.preferences.get(choice, 0.0)
        if choice == "socialising":
            score += bias.get("socialise", 0.0) / 50.0 + _trait(agent, "extraversion") * 0.4
        elif choice == "leisure":
            score += bias.get("leisure", 0.0) / 50.0
        elif choice == "shopping":
            score += 0.15 if agent.money > 2_000 else -0.6
        elif choice == "studying":
            drive = 0.0
            if mind.wants(GoalKind.EDUCATION):
                drive += 0.9
            if mind.wants(GoalKind.MASTERY) or mind.wants(GoalKind.CAREER):
                drive += 0.35
            score += drive * (0.6 + _trait(agent, "conscientiousness") * 0.6)
        scores[choice] = score

    roll = _noise(agent.id, stamp)
    if roll < explore:
        options = sorted(scores)
        return options[int(_noise(agent.id, stamp, 7) * len(options)) % len(options)]
    return max(scores, key=lambda key: scores[key])


# -- 2. learning -------------------------------------------------------------


def learn(agent: "Agent", activity: str, happiness_gain: float, hours: float) -> None:
    """Updates the value estimate for `activity` from what it just did to happiness."""
    if activity not in FREE_TIME_CHOICES or hours <= 0:
        return
    mind = agent.mind
    reward = happiness_gain / hours
    current = mind.preferences.get(activity, 0.0)
    mind.preferences[activity] = round(current + LEARNING_RATE * (reward - current), 4)


def practice(agent: "Agent", hours: float) -> None:
    """Skill growth from doing the job — with diminishing returns near mastery."""
    if agent.profession is None or hours <= 0:
        return
    skill = PROFESSIONS[agent.profession].key_skill
    current = agent.skills.get(skill, 0.0)
    gain = PRACTICE_RATE * hours * (1.0 - current / 100.0) * (0.6 + _trait(agent, "conscientiousness"))
    agent.skills[skill] = min(100.0, current + gain)


def study(agent: "Agent", hours: float) -> Education | None:
    """
    Self-directed study. Returns the new education level when one is earned.

    The skill studied is the one the agent's career goal needs, or general
    knowledge otherwise, so studying is aimed rather than generic.
    """
    if hours <= 0:
        return None
    mind = agent.mind
    mind.study_hours += hours
    mind.total_study_hours += hours

    focus = "general"
    if agent.profession is not None:
        focus = PROFESSIONS[agent.profession].key_skill
    current = agent.skills.get(focus, 0.0)
    rate = STUDY_RATE * (0.7 + _trait(agent, "openness") * 0.6)
    agent.skills[focus] = min(100.0, current + rate * hours * (1.0 - current / 110.0))

    if agent.education >= Education.POSTGRADUATE:
        return None
    following = Education(int(agent.education) + 1)
    if mind.study_hours >= STUDY_HOURS_FOR[following]:
        mind.study_hours = 0.0
        agent.education = following
        return following
    return None


# -- 3. reflecting -----------------------------------------------------------


@dataclass(slots=True)
class CityView:
    """What a citizen can perceive of the city when it reflects."""

    day: int
    tick: int
    has_hospital: bool = True
    has_school: bool = True
    has_university: bool = False
    parks: int = 0
    shops: int = 0
    culture: int = 0
    population: int = 0
    vacancies: int = 0


@dataclass(slots=True)
class Reflection:
    """Notable outcomes of one reflection, for the event log."""

    achieved: list[GoalKind] = field(default_factory=list)
    new_goals: list[GoalKind] = field(default_factory=list)
    graduated: Education | None = None


def reflect(agent: "Agent", view: CityView) -> Reflection:
    """The daily look back. Cheap enough to run for every citizen."""
    mind = agent.mind
    outcome = Reflection()
    if mind.last_reflection_day == view.day:
        return outcome
    mind.last_reflection_day = view.day

    happiness = agent.happiness
    delta = happiness - mind.last_happiness
    mind.last_happiness = happiness
    mind.idle_days = mind.idle_days + 1 if agent.unemployed else 0

    # A memorable day leaves a memory; a reflective mind remembers more.
    if abs(delta) >= 8.0:
        text = "Bugun ajoyib kun bo'ldi" if delta > 0 else "Bugun og'ir kun bo'ldi"
        agent.memory.record(
            view.tick, MemoryKind.EMOTIONAL, text,
            importance=min(0.9, 0.3 + abs(delta) / 40.0 + mind.awareness / 400.0),
            delta=round(delta, 1),
        )

    # Awareness grows with reflection itself and with a richer life to reflect on.
    growth = 0.04 + agent.memory.size / 4000.0 + _trait(agent, "openness") * 0.05
    if agent.is_adult:
        growth *= 1.4
    mind.awareness = min(MAX_AWARENESS, mind.awareness + growth)

    # Offscreen life: statistical agents still practise their craft and study.
    if agent.detail == "statistical":
        if agent.employed:
            practice(agent, 6.0)
        if agent.is_adult and mind.wants(GoalKind.EDUCATION):
            outcome.graduated = study(agent, 1.5 + _trait(agent, "conscientiousness"))

    _update_goals(agent, view, outcome)
    _adapt_goals(agent, view, outcome)
    _update_wishes(agent, view)
    mind.thought = _compose_thought(agent, delta)
    return outcome


def _goal_progress(agent: "Agent", goal: Goal) -> float:
    kind = goal.kind
    if kind is GoalKind.CAREER:
        return 1.0 if agent.employed and agent.salary >= goal.target else (0.4 if agent.employed else 0.0)
    if kind is GoalKind.EDUCATION:
        span = max(1.0, goal.target - 0.0)
        partial = agent.mind.study_hours / max(1.0, STUDY_HOURS_FOR.get(Education(min(4, int(agent.education) + 1)), 1.0))
        return min(1.0, (int(agent.education) + min(0.99, partial)) / span)
    if kind is GoalKind.WEALTH:
        return max(0.0, min(1.0, agent.money / max(1.0, goal.target)))
    if kind is GoalKind.FAMILY:
        return 1.0 if agent.partner_id is not None else 0.0
    if kind is GoalKind.FRIENDSHIP:
        friends = sum(1 for value in agent.relationships.values() if value >= 40.0)
        return min(1.0, friends / max(1.0, goal.target))
    if kind is GoalKind.HOME:
        return 1.0 if agent.home_id is not None else 0.0
    if kind is GoalKind.HEALTH:
        return min(1.0, agent.needs.health / max(1.0, goal.target))
    if kind is GoalKind.MASTERY:
        if agent.profession is None:
            return 0.0
        skill = agent.skills.get(PROFESSIONS[agent.profession].key_skill, 0.0)
        return min(1.0, skill / max(1.0, goal.target))
    return 0.0


def _update_goals(agent: "Agent", view: CityView, outcome: Reflection) -> None:
    mind = agent.mind
    for goal in mind.active_goals:
        goal.progress = _goal_progress(agent, goal)
        if goal.progress >= 1.0:
            goal.achieved_day = view.day
            mind.achievements += 1
            mind.wisdom = min(MAX_AWARENESS, mind.wisdom + 3.0)
            mind.awareness = min(MAX_AWARENESS, mind.awareness + 1.5)
            agent.emotions.adjust(happiness=10.0, confidence=8.0, excitement=6.0)
            agent.memory.record(
                view.tick, MemoryKind.LONG_TERM,
                f"Maqsadimga erishdim: {GOAL_TEXT[goal.kind]}",
                importance=0.85, goal=str(goal.kind),
            )
            outcome.achieved.append(goal.kind)
        # A goal chased for a year without progress is let go — and learned from.
        elif view.day - goal.created_day > 360 and goal.progress < 0.3:
            goal.abandoned = True
            mind.wisdom = min(MAX_AWARENESS, mind.wisdom + 1.0)
            agent.emotions.adjust(sadness=4.0)

    # Keep the list bounded: old finished goals are history, not state.
    finished = [goal for goal in mind.goals if not goal.active]
    if len(finished) > 12:
        drop = set(id(goal) for goal in finished[: len(finished) - 12])
        mind.goals = [goal for goal in mind.goals if id(goal) not in drop]


def _add_goal(agent: "Agent", kind: GoalKind, target: float, view: CityView, outcome: Reflection) -> None:
    mind = agent.mind
    if mind.wants(kind):
        return
    mind.goals.append(Goal(kind=kind, target=target, created_day=view.day))
    outcome.new_goals.append(kind)


def _adapt_goals(agent: "Agent", view: CityView, outcome: Reflection) -> None:
    """Forms new goals from circumstance and temperament."""
    mind = agent.mind
    if agent.life_stage.value in ("baby", "toddler"):
        return

    ambition = _trait(agent, "ambition")
    # Circumstance first: what is missing right now.
    if agent.is_adult and agent.home_id is None:
        _add_goal(agent, GoalKind.HOME, 1.0, view, outcome)
    if agent.needs.health < 55.0:
        _add_goal(agent, GoalKind.HEALTH, 85.0, view, outcome)
    if agent.can_work and not agent.employed:
        _add_goal(agent, GoalKind.CAREER, 1.0, view, outcome)
        # Self-improvement: a long job search with little schooling means study.
        if mind.idle_days > 10 and agent.education < Education.UNIVERSITY:
            _add_goal(agent, GoalKind.EDUCATION, float(int(agent.education) + 1), view, outcome)

    if len(mind.active_goals) >= 3:
        return

    # Then temperament: what this person wants from life.
    roll = _noise(agent.id, view.day, 31)
    if agent.life_stage.value == "teenager" or (agent.is_adult and ambition > 0.6 and agent.education < Education.POSTGRADUATE and roll < 0.3):
        _add_goal(agent, GoalKind.EDUCATION, float(min(4, int(agent.education) + 1)), view, outcome)
    elif agent.employed and roll < 0.25 + ambition * 0.3:
        skill = agent.skills.get(PROFESSIONS[agent.profession].key_skill, 0.0) if agent.profession else 0.0
        _add_goal(agent, GoalKind.MASTERY, min(100.0, skill + 15.0), view, outcome)
    elif agent.is_adult and agent.partner_id is None and agent.age_years < 45 and roll < 0.6:
        _add_goal(agent, GoalKind.FAMILY, 1.0, view, outcome)
    elif _trait(agent, "extraversion") > 0.45 and roll < 0.75:
        _add_goal(agent, GoalKind.FRIENDSHIP, 2.0 + round(_trait(agent, "extraversion") * 3), view, outcome)
    elif agent.employed:
        _add_goal(agent, GoalKind.WEALTH, max(5_000.0, agent.money + agent.salary * (2 + ambition * 6)), view, outcome)
    # Higher-paying work is a career goal for the already employed and ambitious.
    if agent.employed and ambition > 0.7 and len(mind.active_goals) < 3:
        _add_goal(agent, GoalKind.CAREER, agent.salary * 1.25, view, outcome)


def _update_wishes(agent: "Agent", view: CityView) -> None:
    """Forms an opinion of what the city lacks — smoothed so a bad day is not a riot."""
    raw: dict[Wish, float] = {}
    if agent.home_id is None and agent.is_adult:
        raw[Wish.HOUSING] = 1.0
    if agent.unemployed:
        raw[Wish.JOBS] = min(1.0, 0.4 + agent.mind.idle_days / 30.0)
    if agent.needs.health < 60.0:
        raw[Wish.HEALTHCARE] = 0.8 if not view.has_hospital else 0.4
    if agent.is_school_age and agent.school_id is None:
        raw[Wish.EDUCATION] = 0.9
    if agent.mind.wants(GoalKind.EDUCATION) and not view.has_university:
        raw[Wish.EDUCATION] = max(raw.get(Wish.EDUCATION, 0.0), 0.6)
    per_thousand = max(1.0, view.population / 1000.0)
    if agent.needs.fun < 45.0 or view.parks / per_thousand < 3:
        raw[Wish.PARKS] = 0.5 if agent.needs.fun < 45.0 else 0.25
    if agent.needs.hunger < 45.0 or view.shops / per_thousand < 4:
        raw[Wish.SHOPS] = 0.45 if agent.needs.hunger < 45.0 else 0.2
    if view.culture == 0 and agent.is_adult and _trait(agent, "openness") > 0.5:
        raw[Wish.CULTURE] = 0.35

    wishes = agent.mind.wishes
    for wish in Wish:
        before = wishes.get(wish.value, 0.0)
        after = before + (raw.get(wish, 0.0) - before) * 0.25
        if after < 0.02:
            wishes.pop(wish.value, None)
        else:
            wishes[wish.value] = round(after, 3)


def _compose_thought(agent: "Agent", delta: float) -> str:
    """One line of inner monologue, chosen by what weighs on the mind most."""
    mind = agent.mind
    emotions = agent.emotions
    if agent.life_stage.value in ("baby", "toddler"):
        return "Hamma narsa qiziq va yangi."

    if agent.home_id is None and agent.is_adult:
        return "Boshpanam yo'q. Avval uy topishim kerak."
    if agent.needs.health < 45.0:
        return "Tobim yo'q... shifokorga borishim kerak."
    if emotions.loneliness > 60.0:
        return "O'zimni yolg'iz his qilyapman. Kim bilandir gaplashgim keladi."
    if emotions.stress > 65.0:
        return "Juda charchadim, hammasi ustma-ust kelyapti."

    goals = mind.active_goals
    if goals:
        focus = max(goals, key=lambda goal: goal.progress)
        if focus.progress >= 0.75:
            return f"Oz qoldi — tez orada {GOAL_TEXT[focus.kind]} niyatimga yetaman."
        if focus.kind is GoalKind.EDUCATION:
            return "Ko'proq o'qisam, kelajagim yorqinroq bo'ladi."
        if focus.kind is GoalKind.CAREER and agent.unemployed:
            return "Ish qidiryapman. Bilimimni oshirsam, imkoniyat ko'payadi."
        if focus.kind is GoalKind.MASTERY:
            return "Har kuni ishimni biroz yaxshiroq qilishga harakat qilaman."

    wishes = {k: v for k, v in mind.wishes.items() if v >= 0.3}
    if wishes:
        top = max(wishes, key=lambda key: wishes[key])
        return f"Shahrimizga {WISH_TEXT[Wish(top)]} kerak."

    if delta > 5.0:
        return "Bugun yaxshi kun bo'ldi. Hayot go'zal."
    if delta < -5.0:
        return "Bugun omadim kelmadi, ertaga yaxshiroq bo'ladi."
    favourite = max(mind.preferences, key=lambda key: mind.preferences[key])
    if mind.preferences.get(favourite, 0.0) > 0.5:
        return {
            "leisure": "Parkda sayr qilish menga kuch beradi.",
            "socialising": "Do'stlarim bilan vaqt o'tkazish eng yaxshisi.",
            "shopping": "Bozor aylanish kayfiyatimni ko'taradi.",
            "studying": "O'qish menga zavq beradi.",
        }.get(favourite, "Hammasi joyida.")
    return "Hammasi joyida. Yangi kun — yangi imkoniyat."
