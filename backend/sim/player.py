"""
The human player — Umid Ravshanov.

The 3D president *is* the player. Two modes:

* `president` — decrees execute immediately. While the player is silent (offline
  or just watching), the AI still runs the city so work does not stop.
* `prime_minister` — the player briefs the president; those briefs become
  standing orders the AI carries out over simulated time.

Agents accept lasting orders in both modes, so the player can work with people
directly even when they are not looking at the screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .buildings.catalog import BuildingType
from .buildings.catalog import label_for as building_label
from .cabinet import LedgerItem, LedgerKind, TaskStatus
from .jobs.professions import Profession
from .jobs.professions import label_for as profession_label
from .president.models import Action, ActionKind
from .text import normalize
from .workshop import CodingJob

__all__ = ["normalize", "parse_command", "PlayerOffice", "PlayerRole", "StandingOrder"]


class PlayerRole(StrEnum):
    PRESIDENT = "president"
    PRIME_MINISTER = "prime_minister"


@dataclass(slots=True)
class StandingOrder:
    """A brief the AI president keeps working on while the player is away."""

    id: int
    text: str
    done: bool = False
    result: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "done": self.done,
            "result": self.result,
        }


@dataclass(slots=True)
class CommandReply:
    tick: int
    role: str
    text: str
    reply: str

    def as_dict(self) -> dict:
        return {
            "tick": self.tick,
            "role": self.role,
            "text": self.text,
            "reply": self.reply,
        }


@dataclass
class PlayerOffice:
    """Who is speaking, and what they left for the government to do."""

    owner_name: str = "Umid Ravshanov"
    role: PlayerRole = PlayerRole.PRESIDENT
    standing: list[StandingOrder] = field(default_factory=list)
    log: list[CommandReply] = field(default_factory=list)
    tasks: list[LedgerItem] = field(default_factory=list)
    decrees: list[LedgerItem] = field(default_factory=list)
    laws: list[LedgerItem] = field(default_factory=list)
    coding: CodingJob | None = None
    _next_order_id: int = 1
    _next_ledger_id: int = 1

    def remember(self, tick: int, text: str, reply: str) -> CommandReply:
        entry = CommandReply(tick=tick, role=self.role.value, text=text, reply=reply)
        self.log.append(entry)
        if len(self.log) > 40:
            del self.log[:-40]
        return entry

    def add_standing(self, text: str) -> StandingOrder:
        order = StandingOrder(id=self._next_order_id, text=text)
        self._next_order_id += 1
        self.standing.append(order)
        if len(self.standing) > 30:
            del self.standing[:-30]
        return order

    def file_item(self, item: LedgerItem) -> LedgerItem:
        bucket = {
            LedgerKind.TASK: self.tasks,
            LedgerKind.DECREE: self.decrees,
            LedgerKind.LAW: self.laws,
        }[item.kind]
        bucket.append(item)
        if len(bucket) > 80:
            del bucket[:-80]
        return item

    def next_ledger_id(self) -> int:
        value = self._next_ledger_id
        self._next_ledger_id += 1
        return value

    def law_codes(self) -> frozenset[str]:
        return frozenset(item.law_code for item in self.laws if item.law_code and item.status is not TaskStatus.BLOCKED)

    def open_tasks(self) -> list[LedgerItem]:
        return [
            item
            for item in self.tasks
            if item.status in (TaskStatus.QUEUED, TaskStatus.WAITING_AGENT, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
        ]

    def desks_snapshot(self, agents) -> list[dict]:
        found: dict[str, dict] = {}
        for agent in agents:
            desk = getattr(agent, "desk", "") or ""
            if not desk or desk in found:
                continue
            found[desk] = {
                "desk": desk,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "profession": agent.profession.value if agent.profession else None,
            }
        return list(found.values())

    def pending(self) -> list[StandingOrder]:
        return [order for order in self.standing if not order.done]

    def as_dict(self) -> dict:
        return {
            "owner_name": self.owner_name,
            "role": self.role.value,
            "standing": [order.as_dict() for order in self.standing[-12:]],
            "log": [entry.as_dict() for entry in self.log[-12:]],
            "tasks": [item.as_dict() for item in self.tasks[-16:][::-1]],
            "decrees": [item.as_dict() for item in self.decrees[-16:][::-1]],
            "laws": [item.as_dict() for item in self.laws[-16:][::-1]],
            "coding": self.coding.as_dict() if self.coding else None,
        }


#: Building phrases the player is likely to type in Uzbek (latin).
BUILDINGS: tuple[tuple[tuple[str, ...], BuildingType], ...] = (
    (("uy", "uylar", "uy-joy", "xonadon"), BuildingType.HOUSE),
    (("ikki qavatli", "townhouse", "qavatli uy"), BuildingType.TOWNHOUSE),
    (("kvartira", "dom", "ko'p qavatli", "korp", "apartment"), BuildingType.APARTMENT),
    (("avtobus bekat", "avtobus", "bus stop"), BuildingType.BUS_STOP),
    (("maktab",), BuildingType.SCHOOL),
    (("bogcha", "bog'cha", "bog‘cha", "kindergarten"), BuildingType.KINDERGARTEN),
    (("shifoxona", "kasalxona", "hospital"), BuildingType.HOSPITAL),
    (("klinika",), BuildingType.CLINIC),
    (("dokon", "do'kon", "do‘kon", "magazin"), BuildingType.SHOP),
    (("bozor", "market"), BuildingType.MARKET),
    (("kafe", "cafe"), BuildingType.CAFE),
    (("restoran",), BuildingType.RESTAURANT),
    (("zavod", "fabrika"), BuildingType.FACTORY),
    (("ofis", "office"), BuildingType.OFFICE),
    (("park", "bog'"), BuildingType.PARK),
    (("politsiya",), BuildingType.POLICE_STATION),
    (("universitet",), BuildingType.UNIVERSITY),
    (("apteka",), BuildingType.PHARMACY),
    (("elektr", "energiya", "tok stansiya", "power"), BuildingType.POWER_PLANT),
)

JOBS: tuple[tuple[tuple[str, ...], Profession], ...] = (
    (("buxgalter", "accountant", "hisobchi"), Profession.ACCOUNTANT),
    (("shifokor", "doctor", "vrach"), Profession.DOCTOR),
    (("hamshira", "nurse"), Profession.NURSE),
    (("oqituvchi", "o'qituvchi", "o‘qituvchi", "teacher"), Profession.TEACHER),
    (("quruvchi", "builder"), Profession.BUILDER),
    (("dasturchi", "developer", "programmist"), Profession.DEVELOPER),
    (("muhandis", "engineer"), Profession.ENGINEER),
    (("politsiya", "police", "militsiya"), Profession.POLICE),
    (("oshpaz", "chef"), Profession.CHEF),
    (("fermer", "farmer", "dehqon"), Profession.FARMER),
    (("haydovchi", "driver"), Profession.DRIVER),
    (("sotuvchi", "shopkeeper"), Profession.SHOPKEEPER),
    (("menejer", "manager"), Profession.MANAGER),
    (("advokat", "lawyer"), Profession.LAWYER),
    (("qorovul", "security"), Profession.SECURITY),
    (("elektrik", "electrician", "tokchi"), Profession.ELECTRICIAN),
)


@dataclass(slots=True)
class ParsedCommand:
    kind: str
    reply: str
    action: Action | None = None
    profession: Profession | None = None
    activity: str | None = None
    quantity: int = 1
    standing: bool = False
    note: str = ""




def _quantity(text: str) -> int:
    import re

    match = re.search(r"(\d+)\s*ta", text)
    if match:
        return max(1, min(20, int(match.group(1))))
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return max(1, min(20, int(match.group(1))))
    return 1


def parse_command(raw: str) -> ParsedCommand:
    """Turns a short Uzbek order into something the engine can do."""
    text = normalize(raw)
    if not text:
        return ParsedCommand("empty", "Buyruq yozilmagan.")

    standing = any(word in text for word in ("topshir", "prezidentga", "onga yukla", "o'zing qil"))
    qty = _quantity(text)

    if "soliq" in text:
        down = any(w in text for w in ("kamaytir", "tushir", "pasaytir", "kam"))
        up = any(w in text for w in ("oshir", "ko'tar", "kopaytir", "ko'paytir"))
        if down or up:
            delta = -0.02 if down else 0.02
            return ParsedCommand(
                "tax",
                "Soliq o'zgartiriladi.",
                action=Action(kind=ActionKind.SET_TAX, tax_name="income_tax", tax_value=delta),
                standing=standing,
            )

    for keys, building in BUILDINGS:
        if any(key in text for key in keys) and any(
            w in text for w in ("qur", "qurdir", "qurilsin", "quring", "och", "qil", "boshla")
        ):
            return ParsedCommand(
                "build",
                f"{qty} ta {building_label(building)} qurilishi buyurildi.",
                action=Action(kind=ActionKind.BUILD, building_type=building, quantity=qty),
                quantity=qty,
                standing=standing,
            )

    for keys, profession in JOBS:
        if any(key in text for key in keys) and any(
            w in text for w in ("ol", "yolla", "ishga", "qabul", "kerak", "top")
        ):
            return ParsedCommand(
                "hire",
                f"{profession_label(profession)} ishga olinadi.",
                profession=profession,
                quantity=qty,
                standing=standing,
            )

    if any(w in text for w in ("ishchi ol", "odam ol", "fuqaro ol", "agent ol", "aholini oshir")):
        return ParsedCommand(
            "recruit",
            f"{qty} kishi shaharga chaqirildi.",
            action=Action(kind=ActionKind.RECRUIT_WORKERS, quantity=qty),
            quantity=qty,
            standing=standing,
        )

    if any(w in text for w in ("ishga bor", "ishla", "ishni qil")):
        return ParsedCommand("agent_activity", "Ishga yuborildi.", activity="working", standing=standing)
    if any(w in text for w in ("uyga", "uyga qayt", "uyda bol")):
        return ParsedCommand("agent_activity", "Uyga yuborildi.", activity="going_home", standing=standing)
    if any(w in text for w in ("dokonga", "do'konga", "xarid")):
        return ParsedCommand("agent_activity", "Do'konga yuborildi.", activity="shopping", standing=standing)
    if any(w in text for w in ("park", "sayr", "dam ol")):
        return ParsedCommand("agent_activity", "Parkka yuborildi.", activity="leisure", standing=standing)
    if any(w in text for w in ("bekor", "toxta", "to'xta", "buyruqni ol")):
        return ParsedCommand("agent_clear", "Buyruq bekor qilindi.")

    if any(w in text for w in ("mahalla", "turar joy", "turar-joy", "turar joy hudud", "kvartal", "hudud", "rayon")) and any(
        w in text for w in ("och", "qur", "qurdir", "quring", "zonala", "yarat", "qil")
    ):
        return ParsedCommand(
            "zone",
            "Yangi turar-joy mahallasi ochiladi.",
            action=Action(kind=ActionKind.ZONE_DISTRICT),
            standing=standing,
        )

    if "bino" in text and any(w in text for w in ("qur", "qurdir", "quring", "qil")):
        return ParsedCommand(
            "build",
            "Uy qurilishi buyurildi.",
            action=Action(kind=ActionKind.BUILD, building_type=BuildingType.HOUSE, quantity=qty),
            quantity=qty,
            standing=standing,
        )

    if any(w in text for w in ("kengaytir", "kengaytirish", "xaritani kengaytir")):
        return ParsedCommand(
            "expand",
            "Shahar xaritasi kengaytiriladi.",
            action=Action(kind=ActionKind.EXPAND_MAP),
            standing=standing,
        )

    if any(w in text for w in ("qur", "qurdir", "qurilsin", "quring", "och")):
        return ParsedCommand(
            "unknown",
            "Qaysi bino qurilsin? Masalan: '10 ta uy qur', 'ikki qavatli uy qur', 'shifoxona qur'.",
        )
    if any(w in text for w in ("ol", "yolla", "ishga", "qabul")):
        return ParsedCommand(
            "unknown",
            "Qaysi kasb? Masalan: '5 ta quruvchi ishga ol', '3 ta shifokor ol'.",
        )

    return ParsedCommand(
        "unknown",
        "Bu buyruqni bajarib bo'lmaydi. Misol: '10 ta uy qur', '5 ta quruvchi ishga ol', 'avtobus bekat qur'.",
    )
