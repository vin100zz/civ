"""Explorers: go to the nearest unknown land or sea, open huts on the way."""
from __future__ import annotations

from collections import deque
from typing import Optional

from ...engine import actions
from ...engine.model.entities import Unit
from ...engine.model.worldmap import Tile
from .. import pathfinding
from ..missions import Mission
from .common import Context, alive, danger_near, go_home

MAX_SEARCH = 2500
MAX_STEPS_PER_TURN = 12


def act(ctx: Context, unit: Unit, mission: Mission | None) -> None:
    view = ctx.view
    # Railroads cost no movement: bound the number of steps so a unit cannot wander forever.
    for _ in range(MAX_STEPS_PER_TURN):
        if not alive(ctx, unit) or unit.moves_left <= 0:
            return
        here = view.tile_of(unit)
        hut = _adjacent_hut(ctx, unit, here)
        if hut is not None:
            view.do(actions.MoveUnit(unit.id, hut.x, hut.y))
            continue
        step = _next_step_to_frontier(ctx, unit)
        if step is None:
            go_home(ctx, unit)
            return
        result = view.do(actions.MoveUnit(unit.id, step.x, step.y))
        if not result.ok or result.outcome != "moved":
            return


def has_frontier(ctx: Context, unit: Unit) -> bool:
    """Is there still unknown ground this unit knows a way to?"""
    return _next_step_to_frontier(ctx, unit) is not None


def _adjacent_hut(ctx: Context, unit: Unit, here: Tile) -> Optional[Tile]:
    if ctx.rules.units[unit.type].domain != "land":
        return None
    for tile in ctx.view.map.neighbors(here):
        if tile.hut and ctx.view.explored(tile) and ctx.view.can_enter(unit, tile) \
                and not ctx.view.foreign_units_at(tile):
            return tile
    return None


def _next_step_to_frontier(ctx: Context, unit: Unit) -> Optional[Tile]:
    """First step of the shortest known walk to a tile that borders the unknown."""
    view, world = ctx.view, ctx.view.map
    start = view.tile_of(unit)
    first_step: dict[int, Tile] = {}
    queue: deque[Tile] = deque([start])
    seen = {start.index}
    visited = 0
    while queue:
        tile = queue.popleft()
        visited += 1
        if visited > MAX_SEARCH:
            break
        if tile is not start and any(not view.explored(n) for n in world.neighbors(tile)):
            if not danger_near(ctx, tile, 1):
                return first_step[tile.index]
        for other in world.neighbors(tile):
            if other.index in seen:
                continue
            seen.add(other.index)
            if not pathfinding.passable(view, unit, other):
                continue
            if tile is start and not view.can_enter(unit, other):
                continue
            first_step[other.index] = other if tile is start else first_step[tile.index]
            queue.append(other)
    return None
