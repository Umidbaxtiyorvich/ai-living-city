"""
The civilization engine.

Nobody is in charge. Every person decides for themselves, every few simulated
minutes, what matters most right now — sleep, food, a house for the family,
wood for the neighbour's roof, a new idea by the fire, a walk with someone they
like — and then walks off and does it. The settlement's only collective act is
a shared plan of what to build next, drawn up from who is homeless, what is
running short and what has just been discovered.

Out of that come families and children, the first huts and then better houses,
fields once farming is discovered, paths worn by habit, and — when a place
gets crowded — a group that packs up and founds a new settlement elsewhere.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from sim.agents.generator import FEMALE_NAMES, MALE_NAMES, SURNAMES, surname_for

from .catalog import (
    BLUEPRINT_BY_KIND,
    BLUEPRINTS,
    RANKS,
    ROOF_COLOURS,
    SETTLEMENT_NAMES,
    TECH_BY_KEY,
    TECHS,
    WALL_COLOURS,
    era_for,
    rank_for,
)
from .models import (
    ADULT_AGE,
    DAYS_PER_YEAR,
    MINUTES_PER_TICK,
    TICKS_PER_DAY,
    WALK_TILES_PER_SECOND,
    Animal,
    Building,
    Goal,
    Person,
    Settlement,
)
from .leader import CUSTOM_WORDS, HELP_BY_KIND, Custom, Petition, describe, understand

CUSTOM_TEXT = {key: text for key, _, text in CUSTOM_WORDS}
from .world import BUILDABLE, MAX_WOOD, WALKABLE, Terrain, World

FOUNDERS = 10
CARRY_LIMIT = {"food": 8.0, "wood": 6.0, "stone": 4.0}
HOURS_PER_TICK = MINUTES_PER_TICK / 60.0

SKIN_TONES = ("#f1c9a5", "#e0ac80", "#c68c5a", "#a8703f", "#8d5a2b", "#d9a273")
HAIR_TONES = ("#1d140e", "#2b1d14", "#4a2f1d", "#6b4423", "#8c6a3f", "#121212")
CLOTHES = (
    "#3c6e9e", "#9e3c3c", "#4f7f3a", "#8a6d3b", "#6d4c8a", "#2f6f6a", "#b5763a",
    "#5a5a6e", "#a0522d", "#3a5f7f", "#7f3a5f", "#c2a14a",
)

#: Work an adult may choose, mapped to the skill it trains.
WORK_SKILL = {
    "forage": "gathering",
    "chop": "woodcutting",
    "quarry": "stonework",
    "build": "building",
    "farm": "farming",
    "think": "thinking",
}

TASK_LABEL = {
    "idle": "Dam olmoqda",
    "sleep": "Uxlamoqda",
    "eat": "Ovqatlanmoqda",
    "forage": "Meva termoqda",
    "chop": "O'tin kesmoqda",
    "quarry": "Tosh qazmoqda",
    "haul": "Yuk tashimoqda",
    "build": "Qurmoqda",
    "farm": "Dehqonchilik",
    "think": "O'ylamoqda",
    "socialize": "Suhbatlashmoqda",
    "court": "Uchrashuvda",
    "play": "O'ynamoqda",
    "learn": "O'rganmoqda",
    "migrate": "Ko'chmoqda",
    "walk": "Yurmoqda",
    "petition": "Rahbarga murojaat qilmoqda",
    "carried": "Onasining bag'rida",
}


@dataclass
class ChronicleEntry:
    day: int
    year: int
    text: str
    kind: str = "life"

    def as_dict(self) -> dict:
        return {"day": self.day, "year": self.year, "text": self.text, "kind": self.kind}


class Civilization:
    def __init__(self, seed: int = 7, size: int = 96) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.world = World.generate(size, seed)
        self.people: dict[int, Person] = {}
        self.buildings: dict[int, Building] = {}
        self.settlements: dict[int, Settlement] = {}
        # The first people already know fire and how to raise a simple hut.
        self.known: set[str] = {"fire", "shelter"}
        self.insight = 0.0
        self.tick = 0
        self.chronicle: list[ChronicleEntry] = []
        self.births = 0
        self.deaths = 0
        self.next_person = 1
        self.next_building = 1
        self.next_settlement = 1
        #: Tile index → building id, for placement checks.
        self.occupied: dict[int, int] = {}
        self.buildings_version = 1
        self.recent_thinkers: list[int] = []
        self.last_emigration_day: dict[int, int] = {}
        self.new_people: list[int] = []
        self.animals: dict[int, Animal] = {}
        #: Simulated seconds into the current tick, so movement is continuous.
        self.subsecond = 0.0
        #: Tests and headless runs move everyone once per tick; the live
        #: runtime instead calls `move()` many times a second.
        self.auto_move = True
        self.player_id: int | None = None
        self._night_now = False
        self.petitions: dict[int, Petition] = {}
        self.next_petition = 1
        self.customs: list[Custom] = []

    # -- time --------------------------------------------------------------

    @property
    def day(self) -> int:
        return self.tick // TICKS_PER_DAY

    @property
    def year(self) -> int:
        return self.day // DAYS_PER_YEAR + 1

    @property
    def hour(self) -> float:
        return ((self.tick % TICKS_PER_DAY) * MINUTES_PER_TICK * 60.0 + self.subsecond) / 3600.0

    @property
    def clock_seconds(self) -> float:
        return self.tick * MINUTES_PER_TICK * 60.0 + self.subsecond

    @property
    def night(self) -> bool:
        dawn = 4.5 if self.has("early_rise") else 5.5
        return self.hour >= 21.5 or self.hour < dawn

    def has(self, custom: str) -> bool:
        # Asked tens of thousands of times a tick; the list is only ever appended to.
        if len(self.customs) != getattr(self, "_custom_count", -1):
            self._custom_keys = {c.key for c in self.customs}
            self._custom_count = len(self.customs)
        return custom in self._custom_keys

    @property
    def living(self) -> list[Person]:
        return [p for p in self.people.values() if p.alive]

    def log(self, text: str, kind: str = "life") -> None:
        self.chronicle.append(ChronicleEntry(self.day, self.year, text, kind))
        if len(self.chronicle) > 400:
            del self.chronicle[:100]

    # -- genesis -----------------------------------------------------------

    def genesis(self, start_minutes: int | None = None) -> None:
        """Ten people, a fire, and the land."""
        site = self._best_site(None, min_distance=0, max_distance=self.world.width)
        settlement = self._found_settlement(site, founders=[])
        fire = self._place(settlement, "campfire", near=site, owner=None, instant=True)
        if fire is None:
            raise RuntimeError("no room for the first fire")
        settlement.storage.food = 30.0
        used_surnames: set[str] = set()
        for index in range(FOUNDERS):
            gender = "male" if index % 2 == 0 else "female"
            surname = self.rng.choice([s for s in SURNAMES if s not in used_surnames] or SURNAMES)
            used_surnames.add(surname)
            person = self._make_person(
                gender=gender,
                surname=surname,
                age_years=self.rng.uniform(17, 27),
                x=site[0] + self.rng.uniform(-2, 2),
                y=site[1] + self.rng.uniform(-2, 2),
            )
            person.settlement_id = settlement.id
            settlement.founders.append(person.id)
        # The story opens at the given time of day (the real clock when live),
        # or at sunrise.
        minutes = 7 * 60 if start_minutes is None else start_minutes
        self.tick = minutes // MINUTES_PER_TICK
        self.subsecond = (minutes % MINUTES_PER_TICK) * 60.0
        self.log("Birinchi o'n kishi gulxan atrofida to'plandi. Tarix boshlandi.", "era")
        self.ensure_player()
        self.spawn_animals()
        self._update_settlements()

    def _site_score(self, x: int, y: int) -> float:
        w = self.world
        if not w.inside(x, y) or w.at(x, y) not in (Terrain.GRASS, Terrain.FERTILE):
            return -1.0
        score = 0.0
        if w.near_water(x, y, 3):
            score += 3.0
        forest = rock = fertile = berries = 0
        for dy in range(-7, 8, 2):
            for dx in range(-7, 8, 2):
                nx, ny = x + dx, y + dy
                if not w.inside(nx, ny):
                    continue
                t = w.at(nx, ny)
                i = w.index(nx, ny)
                forest += t is Terrain.FOREST
                rock += t is Terrain.ROCK
                fertile += t is Terrain.FERTILE
                berries += w.berries[i] > 0
                if t is Terrain.WATER:
                    score -= 0.15
        score += min(forest, 10) * 0.35 + min(rock, 4) * 0.5 + fertile * 0.12 + berries * 0.4
        return score

    def _best_site(self, origin: tuple[float, float] | None, min_distance: float, max_distance: float) -> tuple[int, int]:
        w = self.world
        best = (-1e9, w.width // 2, w.height // 2)
        for _ in range(500):
            x = self.rng.randrange(4, w.width - 4)
            y = self.rng.randrange(4, w.height - 4)
            if origin is not None:
                d = math.hypot(x - origin[0], y - origin[1])
                if d < min_distance or d > max_distance:
                    continue
            # Stay clear of every other settlement.
            if any(math.hypot(x - s.x, y - s.y) < 16 for s in self.settlements.values() if not s.abandoned):
                continue
            score = self._site_score(x, y)
            if score > best[0]:
                best = (score, x, y)
        return best[1], best[2]

    def _found_settlement(self, site: tuple[int, int], founders: list[int]) -> Settlement:
        used = {s.name for s in self.settlements.values()}
        name = next((n for n in SETTLEMENT_NAMES if n not in used), f"Manzil-{self.next_settlement}")
        settlement = Settlement(
            id=self.next_settlement, name=name, x=site[0], y=site[1],
            founded_day=self.day, founders=list(founders),
        )
        self.next_settlement += 1
        self.settlements[settlement.id] = settlement
        return settlement

    def _make_person(
        self,
        *,
        gender: str,
        surname: str,
        age_years: float,
        x: float,
        y: float,
        parents: tuple[Person, Person] | None = None,
    ) -> Person:
        rng = self.rng
        names = MALE_NAMES if gender == "male" else FEMALE_NAMES
        used = {p.name for p in self.people.values() if p.alive and surname_for(p.surname, "male") == surname_for(surname, "male")}
        name = rng.choice([n for n in names if n not in used] or names)
        personality = {
            trait: round(rng.uniform(0.05, 0.95), 2)
            for trait in ("openness", "conscientiousness", "extraversion", "agreeableness", "ambition", "resilience")
        }
        if parents is not None:
            mother, father = parents
            # Children inherit temperament and looks, with variation.
            for trait in personality:
                inherited = (mother.trait(trait) + father.trait(trait)) / 2
                personality[trait] = round(min(0.95, max(0.05, inherited + rng.uniform(-0.25, 0.25))), 2)
            skin = rng.choice((mother.skin, father.skin))
            hair = rng.choice((mother.hair, father.hair))
            height = (mother.height + father.height) / 2 + rng.uniform(-0.05, 0.05)
        else:
            skin = rng.choice(SKIN_TONES)
            hair = rng.choice(HAIR_TONES)
            height = rng.uniform(0.92, 1.08) * (1.0 if gender == "male" else 0.94)
        person = Person(
            id=self.next_person,
            name=name,
            surname=surname_for(surname, gender),
            gender=gender,
            age_days=age_years * DAYS_PER_YEAR,
            x=x,
            y=y,
            personality=personality,
            skin=skin,
            hair=hair,
            clothes=rng.choice(CLOTHES),
            height=height,
            skills={skill: rng.uniform(3, 18) for skill in set(WORK_SKILL.values())},
        )
        self.next_person += 1
        self.people[person.id] = person
        self.new_people.append(person.id)
        return person

    # -- the tick ----------------------------------------------------------

    def step(self) -> None:
        if self.auto_move:
            self.move(MINUTES_PER_TICK * 60.0)
        self.tick += 1
        self.subsecond = 0.0
        self._night_now = self.night
        for person in list(self.people.values()):
            if person.alive:
                self._live(person)
        if self.tick % 36 == 0:
            for settlement in list(self.settlements.values()):
                if not settlement.abandoned:
                    self._plan(settlement)
        if self.tick % 6 == 0:
            self._grow_fields()
        if self.tick % TICKS_PER_DAY == 0:
            self._new_day()

    # -- one person --------------------------------------------------------

    def _live(self, p: Person) -> None:
        sleeping = p.task == "sleep" and not p.path
        if sleeping and self._night_now and p.health > 30 and p.stage != "baby":
            # Fast path for the third of the day everyone is asleep: just the body.
            p.hunger = max(0.0, p.hunger - 0.12 * (1.0 if p.adult else 0.6))
            p.energy = min(100.0, p.energy + 0.75)
            p.task_ticks += 1
            return
        child_rate = 0.35 if self.has("feed_children") else 0.6
        p.hunger = max(0.0, p.hunger - (0.12 if sleeping else 0.2) * (child_rate if not p.adult else 1.0))
        if sleeping:
            p.energy = min(100.0, p.energy + 0.75)
        else:
            p.energy = max(0.0, p.energy - (0.16 if p.task in ("chop", "quarry", "build", "farm") else 0.1))
        p.social = max(0.0, p.social - 0.05)
        if p.hunger < 8:
            p.health = max(0.0, p.health - 0.15)
        elif p.health < 100 and p.hunger > 40:
            p.health = min(100.0, p.health + 0.02)

        p.task_ticks += 1
        if p.stage == "baby":
            self._carry_baby(p)
            return

        if p.task == "petition":
            self._petition_tick(p)
            return

        if self._controlled(p):
            if not p.path:
                self._work(p)
            return

        if (p.task == "idle" and p.task_ticks >= 3) or self._should_reconsider(p):
            self._decide(p)

        if p.path:
            return
        self._work(p)

    def _controlled(self, p: Person) -> bool:
        """The player's character obeys the player unless they hand it to autopilot."""
        if not p.player or p.auto:
            return False
        # Even the player's character will not starve while they look away.
        if p.hunger < 12 and p.task not in ("eat", "forage"):
            self._decide(p)
        return True

    # -- continuous movement ------------------------------------------------

    def move(self, seconds: float) -> None:
        """Walks everyone `seconds` of simulated time. Called many times a second when live."""
        if seconds <= 0:
            return
        if not self.auto_move:
            self.subsecond = min(self.subsecond + seconds, MINUTES_PER_TICK * 60.0 - 0.001)
        now = self.clock_seconds
        for p in self.people.values():
            if not p.alive:
                continue
            if p.stage == "baby":
                self._carry_baby(p)
                continue
            if p.path:
                factor = 0.6 if p.stage in ("child", "elder") else 1.0
                if p.carry > 0:
                    factor *= 0.85
                self._walk(p, WALK_TILES_PER_SECOND * seconds * factor)
                if not p.path and p.task in ("eat", "haul"):
                    self._work(p)
                elif not p.path and p.task == "walk":
                    p.task = "idle"
            elif not self.auto_move and p.task == "petition" and now >= p.rest_until:
                # Keep up with the leader if they walk off.
                p.rest_until = now + 4.0
                self._petition_tick(p)
            elif not self.auto_move and p.task == "idle" and now >= p.rest_until and not (p.player and not p.auto):
                # Live, nobody stands about for ten minutes waiting for a tick.
                p.rest_until = now + 45.0
                self._decide(p)
        self._move_animals(seconds)

    def _should_reconsider(self, p: Person) -> bool:
        if p.task == "petition":
            return False
        if p.task == "sleep":
            return not self._night_now and p.energy > 70
        if p.task in ("migrate", "haul", "build", "eat"):
            return p.task_ticks > 200
        if self._night_now and p.task not in ("sleep", "migrate"):
            return True
        if p.hunger < 25 and p.task not in ("eat", "forage"):
            return True
        return p.task_ticks > 60 and p.carry <= 0

    def _carry_baby(self, p: Person) -> None:
        mother = self.people.get(p.parent_ids[0]) if p.parent_ids else None
        p.task = "carried"
        if mother is not None and mother.alive:
            p.x, p.y = mother.x + 0.25, mother.y + 0.1
            if p.hunger < 50:
                p.hunger = 90.0
                mother.hunger = max(0.0, mother.hunger - 6)
        elif p.hunger < 50:
            # An orphan is fed by the whole settlement.
            s = self.settlements.get(p.settlement_id) if p.settlement_id else None
            if s is not None and s.storage.food >= 0.5:
                s.storage.food -= 0.5
                p.hunger = 90.0
        p.energy = 80.0

    # -- deciding ----------------------------------------------------------

    def _decide(self, p: Person) -> None:
        settlement = self.settlements.get(p.settlement_id) if p.settlement_id else None
        p.task_ticks = 0
        p.target = None
        p.target_building = None
        p.path = []

        if p.task == "migrate" and settlement is not None and math.hypot(p.x - settlement.x, p.y - settlement.y) > 3:
            self._go(p, "migrate", (settlement.x, settlement.y))
            return

        if self._night_now or p.energy < 18:
            spot = self._bed_for(p, settlement)
            self._go(p, "sleep", spot)
            return

        if p.hunger < 40:
            if settlement is not None and settlement.storage.food >= 1:
                self._go(p, "eat", self._drop_point(settlement))
                return
            self._start_gathering(p, "forage", eat=True)
            return

        if p.stage == "child":
            anchor = self._home_or_center(p, settlement)
            jitter = (anchor[0] + self.rng.randint(-3, 3), anchor[1] + self.rng.randint(-3, 3))
            self._go(p, "play", jitter)
            return

        if p.stage == "teenager":
            parent = next((self.people[i] for i in p.parent_ids if i in self.people and self.people[i].alive), None)
            if parent is not None and self.rng.random() < (1.0 if self.has("teach_children") else 0.6):
                p.target_building = parent.id  # reused as "who I learn from"
                self._go(p, "learn", (int(parent.x), int(parent.y)))
                return

        if settlement is None:
            self._go(p, "idle", (int(p.x), int(p.y)))
            return

        for choice in self._choose_work(p, settlement):
            self._begin(p, settlement, choice)
            if p.task != "idle":
                return
        self._go(p, "idle", self._gathering_point(settlement))

    def _begin(self, p: Person, settlement: Settlement, choice: str) -> None:
        p.task = "idle"
        if choice == "socialize":
            self._go(p, "socialize", self._gathering_point(settlement))
        elif choice == "court":
            partner = self._courtship_target(p)
            if partner is not None:
                p.target_building = partner.id
                self._go(p, "court", (int(partner.x), int(partner.y)))
            else:
                self._go(p, "socialize", self._gathering_point(settlement))
        elif choice == "think":
            self._go(p, "think", self._gathering_point(settlement))
        elif choice == "build":
            self._start_building(p, settlement)
        elif choice == "farm":
            self._start_farming(p, settlement)
        elif choice in ("forage", "chop", "quarry"):
            self._start_gathering(p, choice)

    def _choose_work(self, p: Person, s: Settlement) -> list[str]:
        """Scores every option against the settlement's needs and the person's taste."""
        residents = max(1, s.population)
        sites = [b for b in self.buildings.values() if b.settlement_id == s.id and not b.complete and not b.demolished]
        workable = [b for b in sites if self._workable(b, s)]
        wood_need = sum(b.need_wood for b in sites) + residents * 1.5 - s.storage.wood
        stone_need = sum(b.need_stone for b in sites) + (residents * 0.6 if "masonry" in self.known else 0) - s.storage.stone
        food_need = residents * (10.0 if self.has("stockpile") else 5.0) - s.storage.food
        fields = [b for b in self.buildings.values() if b.settlement_id == s.id and b.kind == "field" and b.complete]

        scores: dict[str, float] = {
            "forage": 0.4 + max(0.0, food_need) / (residents * 3.0),
            "chop": 0.2 + max(0.0, wood_need) / 25.0,
            "quarry": (0.1 + max(0.0, stone_need) / 25.0) if stone_need > 0 else -1.0,
            "build": (0.9 + 0.25 * len(workable)) if workable else -1.0,
            "farm": (0.7 + max(0.0, food_need) / (residents * 4.0)) if fields else -1.0,
            "think": (0.05 + p.trait("openness") * 0.45 + p.awareness / 160.0) if self.next_discovery() else -1.0,
            "socialize": 0.1 + max(0.0, 50 - p.social) / 40.0 + p.trait("extraversion") * 0.2,
        }
        if fields:
            scores["forage"] *= 0.6
        if self.has("cooperation") and scores["build"] > 0:
            scores["build"] += 0.6
        if p.adult and p.partner_id is None and p.age_years < 40:
            scores["court"] = 0.3 + p.trait("extraversion") * 0.4 + (0.4 if p.social < 50 else 0)
        if self.hour >= 18:
            scores["think"] += 0.4
            scores["socialize"] += 0.5
        for task in scores:
            scores[task] += p.likes.get(task, 0.0) * 0.35 + self.rng.uniform(-0.15, 0.15)
            skill = WORK_SKILL.get(task)
            if skill:
                scores[task] += p.skill(skill) / 300.0
        ranked = sorted((task for task in scores if scores[task] > -0.5), key=lambda key: -scores[key])
        return ranked[:4]

    # -- movement ----------------------------------------------------------

    def _go(self, p: Person, task: str, target: tuple[float, float]) -> None:
        p.task = task
        tx, ty = int(round(target[0])), int(round(target[1]))
        world = self.world
        if not world.walkable(tx, ty):
            found = world.nearest(tx, ty, lambda i: world.terrain[i] in WALKABLE, radius=4)
            if found is None:
                p.target = None
                return
            tx, ty = found
        p.target = (tx, ty)
        start = (int(round(p.x)), int(round(p.y)))
        if not world.walkable(*start):
            # Stepped into rock or water somehow — hop to the nearest land.
            near = world.nearest(p.x, p.y, lambda i: world.terrain[i] in WALKABLE, radius=3)
            if near is not None:
                p.x, p.y = float(near[0]), float(near[1])
                start = near
        if math.hypot(tx - p.x, ty - p.y) < 0.8:
            p.path = []
            return
        if self.auto_move:
            # Moved a whole tick at a time (headless, or a year a second):
            # every walk ends within the tick, so nobody can see the route.
            p.path = [(tx, ty)]
            return
        p.path = world.route(start, (tx, ty))
        if not p.path:
            p.path = [(tx, ty)] if math.hypot(tx - p.x, ty - p.y) < 3 else []

    def _walk(self, p: Person, budget: float) -> None:
        while budget > 0 and p.path:
            tx, ty = p.path[0]
            dx, dy = tx - p.x, ty - p.y
            dist = math.hypot(dx, dy)
            before = (int(round(p.x)), int(round(p.y)))
            if dist <= budget:
                p.x, p.y = float(tx), float(ty)
                p.path.pop(0)
                budget -= dist
            else:
                p.x += dx / dist * budget
                p.y += dy / dist * budget
                budget = 0
            now_tile = (int(round(p.x)), int(round(p.y)))
            # Long straight segments still wear a path tile by tile.
            if now_tile != before and self.world.inside(*now_tile):
                self.world.walk_over(*now_tile, 3.0 if self.has("roads") else 1.0)

    # -- places ------------------------------------------------------------

    def _drop_point(self, s: Settlement) -> tuple[int, int]:
        stores = [
            b for b in self.buildings.values()
            if b.settlement_id == s.id and b.complete and b.kind in ("storehouse", "granary")
        ]
        if stores:
            return min(stores, key=lambda b: math.hypot(b.x - s.x, b.y - s.y)).door
        return (s.x, s.y + 1)

    def _gathering_point(self, s: Settlement) -> tuple[int, int]:
        for kind in ("market", "townhall", "temple", "campfire"):
            place = next(
                (b for b in self.buildings.values() if b.settlement_id == s.id and b.complete and b.kind == kind),
                None,
            )
            if place is not None:
                return place.door[0] + self.rng.randint(-2, 2), place.door[1] + self.rng.randint(0, 2)
        return s.x + self.rng.randint(-2, 2), s.y + self.rng.randint(-2, 2)

    def _home_or_center(self, p: Person, s: Settlement | None) -> tuple[int, int]:
        home = self.buildings.get(p.home_id) if p.home_id else None
        if home is not None and home.complete:
            return home.door
        if s is not None:
            return s.x, s.y
        return int(p.x), int(p.y)

    def _bed_for(self, p: Person, s: Settlement | None) -> tuple[int, int]:
        home = self.buildings.get(p.home_id) if p.home_id else None
        if home is not None and home.complete:
            cx, cy = home.center
            return int(round(cx)), int(round(cy))
        if s is not None:
            return s.x + self.rng.randint(-2, 2), s.y + self.rng.randint(-2, 2)
        return int(p.x), int(p.y)

    # -- work --------------------------------------------------------------

    def _start_gathering(self, p: Person, kind: str, eat: bool = False) -> None:
        world = self.world
        if kind == "forage":
            predicate = lambda i: world.berries[i] >= 1.0  # noqa: E731
        elif kind == "chop":
            # Under forest care only mature trees are felled.
            mature = MAX_WOOD * 0.5 if self.has("forest_care") else 1.0
            predicate = lambda i: world.terrain[i] == Terrain.FOREST and world.wood[i] >= mature  # noqa: E731
        else:
            predicate = lambda i: world.terrain[i] == Terrain.ROCK and world.stone[i] >= 1.0  # noqa: E731
        busy = {
            world.index(*q.target) for q in self.people.values()
            if q.alive and q is not p and q.task == kind and q.target is not None
        }
        settlement = self.settlements.get(p.settlement_id) if p.settlement_id else None
        resource = {"forage": "food", "chop": "wood", "quarry": "stone"}[kind]
        origin = self._directed_origin(settlement, resource) or (p.x, p.y)
        found = None
        if kind == "forage" and self.has("fishing") and not world.nearest(p.x, p.y, predicate, radius=10, skip=busy):
            found = None  # bushes are far: fish instead, as the leader taught
        else:
            found = world.nearest(origin[0], origin[1], predicate, radius=42, skip=busy)
        if found is None:
            if kind == "forage":
                # Fishing at the shore when the bushes are bare.
                shore = world.nearest(
                    p.x, p.y,
                    lambda i: world.terrain[i] in (1, 2, 5, 7) and world.near_water(i % world.width, i // world.width),
                    radius=40 if self.has("fishing") else 30,
                )
                if shore is not None:
                    self._go(p, "forage", shore)
                    p.target = shore
                    p.target_building = -1
                    p.carry_kind = "food" if not eat else p.carry_kind
                    return
            p.task = "idle"
            self._raise(p, {"chop": "no_wood", "quarry": "no_stone", "forage": "no_food"}[kind], {
                "chop": "Yaqin atrofda o'tin qolmadi. Qayerdan o'tin olaylik?",
                "quarry": "Tosh topolmayapmiz. Qayerdan qazib olsak bo'ladi?",
                "forage": "Atrofda meva ham, baliq ham qolmadi. Nima yeymiz?",
            }[kind])
            return
        # Standing on rock or in a forest blocks routing; aim for an adjacent free tile.
        tx, ty = found
        if not world.walkable(tx, ty):
            near = world.nearest(tx, ty, lambda i: world.terrain[i] in WALKABLE, radius=2)
            stand = near or found
        else:
            stand = found
        self._go(p, kind, stand)
        p.target = found
        p.target_building = -2 if eat else None

    def _workable(self, b: Building, s: Settlement) -> bool:
        """Whether someone can make progress on a site right now."""
        if b.supplied:
            return True
        if b.need_wood > 0.01 and s.storage.wood >= 1:
            return True
        return b.need_stone > 0.01 and s.storage.stone >= 1 and b.need_wood <= 0.01

    def _stone_reachable(self, s: Settlement) -> bool:
        if s.storage.stone >= 10:
            return True
        w = self.world
        return w.nearest(s.x, s.y, lambda i: w.terrain[i] == Terrain.ROCK and w.stone[i] >= 1, radius=26) is not None

    def _start_building(self, p: Person, s: Settlement) -> None:
        sites = [
            b for b in self.buildings.values()
            if b.settlement_id == s.id and not b.complete and not b.demolished and self._workable(b, s)
        ]
        if not sites:
            p.task = "idle"
            return
        # Own home first, then the nearest unfinished site.
        own = [b for b in sites if b.owner_id in (p.id, p.partner_id)]
        site = own[0] if own else min(sites, key=lambda b: math.hypot(b.x - p.x, b.y - p.y))
        p.target_building = site.id
        if not site.supplied:
            need_kind = "wood" if site.need_wood > 0.01 else "stone"
            have = s.storage.wood if need_kind == "wood" else s.storage.stone
            if have >= 1:
                take = min(CARRY_LIMIT[need_kind], have, site.need_wood if need_kind == "wood" else site.need_stone)
                if need_kind == "wood":
                    s.storage.wood -= take
                else:
                    s.storage.stone -= take
                p.carry_kind, p.carry = need_kind, take
                self._go(p, "haul", site.door)
                return
            self._start_gathering(p, "chop" if need_kind == "wood" else "quarry")
            return
        self._go(p, "build", site.door)

    def _start_farming(self, p: Person, s: Settlement) -> None:
        fields = [b for b in self.buildings.values() if b.settlement_id == s.id and b.kind == "field" and b.complete]
        if not fields:
            p.task = "idle"
            return
        field = max(fields, key=lambda b: (b.growth >= 1.0, -math.hypot(b.x - p.x, b.y - p.y)))
        p.target_building = field.id
        cx, cy = field.center
        self._go(p, "farm", (cx + self.rng.uniform(-1, 1), cy + self.rng.uniform(-1, 1)))

    def _work(self, p: Person) -> None:
        settlement = self.settlements.get(p.settlement_id) if p.settlement_id else None
        task = p.task
        tool = 1.0 + (0.4 if "tools" in self.known else 0) + (0.6 if "bronze" in self.known else 0)

        if task in ("forage", "chop", "quarry"):
            self._gather_tick(p, settlement, tool)
        elif task == "haul":
            self._deliver(p)
        elif task == "build":
            self._build_tick(p, settlement, tool)
        elif task == "farm":
            self._farm_tick(p, settlement, tool)
        elif task == "eat":
            if settlement is not None and settlement.storage.food >= 1:
                settlement.storage.food -= 1
                p.hunger = min(100.0, p.hunger + 60)
                p.social = min(100.0, p.social + 2)
            p.task = "idle"
        elif task == "think":
            gain = (0.4 + p.trait("openness") + p.awareness / 60.0) * HOURS_PER_TICK * 0.45
            if "writing" in self.known:
                gain *= 1.5
            self.insight += gain
            p.awareness = min(100.0, p.awareness + 0.01)
            p.improve("thinking", HOURS_PER_TICK)
            if p.id not in self.recent_thinkers[-12:]:
                self.recent_thinkers.append(p.id)
                del self.recent_thinkers[:-30]
            self._research()
            self._mingle(p, 0.15)
        elif task in ("socialize", "court"):
            p.social = min(100.0, p.social + 0.9)
            self._mingle(p, 0.6 if task == "socialize" else 0.3)
            if task == "court":
                other = self.people.get(p.target_building or -1)
                if other is not None and other.alive and math.hypot(other.x - p.x, other.y - p.y) < 2.5:
                    p.bond(other.id, 2.0)
                    other.bond(p.id, 1.6)
                    other.social = min(100.0, other.social + 0.5)
                elif other is not None and other.alive and p.task_ticks % 12 == 0:
                    self._go(p, "court", (int(other.x), int(other.y)))
        elif task == "learn":
            teacher = self.people.get(p.target_building or -1)
            if teacher is not None and teacher.alive:
                best = max(teacher.skills, key=lambda k: teacher.skills[k]) if teacher.skills else "gathering"
                p.improve(best, HOURS_PER_TICK * (1.6 if self.has("teach_children") else 0.8))
                if math.hypot(teacher.x - p.x, teacher.y - p.y) > 3 and p.task_ticks % 10 == 0:
                    self._go(p, "learn", (int(teacher.x), int(teacher.y)))
            p.awareness = min(100.0, p.awareness + 0.004)
        elif task == "play":
            p.social = min(100.0, p.social + 0.5)
            p.improve("gathering", HOURS_PER_TICK * 0.2)
            if p.task_ticks % 8 == 0:
                anchor = self._home_or_center(p, settlement)
                self._go(p, "play", (anchor[0] + self.rng.randint(-3, 3), anchor[1] + self.rng.randint(-3, 3)))
        elif task == "migrate":
            if settlement is not None and math.hypot(p.x - settlement.x, p.y - settlement.y) <= 3:
                p.task = "idle"
        # sleep / idle: nothing to do but be there.

    def _gather_tick(self, p: Person, s: Settlement | None, tool: float) -> None:
        world = self.world
        kind = {"forage": "food", "chop": "wood", "quarry": "stone"}[p.task]
        skill_name = WORK_SKILL[p.task]
        if p.carry_kind and p.carry_kind != kind and p.carry > 0:
            self._go_drop(p, s)
            return
        if p.target is None:
            p.task = "idle"
            return
        tx, ty = p.target
        i = world.index(tx, ty)
        rate = (0.5 + p.skill(skill_name) / 60.0) * tool * HOURS_PER_TICK * 6
        if kind == "food":
            if p.target_building == -1 or world.berries[i] <= 0:
                got = rate * (0.75 if self.has("fishing") else 0.5) if world.near_water(int(p.x), int(p.y), 2) else 0.0  # fishing
            else:
                got = world.take_berries(i, rate * 0.6)
        elif kind == "wood":
            got = world.take_wood(i, rate * 0.5)
        else:
            got = world.take_stone(i, rate * 0.3)
        p.improve(skill_name, HOURS_PER_TICK)
        self.insight += 0.004 * p.skill(skill_name) / 50.0

        if got <= 0:
            if p.carry > 0:
                self._go_drop(p, s)
            else:
                p.task = "idle"
            return
        if kind == "food" and (p.target_building == -2 or p.hunger < 30):
            # Too hungry to carry it home: eat on the spot.
            p.hunger = min(100.0, p.hunger + got * 12)
            if p.hunger > 75:
                p.task = "idle"
            return
        p.carry_kind = kind
        p.carry += got
        if p.carry >= CARRY_LIMIT[kind]:
            self._go_drop(p, s)

    def _go_drop(self, p: Person, s: Settlement | None) -> None:
        if s is None:
            p.carry, p.carry_kind = 0.0, ""
            p.task = "idle"
            return
        # Wood or stone goes straight to a site of one's own household if it needs it.
        own_site = next(
            (
                b for b in self.buildings.values()
                if b.settlement_id == s.id and not b.complete and not b.demolished
                and b.owner_id in (p.id, p.partner_id)
                and ((p.carry_kind == "wood" and b.need_wood > 0) or (p.carry_kind == "stone" and b.need_stone > 0))
            ),
            None,
        )
        if own_site is not None:
            p.target_building = own_site.id
            self._go(p, "haul", own_site.door)
            return
        p.target_building = None
        self._go(p, "haul", self._drop_point(s))

    def _deliver(self, p: Person) -> None:
        settlement = self.settlements.get(p.settlement_id) if p.settlement_id else None
        site = self.buildings.get(p.target_building) if p.target_building else None
        amount, kind = p.carry, p.carry_kind
        if site is not None and not site.complete and not site.demolished:
            if kind == "wood":
                used = min(amount, site.need_wood)
                site.need_wood -= used
                amount -= used
            elif kind == "stone":
                used = min(amount, site.need_stone)
                site.need_stone -= used
                amount -= used
        if settlement is not None and amount > 0:
            if kind == "food":
                settlement.storage.food += amount
            elif kind == "wood":
                settlement.storage.wood += amount
            elif kind == "stone":
                settlement.storage.stone += amount
        before = p.happiness
        p.carry, p.carry_kind = 0.0, ""
        self._learn_taste(p, {"food": "forage", "wood": "chop", "stone": "quarry"}.get(kind, "haul"), 0.6 + (p.happiness - before) / 10)
        p.task = "idle"

    def _build_tick(self, p: Person, s: Settlement | None, tool: float) -> None:
        site = self.buildings.get(p.target_building) if p.target_building else None
        if site is None or site.complete or site.demolished:
            p.task = "idle"
            return
        if not site.supplied:
            p.task = "idle"
            return
        rate = (0.7 + p.skill("building") / 70.0) * tool * HOURS_PER_TICK
        site.work_done += rate
        p.improve("building", HOURS_PER_TICK)
        self.insight += 0.005 * p.skill("building") / 50.0
        if site.work_done >= site.blueprint.work:
            self._complete(site, p)
            p.buildings_built += 1
            self._learn_taste(p, "build", 1.0)
            p.task = "idle"

    def _farm_tick(self, p: Person, s: Settlement | None, tool: float) -> None:
        field = self.buildings.get(p.target_building) if p.target_building else None
        if field is None or not field.complete:
            p.task = "idle"
            return
        p.improve("farming", HOURS_PER_TICK)
        if field.growth >= 1.0:
            harvest = (16 + p.skill("farming") / 6) * tool
            field.growth = 0.0
            self.buildings_version += 1
            p.carry_kind, p.carry = "food", 0.0
            if s is not None:
                s.storage.food += harvest
            self._learn_taste(p, "farm", 1.2)
            p.task = "idle"
            return
        field.growth = min(1.0, field.growth + 0.0016 * (0.6 + p.skill("farming") / 80))

    def _grow_fields(self) -> None:
        changed = False
        for b in self.buildings.values():
            if b.kind == "field" and b.complete and b.growth < 1.0:
                b.growth = min(1.0, b.growth + 0.0015)
                changed = True
        if changed and self.tick % 36 == 0:
            self.buildings_version += 1

    def _mingle(self, p: Person, strength: float) -> None:
        for q in self.people.values():
            if q is p or not q.alive or q.settlement_id != p.settlement_id:
                continue
            if abs(q.x - p.x) < 2.5 and abs(q.y - p.y) < 2.5:
                compat = 1.0 - abs(p.trait("agreeableness") - q.trait("agreeableness")) * 0.6
                p.bond(q.id, strength * compat)
                q.social = min(100.0, q.social + 0.1)

    def _learn_taste(self, p: Person, task: str, reward: float) -> None:
        current = p.likes.get(task, 0.0)
        p.likes[task] = round(current + 0.2 * (reward - current), 3)

    def _courtship_target(self, p: Person) -> Person | None:
        candidates = [
            q for q in self.people.values()
            if q.alive and q.adult and q.gender != p.gender and q.partner_id is None
            and q.settlement_id == p.settlement_id and abs(q.age_years - p.age_years) < 14
            and q.id not in p.parent_ids and p.id not in q.parent_ids
            and not set(q.parent_ids) & set(p.parent_ids)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda q: p.relationships.get(q.id, 0.0) + self.rng.uniform(0, 8))


    # -- the player ----------------------------------------------------------

    def ensure_player(self, name: str = "Umid", surname: str = "Ravshanov") -> Person:
        existing = next((p for p in self.people.values() if p.player and p.alive), None)
        if existing is not None:
            self.player_id = existing.id
            return existing
        home = next((s for s in self.settlements.values() if not s.abandoned), None)
        x, y = (home.x, home.y) if home else (self.world.width / 2, self.world.height / 2)
        person = self._make_person(gender="male", surname=surname, age_years=30, x=x + 1.5, y=y + 1.5)
        person.name = name
        person.player = True
        person.auto = False
        person.skin, person.hair, person.clothes = "#d9a273", "#1d140e", "#2f5d8a"
        person.settlement_id = home.id if home else None
        person.personality.update({"openness": 0.85, "ambition": 0.9, "extraversion": 0.7})
        self.player_id = person.id
        self.log(f"{name} {surname} bu dunyoga qadam qo'ydi.", "era")
        return person

    @property
    def player(self) -> Person | None:
        p = self.people.get(self.player_id) if self.player_id else None
        return p if p is not None and p.alive else None

    def player_goto(self, x: float, y: float) -> str:
        p = self.player
        if p is None:
            return "Qahramon topilmadi"
        self._go(p, "walk", (x, y))
        return "Yo'lga chiqdingiz" if p.path or p.target else "U yerga yo'l yo'q"

    def player_do(self, action: str) -> str:
        p = self.player
        if p is None:
            return "Qahramon topilmadi"
        s = self.settlements.get(p.settlement_id) if p.settlement_id else None
        p.task_ticks = 0
        if action == "auto":
            p.auto = not p.auto
            return "Avtopilot yoqildi — qahramoningiz o'zi yashaydi" if p.auto else "Boshqaruv sizda"
        if action in ("forage", "chop", "quarry"):
            self._start_gathering(p, action)
        elif action == "build" and s is not None:
            self._start_building(p, s)
        elif action == "eat":
            if s is not None and s.storage.food >= 1:
                self._go(p, "eat", self._drop_point(s))
            else:
                self._start_gathering(p, "forage", eat=True)
        elif action == "sleep":
            self._go(p, "sleep", self._bed_for(p, s))
        elif action == "think" and s is not None:
            self._go(p, "think", self._gathering_point(s))
        elif action == "farm" and s is not None:
            self._start_farming(p, s)
        elif action == "rest":
            self._go(p, "idle", (int(p.x), int(p.y)))
        return self.task_label(p.task) if p.task != "idle" or action == "rest" else "Hozir buni qilib bo'lmaydi"

    def task_label(self, task: str) -> str:
        return TASK_LABEL.get(task, task)

    def player_build(self, kind: str, x: int, y: int, creative: bool = False) -> dict:
        p = self.player
        if p is None:
            return {"ok": False, "reply": "Qahramon topilmadi"}
        bp = BLUEPRINT_BY_KIND.get(kind)
        if bp is None:
            return {"ok": False, "reply": "Bunday bino yo'q"}
        s = self.settlements.get(p.settlement_id) if p.settlement_id else None
        if s is None:
            return {"ok": False, "reply": "Avval biror manzilga qo'shiling"}
        ox, oy = int(round(x - (bp.width - 1) / 2)), int(round(y - (bp.height - 1) / 2))
        if not self._plot_ok(ox, oy, bp.width, bp.height, field=kind == "field"):
            return {"ok": False, "reply": "Bu joyga qurib bo'lmaydi — suv, tosh yoki boshqa bino bor"}
        building = Building(
            id=self.next_building, kind=kind, x=ox, y=oy, settlement_id=s.id, owner_id=p.id,
            need_wood=bp.wood, need_stone=bp.stone,
            wall=WALL_COLOURS[p.id % len(WALL_COLOURS)], roof=ROOF_COLOURS[p.id % len(ROOF_COLOURS)],
            style=self.rng.randrange(8),
        )
        self.next_building += 1
        self.buildings[building.id] = building
        for dy in range(bp.height):
            for dx in range(bp.width):
                i = self.world.index(ox + dx, oy + dy)
                self.occupied[i] = building.id
                if self.world.terrain[i] == Terrain.FOREST:
                    self.world.take_wood(i, 99)
                    self.world.set(ox + dx, oy + dy, Terrain.GRASS)
        self.buildings_version += 1
        if creative:
            building.need_wood = building.need_stone = 0.0
            building.work_done = bp.work
            self._complete(building, p)
            return {"ok": True, "reply": f"{bp.name} tayyor!", "id": building.id}
        self.log(f"{p.name} {p.surname} {bp.name.lower()} qurishni boshladi", "build")
        return {
            "ok": True,
            "id": building.id,
            "reply": f"{bp.name} qurilishi boshlandi: {int(bp.wood)} yog'och, {int(bp.stone)} tosh kerak. "
                     "Qo'shnilar yordam beradi, o'zingiz ham \"Qurish\" tugmasini bosing.",
        }

    def player_talk(self, other_id: int) -> str:
        p = self.player
        q = self.people.get(other_id)
        if p is None or q is None or not q.alive or q is p:
            return "Suhbatdosh topilmadi"
        if math.hypot(q.x - p.x, q.y - p.y) > 3.0:
            self._go(p, "walk", (int(q.x), int(q.y)))
            return f"{q.name} tomon yurdingiz — yetib borgach yana bosing"
        warmth = 6 + q.trait("agreeableness") * 8
        value = p.bond(q.id, warmth)
        q.bond(p.id, warmth * 0.9)
        p.social = min(100.0, p.social + 15)
        q.social = min(100.0, q.social + 10)
        q.remember(f"{p.name} bilan suhbatlashdim")
        line = q.thought or "Salom!"
        return f"{q.name}: «{line}» (munosabat {int(value)})"

    def player_propose(self, other_id: int) -> str:
        p = self.player
        q = self.people.get(other_id)
        if p is None or q is None or not q.alive:
            return "Topilmadi"
        if p.partner_id is not None:
            return "Siz allaqachon oilalisiz"
        if q.gender == p.gender or not q.adult or q.partner_id is not None:
            return f"{q.name} bilan turmush qurib bo'lmaydi"
        if q.relationships.get(p.id, 0.0) < 20:
            return f"{q.name}: «Sizni hali yaxshi tanimayman...» — ko'proq suhbatlashing"
        self._marry(p, q)
        return f"Tabriklaymiz! {q.name} rozi bo'ldi — siz oila qurdingiz 💍"


    # -- the leader --------------------------------------------------------------

    def _raise(self, p: Person, kind: str, text: str) -> Petition | None:
        """Someone who is stuck goes to the leader — within reason."""
        me = self.player
        if me is None or p.player or not p.adult or p.stage == "elder" and kind != "sick":
            return None
        if self.day - p.last_petition_day < 3:
            return None
        open_now = [x for x in self.petitions.values() if x.status == "open"]
        if len(open_now) >= 6 or any(x.person_id == p.id for x in open_now):
            return None
        if any(x.kind == kind and x.settlement_id == p.settlement_id for x in open_now):
            return None
        pet = Petition(
            id=self.next_petition, person_id=p.id, settlement_id=p.settlement_id,
            kind=kind, text=text, day=self.day,
        )
        self.next_petition += 1
        self.petitions[pet.id] = pet
        p.last_petition_day = self.day
        p.carry, p.carry_kind = 0.0, ""
        p.target_building = pet.id
        p.task_ticks = 0
        self._go(p, "petition", (me.x + self.rng.uniform(-1.5, 1.5), me.y + self.rng.uniform(-1.5, 1.5)))
        p.task = "petition"
        p.thought = f"Rahbarimizdan maslahat so'rayman: {text}"
        return pet

    def _petition_tick(self, p: Person) -> None:
        pet = self.petitions.get(p.target_building or -1)
        me = self.player
        if pet is None or pet.status != "open" or me is None:
            p.task = "idle"
            return
        if p.hunger < 12:
            # Hunger wins; the question can wait.
            pet.arrived = False
            p.task = "idle"
            self._decide(p)
            return
        if math.hypot(me.x - p.x, me.y - p.y) > 2.2:
            if not p.path or p.task_ticks % 2 == 0:
                self._go(p, "petition", (me.x + self.rng.uniform(-1.2, 1.2), me.y + self.rng.uniform(-1.2, 1.2)))
                p.task = "petition"
            pet.arrived = False
        else:
            p.path = []
            if not pet.arrived:
                pet.arrived = True

    def _daily_troubles(self) -> None:
        for pet in self.petitions.values():
            if pet.status == "open" and self.day - pet.day >= 2:
                pet.status = "expired"
                person = self.people.get(pet.person_id)
                if person is not None and person.task == "petition":
                    person.task = "idle"
                    person.remember("Rahbarimiz javob bermadi, o'zimiz hal qilishga urindik")
        if self.player is None:
            return
        for s in self.settlements.values():
            if s.abandoned or s.population < 5:
                continue
            adults = [p for p in self.people.values() if p.alive and p.settlement_id == s.id and p.adult and not p.player]
            if not adults:
                continue
            if s.storage.food < s.population * 0.3 and any(p.hunger < 30 for p in adults):
                self._raise(self.rng.choice(adults), "famine", "Omborda ovqat tugab qoldi, bolalar och. Nima qilaylik?")
        for p in self.living:
            if p.player or not p.adult:
                continue
            if p.health < 35:
                self._raise(p, "sick", "Kasal bo'lib qoldim, ahvolim og'ir. Nima qilay?")
            elif (
                p.partner_id is None and 24 <= p.age_years <= 40
                and self._courtship_target(p) is None and self.rng.random() < 0.05
            ):
                self._raise(p, "lonely", "Oila qurmoqchiman, lekin munosib juft topolmayapman. Maslahat bering.")

    def _directed_origin(self, s: Settlement | None, resource: str) -> tuple[float, float] | None:
        if s is None:
            return None
        direction = s.directives.get(resource)
        if not direction:
            return None
        w = self.world
        offsets = {"north": (0, -24), "south": (0, 24), "east": (24, 0), "west": (-24, 0)}
        if direction in offsets:
            dx, dy = offsets[direction]
            return (min(w.width - 2, max(1, s.x + dx)), min(w.height - 2, max(1, s.y + dy)))
        kinds = {"water": Terrain.WATER, "forest": Terrain.FOREST, "rocks": Terrain.ROCK}
        target = kinds.get(direction)
        if target is None:
            return None
        found = w.nearest(s.x, s.y, lambda i: w.terrain[i] == target, radius=60)
        return (float(found[0]), float(found[1])) if found else None

    def _teach(self, key: str, teacher: Person | None) -> list[str]:
        """Teaches a technology and anything it rests on."""
        taught: list[str] = []
        tech = TECH_BY_KEY.get(key)
        if tech is None or key in self.known:
            return taught
        for need in tech.requires:
            taught += self._teach(need, teacher)
        self.known.add(key)
        taught.append(tech.name)
        who = f"{teacher.name} {teacher.surname}" if teacher else "Rahbar"
        self.log(f"O'RGATILDI: {tech.name}. {who} xalqqa o'rgatdi — {tech.story}", "discovery")
        if teacher is not None:
            teacher.discoveries += 1
        return taught

    def _migrate_now(self, asker: Person, direction: str) -> bool:
        s = self.settlements.get(asker.settlement_id) if asker.settlement_id else None
        if s is None:
            return False
        offsets = {"north": (0, -30), "south": (0, 30), "east": (30, 0), "west": (-30, 0)}
        if direction in offsets:
            dx, dy = offsets[direction]
            origin = (s.x + dx, s.y + dy)
            site = self._best_site(origin, 0, 18)
        else:
            site = self._best_site((s.x, s.y), 16, 40)
        if math.hypot(site[0] - s.x, site[1] - s.y) < 12:
            return False
        head = asker
        partner = self.people.get(head.partner_id) if head.partner_id else None
        kids = [self.people[c] for c in head.children_ids if c in self.people and self.people[c].alive and not self.people[c].adult]
        group = [head] + ([partner] if partner and partner.alive else []) + kids
        singles = [
            p for p in self.people.values()
            if p.alive and p.settlement_id == s.id and p.adult and p.partner_id is None
            and p.age_years < 30 and p not in group and not p.player
        ]
        group += singles[:3]
        new = self._found_settlement(site, [p.id for p in group])
        new.storage.food = s.storage.food * 0.2
        s.storage.food -= new.storage.food
        for member in group:
            old_home = member.home_id
            member.settlement_id = new.id
            member.home_id = None
            member.task = "migrate"
            member.task_ticks = 0
            member.path = []
            self._decide(member)
            member.remember(f"Rahbarimiz maslahati bilan {new.name}ga ko'chdik")
            if old_home is not None:
                self._vacate(old_home, [member])
        self.log(f"YANGI MANZIL: rahbar maslahati bilan {head.name} {head.surname} {len(group)} kishi bilan {new.name}ga asos soldi", "settlement")
        return True

    def leader_says(self, text: str, petition_id: int | None = None, person_id: int | None = None) -> dict:
        """The leader's words, to one petitioner, one person, or everyone."""
        me = self.player
        pet = self.petitions.get(petition_id) if petition_id else None
        if pet is not None and pet.status != "open":
            return {"ok": False, "reply": "Bu murojaat allaqachon yopilgan"}
        asker = self.people.get(pet.person_id) if pet else (self.people.get(person_id) if person_id else None)
        if asker is not None and not asker.alive:
            asker = None
        names = [p.name for p in self.living if p.adult and not p.player]
        order = understand(text, names=names)
        who = asker.name if asker else "Xalq"
        if order.empty:
            hint = HELP_BY_KIND.get(pet.kind, "") if pet else (
                "Masalan: «dehqonchilikni o'rgataman», «o'rmonni asranglar», «shimolga borib o'tin kesinglar», "
                "«hammaga qurilishni o'rgataman»."
            )
            return {"ok": False, "reply": f"{who}: «Kechirasiz, tushunmadim.» {hint}"}

        if asker is None:
            # Words to the whole people: deeds that belong to one family do not apply.
            order.migrate = None
            order.build_here = False
            order.heal = False
            order.marry = None
            if order.empty:
                return {"ok": False, "reply": "Xalq: «Kechirasiz, tushunmadim.» Masalan: «dehqonchilikni o'rgataman»."}
        lines = describe(order)
        notes: list[str] = []
        for key in order.lessons:
            if not self._teach(key, me):
                notes.append(f"{TECH_BY_KEY[key].name}ni allaqachon bilamiz")
        for key in order.customs:
            if not self.has(key):
                self.customs.append(Custom(key=key, text=CUSTOM_TEXT[key], day=self.day))
        if order.fishing and not self.has("fishing"):
            self.customs.append(Custom(key="fishing", text="Ovqat kam bo'lsa, baliq tutamiz", day=self.day))
        home_s = self.settlements.get(asker.settlement_id) if asker and asker.settlement_id else (
            self.settlements.get(me.settlement_id) if me and me.settlement_id else None
        )
        if order.skills:
            pupils = (
                [p for p in self.living if p.adult and not p.player and (p.settlement_id == home_s.id if home_s else True)]
                if order.everyone or asker is None else [asker]
            )
            for pupil in pupils:
                for skill in order.skills:
                    pupil.skills[skill] = min(100.0, pupil.skill(skill) + 15)
        if order.gather and home_s is not None:
            home_s.directives.update(order.gather)
        if order.migrate is not None and asker is not None:
            if not self._migrate_now(asker, order.migrate):
                notes.append("lekin yaqinda yaxshi joy topilmadi")
        if order.build_here and asker is not None and me is not None and home_s is not None:
            kind = self.choose_home(asker, home_s, self._stone_reachable(home_s))
            if kind is None or self._place(home_s, kind, near=(int(me.x), int(me.y)), owner=asker) is None:
                notes.append("lekin bu yer qurilishga yaroqsiz")
        if order.share_food and home_s is not None:
            donors = [s for s in self.settlements.values() if s is not home_s and not s.abandoned and s.storage.food > s.population * 3]
            if donors:
                donor = max(donors, key=lambda s: s.storage.food)
                gift = donor.storage.food * 0.3
                donor.storage.food -= gift
                home_s.storage.food += gift
                self.log(f"{donor.name} {home_s.name}ga {int(gift)} ovqat yubordi (rahbar ko'rsatmasi)", "politics")
            else:
                notes.append("lekin boshqa qishloqlarda ortiqcha ovqat yo'q")
        if order.heal and asker is not None:
            asker.health = min(100.0, asker.health + 30)
            asker.energy = min(100.0, asker.energy + 20)
        if order.marry and asker is not None:
            bride = next((p for p in self.living if p.name == order.marry and p.adult and not p.player), None)
            if bride and bride.gender != asker.gender and bride.partner_id is None and asker.partner_id is None:
                self._marry(asker, bride)
            else:
                notes.append(f"lekin {order.marry} bilan turmush qurib bo'lmaydi")

        if pet is not None:
            pet.status = "solved"
            pet.answer = text
        if asker is not None:
            asker.remember(f"Rahbarimiz aytdi: «{text}»")
            asker.wisdom += 2
            asker.awareness = min(100.0, asker.awareness + 1.5)
            if asker.task == "petition":
                asker.task = "idle"
                asker.task_ticks = 0
        reply = "Tushundim! " + "; ".join(lines + notes)
        if pet is not None:
            pet.reply = reply
        target = f"{asker.name}ga" if asker else "xalqqa"
        self.log(f"Rahbar {target}: «{text}» — {reply}", "politics")
        return {"ok": True, "reply": f"{who}: «{reply}»"}

    def petitions_payload(self) -> list[dict]:
        out = []
        for pet in sorted(self.petitions.values(), key=lambda x: -x.id)[:12]:
            person = self.people.get(pet.person_id)
            out.append({
                "id": pet.id,
                "person_id": pet.person_id,
                "name": f"{person.name} {person.surname}" if person else "?",
                "settlement": self.settlements[pet.settlement_id].name if pet.settlement_id in self.settlements else "",
                "kind": pet.kind,
                "text": pet.text,
                "day": pet.day,
                "status": pet.status,
                "arrived": pet.arrived,
                "answer": pet.answer,
                "reply": pet.reply,
            })
        return out

    def customs_payload(self) -> list[dict]:
        return [{"key": c.key, "text": c.text, "day": c.day} for c in self.customs]

    # -- animals ---------------------------------------------------------------

    def spawn_animals(self) -> None:
        w = self.world
        next_id = max(self.animals, default=0) + 1
        for herd in range(3):
            spot = w.nearest(
                self.rng.randrange(8, w.width - 8), self.rng.randrange(8, w.height - 8),
                lambda i: w.terrain[i] in (Terrain.GRASS, Terrain.FERTILE), radius=20,
            )
            if spot is None:
                continue
            for _ in range(self.rng.randint(3, 5)):
                x = spot[0] + self.rng.uniform(-2, 2)
                y = spot[1] + self.rng.uniform(-2, 2)
                self.animals[next_id] = Animal(next_id, "horse", x, y, x, y, wait=self.rng.uniform(0, 200), herd=herd)
                next_id += 1
        for _ in range(6):
            spot = w.nearest(
                self.rng.randrange(6, w.width - 6), self.rng.randrange(6, w.height - 6),
                lambda i: w.terrain[i] == Terrain.GRASS and w.wood[i] == 0, radius=20,
            )
            if spot is None:
                continue
            self.animals[next_id] = Animal(next_id, "fox", spot[0], spot[1], spot[0], spot[1], wait=self.rng.uniform(0, 300))
            next_id += 1

    def _move_animals(self, seconds: float) -> None:
        w = self.world
        leaders: dict[int, Animal] = {}
        for a in self.animals.values():
            if a.kind == "horse":
                leaders.setdefault(a.herd, a)
        for a in self.animals.values():
            if a.wait > 0:
                a.wait -= seconds
                continue
            speed = 0.45 if a.kind == "horse" else 0.6
            dx, dy = a.tx - a.x, a.ty - a.y
            dist = math.hypot(dx, dy)
            step = speed * seconds
            if dist > step:
                a.x += dx / dist * step
                a.y += dy / dist * step
                continue
            a.x, a.y = a.tx, a.ty
            a.wait = self.rng.uniform(40, 240)
            anchor = leaders.get(a.herd) if a.kind == "horse" and leaders.get(a.herd) is not a else a
            for _ in range(8):
                tx = anchor.x + self.rng.uniform(-6, 6)
                ty = anchor.y + self.rng.uniform(-6, 6)
                ix, iy = int(round(tx)), int(round(ty))
                if w.walkable(ix, iy) and w.terrain[w.index(ix, iy)] != Terrain.BUILT:
                    a.tx, a.ty = tx, ty
                    break

    # -- research ----------------------------------------------------------

    def _research(self) -> None:
        target = self.next_discovery()
        if target is None or self.insight < target.cost:
            return
        self.insight -= target.cost
        self.known.add(target.key)
        thinkers = [self.people[i] for i in self.recent_thinkers[-8:] if i in self.people and self.people[i].alive]
        if thinkers:
            hero = max(thinkers, key=lambda q: q.awareness + q.skill("thinking"))
            hero.discoveries += 1
            hero.wisdom += 5
            hero.remember(f"{target.name}ni kashf qildim!")
            who = f"{hero.name} {hero.surname}"
        else:
            who = "Odamlar"
        self.log(f"KASHFIYOT: {target.name}. {who} — {target.story}", "discovery")
        for q in self.living:
            if q.adult:
                q.remember(f"{target.name} haqida eshitdim")

    def next_discovery(self):
        options = [
            t for t in TECHS
            if t.key not in self.known and all(r in self.known for r in t.requires)
        ]
        return min(options, key=lambda t: t.cost) if options else None

    # -- building ----------------------------------------------------------

    def _plot_ok(self, x: int, y: int, w: int, h: int, *, field: bool = False) -> bool:
        world = self.world
        for dy in range(-1, h + 1):
            for dx in range(-1, w + 1):
                nx, ny = x + dx, y + dy
                if not world.inside(nx, ny):
                    return False
                i = world.index(nx, ny)
                inner = 0 <= dx < w and 0 <= dy < h
                if i in self.occupied:
                    return False
                if inner:
                    t = Terrain(world.terrain[i])
                    if t not in BUILDABLE:
                        return False
                    if field and t is Terrain.FOREST:
                        return False
        return True

    def _find_plot(self, s: Settlement, w: int, h: int, *, field: bool = False, near: tuple[int, int] | None = None) -> tuple[int, int] | None:
        ox, oy = near or (s.x, s.y)
        best: tuple[float, int, int] | None = None
        start = 2 if not field else 4
        for r in range(start, 22):
            for _ in range(28):
                angle = self.rng.uniform(0, math.tau)
                x = int(round(ox + math.cos(angle) * r)) - w // 2
                y = int(round(oy + math.sin(angle) * r)) - h // 2
                if not self._plot_ok(x, y, w, h, field=field):
                    continue
                score = r
                if field:
                    fertile = sum(
                        1 for dy in range(h) for dx in range(w)
                        if self.world.at(x + dx, y + dy) is Terrain.FERTILE
                    )
                    score -= fertile * 0.8
                if best is None or score < best[0]:
                    best = (score, x, y)
            if best is not None and r > start + 2:
                break
        return (best[1], best[2]) if best else None

    def _place(
        self,
        s: Settlement,
        kind: str,
        *,
        near: tuple[int, int] | None = None,
        owner: Person | None = None,
        instant: bool = False,
    ) -> Building | None:
        bp = BLUEPRINT_BY_KIND[kind]
        plot = self._find_plot(s, bp.width, bp.height, field=kind == "field", near=near)
        if plot is None:
            return None
        x, y = plot
        rng = self.rng
        if owner is not None:
            # A family's colours follow its temperament, not a city catalogue.
            wall = WALL_COLOURS[int(owner.trait("openness") * 7 + owner.id) % len(WALL_COLOURS)]
            roof = ROOF_COLOURS[int(owner.trait("ambition") * 5 + owner.id) % len(ROOF_COLOURS)]
        else:
            wall, roof = rng.choice(WALL_COLOURS), rng.choice(ROOF_COLOURS)
        building = Building(
            id=self.next_building, kind=kind, x=x, y=y, settlement_id=s.id,
            owner_id=owner.id if owner else None,
            need_wood=bp.wood, need_stone=bp.stone,
            wall=wall, roof=roof, style=rng.randrange(8),
        )
        self.next_building += 1
        self.buildings[building.id] = building
        for dy in range(bp.height):
            for dx in range(bp.width):
                i = self.world.index(x + dx, y + dy)
                self.occupied[i] = building.id
                if self.world.terrain[i] == Terrain.FOREST:
                    # Clearing the plot yields timber for the build itself.
                    timber = self.world.take_wood(i, 99)
                    building.need_wood = max(0.0, building.need_wood - timber * 0.5)
                    self.world.set(x + dx, y + dy, Terrain.GRASS)
        if instant:
            building.need_wood = building.need_stone = 0.0
            building.work_done = bp.work
            self._complete(building, None, quiet=True)
        self.buildings_version += 1
        return building

    def _complete(self, b: Building, builder: Person | None, quiet: bool = False) -> None:
        b.complete = True
        b.built_day = self.day
        bp = b.blueprint
        terrain = Terrain.FIELD if b.kind == "field" else Terrain.BUILT
        for dy in range(bp.height):
            for dx in range(bp.width):
                self.world.set(b.x + dx, b.y + dy, terrain)
        self.buildings_version += 1
        s = self.settlements.get(b.settlement_id)
        if bp.category == "home" and b.owner_id is not None:
            owner = self.people.get(b.owner_id)
            if owner is not None:
                family = [owner]
                partner = self.people.get(owner.partner_id) if owner.partner_id else None
                if partner is not None and partner.alive:
                    family.append(partner)
                family += [self.people[c] for c in owner.children_ids if c in self.people and self.people[c].alive and not self.people[c].adult]
                old_homes = {m.home_id for m in family if m.home_id and m.home_id != b.id}
                for member in family:
                    member.home_id = b.id
                    if member.id not in b.residents:
                        b.residents.append(member.id)
                    member.remember(f"Yangi uyimizga ko'chdik: {bp.name}")
                    member.hunger = min(100.0, member.hunger + 5)
                for old in old_homes:
                    self._vacate(old, family)
                if not quiet and s is not None:
                    self.log(f"{owner.name} {owner.surname} oilasi o'z {bp.name.lower()}ini qurdi ({s.name})", "build")
                return
        if not quiet and s is not None and bp.category != "farm":
            self.log(f"{s.name}da {bp.name.lower()} qurildi", "build")
        if builder is not None and bp.category != "farm":
            builder.remember(f"{bp.name} qurishda qatnashdim")

    def _vacate(self, building_id: int, leaving: list[Person]) -> None:
        old = self.buildings.get(building_id)
        if old is None:
            return
        ids = {m.id for m in leaving}
        old.residents = [r for r in old.residents if r not in ids]
        if old.residents:
            return
        # An empty old hut is pulled down to free its plot.
        old.demolished = True
        bp = old.blueprint
        for dy in range(bp.height):
            for dx in range(bp.width):
                i = self.world.index(old.x + dx, old.y + dy)
                self.occupied.pop(i, None)
                self.world.set(old.x + dx, old.y + dy, Terrain.GRASS)
        s = self.settlements.get(old.settlement_id)
        if s is not None:
            s.storage.wood += bp.wood * 0.4
        self.buildings_version += 1

    def _households(self, s: Settlement) -> list[Person]:
        """Heads of households in this settlement, couples first."""
        heads: list[Person] = []
        seen: set[int] = set()
        for p in self.people.values():
            if not p.alive or p.settlement_id != s.id or not p.adult or p.id in seen:
                continue
            if p.partner_id is not None:
                partner = self.people.get(p.partner_id)
                seen.add(p.partner_id)
                head = p if p.gender == "male" or partner is None or not partner.alive else partner
                heads.append(head)
            elif p.age_years >= 20:
                parent_home = next(
                    (self.people[i].home_id for i in p.parent_ids if i in self.people and self.people[i].alive),
                    None,
                )
                if p.home_id is None or p.home_id == parent_home:
                    if p.home_id is None or p.age_years >= 24:
                        heads.append(p)
            seen.add(p.id)
        heads.sort(key=lambda h: (h.partner_id is None, -len(h.children_ids)))
        return heads

    def choose_home(self, head: Person, s: Settlement, stone_ok: bool = True) -> str | None:
        """The house a family wants — the best they know how to build, coloured by taste."""
        options = [
            bp for bp in BLUEPRINTS
            if bp.category == "home" and all(r in self.known for r in bp.requires)
            and (stone_ok or bp.stone == 0)
        ]
        if not options:
            return None
        best_quality = max(bp.quality for bp in options)
        ambition = head.trait("ambition")
        # Modest families are content one step below the best.
        wanted = best_quality if ambition > 0.4 or best_quality <= 1 else best_quality - 1
        candidates = [bp for bp in options if bp.quality == wanted] or options
        if len(candidates) > 1:
            # Rich in stone → stone; otherwise the family's taste decides.
            return candidates[int(head.trait("openness") * len(candidates)) % len(candidates)].kind
        return candidates[0].kind

    def _plan(self, s: Settlement) -> None:
        """The settlement's shared building plan, revisited every six hours."""
        people = [p for p in self.people.values() if p.alive and p.settlement_id == s.id]
        adults = [p for p in people if p.adult]
        if not people:
            return
        sites = [b for b in self.buildings.values() if b.settlement_id == s.id and not b.complete and not b.demolished]
        capacity = 1 + len(adults) // 4
        if len(sites) >= capacity:
            return
        stone_ok = self._stone_reachable(s)
        mine = [b for b in self.buildings.values() if b.settlement_id == s.id and b.complete and not b.demolished]
        kinds = {b.kind for b in mine}
        counts: dict[str, int] = {}
        for b in mine + sites:
            counts[b.kind] = counts.get(b.kind, 0) + 1
        pop = len(people)

        if "campfire" not in kinds and not any(b.kind == "campfire" for b in sites):
            self._place(s, "campfire", near=(s.x, s.y))
            return

        # 1. Homes: every household wants a roof of its own, and a better one later.
        for head in self._households(s):
            current = self.buildings.get(head.home_id) if head.home_id else None
            planned = any(b.owner_id in (head.id, head.partner_id) for b in sites)
            if planned:
                continue
            kind = self.choose_home(head, s, stone_ok)
            if kind is None:
                break
            if current is not None and current.owner_id in (head.id, head.partner_id):
                if BLUEPRINT_BY_KIND[kind].quality <= current.blueprint.quality + 1:
                    continue
                if s.storage.wood < 20:
                    continue
            near = None
            relatives = [self.people[i] for i in head.parent_ids if i in self.people and self.people[i].home_id]
            if relatives:
                home = self.buildings.get(relatives[0].home_id)
                if home is not None:
                    near = (home.x, home.y)
            if self._place(s, kind, near=near, owner=head) is not None:
                head.remember("Oilamiz uchun uy qurishni boshladik")
                return
            self._raise(head, "no_plot", "Uy qurishga bo'sh joy topolmayapmiz. Qayerga quraylik?")

        # 2. The commons, in the order a growing place needs them.
        wishes: list[tuple[str, bool]] = [
            ("storehouse", pop >= 6 and counts.get("storehouse", 0) == 0),
            ("field", "agriculture" in self.known and counts.get("field", 0) < math.ceil(pop / 4)),
            ("granary", "pottery" in self.known and counts.get("granary", 0) < 1 + pop // 60 and pop >= 14),
            ("well", "pottery" in self.known and counts.get("well", 0) < 1 + pop // 30),
            ("workshop", "carpentry" in self.known and counts.get("workshop", 0) < 1 + pop // 50 and pop >= 12),
            ("healer", "medicine" in self.known and counts.get("healer", 0) < 1 + pop // 70),
            ("school", "writing" in self.known and counts.get("school", 0) < 1 + pop // 60 and pop >= 18),
            ("market", "trade" in self.known and counts.get("market", 0) < 1 + pop // 90 and pop >= 25),
            ("temple", "masonry" in self.known and counts.get("temple", 0) < 1 and pop >= 35),
            ("townhall", "governance" in self.known and counts.get("townhall", 0) < 1 and pop >= 40),
            ("palace", "architecture" in self.known and "governance" in self.known and counts.get("palace", 0) < 1 and pop >= 120),
        ]
        for kind, wanted in wishes:
            if wanted and (stone_ok or BLUEPRINT_BY_KIND[kind].stone == 0):
                if self._place(s, kind) is not None:
                    return

    # -- the day -----------------------------------------------------------

    def _new_day(self) -> None:
        self.world.regrow(self.rng, self.has("forest_care"))
        for s in self.settlements.values():
            # Food spoils; pottery and granaries keep more of it.
            keep = 0.96
            if "pottery" in self.known:
                keep = 0.975
            if any(b.kind == "granary" and b.complete and b.settlement_id == s.id for b in self.buildings.values()):
                keep = 0.988
            s.storage.food *= keep
            stores = sum(
                1 for b in self.buildings.values()
                if b.settlement_id == s.id and b.complete and b.kind in ("storehouse", "granary")
            )
            cap = 60 + stores * 160 + s.population * 4
            s.storage.food = min(s.storage.food, cap)
            s.storage.wood = min(s.storage.wood, 80 + stores * 120)
            s.storage.stone = min(s.storage.stone, 60 + stores * 120)
        for p in list(self.people.values()):
            if not p.alive:
                continue
            before_stage = p.stage
            p.age_days += 1
            if p.stage != before_stage and p.stage == "adult":
                p.remember("Voyaga yetdim")
                self.log(f"{p.name} {p.surname} voyaga yetdi", "life")
            self._mortality(p)
        self._marriages()
        self._births()
        self._daily_troubles()
        for p in self.living:
            self._reflect(p)
        self._emigrate()
        self._elect()
        self._update_settlements()

    def _mortality(self, p: Person) -> None:
        if p.player:
            p.health = max(p.health, 25.0)
            return
        years = p.age_years
        risk = 0.0004
        if years > 50:
            risk += (years - 50) * 0.0009
        if years < 3:
            risk += 0.0012
        if p.health < 20:
            risk += 0.05
        if "medicine" in self.known:
            risk *= 0.6
        if any(b.kind == "healer" and b.complete and b.settlement_id == p.settlement_id for b in self.buildings.values()):
            risk *= 0.7
        if p.health <= 0 or self.rng.random() < risk:
            self._die(p)

    def _die(self, p: Person) -> None:
        p.alive = False
        p.died_day = self.day
        self.deaths += 1
        home = self.buildings.get(p.home_id) if p.home_id else None
        if home is not None and p.id in home.residents:
            home.residents.remove(p.id)
        partner = self.people.get(p.partner_id) if p.partner_id else None
        if partner is not None and partner.alive:
            partner.partner_id = None
            partner.remember(f"{p.name} olamdan o'tdi")
            partner.social = max(0.0, partner.social - 30)
        for child_id in p.children_ids:
            child = self.people.get(child_id)
            if child is not None and child.alive:
                child.remember(f"{'Otam' if p.gender == 'male' else 'Onam'} vafot etdi")
        self.log(f"{p.name} {p.surname} {int(p.age_years)} yoshida vafot etdi", "death")

    def _marriages(self) -> None:
        for p in self.living:
            if not p.adult or p.partner_id is not None or p.gender != "male":
                continue
            best = None
            for other_id, value in p.relationships.items():
                q = self.people.get(other_id)
                if (
                    q is None or not q.alive or q.gender == p.gender or not q.adult
                    or q.partner_id is not None or value < 28
                    or q.relationships.get(p.id, 0.0) < 18
                    or q.id in p.parent_ids or p.id in q.parent_ids
                    or set(q.parent_ids) & set(p.parent_ids)
                ):
                    continue
                if best is None or value > best[0]:
                    best = (value, q)
            if best is None:
                continue
            if p.player or best[1].player:
                continue  # the player chooses for themselves
            self._marry(p, best[1])

    def _marry(self, p: Person, q: Person) -> None:
        p.partner_id, q.partner_id = q.id, p.id
        q.settlement_id = p.settlement_id
        for person, other in ((p, q), (q, p)):
            person.remember(f"{other.name} bilan turmush qurdim")
            person.social = min(100.0, person.social + 25)
            person.goals = [g for g in person.goals if g.kind != "family"]
        self.log(f"To'y! {p.name} {p.surname} va {q.name} {q.surname} turmush qurdi", "wedding")

    def _births(self) -> None:
        for mother in self.living:
            if mother.gender != "female" or mother.partner_id is None:
                continue
            years = mother.age_years
            if years < 18 or years > 42:
                continue
            if self.day - mother.last_birth_day < DAYS_PER_YEAR * 1.3:
                continue
            father = self.people.get(mother.partner_id)
            if father is None or not father.alive:
                continue
            s = self.settlements.get(mother.settlement_id) if mother.settlement_id else None
            pop = s.population if s else 1
            fed = s is not None and s.storage.food >= pop * 0.8
            chance = 0.09 * (1.4 if mother.home_id else 0.6) * (1.2 if fed else 0.5)
            if len(mother.children_ids) >= 6:
                chance *= 0.2
            if self.rng.random() > chance:
                continue
            gender = "male" if self.rng.random() < 0.51 else "female"
            child = self._make_person(
                gender=gender, surname=surname_for(father.surname, "male"), age_years=0.0,
                x=mother.x, y=mother.y, parents=(mother, father),
            )
            child.parent_ids = [mother.id, father.id]
            child.settlement_id = mother.settlement_id
            child.home_id = mother.home_id
            home = self.buildings.get(mother.home_id) if mother.home_id else None
            if home is not None:
                home.residents.append(child.id)
            mother.children_ids.append(child.id)
            father.children_ids.append(child.id)
            mother.last_birth_day = self.day
            self.births += 1
            for parent in (mother, father):
                parent.remember(f"Farzandimiz {child.name} dunyoga keldi!")
                parent.social = min(100.0, parent.social + 20)
            self.log(f"{mother.name} va {father.name}ning {('o' + chr(39) + 'g' + chr(39) + 'li') if gender == 'male' else 'qizi'} {child.name} tug'ildi", "birth")

    # -- the mind ----------------------------------------------------------

    def _reflect(self, p: Person) -> None:
        """Daily: goals, awareness, and one line of inner voice."""
        p.awareness = min(100.0, p.awareness + 0.05 + len(p.memories) * 0.004 + p.trait("openness") * 0.04)
        goals = [g for g in p.goals if g.done_day is None]
        kinds = {g.kind for g in goals}

        def add(kind: str, text: str) -> None:
            if kind not in kinds:
                p.goals.append(Goal(kind=kind, text=text))
                kinds.add(kind)

        if p.adult:
            if p.home_id is None:
                add("home", "o'z uyimga ega bo'lish")
            if p.partner_id is None and p.age_years < 40:
                add("family", "oila qurish")
            if p.partner_id is not None and len(p.children_ids) < 2 and p.gender == "female" and p.age_years < 40:
                add("children", "farzand ko'rish")
            best = max(p.skills, key=lambda k: p.skills[k]) if p.skills else None
            if best and p.skills[best] < 80 and p.trait("ambition") > 0.5:
                add("mastery", f"{best} bo'yicha usta bo'lish")
            if p.trait("openness") > 0.65:
                add("discover", "yangi narsa kashf qilish")
        for goal in p.goals:
            if goal.done_day is not None:
                continue
            if goal.kind == "home":
                goal.progress = 1.0 if p.home_id else 0.0
            elif goal.kind == "family":
                goal.progress = 1.0 if p.partner_id else min(0.9, max(p.relationships.values(), default=0) / 50)
            elif goal.kind == "children":
                goal.progress = min(1.0, len(p.children_ids) / 2)
            elif goal.kind == "mastery":
                best = max(p.skills.values(), default=0)
                goal.progress = min(1.0, best / 80)
            elif goal.kind == "discover":
                goal.progress = 1.0 if p.discoveries > 0 else min(0.9, p.skill("thinking") / 100)
            if goal.progress >= 1.0:
                goal.done_day = self.day
                p.wisdom += 2
                p.remember(f"Orzuim amalga oshdi: {goal.text}")
        p.goals = [g for g in p.goals if g.done_day is None or self.day - g.done_day < DAYS_PER_YEAR][-8:]
        p.thought = self._thought(p)

    def _thought(self, p: Person) -> str:
        if p.stage == "baby":
            return "..."
        if p.stage == "child":
            return self.rng.choice(("O'ynagani chiqdim!", "Katta bo'lsam, uy quraman.", "Otamga yordam beraman."))
        if p.hunger < 30:
            return "Qornim och. Ovqat topishim kerak."
        if p.health < 40:
            return "Tobim yo'q, dam olishim kerak."
        own_site = next(
            (b for b in self.buildings.values() if not b.complete and not b.demolished and b.owner_id in (p.id, p.partner_id)),
            None,
        )
        if own_site is not None:
            return f"{own_site.blueprint.name}imizni qurib bitkazamiz — {int(own_site.progress * 100)}% tayyor."
        if p.home_id is None and p.adult:
            return "Hali o'z uyim yo'q. Yog'och yig'ib, kulba qurmoqchiman."
        if p.partner_id is None and p.adult and p.age_years < 40:
            liked = max(p.relationships.items(), key=lambda kv: kv[1], default=None)
            if liked and liked[1] > 25 and liked[0] in self.people:
                return f"{self.people[liked[0]].name} haqida o'ylayapman..."
            return "Hayotimni baham ko'radigan inson topsam edi."
        if p.memories and self.rng.random() < 0.35:
            return p.memories[-1] + "."
        target = self.next_discovery()
        if target is not None and p.trait("openness") > 0.6:
            return f"Agar {target.name.lower()}ni o'ylab topsak, hayotimiz yengillashardi."
        if p.children_ids:
            return "Bolalarim uchun yaxshi kelajak quraman."
        return self.rng.choice(("Bugun yaxshi ishladim.", "Qishlog'imiz o'syapti.", "Yangi kun — yangi imkoniyat."))

    # -- society -----------------------------------------------------------

    def _emigrate(self) -> None:
        for s in list(self.settlements.values()):
            if s.abandoned:
                continue
            people = [p for p in self.people.values() if p.alive and p.settlement_id == s.id]
            if len(people) < 55:
                continue
            last = self.last_emigration_day.get(s.id, s.founded_day)
            if self.day - last < DAYS_PER_YEAR * 3:
                continue
            if self.rng.random() > 0.25:
                continue
            # Young households with few ties lead the way.
            heads = [
                p for p in people
                if p.adult and p.age_years < 35 and p.partner_id is not None and p.gender == "male"
            ]
            if not heads:
                continue
            self.rng.shuffle(heads)
            group: list[Person] = []
            for head in heads[: max(2, len(people) // 12)]:
                partner = self.people.get(head.partner_id) if head.partner_id else None
                kids = [self.people[c] for c in head.children_ids if c in self.people and self.people[c].alive and not self.people[c].adult]
                group += [head] + ([partner] if partner and partner.alive else []) + kids
            singles = [p for p in people if p.adult and p.partner_id is None and p.age_years < 30 and p not in group]
            group += singles[:3]
            if len(group) < 5:
                continue
            site = self._best_site((s.x, s.y), 16, 40)
            if math.hypot(site[0] - s.x, site[1] - s.y) < 14:
                continue
            new = self._found_settlement(site, [p.id for p in group])
            share = 0.25
            new.storage.food = s.storage.food * share
            new.storage.wood = s.storage.wood * share
            s.storage.food -= new.storage.food
            s.storage.wood -= new.storage.wood
            for member in group:
                old_home = member.home_id
                member.settlement_id = new.id
                member.home_id = None
                member.task = "migrate"
                member.task_ticks = 0
                member.path = []
                self._decide(member)
                member.remember(f"{s.name}dan ko'chib, {new.name}ga asos soldik")
                if old_home is not None:
                    self._vacate(old_home, [member])
            self.last_emigration_day[s.id] = self.day
            leader = group[0]
            self.log(
                f"YANGI MANZIL: {leader.name} {leader.surname} boshchiligida {len(group)} kishi "
                f"{s.name}dan ko'chib, {new.name}ga asos soldi",
                "settlement",
            )

    def _elect(self) -> None:
        if "governance" not in self.known:
            return
        for s in self.settlements.values():
            if s.abandoned or s.population < 20:
                continue
            leader = self.people.get(s.leader_id) if s.leader_id else None
            if leader is not None and leader.alive and leader.settlement_id == s.id and self.day % (DAYS_PER_YEAR * 4):
                continue
            candidates = [p for p in self.people.values() if p.alive and p.settlement_id == s.id and p.adult]
            if not candidates:
                continue
            winner = max(candidates, key=lambda p: p.wisdom * 2 + p.awareness + p.trait("extraversion") * 20 + min(p.age_years, 60) * 0.3)
            if winner.id == s.leader_id:
                continue
            s.leader_id = winner.id
            winner.remember(f"{s.name} rahbari etib saylandim")
            title = "Prezident" if s.rank in ("Shahar", "Poytaxt") else "Oqsoqol"
            self.log(f"SAYLOV: {winner.name} {winner.surname} {s.name}ning {title.lower()}i etib saylandi", "politics")

    def _update_settlements(self) -> None:
        counts: dict[int, int] = {}
        for p in self.people.values():
            if p.alive and p.settlement_id is not None:
                counts[p.settlement_id] = counts.get(p.settlement_id, 0) + 1
        for s in self.settlements.values():
            s.population = counts.get(s.id, 0)
            if s.population == 0 and self.day - s.founded_day > 2:
                if not s.abandoned:
                    s.abandoned = True
                    self.log(f"{s.name} huvillab qoldi", "settlement")
                continue
            rank = rank_for(s.population)
            if rank != s.rank:
                order = [label for _, label in RANKS]
                grew = order.index(rank) > order.index(s.rank)
                s.rank = rank
                if grew:
                    self.log(f"{s.name} endi {rank.lower()}! Aholi: {s.population}", "settlement")

    # -- payloads ----------------------------------------------------------

    def stats(self) -> dict:
        living = self.living
        homes = sum(1 for b in self.buildings.values() if b.complete and not b.demolished and b.blueprint.category == "home")
        target = self.next_discovery()
        return {
            "population": len(living),
            "births": self.births,
            "deaths": self.deaths,
            "homes": homes,
            "buildings": sum(1 for b in self.buildings.values() if b.complete and not b.demolished),
            "sites": sum(1 for b in self.buildings.values() if not b.complete and not b.demolished),
            "families": sum(1 for p in living if p.partner_id is not None and p.gender == "male"),
            "homeless": sum(1 for p in living if p.adult and p.home_id is None),
            "awareness": round(sum(p.awareness for p in living) / max(1, len(living)), 1),
            "happiness": round(sum(p.happiness for p in living) / max(1, len(living)), 1),
            "era": era_for(self.known),
            "known": [
                {"key": t.key, "name": t.name} for t in TECHS if t.key in self.known
            ],
            "researching": (
                {"name": target.name, "progress": round(min(1.0, self.insight / max(1.0, target.cost)), 3)}
                if target else None
            ),
        }

    def time_payload(self) -> dict:
        return {
            "tick": self.tick,
            "day": self.day,
            "year": self.year,
            "day_of_year": self.day % DAYS_PER_YEAR + 1,
            "hour": round(self.hour, 4),
            "night": self.night,
        }

    def buildings_payload(self) -> list[dict]:
        return [b.payload() for b in self.buildings.values() if not b.demolished]

    def settlements_payload(self) -> list[dict]:
        return [s.payload() for s in self.settlements.values() if not s.abandoned]

    def chronicle_payload(self, count: int = 40) -> list[dict]:
        return [entry.as_dict() for entry in self.chronicle[-count:]]

    def take_new_looks(self) -> list[dict]:
        looks = [self.people[i].looks() for i in self.new_people if i in self.people]
        self.new_people.clear()
        return looks

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> dict:
        from sim.codec import encode

        return {
            "version": 1,
            "seed": self.seed,
            "tick": self.tick,
            "world": self.world.snapshot(),
            "people": [encode(p) for p in self.people.values()],
            "buildings": [encode(b) for b in self.buildings.values()],
            "settlements": [encode(s) for s in self.settlements.values()],
            "known": sorted(self.known),
            "insight": self.insight,
            "chronicle": [entry.as_dict() for entry in self.chronicle[-300:]],
            "births": self.births,
            "deaths": self.deaths,
            "last_emigration_day": {str(k): v for k, v in self.last_emigration_day.items()},
            "animals": [encode(a) for a in self.animals.values()],
            "petitions": [encode(x) for x in self.petitions.values()],
            "customs": [encode(c) for c in self.customs],
            "next_petition": self.next_petition,
            "subsecond": self.subsecond,
            "player_id": self.player_id,
            "rng": list(self.rng.getstate()[1]),
        }

    @classmethod
    def restore(cls, data: dict) -> "Civilization":
        from sim.codec import decode_dataclass

        civ = cls.__new__(cls)
        civ.seed = data["seed"]
        civ.rng = random.Random(data["seed"] + data["tick"])
        civ.world = World.restore(data["world"])
        civ.people = {}
        for item in data["people"]:
            person = decode_dataclass(Person, item)
            # Older saves gave women their father's form of the family name.
            person.surname = surname_for(person.surname, person.gender)
            if person.gender == "female" and person.name in MALE_NAMES:
                person.name = FEMALE_NAMES[person.id % len(FEMALE_NAMES)]
            person.goals = [g if isinstance(g, Goal) else Goal(**g) for g in person.goals]
            civ.people[person.id] = person
        civ.buildings = {}
        for item in data["buildings"]:
            b = decode_dataclass(Building, item)
            civ.buildings[b.id] = b
        civ.settlements = {}
        for item in data["settlements"]:
            s = decode_dataclass(Settlement, item)
            civ.settlements[s.id] = s
        civ.known = set(data["known"])
        civ.insight = data.get("insight", 0.0)
        civ.tick = data["tick"]
        civ.chronicle = [ChronicleEntry(**entry) for entry in data.get("chronicle", [])]
        civ.births = data.get("births", 0)
        civ.deaths = data.get("deaths", 0)
        civ.next_person = max(civ.people, default=0) + 1
        civ.next_building = max(civ.buildings, default=0) + 1
        civ.next_settlement = max(civ.settlements, default=0) + 1
        civ.occupied = {}
        for b in civ.buildings.values():
            if b.demolished:
                continue
            bp = b.blueprint
            for dy in range(bp.height):
                for dx in range(bp.width):
                    civ.occupied[civ.world.index(b.x + dx, b.y + dy)] = b.id
        civ.buildings_version = 1
        civ.recent_thinkers = []
        civ.last_emigration_day = {int(k): v for k, v in data.get("last_emigration_day", {}).items()}
        civ.new_people = []
        civ.animals = {}
        for item in data.get("animals", []):
            animal = decode_dataclass(Animal, item)
            civ.animals[animal.id] = animal
        civ.subsecond = data.get("subsecond", 0.0)
        civ.petitions = {}
        for item in data.get("petitions", []):
            pet = decode_dataclass(Petition, item)
            civ.petitions[pet.id] = pet
        civ.customs = [decode_dataclass(Custom, item) for item in data.get("customs", [])]
        civ.next_petition = data.get("next_petition", max(civ.petitions, default=0) + 1)
        civ.auto_move = True
        civ.player_id = data.get("player_id")
        civ.saved_at = data.get("saved_at")
        if not civ.animals:
            civ.spawn_animals()
        civ._night_now = civ.night
        return civ


TASK_LABELS = TASK_LABEL
TECH_NAMES = {key: tech.name for key, tech in TECH_BY_KEY.items()}
