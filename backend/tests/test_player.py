from sim.buildings.catalog import CATALOG, BuildingType
from sim.buildings.models import BuildingStatus
from sim.engine import Engine
from sim.jobs.professions import Profession
from sim.player import parse_command
from sim.state import SimulationConfig, WorldState


def test_parse_build_and_hire():
    build = parse_command("3 ta uy qur")
    assert build.kind == "build"
    assert build.quantity == 3
    assert build.action is not None
    assert build.action.building_type is BuildingType.HOUSE

    hire = parse_command("buxgalter ol")
    assert hire.kind == "hire"
    assert hire.profession is Profession.ACCOUNTANT


def test_president_is_umid_ravshanov():
    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()
    assert state.president is not None
    assert state.president.name == "Umid Ravshanov"
    assert state.player.owner_name == "Umid Ravshanov"


def test_president_builds_houses_immediately():
    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()
    before = len(state.buildings)
    result = engine.handle_player_command("2 ta uy qur")
    assert result["ok"] is True
    assert "qurilishi boshlandi" in result["reply"]
    assert len(state.buildings) >= before + 1


def test_electricity_task_creates_a_specialist_when_missing():
    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()
    result = engine.handle_player_command("shaharga elektr energiya o'tkaz")
    assert result["ok"] is True
    task = state.player.tasks[-1]
    assert task.desk.value == "electricity"
    assert task.created_specialist is True
    assert task.agent_id is None
    assert state.player.coding is not None
    assert "kod" in result["reply"].lower() or "dasturchi" in result["reply"].lower()

    engine.run(400)

    assert state.player.coding is None or state.player.coding.done
    assert task.agent_id is not None
    specialist = state.agents[task.agent_id]
    assert specialist.desk == "electricity"
    assert (state.player.coding is None) or state.player.coding.path
    from pathlib import Path
    written = Path(state.player.coding.path) if state.player.coding and state.player.coding.path else None
    if written is None:
        written = Path(__file__).resolve().parents[1] / "workshop" / "electricity_agent.py"
    assert written.is_file()
    assert "spawn_spec" in written.read_text(encoding="utf-8")


def test_player_can_build_ahead_of_the_city_level_at_a_premium():
    """
    The AI keeps to the unlocked list; the player is the president and is
    charged for the expertise instead of being refused.
    """
    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()

    hospital = BuildingType.HOSPITAL
    assert hospital not in state.unlocked, "test needs a building the village cannot build"

    state.economy.budget = 20_000_000.0
    before = state.economy.budget
    result = engine.handle_player_command("shifoxona qur")

    assert result["ok"] is True
    assert "boshlandi" in result["reply"]
    assert "barobar" in result["reply"], "the premium must be stated"
    assert any(b.type is hospital for b in state.buildings.values())

    base = CATALOG[hospital].construction_cost
    spent = before - state.economy.budget
    assert spent > base * 2, f"early build was not charged the premium (spent {spent})"


def test_an_early_build_the_city_cannot_afford_is_refused():
    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()

    state.economy.budget = 50_000.0
    reply = engine.handle_player_command("shifoxona qur")["reply"]

    assert "byudjet yetmaydi" in reply
    assert not any(b.type is BuildingType.HOSPITAL for b in state.buildings.values())


def test_replies_are_written_in_uzbek():
    """
    Enum values are identifiers, not words. The player typed "uy" and used to be
    answered "3 ta house qurilishi boshlandi".
    """
    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()

    built = engine.handle_player_command("2 ta uy qur")["reply"]
    assert "uy" in built and "house" not in built

    hired = engine.handle_player_command("buxgalter ol")["reply"]
    assert "buxgalter" in hired and "accountant" not in hired

    for event in state.events.recent(60):
        assert "house" not in event.text, event.text


def test_laws_are_filed_separately_from_tasks():
    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()
    result = engine.handle_player_command("Qonun: ishchi yoshdagi hamma majburiy ishlasin")
    assert result["ok"] is True
    assert state.player.laws
    assert "mandatory_work" in state.player.law_codes()
    assert not any(item.kind.value == "law" for item in state.player.tasks)


def test_accounting_writes_a_report():
    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()
    result = engine.handle_player_command("hisob kitob qilib ber")
    assert result["ok"] is True
    task = state.player.tasks[-1]
    assert task.desk.value == "accounting"
    engine.run(400)
    assert task.output_file.endswith(".csv")
    assert task.status.value == "done"


def test_electricity_task_finishes_when_the_plant_opens():
    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()
    engine.handle_player_command("shaharga elektr energiya o'tkaz")
    task = state.player.tasks[-1]
    engine.run(400)
    plants = [b for b in state.buildings.values() if b.type is BuildingType.POWER_PLANT]
    assert plants, "mutaxassis stansiya qurishni boshlashi kerak"
    for plant in plants:
        plant.progress_days = float(plant.spec.build_days)
        plant.status = BuildingStatus.OPEN
    engine._advance_cabinet_tasks()
    assert task.status.value == "done"
    assert task.progress == 1.0


def test_second_task_is_not_blocked_by_the_first():
    """Old loop only advanced open_items[0], so later tasks froze forever."""
    from sim.cabinet import Desk, LedgerItem, LedgerKind, TaskStatus

    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()
    first = LedgerItem(
        id=1, kind=LedgerKind.TASK, desk=Desk.ELECTRICITY,
        title="elektr 1", text="elektr", status=TaskStatus.IN_PROGRESS, progress=0.95,
    )
    second = LedgerItem(
        id=2, kind=LedgerKind.TASK, desk=Desk.VIDEO,
        title="video", text="video montaj", status=TaskStatus.IN_PROGRESS, progress=0.2,
    )
    state.player.tasks.extend([first, second])
    engine._advance_cabinet_tasks()
    assert second.status is TaskStatus.DONE
    assert second.output_file


def test_video_task_without_upload_still_finishes():
    state = WorldState.create(SimulationConfig(seed=7, map_size=60, founding_population=20))
    engine = Engine(state)
    engine.found_city()
    result = engine.handle_player_command("qisqa video montaj qil")
    assert result["ok"] is True
    task = state.player.tasks[-1]
    engine.run(400)
    assert task.status.value == "done"
    assert task.output_file
