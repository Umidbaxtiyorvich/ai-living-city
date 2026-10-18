"""The player as leader: petitions, answers, teaching."""

from __future__ import annotations

import json

from civ.engine import Civilization
from civ.leader import understand
from civ.models import DAYS_PER_YEAR, TICKS_PER_DAY


def test_answers_are_understood():
    order = understand("Shimolga borib o'tin kesinglar")
    assert order.gather == {"wood": "north"}
    assert understand("Sizlarga dehqonchilikni o'rgataman").lessons == ["agriculture"]
    assert "forest_care" in understand("O'rmonni asranglar, ko'chat ekinglar").customs
    assert understand("baliq tutinglar").fishing
    assert understand("yangi joyga ko'chinglar").migrate == ""
    assert understand("hammaga qurilishni o'rgataman").skills == ["building"]
    assert understand("salom, qalaysan").empty
    # A sapling is not a move, and planting saplings is not farming.
    sapling = understand("O'rmonni asranglar, ko'chat ekinglar")
    assert sapling.customs == ["forest_care"]
    assert sapling.migrate is None and not sapling.lessons
    assert understand("bug'doy ekinglar").lessons == ["agriculture"]


def _stuck_villager(civ: Civilization):
    villager = next(p for p in civ.living if p.adult and not p.player)
    return villager, civ._raise(villager, "no_wood", "Yaqin atrofda o'tin qolmadi. Qayerdan o'tin olaylik?")


def test_a_stuck_person_walks_to_the_leader_and_follows_advice():
    civ = Civilization(seed=7)
    civ.genesis()
    villager, pet = _stuck_villager(civ)
    assert pet is not None and villager.task == "petition"
    for _ in range(30):
        civ.step()
    me = civ.player
    assert ((villager.x - me.x) ** 2 + (villager.y - me.y) ** 2) ** 0.5 < 3.0
    assert pet.arrived

    unclear = civ.leader_says("hmm", petition_id=pet.id)
    assert not unclear["ok"] and "tushunmadim" in unclear["reply"]
    assert pet.status == "open"

    answer = civ.leader_says("Shimolga borib o'tin kes", petition_id=pet.id)
    assert answer["ok"] and "Tushundim" in answer["reply"]
    assert pet.status == "solved"
    settlement = civ.settlements[villager.settlement_id]
    assert settlement.directives["wood"] == "north"
    assert villager.task != "petition"


def test_teaching_adds_knowledge_and_customs_that_persist():
    civ = Civilization(seed=7)
    civ.genesis()
    assert "agriculture" not in civ.known
    civ.leader_says("Hammaga dehqonchilikni o'rgataman. O'rmonni asranglar.")
    assert {"agriculture", "tools"} <= civ.known  # prerequisites come along
    assert civ.has("forest_care")
    restored = Civilization.restore(json.loads(json.dumps(civ.snapshot())))
    assert restored.has("forest_care") and "agriculture" in restored.known


def test_unanswered_petitions_expire():
    civ = Civilization(seed=7)
    civ.genesis()
    villager, pet = _stuck_villager(civ)
    for _ in range(TICKS_PER_DAY * 3):
        civ.step()
    assert pet.status == "expired"
    assert villager.task != "petition"


def test_women_carry_the_feminine_family_name():
    civ = Civilization(seed=11)
    civ.genesis()
    for _ in range(int(TICKS_PER_DAY * DAYS_PER_YEAR * 2)):
        civ.step()
    women = [p for p in civ.living if p.gender == "female"]
    assert women and all(p.surname.endswith("a") for p in women)
    men = [p for p in civ.living if p.gender == "male"]
    assert all(not p.surname.endswith(("ova", "eva")) for p in men)
