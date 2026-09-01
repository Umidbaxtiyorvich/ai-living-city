"""
City economy.

Money moves on a monthly settlement rather than every tick: wages, taxes and
upkeep are inherently monthly quantities, and settling them 1440 times a day
would be both slower and harder to reason about. Construction spending is the
exception — it is charged upfront when a project is approved, so the president
cannot commit to more than the treasury holds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Hard bounds on any tax rate (specification section 12).
MIN_TAX_RATE = 0.0
MAX_TAX_RATE = 0.5

#: Tax rate citizens consider fair. Above it, happiness suffers.
NEUTRAL_INCOME_TAX = 0.15


@dataclass(slots=True)
class TaxPolicy:
    """Rates as fractions, e.g. 0.12 means 12%."""

    income_tax: float = 0.12
    business_tax: float = 0.15
    property_tax: float = 0.01

    def clamped(self) -> "TaxPolicy":
        return TaxPolicy(
            income_tax=min(MAX_TAX_RATE, max(MIN_TAX_RATE, self.income_tax)),
            business_tax=min(MAX_TAX_RATE, max(MIN_TAX_RATE, self.business_tax)),
            property_tax=min(MAX_TAX_RATE, max(MIN_TAX_RATE, self.property_tax)),
        )

    @property
    def happiness_modifier(self) -> float:
        """
        How the tax burden bends citizen happiness, in points.

        Symmetric around the neutral rate: cutting taxes below it is a visible
        gift, raising them above it is a visible cost. Scaled so the full legal
        range moves happiness by roughly ±14 points, enough to matter without
        letting tax policy alone decide the president's approval.
        """
        return (NEUTRAL_INCOME_TAX - self.income_tax) * 40.0

    def as_dict(self) -> dict[str, float]:
        return {
            "income_tax": round(self.income_tax, 4),
            "business_tax": round(self.business_tax, 4),
            "property_tax": round(self.property_tax, 4),
        }


@dataclass(slots=True)
class LedgerEntry:
    """One month of the city's books, kept for the dashboard's history chart."""

    day: int
    income: float
    expenses: float
    budget_after: float
    breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def net(self) -> float:
        return self.income - self.expenses

    def as_dict(self) -> dict:
        return {
            "day": self.day,
            "income": round(self.income, 2),
            "expenses": round(self.expenses, 2),
            "net": round(self.net, 2),
            "budget_after": round(self.budget_after, 2),
            "breakdown": {k: round(v, 2) for k, v in self.breakdown.items()},
        }


@dataclass(slots=True)
class MonthlyResult:
    """What one settlement produced, returned so callers can log it."""

    income: float
    expenses: float
    wages_paid: float
    tax_collected: float
    upkeep_paid: float
    budget: float
    gdp: float


class Economy:
    """Owns the treasury, the tax policy and the monthly ledger."""

    #: How many months of history to retain.
    LEDGER_LIMIT = 120

    def __init__(self, starting_budget: float = 5_000_000.0) -> None:
        self.budget = starting_budget
        self.taxes = TaxPolicy()
        self.ledger: list[LedgerEntry] = []
        #: Rolling GDP estimate, updated each settlement.
        self.gdp = 0.0
        #: Cumulative construction spend, for the dashboard.
        self.total_construction_spend = 0.0

    # -- immediate spending ------------------------------------------------

    def can_afford(self, amount: float) -> bool:
        return amount <= self.budget

    def spend(self, amount: float, reason: str) -> bool:
        """
        Charges the treasury. Refuses rather than going negative: the president
        must plan within its means, which is what makes budget pressure real.
        """
        if amount < 0:
            raise ValueError(f"cannot spend a negative amount ({reason})")
        if not self.can_afford(amount):
            return False
        self.budget -= amount
        if reason == "construction":
            self.total_construction_spend += amount
        return True

    def receive(self, amount: float) -> None:
        self.budget += amount

    # -- monthly settlement ------------------------------------------------

    def settle_month(
        self,
        day: int,
        *,
        public_wages: float,
        private_wages: float,
        business_revenue: float,
        property_value: float,
        upkeep: float,
        service_costs: dict[str, float],
    ) -> MonthlyResult:
        """
        Runs one month of the city's books.

        Public wages are paid by the treasury; private wages are paid by
        businesses but still generate income tax. That distinction is what makes
        a city of public employees expensive and a city of private ones
        profitable.
        """
        taxable_wages = public_wages + private_wages
        income_tax = taxable_wages * self.taxes.income_tax
        business_tax = business_revenue * self.taxes.business_tax
        property_tax = property_value * self.taxes.property_tax
        tax_collected = income_tax + business_tax + property_tax

        services = sum(service_costs.values())
        expenses = public_wages + upkeep + services
        income = tax_collected

        self.budget += income - expenses

        # GDP as the value the city produced this month.
        self.gdp = business_revenue + taxable_wages

        entry = LedgerEntry(
            day=day,
            income=income,
            expenses=expenses,
            budget_after=self.budget,
            breakdown={
                "income_tax": income_tax,
                "business_tax": business_tax,
                "property_tax": property_tax,
                "public_wages": public_wages,
                "upkeep": upkeep,
                **service_costs,
            },
        )
        self.ledger.append(entry)
        if len(self.ledger) > self.LEDGER_LIMIT:
            del self.ledger[: len(self.ledger) - self.LEDGER_LIMIT]

        return MonthlyResult(
            income=income,
            expenses=expenses,
            wages_paid=public_wages,
            tax_collected=tax_collected,
            upkeep_paid=upkeep,
            budget=self.budget,
            gdp=self.gdp,
        )

    # -- reading -----------------------------------------------------------

    @property
    def last_month(self) -> LedgerEntry | None:
        return self.ledger[-1] if self.ledger else None

    @property
    def monthly_net(self) -> float:
        return self.last_month.net if self.last_month else 0.0

    @property
    def in_deficit(self) -> bool:
        return self.monthly_net < 0

    def months_of_reserve(self) -> float:
        """
        How long the treasury lasts at the current burn rate.

        The president uses this to decide whether it can afford a large project;
        `inf` means the city is running a surplus.
        """
        net = self.monthly_net
        if net >= 0:
            return float("inf")
        return self.budget / abs(net)

    def as_dict(self) -> dict:
        return {
            "budget": round(self.budget, 2),
            "gdp": round(self.gdp, 2),
            "taxes": self.taxes.as_dict(),
            "monthly_net": round(self.monthly_net, 2),
            "in_deficit": self.in_deficit,
            "months_of_reserve": (
                None if self.months_of_reserve() == float("inf") else round(self.months_of_reserve(), 1)
            ),
            "total_construction_spend": round(self.total_construction_spend, 2),
            "history": [entry.as_dict() for entry in self.ledger[-24:]],
        }

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> dict:
        return {
            "budget": self.budget,
            "gdp": self.gdp,
            "taxes": self.taxes.as_dict(),
            "total_construction_spend": self.total_construction_spend,
            "ledger": [entry.as_dict() for entry in self.ledger],
        }

    @classmethod
    def restore(cls, data: dict) -> "Economy":
        economy = cls(starting_budget=data.get("budget", 0.0))
        economy.gdp = data.get("gdp", 0.0)
        economy.total_construction_spend = data.get("total_construction_spend", 0.0)
        taxes = data.get("taxes", {})
        economy.taxes = TaxPolicy(
            income_tax=taxes.get("income_tax", 0.12),
            business_tax=taxes.get("business_tax", 0.15),
            property_tax=taxes.get("property_tax", 0.01),
        ).clamped()
        economy.ledger = [
            LedgerEntry(
                day=item["day"],
                income=item["income"],
                expenses=item["expenses"],
                budget_after=item["budget_after"],
                breakdown=item.get("breakdown", {}),
            )
            for item in data.get("ledger", [])
        ]
        return economy
