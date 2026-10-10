"""The strategic layer: decides what the civilization wants this turn.

It reads the Knowledge, posts missions for the units and tells the city governors what the
empire lacks (defenders, settlers, workers, attackers, explorers, ships, aircraft).
Everything that crosses the sea is planned in overseas.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..engine.model.entities import City, CityMemory
from ..engine.model.worldmap import Tile
from ..engine.view import PlayerView
from . import missions as M
from . import overseas
from .knowledge import Knowledge
from .missions import Mission


@dataclass
class Plan:
    """What the strategy decided this turn."""
    missions: list[Mission] = field(default_factory=list)
    assignment: dict[int, Mission] = field(default_factory=dict)       # unit id -> mission
    defenders_wanted: dict[int, int] = field(default_factory=dict)     # city id -> count
    defenders_missing: dict[int, int] = field(default_factory=dict)    # city id -> count
    settlers_wanted: int = 0          # more city founders needed
    workers_wanted: int = 0           # more terraforming units needed
    attackers_wanted: int = 0         # more attack units needed
    attackers_surplus: int = 0        # attack units the empire could do without
    explorers_wanted: int = 0         # more explorers needed
    enemies: list[int] = field(default_factory=list)                   # civs we are fighting
    war_targets: list[CityMemory] = field(default_factory=list)
    at_war: bool = False
    wonder_city: Optional[int] = None  # the city allowed to build wonders
    notes: list[str] = field(default_factory=list)
    # Sea and air (overseas.py)
    local_sites: int = 0              # city sites we can walk to
    reserved: set[int] = field(default_factory=set)     # units busy in an expedition
    ferries_wanted: dict[int, int] = field(default_factory=dict)        # port id -> expedition
    sea_explorers_wanted: dict[int, int] = field(default_factory=dict)  # port id -> count
    warships_wanted: int = 0
    aircraft_wanted: int = 0
    nuclear_wanted: int = 0


def make_plan(view: PlayerView, know: Knowledge, previous: dict[int, tuple],
              memory: Optional[dict] = None) -> Plan:
    plan = Plan()
    memory = memory if memory is not None else {}
    plan.enemies = [p.id for p in view.contacts() if view.at_war(p.id)]
    _defense_missions(view, know, plan)
    _intercept_missions(view, know, plan)
    _attack_missions(view, know, plan)
    plan.local_sites = _settle_missions(view, know, plan)
    jobs = improve_missions(view, know, plan)
    explore_capacity = _explore_missions(view, know, plan)
    _caravan_missions(view, know, plan)
    overseas.sea_missions(view, know, plan)
    overseas.plan_expeditions(view, know, plan, memory)

    plan.assignment = M.assign(view, know, plan.missions, previous, frozenset(plan.reserved))
    _count_needs(view, know, plan, plan.local_sites, jobs, explore_capacity)
    overseas.count_needs(view, know, plan)
    plan.wonder_city = _pick_wonder_city(view, know)
    return plan


# ── Defense ───────────────────────────────────────────────────────────────────

def defenders_wanted(view: PlayerView, know: Knowledge, city: City, at_war: bool) -> int:
    get = lambda name: view.rules.ai.get("strategy", name)
    wanted = int(get("defenders_base")) + city.size // int(get("defenders_per_size"))
    if know.threatened(city):
        wanted += int(get("defenders_threatened"))
    elif at_war and _near_enemy_city(view, know, city):
        wanted += 1
    return wanted


def _near_enemy_city(view: PlayerView, know: Knowledge, city: City) -> bool:
    radius = int(view.rules.ai.get("strategy", "threat_radius")) + 3
    for memory in know.foreign_cities:
        if view.at_war(memory.owner) and \
                view.map.steps(city.x, city.y, memory.x, memory.y) <= radius:
            return True
    return False


def _defense_missions(view: PlayerView, know: Knowledge, plan: Plan) -> None:
    weight = view.rules.ai.get("production", "defense")
    plan.at_war = bool(plan.enemies)
    for city in know.cities:
        wanted = defenders_wanted(view, know, city, plan.at_war)
        plan.defenders_wanted[city.id] = wanted
        priority = weight * (1.0 + 0.1 * city.size)
        if know.threatened(city):
            priority *= 2.0
        if not know.defenders_in(city):
            priority *= 1.5
        plan.missions.append(Mission(M.DEFEND, city.x, city.y, priority, capacity=wanted,
                                     target=city.id, note=city.name))


# ── Enemies in sight ──────────────────────────────────────────────────────────

def _intercept_missions(view: PlayerView, know: Knowledge, plan: Plan) -> None:
    """Enemy units close to our cities are hunted down."""
    weight = view.rules.ai.get("production", "attack")
    seen: set[int] = set()
    for city in know.cities:
        threat = know.threats.get(city.id)
        if threat is None:
            continue
        for unit in threat.units:
            if unit.id in seen:
                continue
            seen.add(unit.id)
            # Units inside a city are dealt with by the assault on that city.
            if view.foreign_city_at(view.map.tile(unit.x, unit.y)) is not None:
                continue
            plan.missions.append(Mission(M.ATTACK_UNIT, unit.x, unit.y, weight * 2.5,
                                         capacity=2, target=unit.id,
                                         note=f"enemy near {city.name}"))


# ── War ───────────────────────────────────────────────────────────────────────

def _attack_missions(view: PlayerView, know: Knowledge, plan: Plan) -> None:
    """One enemy city per region is chosen as the target of all attackers there.

    A region where we have no city counts too once our attackers have landed in it.
    """
    rules = view.rules
    get = lambda name: rules.ai.get("strategy", name)
    weight = rules.ai.get("production", "attack")
    group = int(get("siege_group_size"))
    world = view.map
    attackers = [u for u in know.units_with_role("attack") if u.aboard is None]

    for region in know.regions.values():
        landed = [u for u in attackers if know.region_of[view.tile_of(u).index] == region.id]
        bases = [(c.x, c.y) for c in region.my_cities] or [(u.x, u.y) for u in landed]
        if not bases:
            continue
        targets = [m for m in region.foreign_cities if view.at_war(m.owner)]
        if not targets:
            continue

        def appeal(memory: CityMemory) -> float:
            nearest = min(world.steps(memory.x, memory.y, x, y) for x, y in bases)
            value = 3.0 + memory.size - get("target_distance_weight") * nearest
            if memory.has_walls:
                value -= 2.0
            seen = view.city_defenders_seen(memory)
            if seen is not None:
                value += 4.0 if seen == 0 else -0.5 * seen
            return value

        target = max(targets, key=lambda m: (appeal(m), -m.city_id))
        plan.war_targets.append(target)
        if not region.my_cities:
            # A beachhead: no city to gather in, the landing party attacks at once.
            plan.missions.append(Mission(
                M.ATTACK_CITY, target.x, target.y, weight * 1.5, capacity=16,
                target=target.city_id, stage="assault", note=f"{target.name} (landing)"))
            continue
        rally_city = min(region.my_cities,
                         key=lambda c: (world.steps(target.x, target.y, c.x, c.y), c.id))
        nearby = [u for u in landed if world.steps(u.x, u.y, target.x, target.y) <= 4]
        gathered = [u for u in landed
                    if world.steps(u.x, u.y, rally_city.x, rally_city.y) <= 2]
        undefended = view.city_defenders_seen(target) == 0
        ready = len(nearby) + len(gathered) >= group or len(nearby) >= 1 and undefended
        stage = "assault" if ready or undefended else "rally"
        plan.missions.append(Mission(
            M.ATTACK_CITY, target.x, target.y, weight * 1.5, capacity=16,
            target=target.city_id, stage=stage, rally=(rally_city.x, rally_city.y),
            note=f"{target.name} ({stage})"))


# ── Expansion ─────────────────────────────────────────────────────────────────

def _settle_missions(view: PlayerView, know: Knowledge, plan: Plan) -> int:
    """Posts a mission for each good city site. Returns how many sites remain to settle."""
    weight = view.rules.ai.get("production", "settlers")
    founders = [u for u in know.units if view.rules.units[u.type].can("found_city")]
    total = 0
    taken: list[Tile] = []
    for region in sorted(know.regions.values(), key=lambda r: r.id):
        has_presence = bool(region.my_cities) or any(
            know.region_of[view.tile_of(u).index] == region.id for u in founders)
        if not has_presence or not region.sites:
            continue
        wanted = max(2, len([u for u in founders
                             if know.region_of[view.tile_of(u).index] == region.id]) + 1)
        sites = know.best_sites(region, wanted, taken)
        taken.extend(sites)
        for rank, tile in enumerate(sites):
            appeal = next(a for a, t in region.sites if t is tile)
            plan.missions.append(Mission(M.FOUND_CITY, tile.x, tile.y,
                                         weight * (1.0 + appeal / 15.0) / (1 + 0.1 * rank),
                                         note=f"site {appeal:.1f}"))
        total += len(sites)
    return total


def improve_missions(view: PlayerView, know: Knowledge, plan: Plan,
                     wanted: Optional[int] = None) -> int:
    """Terrain work around our cities, most profitable first. Returns the number of jobs.

    Only the `wanted` best jobs are posted: by default, as many as the empire wants workers.
    """
    rules = view.rules
    get = lambda name: rules.ai.get("settlers", name)
    weight = rules.ai.get("production", "workers")
    max_turns = get("max_work_turns")
    government = rules.governments[view.player.government]
    jobs: dict[int, tuple[float, Tile, str]] = {}

    def effective(value: int, city: City) -> int:
        if government.tile_penalty and not city.celebrating and value > 2:
            return value - 1
        return value

    for city in know.cities:
        worked = {(city.x + dx, city.y + dy) for dx, dy in city.worked}
        for (dx, dy), tile in view.map.city_area(city.x, city.y):
            if not view.explored(tile) or not view.is_land(tile):
                continue
            if tile.city_id is not None or view.foreign_units_at(tile):
                continue
            if tile.worked_by is not None and tile.worked_by != city.id:
                continue
            terrain = rules.terrains[tile.terrain]
            base = view.city_tile_yields(city, tile)
            options: list[tuple[float, str]] = []
            irrigation = terrain.irrigation
            if irrigation is not None and irrigation.bonus and not tile.irrigation:
                turns = view.work_turns_at(tile, "irrigate")
                if turns is not None and turns <= max_turns:
                    gain = effective(base.food + irrigation.bonus, city) - base.food
                    options.append((get("irrigate") * gain / turns, "irrigate"))
            mine = terrain.mine
            if mine is not None and mine.bonus and not tile.mine and not tile.irrigation:
                turns = view.work_turns_at(tile, "mine")
                if turns is not None and turns <= max_turns:
                    gain = effective(base.shields + mine.bonus, city) - base.shields
                    options.append((get("mine") * gain / turns, "mine"))
            if terrain.road_trade and not tile.road:
                turns = view.work_turns_at(tile, "road")
                if turns is not None and turns <= max_turns:
                    bonus = rules.game.movement.road_trade_bonus
                    if government.trade_bonus and base.trade == 0:
                        bonus += 1
                    gain = effective(base.trade + bonus, city) - base.trade
                    options.append((get("road") * gain / turns, "road"))
            if tile.road and not tile.railroad and (tile.x, tile.y) in worked:
                turns = view.work_turns_at(tile, "railroad")
                if turns is not None and turns <= max_turns:
                    percent = rules.game.movement.railroad_yield_percent
                    gain = base.shields * percent // 100 + base.food * percent // 100
                    options.append((get("mine") * gain / turns, "railroad"))
            if tile.pollution:
                # Pollution halves the tile and warms the planet: it is cleaned first.
                options.append((get("clean"), "clean"))
            if not options:
                continue
            value, order = max(options)
            if value <= 0:
                continue
            if (tile.x, tile.y) in worked:
                value *= 1.5
            best = jobs.get(tile.index)
            if best is None or value > best[0]:
                jobs[tile.index] = (value, tile, order)

    # Settlers eat food: only as many jobs are posted as the empire wants workers.
    # Settlers left without a job go back to a city and join it.
    ranked = sorted(jobs.values(), key=lambda j: (-j[0], j[1].index))
    if wanted is None:
        wanted = workers_wanted(view, know, len(ranked))
    for value, tile, order in ranked[:wanted]:
        plan.missions.append(Mission(M.IMPROVE, tile.x, tile.y, weight * (0.5 + value),
                                     order=order, note=order))
    return len(ranked)


def workers_wanted(view: PlayerView, know: Knowledge, jobs: int) -> int:
    """Terraforming units the empire should keep, given the work available."""
    if not jobs or not know.cities:
        return 0
    per_city = view.rules.ai.get("production", "workers_per_city")
    return min(jobs, max(1, math.ceil(len(know.cities) * per_city)))


def _explore_missions(view: PlayerView, know: Knowledge, plan: Plan) -> int:
    get = lambda name: view.rules.ai.get("strategy", name)
    weight = view.rules.ai.get("production", "attack")
    per_region = int(get("explorers_per_continent"))
    capacity = 0
    for region in know.regions.values():
        if not region.frontier:
            continue
        has_presence = bool(region.my_cities) or any(
            know.region_of[view.tile_of(u).index] == region.id for u in know.units
            if view.rules.units[u.type].domain == "land")
        if not has_presence:
            continue
        if view.turn > get("explore_until_turn") and len(region.frontier) < 6:
            continue
        anchor = region.my_cities[0] if region.my_cities else None
        tile = region.frontier[0]
        x, y = (anchor.x, anchor.y) if anchor is not None else (tile.x, tile.y)
        plan.missions.append(Mission(M.EXPLORE, x, y, weight * 0.9, capacity=per_region,
                                     target=region.id, note=f"{len(region.frontier)} frontier"))
        capacity += per_region
    return capacity


def _caravan_missions(view: PlayerView, know: Knowledge, plan: Plan) -> None:
    weight = view.rules.ai.get("production", "caravan")
    for city in know.cities:
        item = city.production
        if item is not None and item.kind == "building" and view.rules.buildings[item.id].wonder:
            plan.missions.append(Mission(M.HELP_WONDER, city.x, city.y, weight * 2,
                                         capacity=8, target=city.id, note=city.name))


# ── What the empire lacks ─────────────────────────────────────────────────────

def _count_needs(view: PlayerView, know: Knowledge, plan: Plan, sites: int, jobs: int,
                 explore_capacity: int) -> None:
    rules = view.rules
    strategy = lambda name: rules.ai.get("strategy", name)
    personality = view.player.civ.personality
    bend = lambda name: rules.ai.get("personality", name)

    for mission in plan.missions:
        if mission.kind == M.DEFEND:
            missing = mission.capacity - len(mission.assigned)
            if missing > 0:
                plan.defenders_missing[mission.target] = missing

    founders = [u for u in know.units if rules.units[u.type].can("found_city")]
    founding = sum(1 for u in founders
                   if plan.assignment.get(u.id) and plan.assignment[u.id].kind == M.FOUND_CITY)
    improving = len(founders) - founding
    plan.settlers_wanted = max(0, sites - founding)
    plan.workers_wanted = max(0, workers_wanted(view, know, jobs) - improving)

    attackers = len(know.units_with_role("attack"))
    reachable_enemy = bool(plan.war_targets)
    per_city = strategy("attackers_per_city") if reachable_enemy else strategy("attackers_peace")
    per_city *= 1.0 + personality.mood * bend("aggressive_attack") \
        - personality.ideology * bend("militarist_attack")
    wanted = math.ceil(len(know.cities) * max(0.0, per_city))
    plan.attackers_wanted = max(0, wanted - attackers)
    plan.attackers_surplus = max(0, attackers - math.ceil(wanted * strategy("attackers_excess")))

    exploring = sum(1 for m in plan.missions if m.kind == M.EXPLORE for _ in m.assigned)
    plan.explorers_wanted = max(0, explore_capacity - exploring)


def _pick_wonder_city(view: PlayerView, know: Knowledge) -> Optional[int]:
    """Wonders are built in the city with the most shields, one at a time."""
    if not know.cities:
        return None
    for city in know.cities:
        item = city.production
        if item is not None and item.kind == "building" and view.rules.buildings[item.id].wonder:
            return city.id
    best = max(know.cities, key=lambda c: (c.stats.shields, -c.id))
    return best.id
