"""
Building catalogue.

One table describing every building the city can contain: how much land it
takes, what it costs, how long it takes to build, how many people it houses or
employs, and what service capacity it contributes. The president's decision
engine reads this table rather than hard-coding numbers, so balancing the city
is a matter of editing data here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..jobs.professions import Profession
from ..world.tiles import District


class BuildingCategory(StrEnum):
    RESIDENTIAL = "residential"
    GOVERNMENT = "government"
    EDUCATION = "education"
    HEALTH = "health"
    BUSINESS = "business"
    INDUSTRY = "industry"
    ENTERTAINMENT = "entertainment"
    INFRASTRUCTURE = "infrastructure"


class BuildingType(StrEnum):
    """Specification section 15."""

    # Residential
    HOUSE = "house"
    TOWNHOUSE = "townhouse"
    APARTMENT = "apartment"
    # Government
    CITY_HALL = "city_hall"
    PRESIDENTIAL_PALACE = "presidential_palace"
    COURTHOUSE = "courthouse"
    POLICE_STATION = "police_station"
    FIRE_STATION = "fire_station"
    # Education
    KINDERGARTEN = "kindergarten"
    SCHOOL = "school"
    UNIVERSITY = "university"
    # Health
    CLINIC = "clinic"
    HOSPITAL = "hospital"
    PHARMACY = "pharmacy"
    # Business
    SHOP = "shop"
    MARKET = "market"
    CAFE = "cafe"
    RESTAURANT = "restaurant"
    OFFICE = "office"
    # Industry
    FARM = "farm"
    FACTORY = "factory"
    WAREHOUSE = "warehouse"
    POWER_PLANT = "power_plant"
    # Entertainment
    PARK = "park"
    ZOO = "zoo"
    CINEMA = "cinema"
    SPORT_CENTER = "sport_center"
    # Infrastructure
    BUS_STOP = "bus_stop"
    TRAIN_STATION = "train_station"


@dataclass(frozen=True, slots=True)
class BuildingSpec:
    type: BuildingType
    category: BuildingCategory
    #: Footprint in tiles.
    width: int
    height: int
    construction_cost: int
    #: Simulated days of construction work (specification section 16).
    build_days: int
    #: Budget drain per simulated month once open.
    upkeep: int
    #: Residents it can house. Only residential buildings are non-zero.
    residents: int = 0
    #: Job slots by profession.
    jobs: dict[Profession, int] = field(default_factory=dict)
    #: Preferred zoning. The president looks for land here first.
    district: District = District.UNZONED
    #: Service capacity the building contributes, read by the needs analysis:
    #: hospital beds, school seats, retail throughput, food or power units.
    hospital_beds: int = 0
    school_seats: int = 0
    retail_capacity: int = 0
    food_output: int = 0
    power_output: int = 0
    #: How strongly the building lifts nearby happiness.
    amenity: float = 0.0
    #: Height in metres, for the renderer.
    levels: int = 1


def _spec(**kwargs) -> BuildingSpec:
    return BuildingSpec(**kwargs)


_CATALOG: tuple[BuildingSpec, ...] = (
    # -- Residential -------------------------------------------------------
    _spec(
        type=BuildingType.HOUSE,
        category=BuildingCategory.RESIDENTIAL,
        width=2, height=2,
        construction_cost=45_000, build_days=2, upkeep=120,
        residents=4, district=District.RESIDENTIAL, levels=1,
    ),
    _spec(
        type=BuildingType.TOWNHOUSE,
        category=BuildingCategory.RESIDENTIAL,
        width=2, height=3,
        construction_cost=90_000, build_days=4, upkeep=220,
        residents=8, district=District.RESIDENTIAL, levels=2,
    ),
    _spec(
        type=BuildingType.APARTMENT,
        category=BuildingCategory.RESIDENTIAL,
        width=3, height=3,
        construction_cost=280_000, build_days=10, upkeep=700,
        residents=32, district=District.RESIDENTIAL, levels=5,
    ),
    # -- Government --------------------------------------------------------
    _spec(
        type=BuildingType.PRESIDENTIAL_PALACE,
        category=BuildingCategory.GOVERNMENT,
        width=6, height=6,
        construction_cost=1_500_000, build_days=45, upkeep=4_000,
        jobs={Profession.MANAGER: 6, Profession.SECURITY: 8, Profession.CLEANER: 4},
        district=District.CITY_CENTER, amenity=0.4, levels=3,
    ),
    _spec(
        type=BuildingType.CITY_HALL,
        category=BuildingCategory.GOVERNMENT,
        width=4, height=4,
        construction_cost=600_000, build_days=25, upkeep=2_200,
        # The city hall employs the public works crew: builders have to be
        # hired somewhere, otherwise construction never rises above the
        # contracted base rate and the project queue jams permanently.
        jobs={
            Profession.MANAGER: 4, Profession.ACCOUNTANT: 6, Profession.LAWYER: 3,
            Profession.BUILDER: 12,
        },
        district=District.CITY_CENTER, amenity=0.2, levels=3,
    ),
    _spec(
        type=BuildingType.COURTHOUSE,
        category=BuildingCategory.GOVERNMENT,
        width=4, height=3,
        construction_cost=420_000, build_days=20, upkeep=1_500,
        jobs={Profession.LAWYER: 8, Profession.SECURITY: 4},
        district=District.CITY_CENTER, levels=2,
    ),
    _spec(
        type=BuildingType.POLICE_STATION,
        category=BuildingCategory.GOVERNMENT,
        width=3, height=3,
        construction_cost=260_000, build_days=12, upkeep=1_800,
        jobs={Profession.POLICE: 20, Profession.MANAGER: 2},
        district=District.CITY_CENTER, levels=2,
    ),
    _spec(
        type=BuildingType.FIRE_STATION,
        category=BuildingCategory.GOVERNMENT,
        width=3, height=3,
        construction_cost=240_000, build_days=12, upkeep=1_700,
        jobs={Profession.FIREFIGHTER: 18, Profession.MECHANIC: 2},
        district=District.CITY_CENTER, levels=2,
    ),
    # -- Education ---------------------------------------------------------
    _spec(
        type=BuildingType.KINDERGARTEN,
        category=BuildingCategory.EDUCATION,
        width=3, height=2,
        construction_cost=130_000, build_days=5, upkeep=800,
        jobs={Profession.TEACHER: 6, Profession.CLEANER: 2},
        district=District.SCHOOL, school_seats=60, amenity=0.2, levels=1,
    ),
    _spec(
        type=BuildingType.SCHOOL,
        category=BuildingCategory.EDUCATION,
        width=4, height=4,
        construction_cost=320_000, build_days=7, upkeep=1_900,
        jobs={Profession.TEACHER: 15, Profession.CLEANER: 4, Profession.MANAGER: 2},
        district=District.SCHOOL, school_seats=400, amenity=0.3, levels=2,
    ),
    _spec(
        type=BuildingType.UNIVERSITY,
        category=BuildingCategory.EDUCATION,
        width=6, height=5,
        construction_cost=1_100_000, build_days=30, upkeep=5_500,
        jobs={Profession.TEACHER: 30, Profession.SCIENTIST: 20, Profession.CLEANER: 8},
        district=District.SCHOOL, school_seats=1_200, amenity=0.4, levels=3,
    ),
    # -- Health ------------------------------------------------------------
    _spec(
        type=BuildingType.CLINIC,
        category=BuildingCategory.HEALTH,
        width=3, height=2,
        construction_cost=180_000, build_days=6, upkeep=1_400,
        jobs={Profession.DOCTOR: 3, Profession.NURSE: 6},
        district=District.HOSPITAL, hospital_beds=20, amenity=0.2, levels=1,
    ),
    _spec(
        type=BuildingType.HOSPITAL,
        category=BuildingCategory.HEALTH,
        width=5, height=5,
        construction_cost=850_000, build_days=14, upkeep=4_800,
        jobs={Profession.DOCTOR: 10, Profession.NURSE: 20, Profession.CLEANER: 6},
        district=District.HOSPITAL, hospital_beds=150, amenity=0.4, levels=4,
    ),
    _spec(
        type=BuildingType.PHARMACY,
        category=BuildingCategory.HEALTH,
        width=2, height=2,
        construction_cost=70_000, build_days=3, upkeep=400,
        jobs={Profession.SHOPKEEPER: 3, Profession.NURSE: 1},
        district=District.SHOPPING, retail_capacity=60, amenity=0.1, levels=1,
    ),
    # -- Business ----------------------------------------------------------
    _spec(
        type=BuildingType.SHOP,
        category=BuildingCategory.BUSINESS,
        width=2, height=2,
        construction_cost=80_000, build_days=3, upkeep=450,
        jobs={Profession.SHOPKEEPER: 4, Profession.CLEANER: 1},
        district=District.SHOPPING, retail_capacity=120, amenity=0.1, levels=1,
    ),
    _spec(
        type=BuildingType.MARKET,
        category=BuildingCategory.BUSINESS,
        width=4, height=4,
        construction_cost=220_000, build_days=6, upkeep=1_100,
        jobs={Profession.SHOPKEEPER: 14, Profession.SECURITY: 2, Profession.CLEANER: 3},
        district=District.SHOPPING, retail_capacity=500, amenity=0.2, levels=1,
    ),
    _spec(
        type=BuildingType.CAFE,
        category=BuildingCategory.BUSINESS,
        width=2, height=2,
        construction_cost=90_000, build_days=3, upkeep=500,
        jobs={Profession.CHEF: 2, Profession.SHOPKEEPER: 2},
        district=District.SHOPPING, retail_capacity=80, amenity=0.2, levels=1,
    ),
    _spec(
        type=BuildingType.RESTAURANT,
        category=BuildingCategory.BUSINESS,
        width=3, height=2,
        construction_cost=150_000, build_days=4, upkeep=800,
        jobs={Profession.CHEF: 5, Profession.SHOPKEEPER: 4, Profession.CLEANER: 2},
        district=District.SHOPPING, retail_capacity=150, amenity=0.3, levels=1,
    ),
    _spec(
        type=BuildingType.OFFICE,
        category=BuildingCategory.BUSINESS,
        width=3, height=3,
        construction_cost=340_000, build_days=9, upkeep=1_600,
        jobs={
            Profession.DEVELOPER: 14, Profession.MANAGER: 4,
            Profession.ACCOUNTANT: 5, Profession.CLEANER: 3,
        },
        district=District.OFFICE, levels=6,
    ),
    # -- Industry ----------------------------------------------------------
    _spec(
        type=BuildingType.FARM,
        category=BuildingCategory.INDUSTRY,
        width=6, height=6,
        construction_cost=160_000, build_days=5, upkeep=700,
        jobs={Profession.FARMER: 12, Profession.DRIVER: 2, Profession.MECHANIC: 1},
        district=District.FARM, food_output=400, levels=1,
    ),
    _spec(
        type=BuildingType.FACTORY,
        category=BuildingCategory.INDUSTRY,
        width=6, height=5,
        construction_cost=900_000, build_days=30, upkeep=5_000,
        jobs={
            Profession.FACTORY_WORKER: 100, Profession.ENGINEER: 8,
            Profession.MANAGER: 4, Profession.MECHANIC: 6,
        },
        district=District.INDUSTRIAL, levels=2,
    ),
    _spec(
        type=BuildingType.WAREHOUSE,
        category=BuildingCategory.INDUSTRY,
        width=5, height=4,
        construction_cost=280_000, build_days=8, upkeep=900,
        jobs={
            Profession.DRIVER: 8, Profession.SECURITY: 3, Profession.MANAGER: 1,
            Profession.BUILDER: 8,
        },
        district=District.INDUSTRIAL, levels=1,
    ),
    _spec(
        type=BuildingType.POWER_PLANT,
        category=BuildingCategory.INDUSTRY,
        width=6, height=6,
        construction_cost=1_400_000, build_days=35, upkeep=7_000,
        jobs={Profession.ENGINEER: 14, Profession.ELECTRICIAN: 10, Profession.SECURITY: 4},
        district=District.INDUSTRIAL, power_output=2_000, levels=2,
    ),
    # -- Entertainment -----------------------------------------------------
    _spec(
        type=BuildingType.PARK,
        category=BuildingCategory.ENTERTAINMENT,
        width=5, height=5,
        construction_cost=90_000, build_days=4, upkeep=500,
        jobs={Profession.GARDENER: 4, Profession.CLEANER: 2},
        district=District.PARK, amenity=0.6, levels=0,
    ),
    _spec(
        type=BuildingType.ZOO,
        category=BuildingCategory.ENTERTAINMENT,
        width=8, height=7,
        construction_cost=700_000, build_days=20, upkeep=3_600,
        jobs={
            Profession.VETERINARIAN: 5, Profession.GARDENER: 6,
            Profession.SECURITY: 4, Profession.SHOPKEEPER: 3, Profession.CLEANER: 4,
        },
        district=District.ZOO, amenity=0.7, levels=1,
    ),
    _spec(
        type=BuildingType.CINEMA,
        category=BuildingCategory.ENTERTAINMENT,
        width=4, height=3,
        construction_cost=260_000, build_days=8, upkeep=1_300,
        jobs={Profession.SHOPKEEPER: 6, Profession.CLEANER: 3, Profession.SECURITY: 2},
        district=District.SHOPPING, amenity=0.5, levels=2,
    ),
    _spec(
        type=BuildingType.SPORT_CENTER,
        category=BuildingCategory.ENTERTAINMENT,
        width=5, height=4,
        construction_cost=380_000, build_days=12, upkeep=1_900,
        jobs={Profession.MANAGER: 2, Profession.CLEANER: 4, Profession.SECURITY: 2},
        district=District.PARK, amenity=0.5, levels=1,
    ),
    # -- Infrastructure ----------------------------------------------------
    _spec(
        type=BuildingType.BUS_STOP,
        category=BuildingCategory.INFRASTRUCTURE,
        width=1, height=1,
        construction_cost=12_000, build_days=1, upkeep=90,
        district=District.UNZONED, amenity=0.1, levels=0,
    ),
    _spec(
        type=BuildingType.TRAIN_STATION,
        category=BuildingCategory.INFRASTRUCTURE,
        width=5, height=4,
        construction_cost=650_000, build_days=22, upkeep=3_200,
        jobs={Profession.DRIVER: 12, Profession.MECHANIC: 5, Profession.SECURITY: 4},
        district=District.CITY_CENTER, amenity=0.3, levels=1,
    ),
)

CATALOG: dict[BuildingType, BuildingSpec] = {spec.type: spec for spec in _CATALOG}

#: Uzbek names, for anything a citizen or the player reads. The enum values are
#: identifiers and belong in the API and the database, not in a sentence: the
#: player typed "3 ta uy qur" and was answered "3 ta house qurilishi boshlandi".
LABELS: dict[BuildingType, str] = {
    BuildingType.HOUSE: "uy",
    BuildingType.TOWNHOUSE: "ikki qavatli uy",
    BuildingType.APARTMENT: "ko'p qavatli uy",
    BuildingType.CITY_HALL: "hokimiyat binosi",
    BuildingType.PRESIDENTIAL_PALACE: "prezident saroyi",
    BuildingType.COURTHOUSE: "sud binosi",
    BuildingType.POLICE_STATION: "politsiya bo'limi",
    BuildingType.FIRE_STATION: "o't o'chirish bo'limi",
    BuildingType.KINDERGARTEN: "bog'cha",
    BuildingType.SCHOOL: "maktab",
    BuildingType.UNIVERSITY: "universitet",
    BuildingType.CLINIC: "klinika",
    BuildingType.HOSPITAL: "shifoxona",
    BuildingType.PHARMACY: "dorixona",
    BuildingType.SHOP: "do'kon",
    BuildingType.MARKET: "bozor",
    BuildingType.CAFE: "kafe",
    BuildingType.RESTAURANT: "restoran",
    BuildingType.OFFICE: "ofis",
    BuildingType.FARM: "ferma",
    BuildingType.FACTORY: "zavod",
    BuildingType.WAREHOUSE: "ombor",
    BuildingType.POWER_PLANT: "elektr stansiyasi",
    BuildingType.PARK: "park",
    BuildingType.ZOO: "zoopark",
    BuildingType.CINEMA: "kinoteatr",
    BuildingType.SPORT_CENTER: "sport majmuasi",
    BuildingType.BUS_STOP: "avtobus bekati",
    BuildingType.TRAIN_STATION: "temir yo'l vokzali",
}


def label_for(building_type: BuildingType) -> str:
    return LABELS.get(building_type, str(building_type))


def spec_for(building_type: BuildingType) -> BuildingSpec:
    return CATALOG[building_type]


def types_in_category(category: BuildingCategory) -> list[BuildingType]:
    return [spec.type for spec in _CATALOG if spec.category == category]


def total_job_slots(building_type: BuildingType) -> int:
    return sum(spec_for(building_type).jobs.values())


def _sanity_check() -> None:
    missing = set(BuildingType) - set(CATALOG)
    if missing:
        raise RuntimeError(f"buildings without a spec: {sorted(missing)}")

    unlabelled = set(BuildingType) - set(LABELS)
    if unlabelled:
        raise RuntimeError(f"buildings without an Uzbek label: {sorted(unlabelled)}")

    for spec in _CATALOG:
        if spec.width <= 0 or spec.height <= 0:
            raise RuntimeError(f"{spec.type}: footprint must be positive")
        if spec.build_days <= 0:
            raise RuntimeError(f"{spec.type}: build_days must be positive")
        if spec.category is BuildingCategory.RESIDENTIAL and spec.residents <= 0:
            raise RuntimeError(f"{spec.type}: a residential building must house someone")


_sanity_check()
