"""
The president's decision engine.

Implements the pipeline from specification section 5:

    indicators → analysis → priority → decision → action → result → memory

Deliberately rule-based. The city runs unattended at up to 100x speed, so a
decision must be free, instant and reproducible; an LLM call in this loop would
be none of those. Natural language belongs in `sim/ai/narrator.py`, on top of a
decision that has already been made.

Two guards keep the engine from thrashing:

* **Pipeline awareness** — a concern already being addressed by an in-flight
  project is discounted, so the president does not order ten hospitals while the
  first one is still being built.
* **Cooldowns** — tax changes and map expansions are rate-limited, because their
  effects take months to show up in the indicators.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..buildings.catalog import CATALOG, BuildingCategory, BuildingType
from ..buildings.construction import MAX_CONCURRENT_PROJECTS
from ..buildings.models import Building, BuildingStatus
from ..city.stats import CityStats
from ..clock import DAYS_PER_MONTH
from ..economy.model import MAX_TAX_RATE, MIN_TAX_RATE, Economy
from ..jobs.professions import Profession
from ..memory.model import MemoryKind
from ..world.tiles import District
from .models import (
    Action,
    ActionKind,
    Concern,
    ConcernCode,
    Priority,
    President,
)

#: Unemployment above this is a problem worth acting on (specification 7).
UNEMPLOYMENT_THRESHOLD = 0.15

#: Happiness below this counts as public discontent.
HAPPINESS_FLOOR = 50.0

#: Service coverage below this is treated as a shortage.
COVERAGE_TARGET = 0.95

#: Free residential tiles below this and the city needs new land.
LAND_FLOOR = 40

#: Simulated days between tax adjustments.
TAX_COOLDOWN_DAYS = DAYS_PER_MONTH * 2

#: Simulated days between map expansions.
EXPANSION_COOLDOWN_DAYS = DAYS_PER_MONTH * 3

#: Days after a decision before its outcome is reviewed.
REVIEW_DELAY_DAYS = DAYS_PER_MONTH

#: How much each in-flight project of the same category discounts its concern.
IN_FLIGHT_DISCOUNT = 0.55

#: Floor for that discount.
#:
#: Without a floor the exponential collapsed a real shortage to nothing once a
#: few projects were running — the president watched 68 citizens stay homeless
#: because five townhouses were already being built. A shortage must keep
#: mattering until it is actually solved.
MIN_IN_FLIGHT_FACTOR = 0.3

#: Reserve the president refuses to spend below, as a share of the budget.
#: Without it, one factory can empty the treasury and stall the whole city.
BUDGET_RESERVE_FRACTION = 0.15

#: Months of monthly obligations the treasury should be able to cover. Below
#: this, the city is considered to be running out of money.
BUDGET_RUNWAY_MONTHS = 12.0

#: Runway below which the tax cooldown no longer applies. The cooldown is there
#: to stop the president fine-tuning rates faster than the effects can show up;
#: it must not gag it during a solvency crisis.
BUDGET_EMERGENCY_MONTHS = 3.0


@dataclass(slots=True)
class BrainContext:
    """Everything the engine needs to reason. Read-only by contract."""

    tick: int
    day: int
    stats: CityStats
    economy: Economy
    buildings: dict[int, Building]
    grid_width: int
    grid_height: int
    max_grid_size: int
    last_tax_change_day: int
    last_expansion_day: int
    #: Building types the city's development level permits. Proposing anything
    #: outside this set produces a decision that can never be carried out.
    unlocked: frozenset[BuildingType] = frozenset(BuildingType)
    #: Free slots in the construction queue. At zero, proposing another
    #: building produces a decision that is deferred every single day, which
    #: buries the problems the president could still act on.
    construction_slots: int = MAX_CONCURRENT_PROJECTS
    traffic_congestion: float = 0.0
    parking_shortage: int = 0
    transit_route_count: int = 0

    def first_unlocked(self, *candidates: BuildingType) -> BuildingType | None:
        """The first candidate the city is allowed to build, in preference order."""
        for candidate in candidates:
            if candidate in self.unlocked:
                return candidate
        return None


class PresidentBrain:
    """Stateless analyser. All mutable state lives on the `President`."""

    # -- 1. analysis -------------------------------------------------------

    def assess(self, context: BrainContext) -> list[Concern]:
        """Every problem currently detectable, strongest first."""
        stats = context.stats
        concerns: list[Concern] = []

        for detector in (
            self._housing,
            self._healthcare,
            self._education,
            self._food,
            self._power,
            self._retail,
            self._security,
            self._unemployment,
            self._worker_shortage,
            self._budget,
            self._taxation,
            self._happiness,
            self._land,
            self._traffic,
            self._parking,
            self._transit,
        ):
            concern = detector(context, stats)
            if concern is not None and concern.severity > 0.05:
                concerns.append(concern)

        # With no free slot the trades cannot start anything new, so a building
        # proposal is not a decision — it is a daily deferral.
        if context.construction_slots <= 0:
            concerns = [
                concern
                for concern in concerns
                if concern.action.kind is not ActionKind.BUILD
            ]

        # Discount anything already being built, then rank.
        for concern in concerns:
            concern.severity *= self._in_flight_factor(context, concern)

        concerns.sort(key=lambda item: item.severity, reverse=True)
        return [concern for concern in concerns if concern.severity > 0.05]

    def _in_flight_factor(self, context: BrainContext, concern: Concern) -> float:
        """1.0 when nothing is being built for this concern, lower otherwise."""
        if concern.action.kind is not ActionKind.BUILD or concern.action.building_type is None:
            return 1.0

        category = CATALOG[concern.action.building_type].category
        in_flight = sum(
            1
            for building in context.buildings.values()
            if building.status is BuildingStatus.UNDER_CONSTRUCTION
            and building.spec.category is category
        )
        if in_flight == 0:
            return 1.0
        return max(MIN_IN_FLIGHT_FACTOR, IN_FLIGHT_DISCOUNT**in_flight)

    # -- detectors ---------------------------------------------------------

    def _housing(self, context: BrainContext, stats: CityStats) -> Concern | None:
        if stats.housing_shortage <= 0:
            return None

        # Severity relative to population: 20 homeless in a village is a crisis,
        # in a metropolis it is a rounding error.
        severity = min(1.0, stats.housing_shortage / max(1, stats.population) * 2.5)

        # Denser housing once the shortage justifies the cost, falling back to
        # whatever the city's development level actually permits.
        if stats.housing_shortage >= 24:
            preference = (BuildingType.APARTMENT, BuildingType.TOWNHOUSE, BuildingType.HOUSE)
        elif stats.housing_shortage >= 8:
            preference = (BuildingType.TOWNHOUSE, BuildingType.HOUSE, BuildingType.APARTMENT)
        else:
            preference = (BuildingType.HOUSE, BuildingType.TOWNHOUSE)

        building = context.first_unlocked(*preference)
        if building is None:
            return None

        per_unit = CATALOG[building].residents
        quantity = max(1, min(4, -(-stats.housing_shortage // per_unit)))

        return Concern(
            code=ConcernCode.HOUSING_SHORTAGE,
            severity=severity,
            description=f"{stats.housing_shortage} kishi uysiz",
            action=Action(kind=ActionKind.BUILD, building_type=building, quantity=quantity),
            evidence={
                "population": stats.population,
                "housing_capacity": stats.housing_capacity,
                "shortage": stats.housing_shortage,
            },
        )

    def _coverage_concern(
        self,
        context: BrainContext,
        code: ConcernCode,
        coverage: float,
        supplied: int,
        needed: int,
        small: BuildingType,
        large: BuildingType,
        large_threshold: int,
        label: str,
    ) -> Concern | None:
        if coverage >= COVERAGE_TARGET:
            return None

        deficit = max(0, needed - supplied)
        # Prefer the right size for the deficit, but accept the other if the
        # city has not unlocked it yet.
        building = (
            context.first_unlocked(large, small)
            if deficit >= large_threshold
            else context.first_unlocked(small, large)
        )
        if building is None:
            return None

        return Concern(
            code=code,
            severity=min(1.0, 1.0 - coverage),
            description=f"{label}: {supplied}/{needed}",
            action=Action(kind=ActionKind.BUILD, building_type=building, quantity=1),
            evidence={"supplied": supplied, "needed": needed, "coverage": round(coverage, 3)},
        )

    def _healthcare(self, context: BrainContext, stats: CityStats) -> Concern | None:
        return self._coverage_concern(
            context,
            ConcernCode.HEALTHCARE_SHORTAGE,
            stats.healthcare_coverage,
            stats.hospital_beds,
            stats.beds_needed,
            BuildingType.CLINIC,
            BuildingType.HOSPITAL,
            large_threshold=60,
            label="Kasalxona joylari",
        )

    def _education(self, context: BrainContext, stats: CityStats) -> Concern | None:
        if stats.school_age == 0:
            return None
        return self._coverage_concern(
            context,
            ConcernCode.EDUCATION_SHORTAGE,
            stats.education_coverage,
            stats.school_seats,
            stats.seats_needed,
            BuildingType.KINDERGARTEN,
            BuildingType.SCHOOL,
            large_threshold=120,
            label="Maktab o'rinlari",
        )

    def _food(self, context: BrainContext, stats: CityStats) -> Concern | None:
        return self._coverage_concern(
            context,
            ConcernCode.FOOD_SHORTAGE,
            stats.food_coverage,
            stats.food_output,
            stats.food_needed,
            BuildingType.FARM,
            BuildingType.FARM,
            large_threshold=10**9,
            label="Oziq-ovqat",
        )

    def _power(self, context: BrainContext, stats: CityStats) -> Concern | None:
        return self._coverage_concern(
            context,
            ConcernCode.POWER_SHORTAGE,
            stats.power_coverage,
            stats.power_output,
            stats.power_needed,
            BuildingType.POWER_PLANT,
            BuildingType.POWER_PLANT,
            large_threshold=10**9,
            label="Elektr quvvati",
        )

    def _retail(self, context: BrainContext, stats: CityStats) -> Concern | None:
        return self._coverage_concern(
            context,
            ConcernCode.RETAIL_SHORTAGE,
            stats.retail_coverage,
            stats.retail_capacity,
            stats.retail_needed,
            BuildingType.SHOP,
            BuildingType.MARKET,
            large_threshold=300,
            label="Savdo nuqtalari",
        )

    def _security(self, context: BrainContext, stats: CityStats) -> Concern | None:
        return self._coverage_concern(
            context,
            ConcernCode.SECURITY_SHORTAGE,
            stats.security_coverage,
            stats.police_officers,
            stats.police_needed,
            BuildingType.POLICE_STATION,
            BuildingType.POLICE_STATION,
            large_threshold=10**9,
            label="Politsiya xodimlari",
        )

    def _unemployment(self, context: BrainContext, stats: CityStats) -> Concern | None:
        """
        Too many citizens without work.

        The fix is workplaces, chosen by what the city lacks: offices when the
        workforce is educated, factories when it is not.
        """
        if stats.unemployment_rate <= UNEMPLOYMENT_THRESHOLD:
            return None
        # Existing vacancies mean the jobs exist and hiring simply has not caught
        # up; building more would not help.
        if stats.open_vacancies >= stats.unemployed:
            return None

        severity = min(1.0, (stats.unemployment_rate - UNEMPLOYMENT_THRESHOLD) * 4.0)
        missing_jobs = stats.unemployed - stats.open_vacancies

        if missing_jobs >= 90:
            preference = (BuildingType.FACTORY, BuildingType.OFFICE, BuildingType.SHOP)
        elif missing_jobs >= 20:
            preference = (BuildingType.OFFICE, BuildingType.MARKET, BuildingType.SHOP)
        else:
            preference = (BuildingType.SHOP, BuildingType.CAFE)

        building = context.first_unlocked(*preference)
        if building is None:
            return None

        return Concern(
            code=ConcernCode.UNEMPLOYMENT,
            severity=severity,
            description=f"Ishsizlik {stats.unemployment_rate:.0%}",
            action=Action(kind=ActionKind.BUILD, building_type=building, quantity=1),
            evidence={
                "unemployed": stats.unemployed,
                "vacancies": stats.open_vacancies,
                "rate": round(stats.unemployment_rate, 4),
            },
        )

    def _worker_shortage(self, context: BrainContext, stats: CityStats) -> Concern | None:
        """
        Jobs exist but nobody can fill them (specification section 8).

        Answered by recruitment — new citizens move to the city — rather than by
        construction.
        """
        unfilled = stats.open_vacancies
        if unfilled <= 0:
            return None
        # Locals can still take these jobs; only recruit once they cannot.
        surplus = unfilled - stats.unemployed
        if surplus <= 0:
            return None

        wanted = sorted(
            stats.vacancies_by_profession.items(), key=lambda item: item[1], reverse=True
        )

        # Never import people the city cannot house. Recruiting into a housing
        # shortage was making every indicator worse at once: more homeless, more
        # unhappiness, more wage bill, and the vacancies stayed open anyway
        # because the new arrivals had nowhere to live.
        #
        # Builders are the exception, and the city deadlocks without it: no
        # builders means housing is never finished, and the shortage that blocks
        # recruitment is exactly what the builders would end.
        if stats.housing_shortage > 0:
            builder_posts = stats.vacancies_by_profession.get(Profession.BUILDER, 0)
            if builder_posts <= 0:
                return None
            surplus = min(surplus, builder_posts)
            wanted = [(Profession.BUILDER, builder_posts)]

        severity = min(1.0, surplus / max(10, stats.population * 0.1))

        return Concern(
            code=ConcernCode.WORKER_SHORTAGE,
            severity=severity,
            description=f"{surplus} ish o'rni bo'sh, ishchi yo'q",
            action=Action(
                kind=ActionKind.RECRUIT_WORKERS,
                quantity=min(12, surplus),
                professions=[str(profession) for profession, _ in wanted[:5]],
            ),
            evidence={"vacancies": unfilled, "unemployed": stats.unemployed, "surplus": surplus},
        )

    def _budget(self, context: BrainContext, stats: CityStats) -> Concern | None:
        """
        Running out of money. Raising income tax is the fastest lever.

        Solvency is judged on the treasury against monthly obligations, not on
        the monthly ledger alone. Construction is charged upfront and never
        appears in the ledger, so a city could empty its treasury on apartments
        while the books still showed a surplus — and the president would never
        notice it had gone broke.
        """
        economy = context.economy
        monthly_obligations = stats.public_wage_bill + stats.total_upkeep

        if monthly_obligations <= 0:
            runway = float("inf")
        else:
            runway = economy.budget / monthly_obligations

        if economy.budget < 0:
            severity = 1.0
        elif runway < BUDGET_RUNWAY_MONTHS:
            severity = min(1.0, 1.0 - runway / BUDGET_RUNWAY_MONTHS)
        else:
            return None

        reserve_months = max(0.0, runway)

        # On cooldown there is nothing to propose. Emitting a "wait" concern
        # instead put an unactionable item at the top of the ranking and starved
        # the real problems below it; the deficit is still visible on the
        # dashboard through the economy figures.
        #
        # A solvency crisis overrides the cooldown. The rate limit exists to let
        # a tax change show up in the indicators before the next one, but a city
        # with weeks of runway left cannot wait two more months — it sits frozen,
        # unable to fund anything, until the timer expires.
        on_cooldown = context.day - context.last_tax_change_day < TAX_COOLDOWN_DAYS
        if on_cooldown and runway >= BUDGET_EMERGENCY_MONTHS:
            return None

        new_rate = min(MAX_TAX_RATE, economy.taxes.income_tax + 0.03)
        # At the ceiling the lever is spent. Proposing a rate equal to the
        # current one produced a decision that was approved, cost nothing and
        # changed nothing — hiding the fact that the city had run out of options.
        if new_rate <= economy.taxes.income_tax + 1e-9:
            return None
        return Concern(
            code=ConcernCode.BUDGET_DEFICIT,
            severity=severity,
            description=f"Byudjet taqchilligi, {reserve_months:.1f} oy zaxira",
            action=Action(kind=ActionKind.SET_TAX, tax_name="income_tax", tax_value=new_rate),
            evidence={
                "months_of_reserve": round(reserve_months, 2),
                "monthly_net": round(economy.monthly_net, 2),
                "monthly_obligations": round(monthly_obligations, 2),
                "budget": round(economy.budget, 2),
                "current_rate": economy.taxes.income_tax,
            },
        )

    def _taxation(self, context: BrainContext, stats: CityStats) -> Concern | None:
        """
        Taxes higher than the city needs.

        The mirror of `_budget`: with a healthy surplus and unhappy citizens,
        cutting tax is the cheapest available happiness. This is the mechanism
        that lets the president find the balance the specification asks for.
        """
        economy = context.economy
        if economy.in_deficit or economy.taxes.income_tax <= MIN_TAX_RATE + 0.01:
            return None
        if context.day - context.last_tax_change_day < TAX_COOLDOWN_DAYS:
            return None

        # Only cut when the surplus is comfortable and people are dissatisfied.
        surplus_months = economy.budget / max(1.0, abs(economy.monthly_net) or 1.0)
        if economy.monthly_net <= 0 or surplus_months < 18:
            return None
        if stats.happiness >= 65.0:
            return None

        severity = min(0.5, (65.0 - stats.happiness) / 100.0)
        new_rate = max(MIN_TAX_RATE, economy.taxes.income_tax - 0.02)

        return Concern(
            code=ConcernCode.EXCESSIVE_TAXATION,
            severity=severity,
            description=f"Soliq yuqori, mamnunlik {stats.happiness:.0f}",
            action=Action(kind=ActionKind.SET_TAX, tax_name="income_tax", tax_value=new_rate),
            evidence={
                "happiness": round(stats.happiness, 2),
                "current_rate": economy.taxes.income_tax,
                "monthly_net": round(economy.monthly_net, 2),
            },
        )

    def _happiness(self, context: BrainContext, stats: CityStats) -> Concern | None:
        """
        General discontent with no more specific cause.

        Ranked low on purpose: if housing or healthcare is the real problem,
        those detectors should win. A park is what you build when the basics are
        covered and people are still glum.
        """
        if stats.happiness >= HAPPINESS_FLOOR or stats.population < 10:
            return None

        building = context.first_unlocked(
            BuildingType.PARK, BuildingType.SPORT_CENTER, BuildingType.CAFE
        )
        if building is None:
            return None

        severity = min(0.6, (HAPPINESS_FLOOR - stats.happiness) / 100.0)
        return Concern(
            code=ConcernCode.LOW_HAPPINESS,
            severity=severity,
            description=f"Aholi mamnunligi past ({stats.happiness:.0f})",
            action=Action(kind=ActionKind.BUILD, building_type=building, quantity=1),
            evidence={"happiness": round(stats.happiness, 2)},
        )

    def _land(self, context: BrainContext, stats: CityStats) -> Concern | None:
        """
        Nowhere left to build.

        Two answers: zone unzoned land first because it is free, and only grow
        the map when there is genuinely nothing left to zone.
        """
        if stats.free_residential_land >= LAND_FLOOR:
            return None

        severity = min(1.0, 1.0 - stats.free_residential_land / LAND_FLOOR)

        if stats.free_land >= LAND_FLOOR * 3:
            return Concern(
                code=ConcernCode.NO_BUILDABLE_LAND,
                severity=severity,
                description="Turar joy uchun yer tugadi, yangi hudud zonalanadi",
                action=Action(kind=ActionKind.ZONE_DISTRICT, district=District.RESIDENTIAL),
                evidence={
                    "free_residential": stats.free_residential_land,
                    "free_total": stats.free_land,
                },
            )

        if context.day - context.last_expansion_day < EXPANSION_COOLDOWN_DAYS:
            return None
        if context.grid_width >= context.max_grid_size:
            return None

        grown = min(context.max_grid_size, int(context.grid_width * 1.5))
        return Concern(
            code=ConcernCode.NO_BUILDABLE_LAND,
            severity=severity,
            description=f"Xarita kengaytiriladi: {grown}×{grown}",
            action=Action(kind=ActionKind.EXPAND_MAP, new_width=grown, new_height=grown),
            evidence={"free_total": stats.free_land, "current_size": context.grid_width},
        )

    def _traffic(self, context: BrainContext, stats: CityStats) -> Concern | None:
        if context.traffic_congestion <= 0.55:
            return None
        building = context.first_unlocked(BuildingType.BUS_STOP, BuildingType.TRAIN_STATION)
        if building is None:
            return None
        severity = min(1.0, (context.traffic_congestion - 0.55) * 2.5)
        return Concern(
            code=ConcernCode.TRAFFIC_CONGESTION,
            severity=severity,
            description=f"Tirbandlik {context.traffic_congestion:.0%}",
            action=Action(kind=ActionKind.BUILD, building_type=building, quantity=2),
            evidence={"congestion": round(context.traffic_congestion, 3)},
        )

    def _parking(self, context: BrainContext, stats: CityStats) -> Concern | None:
        if context.parking_shortage <= 0:
            return None
        building = context.first_unlocked(BuildingType.MARKET, BuildingType.SHOP)
        if building is None:
            return None
        severity = min(1.0, context.parking_shortage / max(10, stats.population * 0.2))
        return Concern(
            code=ConcernCode.PARKING_SHORTAGE,
            severity=severity,
            description=f"Parkovka yetmayapti ({context.parking_shortage} joy)",
            action=Action(
                kind=ActionKind.ZONE_DISTRICT,
                district=District.SHOPPING,
            ),
            evidence={"shortage": context.parking_shortage},
        )

    def _transit(self, context: BrainContext, stats: CityStats) -> Concern | None:
        if stats.population < 80:
            return None
        routes = context.transit_route_count
        needed = max(1, stats.population // 120)
        if routes >= needed:
            return None
        building = context.first_unlocked(BuildingType.BUS_STOP, BuildingType.TRAIN_STATION)
        if building is None:
            return None
        severity = min(1.0, (needed - routes) / max(1, needed))
        return Concern(
            code=ConcernCode.TRANSIT_SHORTAGE,
            severity=severity,
            description="Jamoat transporti yetarli emas",
            action=Action(kind=ActionKind.BUILD, building_type=building, quantity=1),
            evidence={"routes": routes, "needed": needed},
        )

    # -- 2. decision -------------------------------------------------------

    def choose(self, context: BrainContext, concerns: list[Concern]) -> Concern | None:
        """
        The concern to act on now.

        Walks the ranked list and returns the first the city can actually
        afford. Skipping an unaffordable critical concern in favour of a cheap
        lesser one is intentional: doing something useful beats stalling.
        """
        if not concerns:
            return None

        spendable = self.spendable_budget(context.economy)

        for concern in concerns:
            cost = self.estimated_cost(concern)
            if cost <= spendable:
                return concern

        # Nothing affordable; report the worst so the dashboard shows the reason.
        return concerns[0]

    @staticmethod
    def spendable_budget(economy: Economy) -> float:
        """Budget minus the untouchable reserve."""
        return max(0.0, economy.budget * (1.0 - BUDGET_RESERVE_FRACTION))

    @staticmethod
    def estimated_cost(concern: Concern) -> float:
        action = concern.action
        if action.kind is ActionKind.BUILD and action.building_type:
            return CATALOG[action.building_type].construction_cost * action.quantity
        # Recruitment pays a relocation allowance per worker.
        if action.kind is ActionKind.RECRUIT_WORKERS:
            return 2_000.0 * action.quantity
        if action.kind is ActionKind.ZONE_DISTRICT:
            return 25_000.0
        if action.kind is ActionKind.EXPAND_MAP:
            return 400_000.0
        return 0.0

    # -- 3. learning -------------------------------------------------------

    def review_outcomes(self, president: President, context: BrainContext) -> list[str]:
        """
        Scores decisions that are old enough to have had an effect.

        Comparing the concern's severity then and now is the only honest signal
        available without a counterfactual, and it is enough to tell a working
        policy from a wasted one.
        """
        notes: list[str] = []
        current = {concern.code: concern.severity for concern in self.assess(context)}
        review_ticks = REVIEW_DELAY_DAYS * 1440

        for decision in president.decisions:
            if decision.reviewed_tick is not None:
                continue
            if context.tick - decision.tick < review_ticks:
                continue

            decision.severity_at_review = current.get(decision.concern.code, 0.0)
            decision.reviewed_tick = context.tick

            verdict = "yaxshi natija" if decision.worked else "natija bermadi"
            note = (
                f"#{decision.id} {decision.concern.code}: {decision.concern.action.describe()} — {verdict} "
                f"({decision.concern.severity:.2f} → {decision.severity_at_review:.2f})"
            )
            notes.append(note)

            president.memory.record(
                context.tick,
                MemoryKind.DEVELOPMENT,
                note,
                importance=0.7 if decision.worked else 0.85,
                decision_id=decision.id,
                concern=str(decision.concern.code),
                worked=bool(decision.worked),
            )

        return notes

    def effectiveness_for(self, president: President, code: ConcernCode) -> float | None:
        """
        Share of past decisions on this concern that helped.

        Exposed for the debug panel and as the hook a future policy-learning
        layer would read.
        """
        reviewed = [d for d in president.decisions_for(code) if d.worked is not None]
        if not reviewed:
            return None
        return sum(1 for d in reviewed if d.worked) / len(reviewed)


def approval_from(stats: CityStats, economy: Economy) -> float:
    """
    Approval rating from governing outcomes (specification section 37).

    A weighted blend of the things citizens actually feel. Tax policy enters
    through `happiness_modifier` rather than as a separate term, because its
    effect is already how people feel about their pay.
    """
    components = (
        (stats.happiness / 100.0, 0.30),
        (stats.employment_rate, 0.18),
        (1.0 - min(1.0, stats.housing_pressure * 3.0), 0.16),
        (stats.healthcare_coverage, 0.12),
        (stats.education_coverage, 0.08),
        (stats.food_coverage, 0.06),
        (stats.security_coverage, 0.05),
        (0.0 if economy.in_deficit else 1.0, 0.05),
    )
    score = sum(value * weight for value, weight in components) * 100.0
    return max(0.0, min(100.0, score + economy.taxes.happiness_modifier))
