"""
Runs the city headlessly and prints its story.

A way to watch the simulation without a frontend: found a city, run it for a
number of simulated days, and report what the citizens and the president
actually did.

    python run_demo.py --days 120
"""

from __future__ import annotations

import argparse
import sys
import time

from sim.clock import MINUTES_PER_DAY
from sim.city.levels import LEVELS
from sim.engine import Engine
from sim.events.model import EventType, Severity
from sim.state import SimulationConfig, WorldState


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the AI Living City simulation")
    parser.add_argument("--days", type=int, default=90, help="simulated days to run")
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--map", type=int, default=100, help="map size in tiles")
    parser.add_argument("--population", type=int, default=30, help="founding population")
    return parser.parse_args()


def heading(text: str) -> None:
    print()
    print(text)
    print("-" * len(text))


def main() -> None:
    # Uzbek text and the report's arrows are outside the default Windows console
    # codepage, which raises rather than mangling the output.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()

    config = SimulationConfig(
        seed=args.seed,
        map_size=args.map,
        founding_population=args.population,
    )
    state = WorldState.create(config)
    engine = Engine(state)

    heading("Shahar ta'sis etilmoqda")
    engine.found_city()
    # Keep the whole city in full simulation so the demo shows real behaviour
    # rather than the statistical approximation used for off-screen agents.
    state.config.full_detail_radius = float(args.map * 2)
    state.camera_focus = (args.map / 2, args.map / 2)

    print(f"Prezident: {state.president.name} ({state.president.gender})")
    print(f"Aholi: {state.population}")
    print(f"Binolar: {len(state.buildings)}")
    print(f"Byudjet: {state.economy.budget:,.0f}")

    heading(f"{args.days} kun simulyatsiya qilinmoqda")
    started = time.perf_counter()
    engine.run(args.days * MINUTES_PER_DAY)
    elapsed = time.perf_counter() - started

    ticks = args.days * MINUTES_PER_DAY
    print(f"{ticks:,} tick — {elapsed:.1f}s ({ticks / elapsed:,.0f} tick/s)")

    state.refresh_stats()
    stats = state.stats

    heading("Shahar holati")
    print(f"Daraja:        {LEVELS[state.city_level].name}")
    print(f"Aholi:         {stats.population} ({stats.children} bola, {stats.seniors} keksa)")
    print(f"Bandlik:       {stats.employed} ishlaydi, {stats.unemployed} ishsiz "
          f"({stats.unemployment_rate:.0%})")
    print(f"Uy-joy:        {stats.housed}/{stats.population} joylashgan, "
          f"{stats.homeless} uysiz")
    print(f"Mamnunlik:     {stats.happiness:.1f}/100")
    print(f"Byudjet:       {state.economy.budget:,.0f}")
    print(f"YaIM:          {state.economy.gdp:,.0f}")
    print(f"Daromad solig'i: {state.economy.taxes.income_tax:.1%}")
    print(f"Binolar:       {stats.buildings_open} ochiq, "
          f"{stats.buildings_under_construction} qurilmoqda")
    print(f"Reyting:       {state.president.approval_rating:.1f}%")

    heading("Xizmatlar qoplamasi")
    for label, value in (
        ("Sog'liq", stats.healthcare_coverage),
        ("Ta'lim", stats.education_coverage),
        ("Savdo", stats.retail_coverage),
        ("Oziq-ovqat", stats.food_coverage),
        ("Elektr", stats.power_coverage),
        ("Xavfsizlik", stats.security_coverage),
    ):
        bar = "#" * int(value * 20)
        print(f"{label:<12} {value:>5.0%} {bar}")

    heading("Prezident qarorlari")
    decisions = state.president.decisions
    print(f"Jami: {len(decisions)}")
    for decision in decisions[-12:]:
        verdict = ""
        if decision.worked is not None:
            verdict = "  natija berdi" if decision.worked else "  natija bermadi"
        print(
            f"  kun {decision.tick // MINUTES_PER_DAY:>4} "
            f"[{decision.status:<9}] {decision.concern.code:<22} "
            f"{decision.concern.action.describe():<26}{verdict}"
        )

    heading("Muhim voqealar")
    for event in state.events.recent(20, min_severity=Severity.NOTICE):
        print(f"  kun {event.day:>4}  {event.type:<20} {event.text}")

    heading("Hayot statistikasi")
    for event_type, label in (
        (EventType.BIRTH, "Tug'ilish"),
        (EventType.DEATH, "O'lim"),
        (EventType.WEDDING, "Nikoh"),
        (EventType.HIRED, "Ishga qabul"),
        (EventType.MOVED_HOME, "Ko'chish"),
        (EventType.BUILDING_STARTED, "Qurilish boshlandi"),
        (EventType.BUILDING_COMPLETE, "Qurilish tugadi"),
        (EventType.ARRIVED, "Shaharga kelgan"),
    ):
        print(f"  {label:<20} {len(state.events.of_type(event_type, 10_000)):>5}")

    heading("Bir necha fuqaro")
    for agent in state.living_agents[:8]:
        home = "uyli" if agent.home_id else "uysiz"
        job = agent.profession or "ishsiz"
        print(
            f"  {agent.name:<24} {int(agent.age_years):>3} yosh  "
            f"{str(job):<16} {home:<7} "
            f"mamnunlik {agent.happiness:>5.1f}  {agent.activity}"
        )

    heading("Ishlash")
    performance = state.dashboard_payload()["performance"]
    print(f"Oxirgi tick:   {performance['last_tick_ms']:.3f} ms")
    print(f"Yo'l keshi:    {performance['path_cache']}")


if __name__ == "__main__":
    main()
