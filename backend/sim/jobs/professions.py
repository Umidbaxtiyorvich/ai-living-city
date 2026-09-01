"""
Professions.

A profession carries the pay and the education it demands; where it is
practised is decided by the building catalogue, not here. Keeping the reference
one-directional avoids a circular import between jobs and buildings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Education(IntEnum):
    """Ordered so requirements can be compared with `>=`."""

    NONE = 0
    SCHOOL = 1
    VOCATIONAL = 2
    UNIVERSITY = 3
    POSTGRADUATE = 4


class Profession(StrEnum):
    """Specification section 8."""

    FARMER = "farmer"
    DOCTOR = "doctor"
    NURSE = "nurse"
    TEACHER = "teacher"
    ENGINEER = "engineer"
    DEVELOPER = "developer"
    BUILDER = "builder"
    ARCHITECT = "architect"
    POLICE = "police"
    FIREFIGHTER = "firefighter"
    DRIVER = "driver"
    SHOPKEEPER = "shopkeeper"
    CHEF = "chef"
    CLEANER = "cleaner"
    FACTORY_WORKER = "factory_worker"
    SCIENTIST = "scientist"
    ACCOUNTANT = "accountant"
    MANAGER = "manager"
    LAWYER = "lawyer"
    ELECTRICIAN = "electrician"
    PLUMBER = "plumber"
    MECHANIC = "mechanic"
    SECURITY = "security"
    GARDENER = "gardener"
    VETERINARIAN = "veterinarian"


@dataclass(frozen=True, slots=True)
class ProfessionSpec:
    profession: Profession
    #: Monthly pay in city currency, before taxes.
    base_salary: int
    education: Education
    #: Whether the city budget pays this wage (public sector) or a business does.
    public_sector: bool = False
    #: Skill the agent's aptitude is drawn against when hiring.
    key_skill: str = "general"


_SPECS: tuple[ProfessionSpec, ...] = (
    ProfessionSpec(Profession.FARMER, 1_800, Education.NONE, key_skill="agriculture"),
    ProfessionSpec(Profession.DOCTOR, 6_500, Education.POSTGRADUATE, True, "medicine"),
    ProfessionSpec(Profession.NURSE, 3_200, Education.VOCATIONAL, True, "medicine"),
    ProfessionSpec(Profession.TEACHER, 3_000, Education.UNIVERSITY, True, "teaching"),
    ProfessionSpec(Profession.ENGINEER, 5_000, Education.UNIVERSITY, key_skill="engineering"),
    ProfessionSpec(Profession.DEVELOPER, 5_500, Education.UNIVERSITY, key_skill="technology"),
    ProfessionSpec(Profession.BUILDER, 2_600, Education.NONE, key_skill="construction"),
    ProfessionSpec(Profession.ARCHITECT, 5_200, Education.UNIVERSITY, key_skill="construction"),
    ProfessionSpec(Profession.POLICE, 3_100, Education.VOCATIONAL, True, "security"),
    ProfessionSpec(Profession.FIREFIGHTER, 3_100, Education.VOCATIONAL, True, "security"),
    ProfessionSpec(Profession.DRIVER, 2_400, Education.SCHOOL, key_skill="driving"),
    ProfessionSpec(Profession.SHOPKEEPER, 2_500, Education.SCHOOL, key_skill="commerce"),
    ProfessionSpec(Profession.CHEF, 2_800, Education.VOCATIONAL, key_skill="cooking"),
    ProfessionSpec(Profession.CLEANER, 1_700, Education.NONE, key_skill="general"),
    ProfessionSpec(Profession.FACTORY_WORKER, 2_500, Education.NONE, key_skill="industry"),
    ProfessionSpec(Profession.SCIENTIST, 5_800, Education.POSTGRADUATE, True, "science"),
    ProfessionSpec(Profession.ACCOUNTANT, 3_800, Education.UNIVERSITY, key_skill="finance"),
    ProfessionSpec(Profession.MANAGER, 4_800, Education.UNIVERSITY, key_skill="leadership"),
    ProfessionSpec(Profession.LAWYER, 5_400, Education.UNIVERSITY, key_skill="law"),
    ProfessionSpec(Profession.ELECTRICIAN, 2_900, Education.VOCATIONAL, key_skill="engineering"),
    ProfessionSpec(Profession.PLUMBER, 2_800, Education.VOCATIONAL, key_skill="engineering"),
    ProfessionSpec(Profession.MECHANIC, 2_900, Education.VOCATIONAL, key_skill="engineering"),
    ProfessionSpec(Profession.SECURITY, 2_300, Education.SCHOOL, key_skill="security"),
    ProfessionSpec(Profession.GARDENER, 1_900, Education.NONE, key_skill="agriculture"),
    ProfessionSpec(Profession.VETERINARIAN, 4_200, Education.UNIVERSITY, key_skill="medicine"),
)

PROFESSIONS: dict[Profession, ProfessionSpec] = {spec.profession: spec for spec in _SPECS}

#: Uzbek names for anything the player reads. The enum values stay English
#: because they are identifiers in the API and the database.
LABELS: dict[Profession, str] = {
    Profession.FARMER: "fermer",
    Profession.DOCTOR: "shifokor",
    Profession.NURSE: "hamshira",
    Profession.TEACHER: "o'qituvchi",
    Profession.ENGINEER: "muhandis",
    Profession.DEVELOPER: "dasturchi",
    Profession.BUILDER: "quruvchi",
    Profession.ARCHITECT: "arxitektor",
    Profession.POLICE: "politsiyachi",
    Profession.FIREFIGHTER: "o't o'chiruvchi",
    Profession.DRIVER: "haydovchi",
    Profession.SHOPKEEPER: "sotuvchi",
    Profession.CHEF: "oshpaz",
    Profession.CLEANER: "farrosh",
    Profession.FACTORY_WORKER: "zavod ishchisi",
    Profession.SCIENTIST: "ilmiy xodim",
    Profession.ACCOUNTANT: "buxgalter",
    Profession.MANAGER: "menejer",
    Profession.LAWYER: "advokat",
    Profession.ELECTRICIAN: "elektrik",
    Profession.PLUMBER: "santexnik",
    Profession.MECHANIC: "mexanik",
    Profession.SECURITY: "qorovul",
    Profession.GARDENER: "bog'bon",
    Profession.VETERINARIAN: "veterinar",
}


def label_for(profession: Profession) -> str:
    return LABELS.get(profession, str(profession))

#: Every skill referenced by a profession. Agents are generated with an
#: aptitude in each, so hiring can compare candidates meaningfully.
SKILLS: tuple[str, ...] = tuple(sorted({spec.key_skill for spec in _SPECS}))


def spec_for(profession: Profession) -> ProfessionSpec:
    return PROFESSIONS[profession]


def professions_for_education(education: Education) -> list[Profession]:
    """Everything an agent with this schooling could plausibly do."""
    return [p for p, spec in PROFESSIONS.items() if spec.education <= education]


def _sanity_check() -> None:
    missing = set(Profession) - set(PROFESSIONS)
    if missing:
        raise RuntimeError(f"professions without a spec: {sorted(missing)}")

    unlabelled = set(Profession) - set(LABELS)
    if unlabelled:
        raise RuntimeError(f"professions without an Uzbek label: {sorted(unlabelled)}")


_sanity_check()
