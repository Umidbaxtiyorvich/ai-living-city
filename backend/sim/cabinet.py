"""
The presidential cabinet — routing work to the right desk.

The player (Umid Ravshanov) issues tasks, decrees and laws. A task goes to an
agent who can do that work. If nobody can, it goes to the prime minister, who
creates the specialist and hands the job over. Ledgers keep the three kinds of
record separate so the player can watch whether work is actually moving.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .jobs.professions import Profession


def normalize(text: str) -> str:
    return (
        text.lower()
        .replace("‘", "'")
        .replace("’", "'")
        .replace("`", "'")
        .strip()
    )


class Desk(StrEnum):
    ELECTRICITY = "electricity"
    ACCOUNTING = "accounting"
    MEDIA = "media"
    VIDEO = "video"
    LEGAL = "legal"
    CONSTRUCTION = "construction"
    HEALTH = "health"
    EDUCATION = "education"
    SECURITY = "security"
    GENERAL = "general"


class LedgerKind(StrEnum):
    TASK = "task"
    DECREE = "decree"
    LAW = "law"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    WAITING_AGENT = "waiting_agent"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


DESK_LABELS: dict[Desk, str] = {
    Desk.ELECTRICITY: "Elektr energiya",
    Desk.ACCOUNTING: "Hisob-kitob",
    Desk.MEDIA: "Rasm / dizayn",
    Desk.VIDEO: "Video montaj",
    Desk.LEGAL: "Qonun / yurist",
    Desk.CONSTRUCTION: "Qurilish",
    Desk.HEALTH: "Sog'liq",
    Desk.EDUCATION: "Ta'lim",
    Desk.SECURITY: "Xavfsizlik",
    Desk.GENERAL: "Umumiy",
}

DESK_PROFESSION: dict[Desk, Profession] = {
    Desk.ELECTRICITY: Profession.ELECTRICIAN,
    Desk.ACCOUNTING: Profession.ACCOUNTANT,
    Desk.MEDIA: Profession.DEVELOPER,
    Desk.VIDEO: Profession.DEVELOPER,
    Desk.LEGAL: Profession.LAWYER,
    Desk.CONSTRUCTION: Profession.BUILDER,
    Desk.HEALTH: Profession.DOCTOR,
    Desk.EDUCATION: Profession.TEACHER,
    Desk.SECURITY: Profession.POLICE,
    Desk.GENERAL: Profession.MANAGER,
}

DESK_KEYWORDS: tuple[tuple[Desk, tuple[str, ...]], ...] = (
    (Desk.ELECTRICITY, ("elektr", "energiya", "tok", "yorug", "svet", "power", "stansiya")),
    (Desk.ACCOUNTING, ("hisob", "excel", "buxgalter", "moliy", "byudjet", "balans", "xisob")),
    (Desk.VIDEO, ("video", "vedio", "montaj", "rolik", "film")),
    (Desk.MEDIA, ("rasm", "foto", "surat", "image", "dizayn", "o'zgartir", "uzgartir")),
    (Desk.LEGAL, ("advokat", "sud", "yurist")),
    (Desk.HEALTH, ("shifokor", "kasal", "sog'liq", "sogliq")),
    (Desk.EDUCATION, ("maktab", "o'qituv", "oqituv", "ta'lim", "talim")),
    (Desk.SECURITY, ("politsiya", "xavfsiz", "qorovul")),
    (Desk.CONSTRUCTION, ("qurilish", "bino", "uy qur", "inshoot")),
)

LAW_WORDS = ("qonun", "taqiqlansin", "majburiy", "farmoyish")
DECREE_WORDS = ("qaror", "farmon")


@dataclass(slots=True)
class LedgerNote:
    tick: int
    day: int
    text: str

    def as_dict(self) -> dict:
        return {"tick": self.tick, "day": self.day, "text": self.text}


@dataclass
class LedgerItem:
    id: int
    kind: LedgerKind
    desk: Desk
    title: str
    text: str
    status: TaskStatus = TaskStatus.QUEUED
    agent_id: int | None = None
    agent_name: str = ""
    created_tick: int = 0
    created_day: int = 0
    updated_tick: int = 0
    created_specialist: bool = False
    result: str = ""
    input_file: str = ""
    output_file: str = ""
    progress: float = 0.0
    law_code: str = ""
    upload_path: str = ""
    created_building_ids: list[int] = field(default_factory=list)
    notes: list[LedgerNote] = field(default_factory=list)

    def note(self, tick: int, day: int, text: str) -> None:
        self.notes.append(LedgerNote(tick=tick, day=day, text=text))
        if len(self.notes) > 24:
            del self.notes[:-24]
        self.updated_tick = tick

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "desk": self.desk.value,
            "desk_label": DESK_LABELS[self.desk],
            "title": self.title,
            "text": self.text,
            "status": self.status.value,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "created_day": self.created_day,
            "created_specialist": self.created_specialist,
            "result": self.result,
            "input_file": self.input_file,
            "output_file": self.output_file,
            "progress": round(self.progress, 2),
            "law_code": self.law_code,
            "upload_path": self.upload_path,
            "notes": [item.as_dict() for item in self.notes[-8:]],
        }


@dataclass(slots=True)
class RoutedWork:
    kind: LedgerKind
    desk: Desk
    title: str
    law_code: str = ""


def classify_work(raw: str, filename: str = "") -> RoutedWork:
    """Picks the ledger and the desk from the player's words (and optional file)."""
    text = normalize(raw)
    name = (filename or "").lower()

    if name.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
        desk = Desk.VIDEO
    elif name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
        desk = Desk.MEDIA
    elif name.endswith((".xlsx", ".xls", ".csv")):
        desk = Desk.ACCOUNTING
    else:
        desk = Desk.GENERAL
        for candidate, keys in DESK_KEYWORDS:
            if any(key in text for key in keys):
                desk = candidate
                break

    if any(word in text for word in LAW_WORDS):
        code = "mandatory_work" if any(w in text for w in ("ishla", "mehnat", "majburiy")) else ""
        if any(w in text for w in ("komendant", "komendantlik", "soat 22", "tungi")):
            code = "curfew"
        if not code:
            code = "general_law"
        return RoutedWork(LedgerKind.LAW, Desk.LEGAL, _title(raw, "Qonun"), law_code=code)

    if any(word in text for word in DECREE_WORDS) and desk is Desk.GENERAL:
        return RoutedWork(LedgerKind.DECREE, Desk.GENERAL, _title(raw, "Qaror"))

    if desk is not Desk.GENERAL:
        return RoutedWork(LedgerKind.TASK, desk, _title(raw, DESK_LABELS[desk]))

    return RoutedWork(LedgerKind.TASK, Desk.GENERAL, _title(raw, "Topshiriq"))


def _title(raw: str, prefix: str) -> str:
    text = " ".join((raw or "").split())
    if len(text) > 72:
        text = text[:69] + "..."
    return f"{prefix}: {text}" if text else prefix


def specialist_blueprint(desk: Desk, profession: Profession) -> str:
    """What the prime minister 'writes' to add a missing specialist."""
    return (
        f"# bosh vazir yangi agent qo'shdi\n"
        f"agent = spawn_citizen(age_years=34)\n"
        f"agent.desk = '{desk.value}'\n"
        f"agent.profession = '{profession.value}'\n"
        f"agent.skills['{profession.value}'] = 90\n"
        f"assign(agent, current_task)"
    )
