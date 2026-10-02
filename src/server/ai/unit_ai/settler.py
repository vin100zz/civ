"""Settlers: found cities, improve the land, stay out of danger."""
from __future__ import annotations

from ...engine import actions
from ...engine.model.entities import WORK_ORDERS, Unit
from .. import missions as M
from ..missions import Mission
from .common import (Context, alive, danger_near, embark, go_home, go_to, nearest_own_city,
                     sentry)


def act(ctx: Context, unit: Unit, mission: Mission | None) -> None:
    view = ctx.view
    here = view.tile_of(unit)

    # An unescorted settler under threat runs for the nearest city.
    if danger_near(ctx, here) and view.my_city_at(unit.x, unit.y) is None \
            and len(view.my_units_at(here)) == 1:
        go_home(ctx, unit)
        return

    if mission is None:
        _idle(ctx, unit)
        return

    if mission.kind == M.EMBARK:
        embark(ctx, unit, mission)
        return

    target = view.map.tile(mission.x, mission.y)
    if mission.kind == M.FOUND_CITY:
        if here is target:
            if not view.do(actions.FoundCity(unit.id)):
                _idle(ctx, unit)
            return
        status = go_to(ctx, unit, target)
        if status == "arrived" and alive(ctx, unit) and unit.moves_left > 0:
            view.do(actions.FoundCity(unit.id))
        elif status == "blocked":
            _first_city_fallback(ctx, unit)
        return

    if mission.kind == M.IMPROVE:
        if unit.order in WORK_ORDERS and here is target:
            return                                   # already at work
        if here is not target:
            status = go_to(ctx, unit, target)
            if status != "arrived" or not alive(ctx, unit):
                return
        if unit.moves_left > 0 and mission.order is not None:
            view.do(actions.SetOrder(unit.id, mission.order))
        return

    _idle(ctx, unit)


def _first_city_fallback(ctx: Context, unit: Unit) -> None:
    """A civilization without any city settles where it stands rather than wander forever."""
    if not ctx.know.cities:
        ctx.view.do(actions.FoundCity(unit.id))


def _idle(ctx: Context, unit: Unit) -> None:
    view = ctx.view
    if unit.order in WORK_ORDERS:
        return
    if not ctx.know.cities:
        # No site in sight for the very first city: settle here if the land allows it.
        if not view.do(actions.FoundCity(unit.id)):
            _wander(ctx, unit)
        return
    # Nothing to found, nothing to improve: the settlers become citizens again.
    city = view.my_city_at(unit.x, unit.y)
    if city is None:
        home = nearest_own_city(ctx, unit)
        if home is None:
            return
        if go_to(ctx, unit, view.tile_of(home)) != "arrived" or not alive(ctx, unit):
            return
    if not view.do(actions.JoinCity(unit.id)):
        sentry(ctx, unit)


def _wander(ctx: Context, unit: Unit) -> None:
    """Looks for land where a city can be founded."""
    view = ctx.view
    here = view.tile_of(unit)
    options = [t for t in view.map.neighbors(here) if view.can_enter(unit, t)]
    if options:
        tile = max(options, key=lambda t: (view.site_score(t), -t.index))
        view.do(actions.MoveUnit(unit.id, tile.x, tile.y))
