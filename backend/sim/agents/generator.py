"""
Agent generation.

Attributes are random but internally consistent: education follows age (a child
cannot hold a degree), skills cluster around the agent's strengths instead of
being uniform noise, and emotional baselines follow personality. Everything
derives from the agent id, so the same citizen is reproduced exactly on reload.
"""

from __future__ import annotations

from ..clock import DAYS_PER_YEAR
from ..emotions.model import EMOTION_NAMES, Emotions
from ..jobs.professions import SKILLS, Education
from ..rng import Rng, RngRegistry
from .models import Agent, Gender, LifeStage, Needs, stage_for_age

#: Given names, split by gender.
MALE_NAMES: tuple[str, ...] = (
    "Aziz", "Bekzod", "Davron", "Eldor", "Farrux", "G'ayrat", "Hasan", "Ilhom",
    "Jasur", "Kamol", "Lutfulla", "Mirzo", "Nodir", "Otabek", "Qahramon",
    "Rustam", "Sardor", "Temur", "Ulug'bek", "Vohid", "Yusuf", "Zafar",
    "Anvar", "Bahodir", "Dilshod", "Erkin", "Fazliddin", "G'olib", "Husan",
    "Islom", "Jahongir", "Komil", "Mansur", "Nurbek", "Olim", "Rashid",
    "Shohruh", "Tohir", "Umid", "Xurshid", "Yodgor", "Zohid",
)

FEMALE_NAMES: tuple[str, ...] = (
    "Aziza", "Barno", "Dilnoza", "Elnora", "Feruza", "Gulnora", "Hulkar",
    "Iroda", "Jamila", "Kamola", "Lola", "Malika", "Nargiza", "Oysha",
    "Qunduz", "Ra'no", "Sevara", "Tursunoy", "Umida", "Vazira", "Yulduz",
    "Zulfiya", "Anora", "Bibisora", "Dildora", "Enajon", "Farida", "Gavhar",
    "Hilola", "Intizor", "Jasmina", "Komila", "Mohira", "Nilufar", "Ozoda",
    "Rayhona", "Shahnoza", "Tabassum", "Umirzoq", "Xadicha", "Yorqinoy", "Zebo",
)

#: Family names. Children inherit theirs from the family.
SURNAMES: tuple[str, ...] = (
    "Karimov", "Rasulov", "Yusupov", "Tosheva", "Nazarov", "Aliyev", "Sobirov",
    "Ergashev", "Qodirov", "Islomov", "Xolmatov", "Jo'rayev", "Mahmudov",
    "Saidov", "Tursunov", "Umarov", "Vohidov", "Yo'ldoshev", "Zaripov",
    "Abdullayev", "Bekmurodov", "Davlatov", "Faxriddinov", "G'ulomov",
)

#: Stable temperament traits, 0..1.
PERSONALITY_TRAITS: tuple[str, ...] = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "resilience",
    "ambition",
)

#: Education attainable by age. A degree takes time to earn.
EDUCATION_WEIGHTS_BY_AGE: tuple[tuple[int, tuple[tuple[Education, float], ...]], ...] = (
    (
        18,
        ((Education.NONE, 3), (Education.SCHOOL, 7)),
    ),
    (
        23,
        ((Education.SCHOOL, 6), (Education.VOCATIONAL, 4), (Education.UNIVERSITY, 1)),
    ),
    (
        30,
        (
            (Education.SCHOOL, 4),
            (Education.VOCATIONAL, 4),
            (Education.UNIVERSITY, 4),
            (Education.POSTGRADUATE, 1),
        ),
    ),
    (
        200,
        (
            (Education.NONE, 1),
            (Education.SCHOOL, 4),
            (Education.VOCATIONAL, 4),
            (Education.UNIVERSITY, 4),
            (Education.POSTGRADUATE, 1.5),
        ),
    ),
)


def _education_for_age(age_years: float, rng: Rng) -> Education:
    for upper, weights in EDUCATION_WEIGHTS_BY_AGE:
        if age_years < upper:
            return rng.weighted(list(weights))
    return Education.SCHOOL


def _skills_for(rng: Rng, education: Education, personality: dict[str, float]) -> dict[str, float]:
    """
    Aptitudes clustered around two or three strengths.

    Uniform random skills would make every agent an equally mediocre candidate
    for every job, which makes hiring meaningless. Picking a few specialities
    gives the recruitment code something to discriminate on.
    """
    base = 12.0 + int(education) * 6.0 + personality["conscientiousness"] * 15.0
    skills = {skill: max(0.0, rng.gaussian(base, 9.0)) for skill in SKILLS}

    for speciality in rng.sample(SKILLS, rng.integer(2, 3)):
        bonus = rng.number(25.0, 45.0) + personality["ambition"] * 15.0
        skills[speciality] = min(100.0, skills[speciality] + bonus)

    return {skill: round(min(100.0, value), 1) for skill, value in skills.items()}


def _personality(rng: Rng) -> dict[str, float]:
    return {trait: round(rng.number(0.05, 0.95), 3) for trait in PERSONALITY_TRAITS}


def _emotional_baseline(rng: Rng, personality: dict[str, float]) -> Emotions:
    """
    Emotional set-points shaped by temperament.

    Resilient agents sit lower on stress and fear; extraverts feel loneliness
    more sharply when alone. Baselines are where feelings return to, so this is
    what gives each citizen a lasting disposition.
    """
    resilience = personality["resilience"]
    extraversion = personality["extraversion"]

    emotions = Emotions(
        happiness=55.0 + resilience * 20.0 + rng.number(-6.0, 6.0),
        sadness=22.0 - resilience * 12.0 + rng.number(-4.0, 4.0),
        anger=16.0 - personality["agreeableness"] * 10.0 + rng.number(-4.0, 4.0),
        fear=18.0 - resilience * 10.0 + rng.number(-4.0, 4.0),
        love=20.0 + personality["agreeableness"] * 10.0,
        stress=26.0 - resilience * 14.0 + rng.number(-5.0, 5.0),
        pain=0.0,
        loneliness=14.0 + extraversion * 16.0 + rng.number(-4.0, 4.0),
        excitement=18.0 + personality["openness"] * 20.0,
        jealousy=10.0 - personality["agreeableness"] * 6.0 + rng.number(-2.0, 3.0),
        confidence=40.0 + personality["ambition"] * 25.0 + resilience * 10.0,
    )
    # Whatever was rolled becomes the set-point this agent drifts back toward.
    emotions.baseline = {name: getattr(emotions, name) for name in EMOTION_NAMES}
    return emotions


class AgentFactory:
    """Creates agents with ids from a shared counter."""

    def __init__(self, registry: RngRegistry, first_id: int = 1) -> None:
        self._registry = registry
        self._next_id = first_id

    @property
    def next_id(self) -> int:
        return self._next_id

    def reserve_id(self) -> int:
        agent_id = self._next_id
        self._next_id += 1
        return agent_id

    def sync_next_id(self, value: int) -> None:
        """Used after restoring a snapshot, so ids never collide."""
        self._next_id = max(self._next_id, value)

    def create(
        self,
        *,
        age_years: float | None = None,
        gender: Gender | None = None,
        surname: str | None = None,
        agent_id: int | None = None,
    ) -> Agent:
        identifier = agent_id if agent_id is not None else self.reserve_id()

        # Derived from the id alone: an agent regenerated after a reload is
        # identical, which is what keeps avatars and personalities stable.
        rng = self._registry.derived("agent", identifier)

        resolved_gender = gender or (Gender.MALE if rng.chance(0.5) else Gender.FEMALE)
        resolved_age = age_years if age_years is not None else self._working_age(rng)
        personality = _personality(rng)

        given = MALE_NAMES if resolved_gender is Gender.MALE else FEMALE_NAMES
        family_name = surname or rng.pick(SURNAMES)
        education = (
            _education_for_age(resolved_age, rng)
            if resolved_age >= 6
            else Education.NONE
        )

        agent = Agent(
            id=identifier,
            name=f"{rng.pick(given)} {family_name}",
            gender=resolved_gender,
            age_days=int(resolved_age * DAYS_PER_YEAR),
            avatar_seed=f"agent-{identifier}",
            appearance={"gender": resolved_gender.value},
            education=education,
            skills=_skills_for(rng, education, personality),
            personality=personality,
            emotions=_emotional_baseline(rng, personality),
            needs=Needs(
                energy=rng.number(60.0, 95.0),
                hunger=rng.number(55.0, 95.0),
                hygiene=rng.number(60.0, 95.0),
                social=rng.number(45.0, 85.0),
                fun=rng.number(45.0, 85.0),
                health=rng.number(80.0, 100.0),
            ),
            money=self._starting_money(rng, resolved_age),
        )
        return agent

    def create_child(self, *, surname: str, parent_ids: list[int], gender: Gender | None = None) -> Agent:
        """A newborn. Age zero, no schooling, no savings."""
        child = self.create(age_years=0.0, gender=gender, surname=surname)
        child.parent_ids = list(parent_ids)
        child.money = 0.0
        child.education = Education.NONE
        return child

    @staticmethod
    def _working_age(rng: Rng) -> float:
        """
        Age for a citizen arriving in the city.

        Weighted toward working age: newcomers are people who move for a job,
        not a demographically representative slice of a population.
        """
        return rng.weighted(
            [
                (rng.number(19.0, 29.0), 4.0),
                (rng.number(30.0, 44.0), 4.0),
                (rng.number(45.0, 59.0), 2.0),
                (rng.number(60.0, 72.0), 0.8),
            ]
        )

    @staticmethod
    def _starting_money(rng: Rng, age_years: float) -> float:
        if age_years < 18:
            return round(rng.number(0.0, 60.0), 2)
        # Older arrivals have had longer to accumulate savings.
        years_working = max(0.0, age_years - 18.0)
        return round(rng.number(400.0, 2_500.0) + years_working * rng.number(20.0, 120.0), 2)


def name_for_stage(agent: Agent) -> str:
    """Display label used by the debug panel."""
    if agent.life_stage in (LifeStage.BABY, LifeStage.TODDLER):
        return f"{agent.name} ({agent.life_stage})"
    return agent.name
