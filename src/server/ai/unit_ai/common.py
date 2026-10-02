"""Helpers shared by the unit behaviours."""
from __future__ import annotations

from typing import Callable, Optional

from ...engine import actions
from ...engine.model.entities import ORDER_FORTIFIED, ORDER_FORTIFY, ORDER_SENTRY, City, Unit
from ...engine.model.worldmap import Tile
from ...engine.view import PlayerView
from .. import overseas, pathfinding
from ..knowledge import Knowledge
from ..missions import Mission


class Context:
    """What a unit behaviour needs: the view, the turn's knowledge and plan, and a memory."""

    def __init__(self, view: PlayerView, know: Knowledge, plan, memory: dict) -> None:
        self.view = view
        self.know = know
        self.plan = plan
        self.memory = memory            # persists from turn to turn (plain data only)
        self.rules = view.rules

    def ai(self, section: str, name: str) -> float:
        return self.rules.ai.get(section, name)


def alive(ctx: Context, unit: Unit) -> bool:
    return ctx.view.unit(unit.id) is not None


def moves(ctx: Context, unit: Unit) -> int:
    """Whole moves the unit has left this turn."""
    return unit.moves_left // ctx.rules.game.movement.points_per_move


def go_to(ctx: Context, unit: Unit, goal: Tile, *, adjacent: bool = False,
          avoid: Optional[Callable[[Tile], bool]] = None) -> str:
    """Moves toward the goal as far as this turn allows.

    Returns "arrived", "moving" (still on the way), "blocked" (no known route) or "dead".
    """
    view = ctx.view
    path = pathfinding.find_path(view, unit, goal, adjacent=adjacent, avoid=avoid)
    if path is None:
        return "blocked"
    if not path:
        return "arrived"
    for step in path:
        if unit.moves_left <= 0:
            return "moving"
        result = view.do(actions.MoveUnit(unit.id, step.x, step.y))
        if not alive(ctx, unit):
            return "dead"
        if not result.ok:
            return "blocked"
        if result.outcome != "moved":
            return "moving"
    return "arrived"


def step_to(ctx: Context, unit: Unit, tile: Tile) -> actions.Result:
    """One step (or attack) into an adjacent tile."""
    return ctx.view.do(actions.MoveUnit(unit.id, tile.x, tile.y))


def fortify(ctx: Context, unit: Unit) -> None:
    if unit.order not in (ORDER_FORTIFY, ORDER_FORTIFIED):
        ctx.view.do(actions.SetOrder(unit.id, ORDER_FORTIFY))


def sentry(ctx: Context, unit: Unit) -> None:
    if unit.order != ORDER_SENTRY:
        ctx.view.do(actions.SetOrder(unit.id, ORDER_SENTRY))


def nearest_own_city(ctx: Context, unit: Unit) -> Optional[City]:
    """Closest own city the unit can reach: same region on land, same sea for a ship,
    within flight range for an aircraft."""
    world = ctx.view.map
    origin = ctx.view.tile_of(unit)
    domain = ctx.rules.units[unit.type].domain
    seas = ctx.know.seas_at(origin) if domain == "sea" else set()
    best = None
    for city in ctx.know.cities:
        tile = ctx.view.tile_of(city)
        if domain == "land" and not ctx.know.same_region(origin, tile):
            continue
        if domain == "sea" and tile is not origin and not seas & ctx.know.seas_at(tile):
            continue
        distance = world.steps(unit.x, unit.y, city.x, city.y)
        if best is None or distance < best[0]:
            best = (distance, city)
    return best[1] if best else None


def go_home(ctx: Context, unit: Unit) -> None:
    """Falls back to the nearest city and stands guard there."""
    city = nearest_own_city(ctx, unit)
    is_land_unit = ctx.rules.units[unit.type].domain == "land"
    wait = fortify if is_land_unit else sentry
    if city is None:
        wait(ctx, unit)
        return
    tile = ctx.view.tile_of(city)
    if ctx.view.tile_of(unit) is tile or go_to(ctx, unit, tile) == "arrived":
        if alive(ctx, unit):
            wait(ctx, unit)


def embark(ctx: Context, unit: Unit, mission: Mission) -> None:
    """Goes to the port of an expedition and boards its ship as soon as it is there."""
    view = ctx.view
    port = view.map.tile(mission.x, mission.y)
    if view.tile_of(unit) is not port:
        if go_to(ctx, unit, port) != "arrived" or not alive(ctx, unit):
            return
    expedition = overseas.expedition_by_id(ctx.memory, mission.target)
    ship = None
    if expedition is not None and expedition["ship"] is not None:
        ship = view.unit(expedition["ship"])
    if ship is not None and view.tile_of(ship) is port \
            and view.do(actions.Board(unit.id, ship.id)):
        return
    sentry(ctx, unit)


def enemies_adjacent(ctx: Context, tile: Tile) -> list[Tile]:
    """Adjacent tiles where enemy units are seen."""
    return [t for t in ctx.view.map.neighbors(tile) if ctx.view.enemy_units_at(t)]


def strike_adjacent(ctx: Context, unit: Unit, min_odds: float,
                    only: Optional[Tile] = None) -> bool:
    """Attacks the adjacent enemy stack we are most likely to destroy. True if it attacked."""
    view = ctx.view
    if unit.moves_left <= 0:
        return False
    here = view.tile_of(unit)
    best = None
    for tile in enemies_adjacent(ctx, here):
        if only is not None and tile is not only:
            continue
        if not view.can_enter(unit, tile):
            continue
        odds = view.attack_odds(unit, tile)
        if odds is None or odds.win_chance < min_odds:
            continue
        value = odds.win_chance * (1 + len(view.enemy_units_at(tile)))
        if best is None or value > best[0]:
            best = (value, tile)
    if best is None:
        return False
    step_to(ctx, unit, best[1])
    return True


def danger_near(ctx: Context, tile: Tile, radius: int = 2) -> bool:
    """An enemy military unit is seen within `radius` steps of the tile."""
    world = ctx.view.map
    for unit in ctx.know.enemy_units:
        if ctx.rules.units[unit.type].attack > 0 \
                and world.steps(tile.x, tile.y, unit.x, unit.y) <= radius:
            return True
    return False
