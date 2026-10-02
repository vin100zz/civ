"""Path search over what a player knows of the map.

A unit only plans through tiles its owner has explored (aircraft fly anywhere). Tiles where
a foreign unit or city is currently seen are avoided, except the destination itself.
"""
from __future__ import annotations

import heapq
from collections import deque
from typing import Callable, Optional

from ..engine.model.entities import Unit
from ..engine.model.worldmap import Tile
from ..engine.view import PlayerView

MAX_NODES = 6000


def near_known_land(view: PlayerView, tile: Tile) -> bool:
    return any(view.explored(t) and view.is_land(t) for t in view.map.neighbors(tile))


def passable(view: PlayerView, unit: Unit, tile: Tile) -> bool:
    """Can the unit plan to go through this tile?"""
    definition = view.rules.units[unit.type]
    domain = definition.domain
    if domain != "air" and not view.explored(tile):
        return False
    is_land = view.is_land(tile)
    own_city = view.my_city_at(tile.x, tile.y) is not None
    if domain == "land" and not is_land:
        return False
    if domain == "sea":
        if is_land and not own_city:
            return False
        # Ships that may be lost at sea follow the coast.
        if not is_land and definition.can("coastal") and not near_known_land(view, tile):
            return False
    if view.foreign_units_at(tile):
        return False
    if view.foreign_city_at(tile) is not None and not own_city:
        return False
    return True


def find_path(view: PlayerView, unit: Unit, goal: Tile, *, adjacent: bool = False,
              avoid: Optional[Callable[[Tile], bool]] = None) -> Optional[list[Tile]]:
    """Cheapest known route from the unit to the goal (A*), as the list of tiles to step on.

    With `adjacent`, stopping next to the goal is enough (to attack it, or to work beside it).
    Returns an empty list if the unit is already there, None if no route is known.
    """
    world = view.map
    start = view.tile_of(unit)
    if start is goal or (adjacent and goal in world.neighbors(start)):
        return []

    def estimate(tile: Tile) -> int:
        return world.steps(tile.x, tile.y, goal.x, goal.y)

    counter = 0
    frontier: list[tuple[int, int, Tile]] = [(estimate(start), counter, start)]
    cost_so_far: dict[int, int] = {start.index: 0}
    came_from: dict[int, Tile] = {}
    explored_nodes = 0

    while frontier:
        _, _, current = heapq.heappop(frontier)
        explored_nodes += 1
        if explored_nodes > MAX_NODES:
            return None
        done = current is goal or (adjacent and goal in world.neighbors(current)
                                   and current is not start)
        if done:
            path = [current]
            while path[-1].index in came_from:
                path.append(came_from[path[-1].index])
            path.reverse()
            return path[1:]
        base = cost_so_far[current.index]
        for nxt in world.neighbors(current):
            if nxt is not goal or adjacent:
                if not passable(view, unit, nxt):
                    continue
                if avoid is not None and avoid(nxt):
                    continue
            elif not _can_stand_on_goal(view, unit, nxt):
                continue
            new_cost = base + max(1, view.move_cost(unit, current, nxt))
            if new_cost < cost_so_far.get(nxt.index, 1 << 30):
                cost_so_far[nxt.index] = new_cost
                came_from[nxt.index] = current
                counter += 1
                heapq.heappush(frontier, (new_cost + estimate(nxt), counter, nxt))
    return None


def _can_stand_on_goal(view: PlayerView, unit: Unit, tile: Tile) -> bool:
    """The goal may hold an enemy (we go there to fight) but must suit the unit's domain."""
    domain = view.rules.units[unit.type].domain
    if domain == "air":
        return True
    if not view.explored(tile):
        return False
    if domain == "land":
        return view.is_land(tile)
    return not view.is_land(tile) or view.my_city_at(tile.x, tile.y) is not None


def sea_route_exists(view: PlayerView, start: Tile, goal: Tile, coastal: bool) -> bool:
    """Is there a known way by sea from `start` (a port or a sea tile) to the sea tile `goal`?
    With `coastal`, only along the shores (for ships that may be lost at sea)."""
    world = view.map
    queue: deque[Tile] = deque([start])
    seen = {start.index}
    visited = 0
    while queue and visited < MAX_NODES:
        tile = queue.popleft()
        visited += 1
        if tile is goal:
            return True
        for other in world.neighbors(tile):
            if other.index in seen:
                continue
            seen.add(other.index)
            if not view.explored(other) or view.is_land(other):
                continue
            if coastal and not near_known_land(view, other):
                continue
            queue.append(other)
    return False
