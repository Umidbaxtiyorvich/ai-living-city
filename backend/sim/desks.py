"""
Desk work the cabinet can actually finish: images, spreadsheets, short video notes.

City construction still happens in the engine. This module only touches files
the player handed over, and writes a result they can download.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
from pathlib import Path

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"


def ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def process_desk_file(desk: str, source: Path, instruction: str, stem: str) -> tuple[str, str]:
    """
    Runs the specialist's craft on one file.

    Returns (relative filename, human result). Missing optional libraries fall
    back to a readable report rather than crashing the city loop.
    """
    folder = ensure_upload_dir()
    text = (instruction or "").lower()
    suffix = source.suffix.lower()

    if desk == "media" or suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return _edit_image(source, folder, stem, text)
    if desk == "accounting" or suffix in {".csv", ".xlsx", ".xls"}:
        return _books(source, folder, stem)
    if desk == "video" or suffix in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        return _montage(source, folder, stem, text)
    copied = folder / f"{stem}_nusxa{suffix or '.bin'}"
    shutil.copy2(source, copied)
    return copied.name, "Fayl qabul qilindi, mutaxassis ko'rib chiqdi."


def write_budget_report(stem: str, rows: list[tuple[str, str]]) -> str:
    folder = ensure_upload_dir()
    path = folder / f"{stem}_hisobot.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ko'rsatkich", "qiymat"])
        writer.writerows(rows)
    return path.name


def write_work_note(stem: str, title: str, body: str) -> str:
    """A finished desk product when the player did not attach a source file."""
    folder = ensure_upload_dir()
    path = folder / f"{stem}_hisobot.txt"
    path.write_text(f"{title}\n\n{body.strip()}\n", encoding="utf-8")
    return path.name


def _edit_image(source: Path, folder: Path, stem: str, text: str) -> tuple[str, str]:
    target = folder / f"{stem}_tahrir.png"
    try:
        from PIL import Image, ImageEnhance, ImageOps
    except ImportError:
        shutil.copy2(source, folder / f"{stem}_asl{source.suffix}")
        return f"{stem}_asl{source.suffix}", "Rasm qabul qilindi (tahrir kutubxonasi yo'q)."

    image = Image.open(source).convert("RGB")
    notes: list[str] = []
    if any(word in text for word in ("qora", "oq", "kulrang", "grayscale")):
        image = ImageOps.grayscale(image).convert("RGB")
        notes.append("qora-oq")
    if any(word in text for word in ("yorqin", "yorug", "bright")):
        image = ImageEnhance.Brightness(image).enhance(1.25)
        notes.append("yorqinlik")
    if any(word in text for word in ("kontrast", "aniq")):
        image = ImageEnhance.Contrast(image).enhance(1.35)
        notes.append("kontrast")
    if any(word in text for word in ("kichik", "thumbnail", "kichray")):
        image.thumbnail((720, 720))
        notes.append("kichraytirildi")
    if any(word in text for word in ("aylantir", "rotate")):
        image = image.rotate(90, expand=True)
        notes.append("aylantirildi")
    if not notes:
        image = ImageEnhance.Contrast(image).enhance(1.15)
        image = ImageEnhance.Color(image).enhance(1.1)
        notes.append("avto tahrir")
    image.save(target, "PNG")
    return target.name, "Rasm tahrirlandi: " + ", ".join(notes)


def _books(source: Path, folder: Path, stem: str) -> tuple[str, str]:
    target = folder / f"{stem}_hisobot.csv"
    rows = _read_table(source)
    numeric: list[float] = []
    for row in rows[1:] if len(rows) > 1 else rows:
        for cell in row:
            try:
                numeric.append(float(str(cell).replace(" ", "").replace(",", ".")))
            except ValueError:
                continue
    total = sum(numeric)
    average = total / len(numeric) if numeric else 0.0
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["maydon", "qiymat"])
        writer.writerow(["qatorlar", str(max(0, len(rows) - 1))])
        writer.writerow(["raqamlar", str(len(numeric))])
        writer.writerow(["yig'indi", f"{total:.2f}"])
        writer.writerow(["o'rtacha", f"{average:.2f}"])
    return target.name, (
        f"Hisob-kitob tayyor: {max(0, len(rows) - 1)} qator, "
        f"yig'indi {total:.2f}."
    )


def _read_table(source: Path) -> list[list[str]]:
    if source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            return [list(row) for row in csv.reader(handle)]
    try:
        import openpyxl
    except ImportError:
        raw = source.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return [["fayl", source.name], ["izoh", "Excel o'qilmadi, CSV yuboring."]]
        return [line.split(";") for line in text.splitlines() if line.strip()]
    book = openpyxl.load_workbook(source, data_only=True)
    sheet = book.active
    return [[str(cell) if cell is not None else "" for cell in row] for row in sheet.iter_rows(values_only=True)]


def _montage(source: Path, folder: Path, stem: str, text: str) -> tuple[str, str]:
    target = folder / f"{stem}_montaj.mp4"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        cmd = [
            ffmpeg, "-y", "-i", str(source),
            "-vf", "scale=1280:-2", "-t", "45",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-an", str(target),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            return target.name, "Video montaj qilindi (45 soniya, 1280px)."
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    copied = folder / f"{stem}_video{source.suffix}"
    shutil.copy2(source, copied)
    note = folder / f"{stem}_montaj.txt"
    note.write_text(
        f"Montaj reja\nmanba: {source.name}\nso'rov: {text or '—'}\n"
        "ffmpeg topilmadi, asl fayl saqlandi.",
        encoding="utf-8",
    )
    return copied.name, "Video qabul qilindi. Montaj reja yozildi (ffmpeg yo'q)."
