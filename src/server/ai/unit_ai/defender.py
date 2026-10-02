"""Defenders: reach the city they are assigned to and dig in."""
from __future__ import annotations

from ...engine import actions
from ...engine.model.entities import Unit
from .. import missions as M
from ..missions import Mission
from .common import Context, alive, embark, enemies_adjacent, fortify, go_home, go_to, step_to


def act(ctx: Context, unit: Unit, mission: Mission | None) -> None:
    view = ctx.view
    if mission is not None and mission.kind == M.EMBARK:
        embark(ctx, unit, mission)
        return
    if mission is None or mission.kind != M.DEFEND:
        go_home(ctx, unit)
        return
    target = view.map.tile(mission.x, mission.y)
    here = view.tile_of(unit)
    if here is not target:
        status = go_to(ctx, unit, target)
        if status != "arrived" or not alive(ctx, unit):
            return
    # The city a unit defends pays for it.
    if mission.target is not None and unit.home_city != mission.target:
        view.do(actions.Rehome(unit.id))
    _sortie(ctx, unit, mission)
    if alive(ctx, unit):
        fortify(ctx, unit)


def _sortie(ctx: Context, unit: Unit, mission: Mission) -> None:
    """Strikes an adjacent enemy when the odds are good and the city stays guarded."""
    view = ctx.view
    if unit.moves_left < ctx.rules.game.movement.points_per_move:
        return
    here = view.tile_of(unit)
    others = [u for u in view.my_units_at(here)
              if u.id != unit.id and ctx.rules.units[u.type].is_military]
    if not others:
        return
    minimum = ctx.ai("military", "defend_min_odds")
    best = None
    for tile in enemies_adjacent(ctx, here):
        if view.foreign_city_at(tile) is not None:
            continue
        odds = view.attack_odds(unit, tile)
        if odds is not None and odds.win_chance >= minimum:
            if best is None or odds.win_chance > best[0]:
                best = (odds.win_chance, tile)
    if best is not None:
        step_to(ctx, unit, best[1])
