"""Missions: what the strategy wants done, and which unit does it.

The strategic layer posts missions (a place, a kind of job, a priority, a number of units).
Each free unit takes the mission that suits it best: high priority, close by. A unit keeps
its mission from one turn to the next as long as the mission is still wanted, which avoids
units changing their mind every turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..engine.model.entities import Unit
from ..engine.model.worldmap import Tile
from ..engine.view import PlayerView
from .knowledge import Knowledge

FOUND_CITY = "found_city"
IMPROVE = "improve"
DEFEND = "defend"
ATTACK_CITY = "attack_city"
ATTACK_UNIT = "attack_unit"
EXPLORE = "explore"
EXPLORE_SEA = "explore_sea"
EMBARK = "embark"                # go to a port and board the ship of an expedition
HELP_WONDER = "help_wonder"
TRADE = "trade"

# Which kinds of mission each unit role may take, best fit first. Aircraft and ships on an
# expedition take no mission: they decide by themselves (unit_ai/aircraft.py, ship.py).
ROLE_MISSIONS: dict[str, tuple[str, ...]] = {
    "settler": (FOUND_CITY, EMBARK, IMPROVE),
    "defense": (DEFEND, EMBARK, EXPLORE),
    "attack": (ATTACK_UNIT, ATTACK_CITY, EMBARK, EXPLORE, DEFEND),
    "neutral": (HELP_WONDER, TRADE),
    "sea_attack": (ATTACK_UNIT, ATTACK_CITY, EXPLORE_SEA),
    "transport": (EXPLORE_SEA,),
}
# Settings (ai.yaml, strategy) giving how well a role fits a mission that is not its first choice.
ROLE_FIT: dict[tuple[str, str], str] = {
    ("defense", EXPLORE): "fit_defense_explore",
    ("attack", DEFEND): "fit_attack_defend",
    ("attack", EXPLORE): "fit_attack_explore",
}
# Passengers an expedition asks for (Mission.order of an EMBARK mission).
PASSENGER_SETTLER = "settler"
PASSENGER_ESCORT = "escort"
PASSENGER_ATTACK = "attack"


@dataclass
class Mission:
    kind: str
    x: int
    y: int
    priority: float
    capacity: int = 1
    order: Optional[str] = None           # IMPROVE: the terrain work; EMBARK: the passenger wanted
    target: Optional[int] = None          # city id, enemy unit id, region, sea or expedition id
    stage: str = ""                       # for ATTACK_CITY: "rally" or "assault"
    rally: Optional[tuple[int, int]] = None
    note: str = ""
    assigned: list[int] = field(default_factory=list)

    @property
    def key(self) -> tuple:
        return (self.kind, self.x, self.y, self.order)

    @property
    def free(self) -> int:
        return self.capacity - len(self.assigned)


def is_garrison(view: PlayerView, unit: Unit) -> bool:
    """A unit that can hold a city: a land unit able to fight."""
    definition = view.rules.units[unit.type]
    return definition.domain == "land" and definition.is_military and definition.defense > 0


def assign(view: PlayerView, know: Knowledge, missions: list[Mission],
           previous: dict[int, tuple], reserved: frozenset[int] = frozenset()) -> dict[int, Mission]:
    """Gives each unit at most one mission. Returns unit id -> mission.

    Units in `reserved` (ships of an expedition) and units aboard a ship are left alone.
    """
    rules = view.rules
    world = view.map
    setting = lambda name: rules.ai.get("strategy", name)
    stickiness = setting("mission_stickiness")
    distance_scale = setting("mission_distance_scale")
    result: dict[int, Mission] = {}
    free_units = [u for u in know.units if u.id not in reserved and u.aboard is None]

    # 1. Cities keep the defenders they already have, best defenders first.
    for mission in missions:
        if mission.kind != DEFEND:
            continue
        tile = world.tile(mission.x, mission.y)
        inside = [u for u in view.my_units_at(tile)
                  if is_garrison(view, u) and u.id not in reserved and u.aboard is None]
        inside.sort(key=lambda u: (rules.units[u.type].role != "defense",
                                   -rules.units[u.type].defense, u.id))
        for unit in inside[:mission.capacity]:
            mission.assigned.append(unit.id)
            result[unit.id] = mission

    # 2. Everybody else: best (priority, distance) pairs first.
    candidates: list[tuple[float, int, int]] = []
    for unit in free_units:
        if unit.id in result:
            continue
        kinds = ROLE_MISSIONS.get(rules.units[unit.type].role, ())
        if not kinds:
            continue
        for index, mission in enumerate(missions):
            if mission.kind not in kinds or mission.free <= 0:
                continue
            if not _suits(view, unit, mission):
                continue
            steps = _steps_if_reachable(view, know, unit, mission)
            if steps is None:
                continue
            fit_setting = ROLE_FIT.get((rules.units[unit.type].role, mission.kind))
            fit = setting(fit_setting) if fit_setting else 1.0
            score = mission.priority * fit / (1.0 + steps / distance_scale)
            if previous.get(unit.id) == mission.key:
                score *= stickiness
            candidates.append((score, unit.id, index))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    for score, unit_id, index in candidates:
        mission = missions[index]
        if unit_id in result or mission.free <= 0:
            continue
        mission.assigned.append(unit_id)
        result[unit_id] = mission
    return result


def _steps_if_reachable(view: PlayerView, know: Knowledge, unit: Unit,
                        mission: Mission) -> Optional[int]:
    """Distance to the mission, or None if the unit has no known way to get there."""
    world = view.map
    origin = view.tile_of(unit)
    target = world.tile(mission.x, mission.y)
    if mission.kind == EXPLORE:
        # An explorer works anywhere in its region: distance to the anchor is irrelevant.
        return 0 if know.region_of[origin.index] == mission.target else None
    if mission.kind == EXPLORE_SEA:
        return 0 if mission.target in know.seas_at(origin) else None
    steps = world.steps(unit.x, unit.y, mission.x, mission.y)
    if view.rules.units[unit.type].domain == "sea":
        return steps if know.seas_at(origin) & know.seas_at(target) else None
    if steps > 0 and not know.same_region(origin, target) \
            and not _next_to_region(know, origin, target):
        return None
    return steps


def _suits(view: PlayerView, unit: Unit, mission: Mission) -> bool:
    definition = view.rules.units[unit.type]
    if mission.kind == FOUND_CITY:
        return definition.can("found_city")
    if mission.kind == IMPROVE:
        return definition.can("terraform")
    if mission.kind in (HELP_WONDER, TRADE):
        return definition.can("trade")
    if mission.kind in (ATTACK_CITY, ATTACK_UNIT):
        if definition.attack <= 0:
            return False
        on_land = view.is_land(view.map.tile(mission.x, mission.y))
        if definition.domain == "land":
            return on_land
        return not (on_land and definition.can("no_shore_attack"))
    if mission.kind in (EXPLORE, DEFEND):
        return definition.domain == "land"
    if mission.kind == EXPLORE_SEA:
        return definition.domain == "sea"
    if mission.kind == EMBARK:
        if mission.order == PASSENGER_SETTLER:
            return definition.can("found_city")
        if mission.order == PASSENGER_ESCORT:
            return definition.role == "defense"
        return definition.role == "attack"
    return True


def _next_to_region(know: Knowledge, origin: Tile, target: Tile) -> bool:
    """A target on a tile we cannot stand on (a foreign city) is reached from its side."""
    world = know.view.map
    region = know.region_of[origin.index]
    return any(know.region_of[t.index] == region for t in world.neighbors(target))
