"""
The player as the people's leader.

When someone cannot solve a problem on their own — no timber left nearby, no
land for a house, an empty granary, an illness, nobody to marry — they walk to
the player and ask. The player answers in plain Uzbek; this module works out
what was meant and turns it into something the people can act on:

* a **directive** for one settlement ("go north for wood"),
* a **lesson** that adds knowledge at once ("I will teach you farming"),
* a **custom** everyone follows from then on ("look after the forest"),
* or a **deed** done now (move to a new place, build here, share food, marry).

Understanding is rule-based on purpose: it is instant, free and predictable, and
when it fails the person says so and offers examples instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .catalog import TECH_BY_KEY


@dataclass
class Petition:
    id: int
    person_id: int
    settlement_id: int | None
    kind: str
    text: str
    day: int
    status: str = "open"  # open | solved | expired
    answer: str = ""
    reply: str = ""
    arrived: bool = False


@dataclass
class Custom:
    key: str
    text: str
    day: int


@dataclass
class Order:
    """What an answer was understood to mean."""

    lessons: list[str] = field(default_factory=list)
    customs: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    gather: dict[str, str] = field(default_factory=dict)  # resource → direction
    fishing: bool = False
    migrate: str | None = None  # direction or "" for anywhere
    build_here: bool = False
    share_food: bool = False
    heal: bool = False
    marry: str | None = None
    everyone: bool = False

    @property
    def empty(self) -> bool:
        return not (
            self.lessons or self.customs or self.skills or self.gather or self.fishing
            or self.migrate is not None or self.build_here or self.share_food or self.heal or self.marry
        )


#: Technology by the words people use for it.
TECH_WORDS: tuple[tuple[str, str], ...] = (
    ("tools", r"qurol|bolta|pichoq|asbob"),
    ("agriculture", r"dehqon|urug'|hosil|ekinzor|ekinchilik|g'alla|bug'doy|ekin\s*ek"),
    ("pottery", r"kulol|loy|idish|xum"),
    ("carpentry", r"duradgor|taxta|yog'och\s*uy"),
    ("masonry", r"toshtarosh|tosh\s*uy|g'isht|devor"),
    ("medicine", r"tabobat|dori|davola|shifo|tabib"),
    ("writing", r"yozuv|yozish|savod|kitob|maktab"),
    ("trade", r"savdo|bozor|ayirboshla|tijorat"),
    ("bronze", r"bronza|metall|mis\b|temir"),
    ("architecture", r"me'mor|ko'p\s*qavat|saroy"),
    ("governance", r"davlat|kengash|saylov|qonun"),
    ("engineering", r"muhandis|ko'prik|inshoot"),
)

CUSTOM_WORDS: tuple[tuple[str, str, str], ...] = (
    ("forest_care", r"o'rmonni\s*asra|daraxt\s*ek|hammasini\s*kesma|ko'chat", "O'rmonni asraymiz: yosh daraxtlarni kesmaymiz, ko'chat ekamiz"),
    ("teach_children", r"bolalarni\s*o'qit|bolalarga\s*o'rgat|yoshlarga\s*o'rgat", "Bolalarga bilganimizni o'rgatamiz"),
    ("stockpile", r"zaxira|ombor(ni)?\s*to'ldir|qishga\s*tayyor|g'amla", "Har doim ikki baravar zaxira to'playmiz"),
    ("cooperation", r"birga\s*ishla|hamjihat|bir-?biringizga\s*yordam|hashar", "Hashar qilamiz: avval umumiy qurilishga yordam beramiz"),
    ("roads", r"yo'l\s*qur|yo'l\s*sol|ko'cha\s*qur", "Yo'llarni bosib-tekislab, yo'l qilamiz"),
    ("early_rise", r"erta\s*tur|tongda\s*tur", "Tong otishi bilan ishga chiqamiz"),
    ("feed_children", r"avval\s*bolalar|bolalarni\s*(avval\s*)?boq", "Avval bolalarni to'ydiramiz"),
)

SKILL_WORDS: tuple[tuple[str, str], ...] = (
    ("building", r"qurilish|qurish|usta"),
    ("farming", r"dehqonchilik|ekin"),
    ("woodcutting", r"o'tin|daraxt\s*kes"),
    ("stonework", r"tosh\s*qaz|toshtarosh"),
    ("gathering", r"meva|terish|baliq"),
    ("thinking", r"o'ylash|fikrlash|ixtiro"),
)

DIRECTIONS: tuple[tuple[str, str], ...] = (
    ("north", r"shimol|tepa|yuqori"),
    ("south", r"janub|past"),
    ("east", r"sharq|o'ng"),
    ("west", r"g'arb|chap"),
    ("water", r"daryo|ko'l|suv\s*bo'y|dengiz|qirg'oq"),
    ("forest", r"o'rmon"),
    ("rocks", r"tog'|qoya|toshloq"),
)

RESOURCE_WORDS: tuple[tuple[str, str], ...] = (
    ("wood", r"o'tin|yog'och|daraxt"),
    ("stone", r"tosh"),
    ("food", r"meva|ovqat|oziq|yegulik"),
)


def normalise(text: str) -> str:
    text = text.lower()
    for mark in ("ʻ", "‘", "’", "`", "ʼ", "´"):
        text = text.replace(mark, "'")
    text = text.replace("o‘", "o'").replace("g‘", "g'")
    return re.sub(r"\s+", " ", text).strip()


def _first(patterns: tuple[tuple[str, str], ...], text: str) -> str | None:
    for key, pattern in patterns:
        if re.search(pattern, text):
            return key
    return None


def understand(raw: str, *, names: list[str] | None = None) -> Order:
    """What the leader meant. Several instructions may share one answer."""
    text = normalise(raw)
    order = Order()
    order.everyone = bool(re.search(r"hamma|barcha|xalq|hammaga", text))
    teaching = bool(re.search(r"o'rgat|o'rgan|bilib\s*ol|kashf", text))

    # Knowledge: named technologies are taught outright.
    for key, pattern in TECH_WORDS:
        if re.search(pattern, text) and (teaching or key in ("agriculture", "medicine", "pottery")):
            order.lessons.append(key)
    for key, pattern, _ in CUSTOM_WORDS:
        if re.search(pattern, text):
            order.customs.append(key)
    if teaching:
        for key, pattern in SKILL_WORDS:
            if re.search(pattern, text):
                order.skills.append(key)

    if re.search(r"baliq", text):
        order.fishing = True
    # "ko'chat" (a sapling) is not "ko'chish" (moving away).
    if re.search(r"ko'ch(?!at)|yangi\s*joy|boshqa\s*joy|yangi\s*qishloq", text):
        order.migrate = _first(DIRECTIONS, text) or ""
    if re.search(r"shu\s*yer|yonimga|men\s*turgan|mana\s*bu\s*yer", text) and re.search(r"qur|uy", text):
        order.build_here = True
    if re.search(r"bo'lish|ulash|bo'lib\s*ber|ombordan|men\s*beraman|yordam\s*ber", text) and re.search(r"ovqat|oziq|don|ombor", text):
        order.share_food = True
    if re.search(r"dam\s*ol|uxla|davolan|tabibga|dori\s*ich|o't\s*damla", text):
        order.heal = True
    marry = re.search(r"(\w[\w']*)\s*(bilan|ga)\s*(turmush|uylan|nikoh)", text)
    if marry and names:
        wanted = marry.group(1)
        hit = next((n for n in names if normalise(n) == wanted or normalise(n).startswith(wanted)), None)
        if hit:
            order.marry = hit

    # Where to look for a resource: "shimolga borib o'tin kes".
    direction = _first(DIRECTIONS, text)
    resource = _first(RESOURCE_WORDS, text)
    if direction and resource and order.migrate is None:
        order.gather[resource] = direction
    return order


def describe(order: Order) -> list[str]:
    """How the person repeats the instruction back, in their own words."""
    lines: list[str] = []
    for key in order.lessons:
        lines.append(f"{TECH_BY_KEY[key].name}ni o'rgatdingiz — endi bilamiz!")
    custom_text = {key: text for key, _, text in CUSTOM_WORDS}
    for key in order.customs:
        lines.append(custom_text[key])
    skill_names = {
        "building": "qurilish", "farming": "dehqonchilik", "woodcutting": "o'tin kesish",
        "stonework": "tosh qazish", "gathering": "terish", "thinking": "fikrlash",
    }
    for key in order.skills:
        lines.append(f"{skill_names[key]} mahoratimiz oshdi")
    where = {
        "north": "shimolga", "south": "janubga", "east": "sharqqa", "west": "g'arbga",
        "water": "suv bo'yiga", "forest": "o'rmonga", "rocks": "toshloqqa",
    }
    resources = {"wood": "o'tin", "stone": "tosh", "food": "ovqat"}
    for resource, direction in order.gather.items():
        lines.append(f"{resources[resource]} uchun {where[direction]} boramiz")
    if order.fishing:
        lines.append("Baliq tutishni boshlaymiz")
    if order.migrate is not None:
        lines.append(f"Yangi joyga ko'chamiz{' — ' + where[order.migrate] if order.migrate in where else ''}")
    if order.build_here:
        lines.append("Uyimizni siz ko'rsatgan joyga quramiz")
    if order.share_food:
        lines.append("Boshqa qishloqdan ovqat keltiramiz")
    if order.heal:
        lines.append("Dam olib, o'tlar bilan davolanaman")
    if order.marry:
        lines.append(f"{order.marry} bilan sovchi qo'yamiz")
    return lines


HELP_BY_KIND = {
    "no_wood": "Masalan: «shimolga borib o'tin kes» yoki «o'rmonni asranglar, ko'chat eking».",
    "no_stone": "Masalan: «tog'ga borib tosh qaz» yoki «yangi joyga ko'chinglar».",
    "no_food": "Masalan: «baliq tuting», «dehqonchilikni o'rgataman» yoki «ombordan ovqat bo'lib beraman».",
    "famine": "Masalan: «dehqonchilikni o'rgataman», «baliq tuting» yoki «zaxira to'planglar».",
    "no_plot": "Masalan: «shu yerga uy quring» (o'zingiz kerakli joyda turing) yoki «yangi joyga ko'chinglar».",
    "sick": "Masalan: «dam ol, tabibga bor» yoki «tabobatni o'rgataman».",
    "lonely": "Masalan: «Malika bilan turmush qur».",
}
