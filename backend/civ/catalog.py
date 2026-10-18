"""
What people can know and what they can build.

Technologies are discovered collectively: every hour spent thinking by the
fire, and every skilled hour of work, adds insight; enough insight and the
settlement's most curious minds make the discovery. Each discovery unlocks
buildings, house styles or better tools, so the look of the world tracks what
its people know.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tech:
    key: str
    name: str
    cost: float
    requires: tuple[str, ...] = ()
    #: One sentence shown in the chronicle when it is discovered.
    story: str = ""


TECHS: tuple[Tech, ...] = (
    Tech("fire", "Olov", 0, story="Odamlar olov yoqishni biladi."),
    Tech("tools", "Tosh qurollar", 200, ("fire",), "Tosh bolta va pichoq yasaldi — ish tezlashdi."),
    Tech("shelter", "Kulba qurish", 300, ("fire",), "Shox-shabbadan kulba qurishni o'rgandilar."),
    Tech("agriculture", "Dehqonchilik", 800, ("tools",), "Urug' ekib, hosil olish kashf qilindi!"),
    Tech("pottery", "Kulolchilik", 1100, ("fire", "agriculture"), "Loydan idish — don saqlash mumkin."),
    Tech("carpentry", "Duradgorlik", 1300, ("tools", "shelter"), "Yog'ochdan mustahkam uylar qurila boshlandi."),
    Tech("masonry", "Toshtaroshlik", 2100, ("tools", "carpentry"), "Toshdan uy qurish kashf qilindi."),
    Tech("medicine", "Tabobat", 2400, ("agriculture",), "O'simliklardan dori — kasallik kamaydi."),
    Tech("writing", "Yozuv", 3250, ("pottery",), "Yozuv paydo bo'ldi — bilim avloddan avlodga o'tadi."),
    Tech("trade", "Savdo", 3500, ("pottery", "carpentry"), "Bozor va savdo boshlandi."),
    Tech("bronze", "Bronza", 4250, ("masonry",), "Bronza asboblar — ish ikki barobar tezlashdi."),
    Tech("architecture", "Me'morchilik", 5500, ("masonry", "writing"), "Ko'p qavatli uylar va saroylar qurish mumkin."),
    Tech("governance", "Davlatchilik", 6500, ("writing", "trade"), "Shahar kengashi va rahbar saylovi joriy qilindi."),
    Tech("engineering", "Muhandislik", 9000, ("architecture", "bronze"), "Ko'priklar, suv inshootlari, katta shahar."),
)
TECH_BY_KEY = {tech.key: tech for tech in TECHS}


@dataclass(frozen=True)
class Blueprint:
    kind: str
    name: str
    width: int
    height: int
    wood: float
    stone: float
    #: Person-hours of building work.
    work: float
    requires: tuple[str, ...] = ()
    #: Beds, for homes.
    beds: int = 0
    category: str = "civic"
    levels: int = 1
    #: Quality ranking among homes; families upgrade towards higher ones.
    quality: int = 0


BLUEPRINTS: tuple[Blueprint, ...] = (
    # Homes, from a lean-to to a villa.
    Blueprint("hut", "Kulba", 1, 1, 8, 0, 10, ("shelter",), beds=3, category="home", quality=1),
    Blueprint("cabin", "Yog'och uy", 2, 2, 24, 0, 24, ("carpentry",), beds=5, category="home", quality=2),
    Blueprint("mudhouse", "Paxsa uy", 2, 2, 10, 8, 26, ("pottery",), beds=5, category="home", quality=2),
    Blueprint("stonehouse", "Tosh uy", 2, 2, 12, 26, 40, ("masonry",), beds=6, category="home", quality=3),
    Blueprint("twostory", "Ikki qavatli uy", 2, 3, 22, 34, 60, ("architecture",), beds=9, category="home", levels=2, quality=4),
    Blueprint("villa", "Hovli-saroy", 3, 3, 30, 50, 90, ("architecture",), beds=10, category="home", levels=2, quality=5),
    # The commons.
    Blueprint("campfire", "Gulxan", 1, 1, 2, 0, 2, ("fire",), category="civic"),
    Blueprint("storehouse", "Ombor", 2, 2, 16, 0, 18, ("shelter",), category="storage"),
    Blueprint("granary", "G'allaxona", 2, 2, 14, 10, 24, ("pottery",), category="storage"),
    Blueprint("field", "Ekin maydoni", 3, 3, 2, 0, 8, ("agriculture",), category="farm"),
    Blueprint("well", "Quduq", 1, 1, 2, 8, 12, ("pottery",), category="civic"),
    Blueprint("workshop", "Ustaxona", 2, 2, 18, 6, 26, ("carpentry",), category="work"),
    Blueprint("healer", "Tabib uyi", 2, 2, 14, 10, 26, ("medicine",), category="civic"),
    Blueprint("school", "Maktab", 3, 2, 20, 20, 40, ("writing",), category="civic"),
    Blueprint("market", "Bozor", 3, 3, 20, 14, 36, ("trade",), category="civic"),
    Blueprint("temple", "Ibodatxona", 3, 3, 16, 40, 60, ("masonry",), category="civic", levels=2),
    Blueprint("townhall", "Shahar kengashi", 3, 3, 30, 50, 80, ("governance",), category="civic", levels=2),
    Blueprint("palace", "Saroy", 4, 4, 50, 90, 160, ("architecture", "governance"), category="civic", levels=3),
)
BLUEPRINT_BY_KIND = {bp.kind: bp for bp in BLUEPRINTS}
HOME_KINDS = [bp.kind for bp in BLUEPRINTS if bp.category == "home"]

#: Settlement ranks by population, with the buildings that mark them.
RANKS: tuple[tuple[int, str], ...] = (
    (0, "Qarorgoh"),
    (12, "Ovul"),
    (30, "Qishloq"),
    (70, "Shaharcha"),
    (150, "Shahar"),
    (320, "Poytaxt"),
)


def rank_for(population: int) -> str:
    name = RANKS[0][1]
    for threshold, label in RANKS:
        if population >= threshold:
            name = label
    return name


ERAS: tuple[tuple[str, str], ...] = (
    ("engineering", "Muhandislik davri"),
    ("governance", "Davlatchilik davri"),
    ("bronze", "Bronza davri"),
    ("writing", "Yozuv davri"),
    ("agriculture", "Dehqonchilik davri"),
    ("fire", "Tosh asri"),
)


def era_for(known: set[str]) -> str:
    for key, name in ERAS:
        if key in known:
            return name
    return "Tosh asri"


@dataclass
class Storage:
    food: float = 0.0
    wood: float = 0.0
    stone: float = 0.0

    def as_dict(self) -> dict:
        return {"food": round(self.food), "wood": round(self.wood), "stone": round(self.stone)}


SETTLEMENT_NAMES = (
    "Yangiobod", "Navbahor", "Oqtepa", "Zarafshon", "Bog'ishamol", "Chinor", "Qoraqamish",
    "Shirinsoy", "Olmazor", "Tinchlik", "Do'stlik", "Kumushkon", "Oltinsoy", "Yashnobod",
    "Gulzor", "Sayhun", "Bunyodkor", "Mehrobod", "Nurafshon", "Qorasuv", "Bahoriston",
)

#: Colours families pick their walls from — chosen by temperament, not assigned.
WALL_COLOURS = (
    "#d9c7a3", "#c9a77c", "#e3d5b8", "#b88a5a", "#cfb08a", "#e8e0cc",
    "#a8b8c8", "#d4b49a", "#c2c9a6", "#e0c39a",
)
ROOF_COLOURS = ("#8a3b2e", "#6b4a2b", "#4f5b66", "#7c2f2f", "#3f5a3a", "#9a6b3a", "#5b4636")

