"""Attack units: hunt enemies near our cities, gather, then assault the target city."""
from __future__ import annotations

from ...engine.model.entities import Unit
from .. import missions as M
from ..missions import Mission
from . import explorer
from .common import (Context, alive, embark, fortify, go_home, go_to, sentry, step_to,
                     strike_adjacent)


def act(ctx: Context, unit: Unit, mission: Mission | None) -> None:
    view = ctx.view

    # Any enemy next to us that we are likely to beat is attacked first.
    if strike_adjacent(ctx, unit, ctx.ai("military", "attack_min_odds")):
        if not alive(ctx, unit) or unit.moves_left <= 0:
            return

    if mission is None:
        go_home(ctx, unit)
        return
    if mission.kind == M.EMBARK:
        embark(ctx, unit, mission)
    elif mission.kind == M.EXPLORE:
        explorer.act(ctx, unit, mission)
    elif mission.kind == M.ATTACK_UNIT:
        _hunt(ctx, unit, mission)
    elif mission.kind == M.ATTACK_CITY:
        _siege(ctx, unit, mission)
    elif mission.kind == M.DEFEND:
        target = view.map.tile(mission.x, mission.y)
        if view.tile_of(unit) is target or go_to(ctx, unit, target) == "arrived":
            if alive(ctx, unit):
                fortify(ctx, unit)
    else:
        go_home(ctx, unit)


def _hunt(ctx: Context, unit: Unit, mission: Mission) -> None:
    """Closes in on an enemy unit seen near one of our cities."""
    view = ctx.view
    target = view.map.tile(mission.x, mission.y)
    if not view.enemy_units_at(target):
        go_home(ctx, unit)
        return
    odds = view.attack_odds(unit, target)
    if odds is not None and odds.win_chance < ctx.ai("military", "attack_min_odds") * 0.6:
        go_home(ctx, unit)            # hopeless: stay behind the walls
        return
    status = go_to(ctx, unit, target, adjacent=True)
    if status == "arrived" and alive(ctx, unit):
        strike_adjacent(ctx, unit, ctx.ai("military", "attack_min_odds") * 0.8, only=target)


def _siege(ctx: Context, unit: Unit, mission: Mission) -> None:
    view = ctx.view
    world = view.map
    target = world.tile(mission.x, mission.y)

    if mission.stage == "rally" and mission.rally is not None:
        rally = world.tile(*mission.rally)
        if view.tile_of(unit) is rally:
            sentry(ctx, unit)
        elif go_to(ctx, unit, rally) == "arrived" and alive(ctx, unit):
            sentry(ctx, unit)
        return

    here = view.tile_of(unit)
    if target not in world.neighbors(here):
        status = go_to(ctx, unit, target, adjacent=True)
        if status != "arrived" or not alive(ctx, unit) or unit.moves_left <= 0:
            return
        here = view.tile_of(unit)

    if not view.can_enter(unit, target):
        fortify(ctx, unit)
        return
    if not view.foreign_units_at(target):
        step_to(ctx, unit, target)          # undefended: walk in
        return
    odds = view.attack_odds(unit, target)
    comrades = sum(1 for other in ctx.know.units
                   if other.id != unit.id and ctx.rules.units[other.type].role == "attack"
                   and world.steps(other.x, other.y, target.x, target.y) <= 2)
    minimum = ctx.ai("military", "attack_city_min_odds")
    if comrades + 1 >= ctx.ai("strategy", "siege_group_size"):
        minimum *= 0.5                       # in numbers, accept worse odds
    if odds is not None and odds.win_chance >= minimum:
        step_to(ctx, unit, target)
    else:
        fortify(ctx, unit)
