"""Ships: ferry an expedition, explore the seas, hunt enemy ships, bombard coastal cities."""
from __future__ import annotations

from ...engine import actions
from ...engine.model.entities import Unit
from ...engine.model.worldmap import Tile
from .. import missions as M
from .. import overseas
from ..missions import Mission
from . import explorer
from .common import Context, alive, go_home, go_to, sentry, strike_adjacent


def act(ctx: Context, ship: Unit, mission: Mission | None) -> None:
    view = ctx.view
    expedition = overseas.expedition_of_ship(ctx.memory, ship.id)
    if expedition is not None:
        _ferry(ctx, ship, expedition)
        return

    if ctx.rules.units[ship.type].role == "sea_attack":
        if strike_adjacent(ctx, ship, ctx.ai("military", "attack_min_odds")):
            if not alive(ctx, ship) or ship.moves_left <= 0:
                return

    if view.cargo_of(ship):
        _bring_back(ctx, ship)                  # passengers of an expedition that was given up
    elif mission is None:
        go_home(ctx, ship)
    elif mission.kind == M.EXPLORE_SEA:
        explorer.act(ctx, ship, mission)
    elif mission.kind == M.ATTACK_UNIT:
        _hunt(ctx, ship, mission)
    elif mission.kind == M.ATTACK_CITY:
        _bombard(ctx, ship, mission)
    else:
        go_home(ctx, ship)


# ── Expeditions ───────────────────────────────────────────────────────────────

def _ferry(ctx: Context, ship: Unit, expedition: dict) -> None:
    view = ctx.view
    if expedition["stage"] == overseas.GATHER:
        port = view.city(expedition["port"])
        if port is None:
            return
        port_tile = view.tile_of(port)
        if view.tile_of(ship) is not port_tile:
            if go_to(ctx, ship, port_tile) != "arrived" or not alive(ctx, ship):
                return
        if not overseas.ready_to_sail(view, expedition, ship):
            sentry(ctx, ship)
            return
        expedition["stage"] = overseas.SAIL
        expedition["started"] = view.turn

    goal = view.map.tile(*expedition["goal"])
    here = view.tile_of(ship)
    spots: list[tuple[Tile, Tile]] = []
    for sea_id in sorted(ctx.know.seas_at(here)):
        spots.extend(overseas.landing_spots(view, ctx.know, sea_id, goal))
    world = view.map
    spots.sort(key=lambda s: (world.steps(s[1].x, s[1].y, goal.x, goal.y), s[0].index, s[1].index))
    anchorages: list[Tile] = []
    for water, _ in spots:
        if water not in anchorages:
            anchorages.append(water)
    for water in anchorages[:3]:
        status = "arrived" if here is water else go_to(ctx, ship, water)
        if status == "blocked":
            continue
        if status == "arrived" and alive(ctx, ship):
            _put_ashore(ctx, ship, expedition, goal)
        return
    expedition["stage"] = overseas.DONE          # no known way: the ship turns back


def _put_ashore(ctx: Context, ship: Unit, expedition: dict, goal: Tile) -> None:
    """Passengers step onto the land next to the ship, as close to the goal as they can."""
    view, world = ctx.view, ctx.view.map
    here = view.tile_of(ship)
    region = ctx.know.region_of[goal.index]
    for passenger in sorted(view.cargo_of(ship), key=lambda u: u.id):
        options = [t for t in world.neighbors(here)
                   if ctx.know.region_of[t.index] == region and view.is_land(t)
                   and not view.foreign_units_at(t) and view.foreign_city_at(t) is None
                   and view.can_enter(passenger, t)]
        if options:
            tile = min(options, key=lambda t: (world.steps(t.x, t.y, goal.x, goal.y), t.index))
            view.do(actions.MoveUnit(passenger.id, tile.x, tile.y))
    if alive(ctx, ship) and not view.cargo_of(ship):
        expedition["stage"] = overseas.DONE


def _bring_back(ctx: Context, ship: Unit) -> None:
    """Returns to a port, where the passengers go ashore."""
    view = ctx.view
    go_home(ctx, ship)
    if alive(ctx, ship) and view.my_city_at(ship.x, ship.y) is not None:
        for passenger in view.cargo_of(ship):
            view.do(actions.Disembark(passenger.id))


# ── Warships ──────────────────────────────────────────────────────────────────

def _hunt(ctx: Context, ship: Unit, mission: Mission) -> None:
    """Closes in on an enemy seen near one of our cities and attacks it if the odds allow."""
    view = ctx.view
    target = view.map.tile(mission.x, mission.y)
    minimum = ctx.ai("military", "attack_min_odds")
    odds = view.attack_odds(ship, target)
    if odds is None or odds.win_chance < minimum * 0.8 or not view.can_attack(ship, target):
        go_home(ctx, ship)
        return
    if go_to(ctx, ship, target, adjacent=True) == "arrived" and alive(ctx, ship):
        strike_adjacent(ctx, ship, minimum * 0.8, only=target)


def _bombard(ctx: Context, ship: Unit, mission: Mission) -> None:
    """Shells the defenders of an enemy coastal city."""
    view = ctx.view
    target = view.map.tile(mission.x, mission.y)
    if go_to(ctx, ship, target, adjacent=True) != "arrived" or not alive(ctx, ship):
        return
    if not strike_adjacent(ctx, ship, ctx.ai("military", "attack_min_odds"), only=target):
        sentry(ctx, ship)
