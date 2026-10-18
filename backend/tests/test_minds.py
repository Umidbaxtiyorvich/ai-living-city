"""Citizen minds, the collective voice, self-improving president and renewal."""

from __future__ import annotations

import json

from sim.agents.models import Agent, Gender
from sim.ai import mind as minds
from sim.ai.voice import listen
from sim.buildings.catalog import BuildingType
from sim.buildings.models import Building, BuildingStatus
from sim.codec import decode_dataclass, encode
from sim.jobs.professions import Education, Profession
from sim.president.brain import PresidentBrain
from sim.president.models import (
    Action,
    ActionKind,
    Concern,
    ConcernCode,
    Decision,
    DecisionStatus,
    President,
)
from sim.urban import renewal


def adult(agent_id: int = 1, **traits: float) -> Agent:
    personality = {
        "openness": 0.5, "conscientiousness": 0.5, "extraversion": 0.5,
        "agreeableness": 0.5, "ambition": 0.5, "resilience": 0.5,
    }
    personality.update(traits)
    return Agent(
        id=agent_id, name=f"Fuqaro {agent_id}", gender=Gender.FEMALE,
        age_days=30 * 360, personality=personality, education=Education.SCHOOL,
    )


def view(day: int = 1, **kwargs) -> minds.CityView:
    return minds.CityView(day=day, tick=day * 1440, **kwargs)


def test_learning_moves_preference_toward_experience():
    agent = adult()
    for _ in range(20):
        minds.learn(agent, "socialising", happiness_gain=4.0, hours=1.0)
        minds.learn(agent, "shopping", happiness_gain=-2.0, hours=1.0)
    assert agent.mind.preferences["socialising"] > 2.0
    assert agent.mind.preferences["shopping"] < -1.0


def test_learned_preference_steers_free_time():
    agent = adult()
    agent.mind.awareness = 100.0  # minimal exploration
    agent.mind.preferences["shopping"] = 5.0
    agent.money = 10_000
    picks = [
        minds.choose_free_time(agent, bias={"socialise": 0, "leisure": 0}, stamp=stamp, can_study=True)
        for stamp in range(200)
    ]
    assert picks.count("shopping") > 150


def test_study_earns_the_next_education_level():
    agent = adult()
    earned = None
    for _ in range(400):
        earned = minds.study(agent, 1.0) or earned
    assert earned is Education.VOCATIONAL
    assert agent.education is Education.VOCATIONAL
    assert agent.skills.get("general", 0) > 0


def test_practice_improves_the_job_skill_with_diminishing_returns():
    agent = adult()
    agent.profession = Profession.CHEF
    minds.practice(agent, 10.0)
    first = agent.skills["cooking"]
    agent.skills["cooking"] = 95.0
    minds.practice(agent, 10.0)
    assert first > 0
    assert agent.skills["cooking"] - 95.0 < first


def test_reflection_forms_goals_thoughts_and_awareness():
    agent = adult(ambition=0.9)
    before = agent.mind.awareness
    minds.reflect(agent, view(1))
    assert agent.mind.goals, "an unemployed adult should want something"
    assert any(goal.kind is minds.GoalKind.CAREER for goal in agent.mind.goals)
    assert agent.mind.thought
    assert agent.mind.awareness > before
    # Reflection is once a day.
    awareness = agent.mind.awareness
    minds.reflect(agent, view(1))
    assert agent.mind.awareness == awareness


def test_a_homeless_citizen_wishes_for_housing_and_the_city_hears_it():
    agents = [adult(i) for i in range(1, 11)]
    for _ in range(10):
        for day_agent in agents:
            minds.reflect(day_agent, view(day_agent.mind.last_reflection_day + 1, population=10))
    pulse = listen(agents)
    top = pulse.top_wish()
    assert top is not None
    assert top[0] is minds.Wish.HOUSING
    assert pulse.awareness > 0


def test_achieving_a_goal_is_remembered():
    agent = adult()
    agent.home_id = None
    minds.reflect(agent, view(1))
    assert agent.mind.wants(minds.GoalKind.HOME)
    agent.home_id = 42
    minds.reflect(agent, view(2))
    assert not agent.mind.wants(minds.GoalKind.HOME)
    assert agent.mind.achievements >= 1
    assert any("Maqsadimga" in entry.text for entry in agent.memory.recent_all(10))


def test_mind_survives_a_save():
    agent = adult()
    minds.reflect(agent, view(3))
    minds.learn(agent, "leisure", 3.0, 1.0)
    restored = decode_dataclass(Agent, json.loads(json.dumps(encode(agent))))
    assert restored.mind.as_dict() == agent.mind.as_dict()


def _decision(code: ConcernCode, before: float, after: float) -> Decision:
    concern = Concern(code=code, severity=before, description="x", action=Action(kind=ActionKind.WAIT))
    decision = Decision(id=1, tick=0, concern=concern, status=DecisionStatus.APPROVED, rationale="x")
    decision.severity_at_review = after
    return decision


def test_president_learns_which_policies_work():
    president = President(id=1, name="P", gender=Gender.MALE, age_days=40 * 360)
    brain = PresidentBrain()
    brain._learn(president, _decision(ConcernCode.HOUSING_SHORTAGE, 0.8, 0.2))
    brain._learn(president, _decision(ConcernCode.TRAFFIC_CONGESTION, 0.5, 0.6))
    assert president.weight_for(ConcernCode.HOUSING_SHORTAGE) > 1.0
    assert president.weight_for(ConcernCode.TRAFFIC_CONGESTION) < 1.0
    assert president.lessons_learned == 2


def _building(building_id: int, kind: BuildingType, condition: float) -> Building:
    return Building(
        id=building_id, type=kind, x=building_id * 4, y=0,
        status=BuildingStatus.OPEN, condition=condition,
    )


def test_renewal_redevelops_worn_houses_when_land_is_short():
    buildings = {1: _building(1, BuildingType.HOUSE, 50.0), 2: _building(2, BuildingType.SHOP, 90.0)}
    project = renewal.plan(
        buildings, unlocked=frozenset(BuildingType), spendable=10_000_000,
        housing_shortage=12, land_available=False,
    )
    assert project is not None
    assert project.kind == "redevelop"
    assert project.new_type is BuildingType.APARTMENT


def test_renewal_repairs_when_redevelopment_is_not_needed():
    buildings = {1: _building(1, BuildingType.FACTORY, 30.0)}
    project = renewal.plan(
        buildings, unlocked=frozenset(BuildingType), spendable=10_000_000,
        housing_shortage=0, land_available=True,
    )
    assert project is not None and project.kind == "repair"


def test_buildings_wear_out():
    buildings = {1: _building(1, BuildingType.HOUSE, 80.0)}
    renewal.wear(buildings)
    assert buildings[1].condition < 80.0
