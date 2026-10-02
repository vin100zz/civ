"""The city governor: chooses what each city builds.

Every buildable item gets a score = weight of the need it answers x how urgent that need is
x how efficiently the item answers it. The weights come from ai.yaml and are bent by the
civilization's personality. The best candidates are kept for the observer ("why did Rome
build a temple?").
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..engine import actions
from ..engine.model.entities import City, CityStats, Item
from ..engine.rules.schema import SPACESHIP_PARTS, BuildingDef, UnitDef
from ..engine.view import PlayerView
from . import overseas
from .knowledge import Knowledge
from .strategic import Plan


@dataclass
class Candidate:
    item: Item
    score: float
    reason: str
    turns: int


@dataclass
class Decision:
    city_id: int
    city_name: str
    turn: int
    chosen: Optional[Candidate]
    candidates: list[Candidate] = field(default_factory=list)
    bought: bool = False


class Governor:
    def __init__(self, view: PlayerView, know: Knowledge, plan: Plan) -> None:
        self.view = view
        self.know = know
        self.plan = plan
        self.rules = view.rules
        personality = view.player.civ.personality
        bend = lambda name: self.rules.ai.get("personality", name)
        # How the personality scales each family of needs.
        self.scale = {
            "attack": 1 + personality.mood * bend("aggressive_attack")
                        - personality.ideology * bend("militarist_attack"),
            "defense": 1 + personality.mood * bend("aggressive_defense"),
            "settlers": 1 + personality.policy * bend("expansionist_settlers"),
            "buildings": 1 - personality.policy * bend("perfectionist_buildings"),
            "science": 1 + personality.ideology * bend("civilized_science"),
        }
        # Needs still open this turn; decremented as cities take them on.
        self.settlers_open = plan.settlers_wanted
        self.workers_open = plan.workers_wanted
        self.attackers_open = plan.attackers_wanted
        self.explorers_open = plan.explorers_wanted
        self.warships_open = plan.warships_wanted
        self.aircraft_open = plan.aircraft_wanted
        self.nuclear_open = plan.nuclear_wanted
        self.defenders_open = dict(plan.defenders_missing)
        min_sea = self.rules.ai.get("overseas", "min_sea_size")
        self.sea_ports = {c.id for sea in know.seas.values() if sea.size >= min_sea
                          for c in sea.ports}
        self.spaceship_goal = self._spaceship_goal()
        self.taken: dict[int, str] = {}       # city id -> need its production answers
        self.upkeep_room = self._upkeep_room()
        self._account_for_current_production()

    def w(self, name: str) -> float:
        return self.rules.ai.get("production", name)

    def _upkeep_room(self) -> float:
        """Gold per turn the empire can still commit to building maintenance.

        A share of what the treasury would earn with taxes at their maximum, so that
        science keeps the rest; buildings already under construction are counted.
        """
        if not self.know.cities:
            return 0.0
        limit = self.rules.governments[self.view.player.government].max_rate
        income, _, _ = self.view.budget_with_rates(limit, 0, 100 - limit)
        room = income * self.w("upkeep_share") + self.view.player.gold / 50.0
        for city in self.know.cities:
            item = city.production
            if item is not None and item.kind == "building":
                room -= self.rules.buildings[item.id].upkeep
        return room

    # ── What is already being built ───────────────────────────────────────────

    def _account_for_current_production(self) -> None:
        for city in self.know.cities:
            self._take_on(city, city.production)

    def _take_on(self, city: City, item: Optional[Item]) -> None:
        """Reduces the open needs by what this city is going to deliver."""
        self.taken.pop(city.id, None)
        if item is None or item.kind != "unit":
            return
        unit = self.rules.units[item.id]
        need = None
        if unit.can("found_city"):
            need = "settlers" if self.settlers_open > 0 else "workers" if self.workers_open > 0 else None
        elif unit.role == "attack":
            need = "attackers" if self.attackers_open > 0 else "explorers" if self.explorers_open > 0 else None
        elif unit.role == "defense":
            if self.defenders_open.get(city.id, 0) > 0:
                need = "defenders"
            elif self.explorers_open > 0:
                need = "explorers"
        elif unit.role == "sea_attack":
            need = "warships" if self.warships_open > 0 else None
        elif unit.role == "air_attack":
            if unit.can("nuclear"):
                need = "nuclear" if self.nuclear_open > 0 else None
            else:
                need = "aircraft" if self.aircraft_open > 0 else None
        if need is not None:
            self._adjust(city, need, -1)
            self.taken[city.id] = need

    def _release(self, city: City) -> None:
        """Opposite of _take_on, when a city drops what it was building."""
        need = self.taken.pop(city.id, None)
        if need is not None:
            self._adjust(city, need, +1)

    def _adjust(self, city: City, need: str, delta: int) -> None:
        if need == "settlers":
            self.settlers_open += delta
        elif need == "workers":
            self.workers_open += delta
        elif need == "attackers":
            self.attackers_open += delta
        elif need == "explorers":
            self.explorers_open += delta
        elif need == "warships":
            self.warships_open += delta
        elif need == "aircraft":
            self.aircraft_open += delta
        elif need == "nuclear":
            self.nuclear_open += delta
        elif need == "defenders":
            self.defenders_open[city.id] = self.defenders_open.get(city.id, 0) + delta

    # ── Decision ──────────────────────────────────────────────────────────────

    def needs_decision(self, city: City) -> bool:
        if city.production is None or city.last_completed is not None:
            return True
        if city.production not in self.view.production_options(city):
            return True
        if (self.view.turn + city.id) % int(self.w("review_period")) == 0:
            return True
        # Emergency: an undefended city under threat drops everything for a defender.
        if self.know.threatened(city) and not self.know.defenders_in(city):
            item = city.production
            return not (item.kind == "unit" and self.rules.units[item.id].role == "defense")
        return False

    def decide(self, city: City) -> Decision:
        self._release(city)
        stats = self.view.city_stats(city)
        candidates = self.evaluate(city, stats)
        candidates.sort(key=lambda c: (-c.score, c.item.kind, c.item.id))
        chosen = candidates[0] if candidates else None
        previous = city.production
        if previous is not None and previous.kind == "building":
            self.upkeep_room += self.rules.buildings[previous.id].upkeep
        if chosen is not None:
            self.view.do(actions.SetProduction(city.id, chosen.item.kind, chosen.item.id))
            self._take_on(city, chosen.item)
            if chosen.item.kind == "building":
                self.upkeep_room -= self.rules.buildings[chosen.item.id].upkeep
        return Decision(city.id, city.name, self.view.turn, chosen, candidates[:6])

    def evaluate(self, city: City, stats: CityStats) -> list[Candidate]:
        options = self.view.production_options(city)
        surplus = max(1, stats.shield_surplus)
        max_turns = self.w("max_build_turns")
        result: list[Candidate] = []
        too_slow: list[Candidate] = []

        units = [self.rules.units[i.id] for i in options if i.kind == "unit"]
        buildings = [self.rules.buildings[i.id] for i in options if i.kind == "building"]

        def add(kind: str, item_id: str, cost: int, score: float, reason: str) -> None:
            if score <= 0:
                return
            turns = max(1, math.ceil((cost - city.shields) / surplus))
            # Slow projects lose some appeal: needs are for now.
            score *= 1.0 / (1.0 + turns / 20.0)
            candidate = Candidate(Item(kind, item_id), round(score, 2), reason, turns)
            (result if turns <= max_turns else too_slow).append(candidate)

        for score, unit, reason in self._unit_candidates(city, stats, units):
            add("unit", unit.id, unit.cost, score, reason)
        for building in buildings:
            score, reason = self._building_score(city, stats, building)
            add("building", building.id, building.cost, score, reason)

        if not result:
            fallback = self._fallback(city, stats, units, buildings, too_slow)
            if fallback is not None:
                result.append(fallback)
        return result

    # ── Units ─────────────────────────────────────────────────────────────────

    def _unit_candidates(self, city: City, stats: CityStats,
                         units: list[UnitDef]) -> list[tuple[float, UnitDef, str]]:
        out: list[tuple[float, UnitDef, str]] = []
        defenders_here = len(self.know.defenders_in(city))
        threatened = self.know.threatened(city)

        # Defense.
        defender = _best(units, lambda u: u.role == "defense",
                         key=lambda u: (u.defense, -u.cost))
        missing = self.defenders_open.get(city.id, 0)
        if defender is not None and missing > 0:
            wanted = max(1, self.plan.defenders_wanted.get(city.id, 1))
            urgency = missing / wanted
            if defenders_here == 0:
                urgency += 1.5
            if threatened:
                urgency *= 1.5
            out.append((self.w("defense") * self.scale["defense"] * urgency, defender,
                        f"defense: {missing} defender(s) missing"))
        elif defender is not None and defenders_here > 0:
            # Replace an outdated garrison: the weakest defender is far behind the best unit.
            garrison = [u for u in self.know.defenders_in(city)
                        if u.id in self.plan.assignment
                        and self.plan.assignment[u.id].kind == "defend"]
            weakest = min((self.rules.units[u.type].defense for u in garrison),
                          default=defender.defense)
            if defender.defense >= 2 * weakest:
                out.append((self.w("defense") * self.scale["defense"] * self.w("upgrade_urgency"),
                            defender, f"defense: garrison outdated ({weakest} vs {defender.defense})"))

        # Settlers: new cities first, then terrain work.
        founder = _best(units, lambda u: u.can("found_city"), key=lambda u: -u.cost)
        if founder is not None and self._can_spare_citizen(city, stats, founder):
            supported = sum(1 for u in self.view.units_of_city(city)
                            if self.rules.units[u.type].can("found_city"))
            if supported < self.w("max_settlers_per_city") and defenders_here > 0:
                if self.settlers_open > 0:
                    urgency = min(1.5, 0.5 + self.settlers_open / 3.0)
                    if city.size >= 4:
                        urgency *= 1.3
                    out.append((self.w("settlers") * self.scale["settlers"] * urgency, founder,
                                f"expansion: {self.settlers_open} site(s) to settle"))
                elif self.workers_open > 0:
                    urgency = min(1.0, self.workers_open / 2.0)
                    if stats.food_surplus <= 0:
                        urgency *= self.w("workers_when_stagnant")   # the land must be improved
                    out.append((self.w("workers") * urgency, founder,
                                f"terrain work: {self.workers_open} worker(s) missing"))

        # Attack.
        attacker = _best(units, lambda u: u.role == "attack",
                         key=lambda u: (u.attack * u.moves / u.cost, u.attack))
        if attacker is not None and self.attackers_open > 0 and defenders_here > 0:
            urgency = min(1.5, self.attackers_open / 3.0)
            if self.plan.war_targets:
                urgency *= 1.5
            out.append((self.w("attack") * self.scale["attack"] * urgency, attacker,
                        f"offense: {self.attackers_open} attacker(s) missing"))

        if defenders_here > 0:
            out.extend(self._sea_and_air_candidates(city, units))

        # Exploration: the cheapest unit will do, a fast one is better.
        if self.explorers_open > 0 and defenders_here > 0:
            scout = _best(units, lambda u: u.is_military and u.domain == "land",
                          key=lambda u: (u.moves / u.cost, -u.cost))
            if scout is not None:
                out.append((self.w("attack") * 0.8, scout, "exploration: unknown land nearby"))

        # Caravans carry shields to the wonder city.
        caravan = _best(units, lambda u: u.can("trade"), key=lambda u: -u.cost)
        wonder_city = self.plan.wonder_city
        if caravan is not None and wonder_city is not None and wonder_city != city.id \
                and defenders_here > 0:
            target = self.view.city(wonder_city)
            if target is not None and target.production is not None \
                    and target.production.kind == "building" \
                    and self.rules.buildings[target.production.id].wonder \
                    and self.know.same_region(self.view.tile_of(city), self.view.tile_of(target)):
                out.append((self.w("caravan") * self.scale["buildings"], caravan,
                            f"wonder in {target.name}"))
        return out

    def _sea_and_air_candidates(self, city: City,
                                units: list[UnitDef]) -> list[tuple[float, UnitDef, str]]:
        """Ships (only in ports on a real sea) and aircraft."""
        out: list[tuple[float, UnitDef, str]] = []
        if city.id in self.sea_ports:
            ships = overseas.transports(self.view, city)
            if city.id in self.plan.ferries_wanted and ships:
                out.append((self.w("ferry"), ships[0], "expedition: a ship is needed"))
            elif city.id in self.plan.sea_explorers_wanted:
                scout = _best(units, lambda u: u.domain == "sea" and u.role != "carrier",
                              key=lambda u: (not u.can("coastal"), -u.cost))
                if scout is not None:
                    out.append((self.w("sea_explore"), scout, "exploration: unknown seas"))
            # A warship must hold the sea and shell the coast: attack and defense both count.
            warship = _best(units, lambda u: u.role == "sea_attack",
                            key=lambda u: (not u.can("no_shore_attack"),
                                           (u.attack + u.defense) * u.moves / u.cost))
            if warship is not None and self.warships_open > 0:
                urgency = min(1.5, 0.5 + self.warships_open / 2.0)
                out.append((self.w("navy") * self.scale["attack"] * urgency, warship,
                            f"navy: {self.warships_open} warship(s) missing"))
        plane = _best(units, lambda u: u.role == "air_attack" and not u.can("nuclear"),
                      key=lambda u: (u.attack / u.cost, u.attack))
        if plane is not None and self.aircraft_open > 0:
            urgency = min(1.5, 0.5 + self.aircraft_open / 2.0)
            out.append((self.w("aircraft") * self.scale["attack"] * urgency, plane,
                        f"air force: {self.aircraft_open} aircraft missing"))
        bomb = _best(units, lambda u: u.can("nuclear"), key=lambda u: -u.cost)
        if bomb is not None and self.nuclear_open > 0:
            out.append((self.w("nuclear") * self.scale["attack"], bomb, "nuclear deterrent"))
        return out

    def _can_spare_citizen(self, city: City, stats: CityStats, unit: UnitDef) -> bool:
        minimum = max(self.w("settlers_min_size"), unit.pop_cost + 1)
        if city.size < minimum:
            # A city about to grow may start now: the citizen will be there in time.
            return city.size + 1 >= minimum and stats.food_surplus > 0
        return stats.food_surplus >= self.w("settlers_food_surplus")

    # ── Buildings ─────────────────────────────────────────────────────────────

    def _building_score(self, city: City, stats: CityStats,
                        building: BuildingDef) -> tuple[float, str]:
        if building.wonder:
            return self._wonder_score(city, stats, building)
        if building.spaceship_part is not None:
            return self._spaceship_score(city, stats, building)
        if building.has_effect("capital"):
            if self.view.capital() is None and self._is_largest(city):
                return self.w("courthouse") * 3, "no capital"
            return 0.0, ""

        scale = self.scale["buildings"]
        cost = building.cost
        upkeep = building.upkeep
        # The empire cannot take on more maintenance than its taxes can pay for.
        if upkeep > self.upkeep_room:
            if not any(e.type == "yield_bonus" and e.yield_kind == "tax" for e in building.effects):
                scale *= self.w("over_budget_factor")
        best = 0.0
        reason = ""

        def consider(score: float, why: str) -> None:
            nonlocal best, reason
            if score > best:
                best, reason = score, why

        entertainers = city.specialists.get("entertainer", 0)
        pressure = entertainers + max(0, stats.unhappy - stats.happy + 1)
        limit = self.view.city_max_size(city)
        current = self.view.city_effects(city)
        groups = {e.exclusive_group for e in current if e.exclusive_group is not None}
        cleanest = min((e.percent for e in current if e.type == "pollution_percent"), default=100)

        for effect in building.effects:
            if effect.requires_tech is not None and effect.requires_tech not in self.view.player.techs:
                continue
            if effect.type == "content":
                if pressure > 0:
                    # A calmed citizen goes back to work; maintenance eats part of the gain.
                    relief = min(effect.amount, pressure)
                    worth = relief * self.w("citizen_worth") - upkeep
                    if worth > 0:
                        consider(self.w("happiness") * scale * worth * 15 / cost,
                                 f"happiness: {pressure} citizen(s) to calm")
            elif effect.type == "yield_bonus":
                if effect.exclusive_group in groups:
                    continue                    # the city already has a bonus of that kind
                gain_per_turn = self._yield_gain(stats, effect.yield_kind, effect.percent)
                net = gain_per_turn - (upkeep if effect.yield_kind in ("tax", "luxury") else upkeep / 2)
                if effect.yield_kind == "science":
                    weight = self.w("science") * self.scale["science"]
                    net = gain_per_turn - upkeep / 2
                elif effect.yield_kind == "shields":
                    weight = self.w("shields")
                    net = gain_per_turn - upkeep / 2
                else:
                    weight = self.w("economy")
                if net > 0:
                    consider(weight * scale * net * 30 / cost,
                             f"{effect.yield_kind}: +{gain_per_turn:.1f}/turn")
            elif effect.type == "food_box_keep":
                if city.size >= 3 and stats.food_surplus > 0:
                    consider(self.w("growth") * scale * 0.5 * (40 / cost) * min(2, stats.food_surplus),
                             "growth: faster growth")
            elif effect.type == "allow_size_above":
                if limit is not None and effect.size == limit and stats.food_surplus > 0:
                    closeness = max(0.0, 1.0 - (limit - city.size) / 3.0)
                    consider(self.w("growth") * scale * 3 * closeness,
                             f"growth: size limit {limit}")
            elif effect.type == "corruption_percent":
                saved = stats.corruption * (100 - effect.percent) / 100
                if saved - upkeep > 0:
                    consider(self.w("courthouse") * scale * (saved - upkeep) * 30 / cost,
                             f"corruption: {stats.corruption} trade lost")
            elif effect.type == "defense_multiplier":
                exposed = self.know.threatened(city) or (
                    self.plan.at_war and city.id in self.plan.defenders_wanted
                    and self.plan.defenders_wanted[city.id] > self.rules.ai.get("strategy", "defenders_base")
                    + city.size // self.rules.ai.get("strategy", "defenders_per_size"))
                if exposed and self.know.defenders_in(city):
                    consider(self.w("walls") * self.scale["defense"] * (1.0 + 0.1 * city.size),
                             "walls: enemies nearby")
            elif effect.type == "pollution_percent":
                if stats.pollution > 0 and effect.percent < cleanest:
                    consider(self.w("pollution") * scale * min(1.5, 0.5 + stats.pollution / 10),
                             f"pollution: index {stats.pollution}")
            elif effect.type == "no_population_pollution":
                if stats.pollution > 0 and city.size >= 10:
                    consider(self.w("pollution") * scale * min(1.5, 0.5 + stats.pollution / 10),
                             f"pollution: index {stats.pollution}")
            elif effect.type == "nuclear_shield":
                if self._nuclear_threat() and city.size >= 8:
                    consider(self.w("sdi") * self.scale["defense"] * (1.0 + 0.05 * city.size),
                             "nuclear weapons exist")
            elif effect.type == "veteran_units":
                # One arsenal is enough: the city that produces the most.
                arsenal = self.plan.wonder_city == city.id
                if arsenal and self.plan.war_targets and self.attackers_open > 1:
                    consider(self.w("barracks") * self.scale["attack"], "barracks: war effort")
        return best, reason

    def _yield_gain(self, stats: CityStats, kind: Optional[str], percent: float) -> float:
        base = {"tax": stats.tax, "luxury": stats.luxury, "science": stats.science,
                "shields": stats.shields}.get(kind or "", 0)
        return base * percent / 100.0

    def _wonder_score(self, city: City, stats: CityStats, wonder: BuildingDef) -> tuple[float, str]:
        if self.plan.wonder_city != city.id:
            return 0.0, ""
        if stats.shields < self.w("wonder_min_shields") or not self.know.defenders_in(city):
            return 0.0, ""
        if self.plan.at_war and self.plan.war_targets:
            return 0.0, ""
        # Caravans waiting in the empire are shields ready to be delivered.
        stock = sum(self.rules.units[u.type].cost for u in self._caravans()
                    if self.know.same_region(self.view.tile_of(u), self.view.tile_of(city)))
        turns = math.ceil(max(0, wonder.cost - city.shields - stock) / max(1, stats.shield_surplus))
        if turns > self.w("wonder_max_turns"):
            return 0.0, ""
        # What it brings: its effects, and what it allows everybody to build.
        unlocks_units = [u for u in self.rules.units.values() if u.requires_wonder == wonder.id]
        unlocks_parts = any(b.requires_wonder == wonder.id for b in self.rules.buildings.values())
        if not wonder.effects and not unlocks_units and not unlocks_parts:
            return 0.0, ""
        value = 1.0 + 0.25 * len(self.know.cities) * sum(
            1 for e in wonder.effects if e.scope in ("player", "continent"))
        if unlocks_units:
            value *= max(0.2, self.scale["attack"] - 0.5)     # weapons: for warlike leaders
        if unlocks_parts:
            value *= 1.5
        if stock:
            value *= 1.0 + stock / wonder.cost
        return (self.w("wonder") * self.scale["buildings"] * value * 300 / wonder.cost,
                f"wonder: {wonder.description or wonder.name}")

    # ── Space race ────────────────────────────────────────────────────────────

    def _spaceship_goal(self) -> dict[str, int]:
        """The ship we aim for: the smallest one that flies, with a few extra engines."""
        settings = self.rules.game.spaceship
        goal = dict(settings.min_parts)
        extra = int(self.w("spaceship_extra_components"))
        goal["component"] = min(settings.max_parts["component"], goal["component"] + extra)
        return goal

    def _parts_coming(self, part: str) -> int:
        """Parts of that kind we own or are building."""
        count = self.view.spaceship_parts().get(part, 0)
        for city in self.know.cities:
            item = city.production
            if item is not None and item.kind == "building" \
                    and self.rules.buildings[item.id].spaceship_part == part:
                count += 1
        return count

    def _spaceship_score(self, city: City, stats: CityStats,
                         building: BuildingDef) -> tuple[float, str]:
        part = building.spaceship_part
        coming = self._parts_coming(part)
        item = city.production
        if item is not None and item.kind == "building" and item.id == building.id:
            coming -= 1                         # this city's own part does not count against it
        missing = self.spaceship_goal[part] - coming
        if missing <= 0 or stats.shields < self.w("wonder_min_shields"):
            return 0.0, ""
        if self.know.threatened(city):
            return 0.0, ""
        return (self.w("spaceship") * self.scale["science"],
                f"space race: {missing} {building.name} missing")

    def should_launch_spaceship(self) -> bool:
        """Launch once the ship we wanted is complete, or at once if a rival is on its way."""
        if not self.view.can_launch_spaceship():
            return False
        parts = self.view.spaceship_parts()
        complete = all(parts.get(part, 0) >= self.spaceship_goal[part] for part in SPACESHIP_PARTS)
        return complete or bool(self.view.rival_spaceships())

    def _nuclear_threat(self) -> bool:
        """Somebody may build nuclear weapons: the wonder they need exists."""
        return any(u.can("nuclear") and u.enabled
                   and (u.requires_wonder is None or self.view.wonder_built(u.requires_wonder))
                   for u in self.rules.units.values())

    def _caravans(self) -> list:
        return [u for u in self.know.units if self.rules.units[u.type].can("trade")]

    def _is_largest(self, city: City) -> bool:
        return all(city.size >= other.size for other in self.know.cities)

    def _fallback(self, city: City, stats: CityStats, units: list[UnitDef],
                  buildings: list[BuildingDef], too_slow: list[Candidate]) -> Optional[Candidate]:
        """Nothing is needed right now. In order: a cheap civil building the treasury can
        maintain, a caravan (no upkeep, useful for wonders and trade), a useful project
        however long it takes, a unit for the standing army if the city can support it."""
        civil = ("content", "yield_bonus", "food_box_keep", "corruption_percent")
        affordable = [b for b in buildings
                      if not b.wonder and b.upkeep <= min(1, self.upkeep_room)
                      and any(e.type in civil for e in b.effects)]
        if affordable:
            building = min(affordable, key=lambda b: (b.cost, b.id))
            return Candidate(Item("building", building.id), 0.1, "nothing urgent", 0)
        caravan = _best(units, lambda u: u.can("trade"), key=lambda u: -u.cost)
        if caravan is not None and len(self._caravans()) < self.w("caravan_stock"):
            return Candidate(Item("unit", caravan.id), 0.08, "nothing urgent: trade", 0)
        if too_slow:
            best = max(too_slow, key=lambda c: (c.score, c.item.id))
            return Candidate(best.item, best.score, best.reason + " (long project)", best.turns)
        attacker = _best(units, lambda u: u.role == "attack",
                         key=lambda u: (u.attack * u.moves / u.cost, u.attack))
        affordable_army = stats.shield_upkeep * self.w("army_upkeep_limit") < stats.shields
        if attacker is not None and affordable_army:
            return Candidate(Item("unit", attacker.id), 0.05, "nothing urgent: standing army", 0)
        # Last resort: a city always builds something. Spare defenders are disbanded
        # again if the city has to pay for them (see AIController._trim_army).
        defender = _best(units, lambda u: u.role == "defense", key=lambda u: (u.defense, -u.cost))
        if defender is not None:
            return Candidate(Item("unit", defender.id), 0.01, "nothing useful to build", 0)
        return None

    # ── Buying ────────────────────────────────────────────────────────────────

    def maybe_buy(self, city: City, emergency_only: bool = False) -> bool:
        """Spends gold to finish what matters: a defender for an exposed city first."""
        view = self.view
        item = city.production
        if item is None or not view.can_buy(city):
            return False
        cost = view.buy_cost(city)
        gold = view.player.gold
        emergency = (item.kind == "unit" and self.rules.units[item.id].role == "defense"
                     and not self.know.defenders_in(city))
        if emergency and (self.know.threatened(city) or gold >= cost + self.w("buy_reserve") / 2):
            return bool(view.do(actions.Buy(city.id)))
        if emergency_only or gold - cost < self.w("buy_reserve"):
            return False
        if item.kind == "building" and self.rules.buildings[item.id].wonder:
            return False
        # Otherwise buy what is good value (mostly built already), or what the city
        # would take ages to finish by itself.
        surplus = max(1, city.stats.shield_surplus)
        turns_left = (view.item_cost(item) - city.shields) / surplus
        mostly_built = city.shields * 2 >= view.item_cost(item)
        if mostly_built or gold >= cost * 4 or turns_left >= self.w("buy_if_slower_than"):
            return bool(view.do(actions.Buy(city.id)))
        return False


def _best(units: list[UnitDef], predicate, key) -> Optional[UnitDef]:
    matching = [u for u in units if predicate(u)]
    if not matching:
        return None
    return max(matching, key=lambda u: (key(u), u.id))
