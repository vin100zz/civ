"""Aircraft: strike from a city and come back before the fuel runs out.

Aircraft take no mission from the strategy: each one looks for the best target within reach
of its base, and moves to the city closest to the front when it has nothing to hit.
Nuclear weapons fly one way.
"""
from __future__ import annotations

from typing import Optional

from ...engine.model.entities import City, Unit
from ...engine.model.worldmap import Tile
from ..missions import Mission
from .common import Context, alive, go_to, moves, sentry, step_to

# Moves kept in reserve when planning a flight: the way around foreign units and cities
# can be longer than the straight line.
MARGIN = 2


def act(ctx: Context, unit: Unit, mission: Mission | None) -> None:
    if ctx.rules.units[unit.type].can("nuclear"):
        _nuclear(ctx, unit)
        return
    if ctx.view.my_city_at(unit.x, unit.y) is None:
        _return(ctx, unit)                      # caught in flight: land first
        return
    target = _pick_target(ctx, unit)
    if target is not None:
        _strike(ctx, unit, target)
        if alive(ctx, unit):
            _return(ctx, unit)
        return
    _rebase(ctx, unit, _front(ctx, unit))


def _nearest_base(ctx: Context, tile: Tile) -> int:
    """Steps from the tile to our closest city."""
    world = ctx.view.map
    return min((world.steps(tile.x, tile.y, c.x, c.y) for c in ctx.know.cities), default=99)


def _pick_target(ctx: Context, unit: Unit) -> Optional[Tile]:
    """The enemy stack we are most likely to destroy and can come back from."""
    view, world = ctx.view, ctx.view.map
    minimum = ctx.ai("overseas", "air_min_odds")
    reach = moves(ctx, unit)
    targets = {m.city_id: (m.x, m.y) for m in ctx.plan.war_targets}
    best = None
    seen: set[int] = set()
    for enemy in ctx.know.enemy_units:
        tile = view.tile_of(enemy)
        if tile.index in seen:
            continue
        seen.add(tile.index)
        distance = world.steps(unit.x, unit.y, tile.x, tile.y)
        if distance + _nearest_base(ctx, tile) + MARGIN > reach:
            continue
        if not view.can_attack(unit, tile):
            continue
        odds = view.attack_odds(unit, tile)
        if odds is None or odds.win_chance < minimum:
            continue
        value = odds.win_chance * (1 + len(view.enemy_units_at(tile)))
        if (tile.x, tile.y) in targets.values() or _nearest_base(ctx, tile) <= 2:
            value *= 2.0                        # the city under siege, or a threat at our door
        if best is None or value > best[0]:
            best = (value, tile)
    return best[1] if best else None


def _strike(ctx: Context, unit: Unit, target: Tile) -> None:
    if go_to(ctx, unit, target, adjacent=True) != "arrived" or not alive(ctx, unit):
        return
    here = ctx.view.tile_of(unit)
    # The way was longer than expected: keep enough fuel to come back.
    if moves(ctx, unit) - 1 < _nearest_base(ctx, here) + 1:
        return
    step_to(ctx, unit, target)


def _return(ctx: Context, unit: Unit) -> None:
    view, world = ctx.view, ctx.view.map
    if view.my_city_at(unit.x, unit.y) is not None:
        return
    cities = sorted(ctx.know.cities, key=lambda c: (world.steps(unit.x, unit.y, c.x, c.y), c.id))
    for city in cities[:3]:
        if go_to(ctx, unit, view.tile_of(city)) != "blocked":
            return


def _front(ctx: Context, unit: Unit) -> Optional[tuple[int, int]]:
    """Where the aircraft are needed: the nearest war target, else a threatened city."""
    world = ctx.view.map
    places = [(m.x, m.y) for m in ctx.plan.war_targets]
    places += [(c.x, c.y) for c in ctx.know.cities if ctx.know.threatened(c)]
    if not places:
        return None
    return min(places, key=lambda p: (world.steps(unit.x, unit.y, p[0], p[1]), p))


def _rebase(ctx: Context, unit: Unit, front: Optional[tuple[int, int]]) -> None:
    """Moves to our city closest to the front that can be reached in one flight."""
    view, world = ctx.view, ctx.view.map
    if front is None:
        sentry(ctx, unit)
        return
    reach = moves(ctx, unit) - MARGIN
    here = world.steps(unit.x, unit.y, front[0], front[1])
    best: Optional[tuple[int, int, City]] = None
    for city in ctx.know.cities:
        if world.steps(unit.x, unit.y, city.x, city.y) > reach:
            continue
        distance = world.steps(city.x, city.y, front[0], front[1])
        if distance < here - 1 and (best is None or (distance, city.id) < best[:2]):
            best = (distance, city.id, city)
    if best is None or go_to(ctx, unit, view.tile_of(best[2])) == "blocked":
        sentry(ctx, unit)


def _nuclear(ctx: Context, unit: Unit) -> None:
    """Flies to the largest enemy city within reach; otherwise waits closer to the enemy."""
    view, world = ctx.view, ctx.view.map
    reach = moves(ctx, unit)
    enemy_cities = [m for m in ctx.know.foreign_cities
                    if view.at_war(m.owner) and not view.is_barbarian(m.owner)]
    in_reach = [m for m in enemy_cities if world.steps(unit.x, unit.y, m.x, m.y) <= reach]
    if in_reach:
        memory = max(in_reach, key=lambda m: (m.size, -m.city_id))
        target = world.tile(memory.x, memory.y)
        if go_to(ctx, unit, target, adjacent=True) == "arrived" and alive(ctx, unit):
            step_to(ctx, unit, target)
        return
    if view.my_city_at(unit.x, unit.y) is None:
        _return(ctx, unit)
        return
    nearest = min(enemy_cities, default=None,
                  key=lambda m: (world.steps(unit.x, unit.y, m.x, m.y), m.city_id))
    _rebase(ctx, unit, (nearest.x, nearest.y) if nearest is not None else None)
