"""Expeditions across the sea: new colonies and invasions.

An expedition gathers passengers in a port, carries them on a ship to a shore near its
goal and puts them ashore; from there the ordinary land AI takes over (the settlers found
their city, the attackers assault theirs). Expeditions live in the controller's memory as
plain dictionaries, so they survive from turn to turn and in saved games:

    {"id", "kind": settle | invade, "port": city id, "goal": [x, y], "target": city id | None,
     "ship": unit id | None, "stage": gather | sail | done, "started": turn,
     "ready_since": turn | None}
"""
from __future__ import annotations

import math
from typing import Optional

from ..engine.model.entities import City, Unit
from ..engine.model.worldmap import Tile
from ..engine.rules.schema import UnitDef
from ..engine.view import PlayerView
from . import diplomacy, pathfinding
from . import missions as M
from .knowledge import Knowledge, Sea
from .missions import Mission

SETTLE, INVADE = "settle", "invade"
GATHER, SAIL, DONE = "gather", "sail", "done"


def expeditions(memory: dict) -> list[dict]:
    return memory.setdefault("expeditions", [])


def expedition_of_ship(memory: dict, ship_id: int) -> Optional[dict]:
    for expedition in expeditions(memory):
        if expedition["ship"] == ship_id and expedition["stage"] != DONE:
            return expedition
    return None


def expedition_by_id(memory: dict, expedition_id: int) -> Optional[dict]:
    for expedition in expeditions(memory):
        if expedition["id"] == expedition_id:
            return expedition
    return None


# ── Planning (start of the turn) ──────────────────────────────────────────────

def plan_expeditions(view: PlayerView, know: Knowledge, plan, memory: dict) -> None:
    """Drops dead expeditions, maybe starts one, and posts what the others need."""
    current = expeditions(memory)
    current[:] = [e for e in current if _still_valid(view, know, e)]
    _maybe_start(view, know, plan, memory)
    for expedition in current:
        ship = view.unit(expedition["ship"]) if expedition["ship"] is not None else None
        if ship is not None:
            plan.reserved.add(ship.id)
            plan.reserved.update(u.id for u in view.cargo_of(ship))
        if expedition["stage"] == GATHER:
            _gather(view, know, plan, expedition)
        goal = expedition["goal"]
        plan.notes.append(f"expedition {expedition['kind']} to ({goal[0]}, {goal[1]}): "
                          f"{expedition['stage']}")


def _still_valid(view: PlayerView, know: Knowledge, expedition: dict) -> bool:
    get = lambda name: view.rules.ai.get("overseas", name)
    if expedition["stage"] == DONE:
        return False
    sailing = expedition["stage"] == SAIL
    if expedition["ship"] is not None and view.unit(expedition["ship"]) is None:
        if sailing:
            return False                         # lost at sea
        expedition["ship"] = None
    limit = get("sail_timeout") if sailing else get("gather_timeout")
    if view.turn - expedition["started"] > limit:
        return False
    if not sailing and view.city(expedition["port"]) is None:
        return False
    goal = view.map.tile(*expedition["goal"])
    region = know.regions.get(know.region_of[goal.index])
    if expedition["kind"] == SETTLE:
        if not view.can_found_city(goal):
            return False
        # Somebody of ours got there first: the land AI will do the rest.
        return sailing or region is None or not region.my_cities
    memory = view.foreign_city_at(goal)
    return memory is not None and view.at_war(memory.owner)


def _maybe_start(view: PlayerView, know: Knowledge, plan, memory: dict) -> None:
    get = lambda name: view.rules.ai.get("overseas", name)
    current = expeditions(memory)
    if len(current) >= get("max_expeditions") or not know.cities:
        return
    if view.turn < memory.get("expedition_cooldown_until", 0):
        return
    kinds = {e["kind"] for e in current}
    choice = None
    if SETTLE not in kinds and plan.local_sites == 0:
        choice = _best_colony(view, know)
    if choice is None and INVADE not in kinds and plan.at_war and not plan.war_targets:
        choice = _best_invasion(view, know)
    if choice is None:
        return
    kind, port, goal, target = choice
    current.append({
        "id": memory.get("next_expedition_id", 1), "kind": kind, "port": port.id,
        "goal": [goal.x, goal.y], "target": target, "ship": None, "stage": GATHER,
        "started": view.turn, "ready_since": None})
    memory["next_expedition_id"] = memory.get("next_expedition_id", 1) + 1
    memory["expedition_cooldown_until"] = view.turn + int(get("expedition_cooldown"))


def _best_colony(view: PlayerView, know: Knowledge):
    """The most appealing city site on a shore we can sail to and have not settled."""
    founders = [u for u in know.units if view.rules.units[u.type].can("found_city")]
    best = None
    for region in know.regions.values():
        if region.my_cities or not region.sites:
            continue
        if any(know.region_of[view.tile_of(u).index] == region.id for u in founders):
            continue                             # settlers already there
        appeal, site = region.sites[0]
        port = _port_for(view, know, region.id, site)
        if port is None:
            continue
        value = appeal - 0.1 * view.map.steps(port.x, port.y, site.x, site.y)
        if best is None or value > best[0]:
            best = (value, port, site)
    if best is None:
        return None
    return SETTLE, best[1], best[2], None


def _best_invasion(view: PlayerView, know: Knowledge):
    """An enemy city across the sea worth an invasion, if we are strong enough."""
    get = lambda name: view.rules.ai.get("overseas", name)
    world = view.map
    best = None
    mine = diplomacy.my_power(view, know)
    for memory in know.foreign_cities:
        if not view.at_war(memory.owner) or view.is_barbarian(memory.owner):
            continue
        if mine < diplomacy.their_power(view, memory.owner) * get("invade_strength_ratio"):
            continue
        tile = world.tile(memory.x, memory.y)
        port = _port_for(view, know, know.region_of[tile.index], tile)
        if port is None:
            continue
        value = memory.size - get("invade_distance_weight") * world.steps(port.x, port.y,
                                                                          tile.x, tile.y)
        if memory.has_walls:
            value -= 2.0
        if best is None or value > best[0]:
            best = (value, port, tile, memory.city_id)
    if best is None:
        return None
    return INVADE, best[1], best[2], best[3]


def _port_for(view: PlayerView, know: Knowledge, region_id: int, goal: Tile) -> Optional[City]:
    """Our closest port from which a ship we have or can build reaches the goal's shore."""
    min_size = view.rules.ai.get("overseas", "min_sea_size")
    world = view.map
    best = None
    for sea in know.seas.values():
        if sea.size < min_size or not sea.ports or region_id not in sea.regions:
            continue
        spots = landing_spots(view, know, sea.id, goal)
        if not spots:
            continue
        for port in sea.ports:
            if know.region_of[view.tile_of(port).index] == region_id:
                continue
            if not _ship_available(view, know, sea, port, spots[0][0]):
                continue
            distance = world.steps(port.x, port.y, goal.x, goal.y)
            if best is None or (distance, port.id) < best[0]:
                best = ((distance, port.id), port)
    return best[1] if best else None


def landing_spots(view: PlayerView, know: Knowledge, sea_id: int, goal: Tile) -> list[tuple[Tile, Tile]]:
    """(sea tile, land tile) pairs where passengers can go ashore, closest to the goal first."""
    world = view.map
    region_id = know.region_of[goal.index]
    spots = []
    for water in know.shore(region_id, sea_id, goal, count=8):
        for land in world.neighbors(water):
            if know.region_of[land.index] != region_id:
                continue
            if view.foreign_city_at(land) is not None or view.foreign_units_at(land):
                continue
            spots.append((world.steps(land.x, land.y, goal.x, goal.y), water.index, land.index,
                          water, land))
    spots.sort(key=lambda s: s[:3])
    return [(water, land) for _, _, _, water, land in spots]


def transports(view: PlayerView, city: City) -> list[UnitDef]:
    """Ships able to carry land units that the city can build, best first."""
    rules = view.rules
    ships = [rules.units[i.id] for i in view.production_options(city) if i.kind == "unit"]
    ships = [u for u in ships if u.carries == "land"]
    return sorted(ships, key=lambda u: (u.can("coastal"), -u.capacity, u.cost, u.id))


def _ship_available(view: PlayerView, know: Knowledge, sea: Sea, port: City, landing: Tile) -> bool:
    """Do we have, or can the port build, a ship that can make the crossing?"""
    port_tile = view.tile_of(port)
    coastal_route = None

    def can_cross(definition: UnitDef) -> bool:
        nonlocal coastal_route
        if not definition.can("coastal"):
            return True
        if coastal_route is None:
            coastal_route = pathfinding.sea_route_exists(view, port_tile, landing, coastal=True)
        return coastal_route

    if any(can_cross(view.rules.units[ship.type]) for ship in free_ships(view, know, sea, set())):
        return True
    return any(can_cross(definition) for definition in transports(view, port))


def free_ships(view: PlayerView, know: Knowledge, sea: Sea, reserved: set[int]) -> list[Unit]:
    """Our transport ships on this sea that no expedition uses."""
    result = []
    for unit in know.units:
        definition = view.rules.units[unit.type]
        if definition.carries != "land" or unit.id in reserved:
            continue
        if sea.id in know.seas_at(view.tile_of(unit)):
            result.append(unit)
    return result


# ── Gathering in the port ─────────────────────────────────────────────────────

def passengers_wanted(view: PlayerView, expedition: dict, capacity: int) -> dict[str, int]:
    if expedition["kind"] == SETTLE:
        return {M.PASSENGER_SETTLER: 1, M.PASSENGER_ESCORT: 1 if capacity >= 2 else 0}
    group = int(view.rules.ai.get("overseas", "invade_group"))
    return {M.PASSENGER_ATTACK: max(1, min(capacity, group))}


def passengers_aboard(view: PlayerView, ship: Optional[Unit]) -> dict[str, int]:
    aboard = {M.PASSENGER_SETTLER: 0, M.PASSENGER_ESCORT: 0, M.PASSENGER_ATTACK: 0}
    if ship is None:
        return aboard
    for unit in view.cargo_of(ship):
        definition = view.rules.units[unit.type]
        if definition.can("found_city"):
            aboard[M.PASSENGER_SETTLER] += 1
        elif definition.role == "defense":
            aboard[M.PASSENGER_ESCORT] += 1
        else:
            aboard[M.PASSENGER_ATTACK] += 1
    return aboard


def _gather(view: PlayerView, know: Knowledge, plan, expedition: dict) -> None:
    """Finds a ship for the expedition and calls its passengers to the port."""
    rules = view.rules
    port = view.city(expedition["port"])
    port_tile = view.tile_of(port)
    goal = view.map.tile(*expedition["goal"])
    ship = view.unit(expedition["ship"]) if expedition["ship"] is not None else None

    if ship is None:
        ship = _pick_ship(view, know, plan, port, goal)
        if ship is not None:
            expedition["ship"] = ship.id
            plan.reserved.add(ship.id)
    if ship is not None:
        capacity = rules.units[ship.type].capacity
    else:
        buildable = transports(view, port)
        if not buildable:
            expedition["stage"] = DONE            # no ship any more, and none to build
            return
        capacity = buildable[0].capacity
        plan.ferries_wanted[port.id] = expedition["id"]

    wanted = passengers_wanted(view, expedition, capacity)
    aboard = passengers_aboard(view, ship)
    weights = {M.PASSENGER_SETTLER: rules.ai.get("production", "settlers") * 1.3,
               M.PASSENGER_ESCORT: rules.ai.get("production", "defense") * 0.4,
               M.PASSENGER_ATTACK: rules.ai.get("production", "attack") * 1.4}
    for role, count in wanted.items():
        missing = count - aboard[role]
        if missing > 0:
            plan.missions.append(Mission(
                M.EMBARK, port_tile.x, port_tile.y, weights[role], capacity=missing, order=role,
                target=expedition["id"], note=f"{expedition['kind']} from {port.name}"))


def _pick_ship(view: PlayerView, know: Knowledge, plan, port: City, goal: Tile) -> Optional[Unit]:
    world = view.map
    port_tile = view.tile_of(port)
    best = None
    for sea_id in sorted(know.seas_at(port_tile)):
        sea = know.seas[sea_id]
        spots = landing_spots(view, know, sea_id, goal)
        if not spots:
            continue
        for ship in free_ships(view, know, sea, plan.reserved):
            definition = view.rules.units[ship.type]
            if view.cargo_of(ship):
                continue
            if definition.can("coastal") and not pathfinding.sea_route_exists(
                    view, port_tile, spots[0][0], coastal=True):
                continue
            key = (-definition.capacity, world.steps(ship.x, ship.y, port.x, port.y), ship.id)
            if best is None or key < best[0]:
                best = (key, ship)
    return best[1] if best else None


def ready_to_sail(view: PlayerView, expedition: dict, ship: Unit) -> bool:
    """Called by the ship when it is in port: are enough passengers aboard?"""
    get = lambda name: view.rules.ai.get("overseas", name)
    wanted = passengers_wanted(view, expedition, view.rules.units[ship.type].capacity)
    aboard = passengers_aboard(view, ship)
    complete = all(aboard[role] >= count for role, count in wanted.items())
    if expedition["kind"] == SETTLE:
        enough = aboard[M.PASSENGER_SETTLER] >= 1
    else:
        enough = aboard[M.PASSENGER_ATTACK] >= min(get("invade_min_group"),
                                                   wanted[M.PASSENGER_ATTACK])
    if not enough:
        expedition["ready_since"] = None
        return False
    if expedition["ready_since"] is None:
        expedition["ready_since"] = view.turn
    return complete or view.turn - expedition["ready_since"] >= get("passenger_wait")


# ── What the navy and the air force need ──────────────────────────────────────

def sea_missions(view: PlayerView, know: Knowledge, plan) -> None:
    """One ship explores each sea that still has unknown shores."""
    get = lambda name: view.rules.ai.get("overseas", name)
    weight = view.rules.ai.get("production", "sea_explore")
    for sea in know.seas.values():
        if not sea.ports or sea.size < get("min_sea_size"):
            continue
        if len(sea.frontier) < get("sea_frontier_min"):
            continue
        port = max(sea.ports, key=lambda c: (c.stats.shields, -c.id))
        plan.missions.append(Mission(M.EXPLORE_SEA, port.x, port.y, weight,
                                     capacity=int(get("sea_explorers")), target=sea.id,
                                     note=f"{len(sea.frontier)} unknown shores"))


def count_needs(view: PlayerView, know: Knowledge, plan) -> None:
    """After the assignment: ships, aircraft and passengers the empire lacks."""
    rules = view.rules
    get = lambda name: rules.ai.get("overseas", name)
    for mission in plan.missions:
        if mission.kind == M.EXPLORE_SEA and not mission.assigned:
            city = view.my_city_at(mission.x, mission.y)
            if city is not None:
                plan.sea_explorers_wanted[city.id] = 1
        elif mission.kind == M.EMBARK and mission.free > 0:
            if mission.order == M.PASSENGER_SETTLER:
                plan.settlers_wanted += mission.free
            elif mission.order == M.PASSENGER_ATTACK:
                plan.attackers_wanted += mission.free
                plan.attackers_surplus = 0
            else:
                city = view.my_city_at(mission.x, mission.y)
                if city is not None:
                    plan.defenders_missing[city.id] = plan.defenders_missing.get(city.id, 0) + 1

    ports = {c.id for sea in know.seas.values() if sea.size >= get("min_sea_size")
             for c in sea.ports}
    port_seas = {sea.id for sea in know.seas.values() if sea.ports}
    world = view.map
    if plan.at_war and ports:
        enemy_at_sea = any(rules.units[u.type].domain == "sea" for u in know.enemy_units)
        coastal_target = any(
            view.at_war(m.owner) and know.seas_at(world.tile(m.x, m.y)) & port_seas
            for m in know.foreign_cities)
        if enemy_at_sea or coastal_target:
            wanted = math.ceil(len(ports) * get("navy_per_port"))
            plan.warships_wanted = max(0, wanted - len(know.units_with_role("sea_attack")))

    aircraft = know.units_with_role("air_attack")
    bombs = [u for u in aircraft if rules.units[u.type].can("nuclear")]
    if plan.at_war and (plan.war_targets or know.threats):
        wanted = math.ceil(len(know.cities) * get("aircraft_per_city"))
        plan.aircraft_wanted = max(0, wanted - (len(aircraft) - len(bombs)))
    if plan.at_war and any(view.at_war(m.owner) and not view.is_barbarian(m.owner)
                           for m in know.foreign_cities):
        plan.nuclear_wanted = max(0, int(get("nuclear_stock")) - len(bombs))
