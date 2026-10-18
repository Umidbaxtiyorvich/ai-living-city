"""
Urban renewal — the city rebuilding itself.

Buildings wear out. Every structure carries a `condition` that falls a little
each day, faster when it is crowded or overstaffed. The renewal office looks at
the worn stock once a week and does one of two things:

* **Repair** a building whose condition has fallen too far, for a fraction of
  its construction cost.
* **Redevelop** a worn, low-density building into its denser successor once the
  city has unlocked it — a house becomes an apartment block, a clinic a
  hospital, a shop a market. This is how an old village core turns into a
  modern centre without the president ever ordering it street by street.

Redevelopment prefers moments when it is needed: housing is short and there is
no free land, or the building is near the end of its life anyway. One project a
week keeps the city recognisable while it changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..buildings.catalog import CATALOG, BuildingCategory, BuildingType
from ..buildings.models import Building, BuildingStatus

#: Condition points lost per day by an ordinary building (≈ 4 years to zero).
DECAY_PER_DAY = 0.07

#: Below this, a building is repaired if nothing better can be done.
REPAIR_THRESHOLD = 40.0

#: Below this, a building is a redevelopment candidate when density is needed.
REDEVELOP_THRESHOLD = 70.0

#: Below this, a building is redeveloped regardless — it is at end of life.
END_OF_LIFE = 25.0

#: Share of construction cost a full repair costs.
REPAIR_COST_FRACTION = 0.12

#: Days between renewal reviews.
RENEWAL_INTERVAL_DAYS = 7

#: What each building type becomes when redeveloped, best first.
SUCCESSOR: dict[BuildingType, tuple[BuildingType, ...]] = {
    BuildingType.HOUSE: (BuildingType.APARTMENT, BuildingType.TOWNHOUSE),
    BuildingType.TOWNHOUSE: (BuildingType.APARTMENT,),
    BuildingType.SHOP: (BuildingType.MARKET,),
    BuildingType.CAFE: (BuildingType.RESTAURANT,),
    BuildingType.CLINIC: (BuildingType.HOSPITAL,),
    BuildingType.KINDERGARTEN: (BuildingType.SCHOOL,),
}

#: Buildings the renewal office never touches.
PROTECTED: frozenset[BuildingType] = frozenset(
    {BuildingType.PRESIDENTIAL_PALACE, BuildingType.CITY_HALL}
)


@dataclass(slots=True)
class RenewalPlan:
    kind: str  # "repair" | "redevelop"
    building_id: int
    cost: float
    new_type: BuildingType | None = None


def wear(buildings: dict[int, Building]) -> None:
    """One day of wear and tear."""
    for building in buildings.values():
        if building.status is not BuildingStatus.OPEN:
            continue
        rate = DECAY_PER_DAY
        capacity = building.housing_capacity
        if capacity and len(building.residents) >= capacity:
            rate *= 1.5
        if building.spec.category is BuildingCategory.INDUSTRY:
            rate *= 1.3
        building.condition = max(0.0, building.condition - rate)


def plan(
    buildings: dict[int, Building],
    *,
    unlocked: frozenset[BuildingType],
    spendable: float,
    housing_shortage: int,
    land_available: bool,
) -> RenewalPlan | None:
    """The single most useful renewal project this week, if any is affordable."""
    candidates = sorted(
        (
            building
            for building in buildings.values()
            if building.status is BuildingStatus.OPEN and building.type not in PROTECTED
        ),
        key=lambda building: (building.condition, building.id),
    )

    densify = housing_shortage > 0 and not land_available
    for building in candidates:
        if building.condition >= REDEVELOP_THRESHOLD:
            break
        successor = next(
            (option for option in SUCCESSOR.get(building.type, ()) if option in unlocked),
            None,
        )
        wanted = successor is not None and (
            building.condition < END_OF_LIFE
            or (densify and building.spec.category is BuildingCategory.RESIDENTIAL)
        )
        if wanted:
            cost = float(CATALOG[successor].construction_cost)
            if cost <= spendable:
                return RenewalPlan("redevelop", building.id, cost, successor)

    for building in candidates:
        if building.condition >= REPAIR_THRESHOLD:
            break
        cost = CATALOG[building.type].construction_cost * REPAIR_COST_FRACTION
        if cost <= spendable:
            return RenewalPlan("repair", building.id, float(cost))
    return None
