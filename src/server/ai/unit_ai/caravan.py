"""Caravans: carry their shields to a wonder under construction, or open a trade route."""
from __future__ import annotations

from ...engine import actions
from ...engine.model.entities import Unit
from .. import missions as M
from ..missions import Mission
from .common import Context, alive, go_to, sentry


def act(ctx: Context, unit: Unit, mission: Mission | None) -> None:
    view = ctx.view
    if mission is not None and mission.kind == M.HELP_WONDER:
        target = view.map.tile(mission.x, mission.y)
        if view.tile_of(unit) is target or go_to(ctx, unit, target) == "arrived":
            if alive(ctx, unit):
                view.do(actions.HelpBuildWonder(unit.id))
        return
    if view.trade_route_target(unit) is not None:
        view.do(actions.EstablishTradeRoute(unit.id))
        return
    destination = _route_destination(ctx, unit)
    if destination is None:
        sentry(ctx, unit)
        return
    if go_to(ctx, unit, view.tile_of(destination)) == "arrived" and alive(ctx, unit):
        view.do(actions.EstablishTradeRoute(unit.id))


def _route_destination(ctx: Context, unit: Unit):
    """The farthest of our cities reachable by land that has no route with the home city."""
    view = ctx.view
    home = view.city(unit.home_city) if unit.home_city is not None else None
    if home is None:
        return None
    minimum = ctx.rules.game.city.trade_route_min_distance
    origin = view.tile_of(unit)
    best = None
    for city in ctx.know.cities:
        if city.id == home.id or city.id in home.trade_routes:
            continue
        if not ctx.know.same_region(origin, view.tile_of(city)):
            continue
        distance = view.map.distance(home.x, home.y, city.x, city.y)
        if distance < minimum:
            continue
        value = (city.stats.trade, distance)
        if best is None or value > best[0]:
            best = (value, city)
    return best[1] if best else None
