"""
The prime minister's coder writes real Python when a specialist is missing.

The city does not pretend: a living developer agent types a module into
`workshop/`, the file is saved, then imported, and the new specialist is spawned
from that module.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from .cabinet import DESK_LABELS, DESK_PROFESSION, Desk
from .jobs.professions import Profession

WORKSHOP_DIR = Path(__file__).resolve().parent.parent / "workshop"

CHARS_PER_TICK = 18


@dataclass
class CodingJob:
    coder_id: int
    coder_name: str
    desk: str
    task_id: int
    filename: str
    source: str
    typed: int = 0
    done: bool = False
    path: str = ""

    def visible(self) -> str:
        return self.source[: self.typed]

    def as_dict(self) -> dict:
        total = max(1, len(self.source))
        return {
            "coder_id": self.coder_id,
            "coder_name": self.coder_name,
            "desk": self.desk,
            "task_id": self.task_id,
            "filename": self.filename,
            "visible": self.visible(),
            "typed": self.typed,
            "total": total,
            "progress": round(self.typed / total, 3),
            "done": self.done,
            "path": self.path,
        }


def ensure_workshop() -> Path:
    WORKSHOP_DIR.mkdir(parents=True, exist_ok=True)
    init = WORKSHOP_DIR / "__init__.py"
    if not init.exists():
        init.write_text('"""Agent modules written by the city coder."""\n', encoding="utf-8")
    return WORKSHOP_DIR


def module_filename(desk: Desk) -> str:
    return f"{desk.value}_agent.py"


def generate_agent_source(
    *,
    desk: Desk,
    coder_name: str,
    day: int,
    task_text: str,
    agent_hint: str,
) -> str:
    profession = DESK_PROFESSION[desk]
    label = DESK_LABELS[desk]
    safe_task = (task_text or "").replace('"""', "'")
    safe_hint = (agent_hint or "").replace("\\", "\\\\").replace('"', "'")
    safe_coder = (coder_name or "Dasturchi").replace('"', "'")
    return f'''# -*- coding: utf-8 -*-
"""
{label} agenti.

Bu faylni shahar dasturchisi yozdi — tasodifiy matn emas.
Yozuvchi : {safe_coder}
Kun      : {day}
Buyruq   : {safe_task}

Bosh vazir tegishli mutaxassis yo'qligini ko'rib, dasturchiga
ushbu modulni yozishni topshirdi. Import qilingandan keyin
`spawn_spec()` yangi agentning kasbi va stolini beradi.
"""

from __future__ import annotations

DESK = "{desk.value}"
PROFESSION = "{profession.value}"
LABEL = "{label} agenti"
AUTHOR = "{safe_coder}"
CREATED_DAY = {day}


def spawn_spec() -> dict:
    """Yangi fuqaroni qanday yaratish kerakligi."""
    return {{
        "desk": DESK,
        "profession": PROFESSION,
        "age_years": 34.0,
        "skill": 90.0,
        "label": LABEL,
        "author": AUTHOR,
        "seed_note": "{safe_hint}",
    }}


def can_handle(task: str) -> bool:
    text = (task or "").lower()
    needles = {{
        "electricity": ("elektr", "energiya", "tok"),
        "accounting": ("hisob", "excel", "buxgalter"),
        "media": ("rasm", "foto", "tahrir"),
        "video": ("video", "montaj"),
        "legal": ("qonun", "qaror"),
        "construction": ("qur", "bino"),
        "health": ("shifo", "kasal"),
        "education": ("maktab", "ta'lim"),
        "security": ("politsiya", "xavfsiz"),
        "general": (),
    }}.get(DESK, ())
    return any(word in text for word in needles) or not needles


def describe() -> str:
    return f"{{LABEL}} — {{AUTHOR}} yozgan modul, {{CREATED_DAY}}-kun."
'''


def write_and_load(filename: str, source: str):
    """Saves the module and imports it. Returns the loaded module."""
    folder = ensure_workshop()
    path = folder / filename
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"workshop_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"modul yuklanmadi: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def profession_from_spec(data: dict) -> Profession:
    return Profession(str(data.get("profession", "manager")))
