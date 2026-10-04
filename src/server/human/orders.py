"""What the person may ask of a unit: the orders open to it, and what a move would do.

The client shows these and contains no rule of its own. Everything is read through the
player's view, so nothing the player does not know leaks out.
"""
from __future__ import annotations

from typing import Optional

from ..ai import pathfinding
from ..engine.model.entities import (ORDER_FORTIFIED, ORDER_FORTIFY, ORDER_NONE, ORDER_SENTRY,
                                     WORK_ORDERS, Unit)
from ..engine.model.worldmap import Tile
from ..engine.view import PlayerView
from .controller import HumanController

# Terrain work that changes the terrain itself names what the tile becomes.
TERRAIN_WORK = {"irrigate": "irrigation", "mine": "mine"}


def unit_orders(view: PlayerView, controller: HumanController, unit: Unit) -> list[dict]:
    """The orders the unit can take now, most specific first: [{"id": ..., ...}]."""
    rules = view.rules
    definition = rules.units[unit.type]
    tile = view.tile_of(unit)
    terrain = rules.terrains[tile.terrain]
    city = view.my_city_at(unit.x, unit.y)
    can_act = unit.moves_left > 0
    orders: list[dict] = []

    def add(order_id: str, **extra) -> None:
        orders.append({"id": order_id, **extra})

    if controller.task(unit.id):
        add("stop")
    elif unit.order != ORDER_NONE:
        add("wake")

    if definition.can("found_city") and can_act and city is None and view.can_found_city(tile):
        add("found_city")
    if view.can_join_city(unit):
        add("join_city", city=city.name)
    if can_act:
        for order in WORK_ORDERS:
            turns = view.work_turns(unit, order)
            if turns is None or unit.order == order:
                continue
            work = getattr(terrain, TERRAIN_WORK[order], None) if order in TERRAIN_WORK else None
            becomes = rules.terrains[work.becomes].name if work and work.becomes else None
            add(order, turns=turns, becomes=becomes)
    if definition.can("trade"):
        if city is not None and view.wonder_in_progress(city):
            add("help_wonder", city=city.name)
        partner = view.trade_route_target(unit)
        if partner is not None:
            add("trade_route", city=partner.name)

    if unit.aboard is None and view.is_land(tile):
        ship = view.transport_at(unit, tile)
        if ship is not None:
            add("board", ship=ship.id)
    if unit.aboard is not None and view.is_land(tile):
        add("disembark")

    add("goto")
    if definition.domain == "land" and unit.aboard is None \
            and unit.order not in (ORDER_FORTIFY, ORDER_FORTIFIED):
        add("fortify")
    if unit.order != ORDER_SENTRY:
        add("sentry")
    if definition.domain != "air":
        add("explore")
    if definition.can("terraform"):
        add("auto_work")
    if city is not None and unit.home_city != city.id:
        add("home", city=city.name)
    add("disband")
    return orders


def route(view: PlayerView, unit: Unit, goal: Tile) -> Optional[list[tuple[Tile, int]]]:
    """The way to the goal the player knows, each tile with the turn it is reached on
    (1 = this turn, or the next one for a unit that cannot move any more)."""
    path = pathfinding.find_path(view, unit, goal)
    if path is None:
        return None
    full = view.full_moves(unit)
    left = unit.moves_left if unit.moves_left > 0 else full
    here = view.tile_of(unit)
    turn = 1
    steps = []
    for tile in path:
        if left <= 0:
            turn, left = turn + 1, full
        left = max(0, left - view.move_cost(unit, here, tile))
        steps.append((tile, turn))
        here = tile
    return steps


def preview(view: PlayerView, unit: Unit, target: Tile) -> dict:
    """What sending the unit to this tile would do: a fight and its odds, a plain step,
    a refusal and its reason, or the route to a distant tile."""
    here = view.tile_of(unit)
    result: dict = {"unit": unit.id, "x": target.x, "y": target.y}
    if target is here:
        return {**result, "kind": "none"}

    if target in view.map.neighbors(here):
        reason = view.why_cannot_enter(unit, target)
        details = view.attack_details(unit, target)
        if details is not None:
            return {**result, "kind": "attack", "reason": reason, **details}
        if reason is not None:
            return {**result, "kind": "refused", "reason": reason}
        memory = view.foreign_city_at(target)
        if memory is not None and view.at_war(memory.owner):
            return {**result, "kind": "capture", "city": memory.name}
        if not view.is_land(target) and view.rules.units[unit.type].domain == "land":
            return {**result, "kind": "board"}
        return {**result, "kind": "move"}

    steps = route(view, unit, target)
    if not steps:
        return {**result, "kind": "no_route"}
    return {**result, "kind": "route", "turns": steps[-1][1],
            "steps": [[tile.x, tile.y, turn] for tile, turn in steps]}
