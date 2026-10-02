"""Everything a player can do, as commands validated and applied by the engine.

An AI today, a human tomorrow: both change the game only through `apply`. A refused action
leaves the game untouched and says why.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .model.entities import Item
from .model.game import Game
from .systems import cities, city as city_rules, diplomacy, government, movement, production
from .systems import research, spaceship, trade


# ── Commands ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MoveUnit:
    """Step to an adjacent tile; attacks or captures if an enemy holds it.

    Stepping onto one of your ships boards it; stepping from a ship onto land leaves it.
    """
    unit_id: int
    x: int
    y: int


@dataclass(frozen=True)
class Board:
    """Go aboard a ship standing on the same tile (in a port)."""
    unit_id: int
    ship_id: int


@dataclass(frozen=True)
class Disembark:
    """Leave the ship without moving (in a port)."""
    unit_id: int


@dataclass(frozen=True)
class FoundCity:
    unit_id: int


@dataclass(frozen=True)
class JoinCity:
    unit_id: int


@dataclass(frozen=True)
class SetOrder:
    """order: none, fortify, sentry, road, railroad, irrigate, mine, fortress, clean."""
    unit_id: int
    order: str


@dataclass(frozen=True)
class Disband:
    unit_id: int


@dataclass(frozen=True)
class Rehome:
    unit_id: int


@dataclass(frozen=True)
class HelpBuildWonder:
    """A caravan adds its cost to the wonder under construction in the city it stands in."""
    unit_id: int


@dataclass(frozen=True)
class EstablishTradeRoute:
    """A caravan opens a trade route between its home city and the city it stands in."""
    unit_id: int


@dataclass(frozen=True)
class SetProduction:
    city_id: int
    kind: str
    id: str


@dataclass(frozen=True)
class Buy:
    city_id: int


@dataclass(frozen=True)
class ArrangeWorkers:
    """Lets the city place its citizens on the best tiles again."""
    city_id: int


@dataclass(frozen=True)
class SetResearch:
    tech_id: str


@dataclass(frozen=True)
class SetRates:
    tax: int
    luxury: int
    science: int


@dataclass(frozen=True)
class Revolution:
    government: str


@dataclass(frozen=True)
class DeclareWar:
    target: int


@dataclass(frozen=True)
class ProposePeace:
    target: int


@dataclass(frozen=True)
class LaunchSpaceship:
    """Sends the spaceship to Alpha Centauri with the parts built so far."""


Action = Union[MoveUnit, Board, Disembark, FoundCity, JoinCity, SetOrder, Disband, Rehome,
               HelpBuildWonder, EstablishTradeRoute, SetProduction, Buy, ArrangeWorkers,
               SetResearch, SetRates, Revolution, DeclareWar, ProposePeace, LaunchSpaceship]


@dataclass(frozen=True)
class Result:
    ok: bool
    outcome: str = ""       # for moves: moved, stalled, attack_won, attack_lost, captured, nuked
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


def _refuse(reason: str) -> Result:
    return Result(False, reason=reason)


OK = Result(True)


# ── Dispatcher ────────────────────────────────────────────────────────────────

def apply(game: Game, player_id: int, action: Action) -> Result:
    if game.current_player != player_id:
        return _refuse("not this player's turn")
    player = game.players[player_id]
    if not player.alive:
        return _refuse("player is dead")
    handler = _HANDLERS.get(type(action))
    if handler is None:
        return _refuse(f"unknown action {type(action).__name__}")
    return handler(game, player, action)


def _own_unit(game: Game, player, unit_id: int):
    unit = game.units.get(unit_id)
    return unit if unit is not None and unit.owner == player.id else None


def _own_city(game: Game, player, city_id: int):
    city = game.cities.get(city_id)
    return city if city is not None and city.owner == player.id else None


def _move_unit(game: Game, player, action: MoveUnit) -> Result:
    unit = _own_unit(game, player, action.unit_id)
    if unit is None:
        return _refuse("no such unit")
    target = game.map.tile(action.x, action.y)
    if target is None:
        return _refuse("off the map")
    reason = movement.why_cannot_enter(game, unit, target)
    if reason is not None:
        return _refuse(reason)
    return Result(True, outcome=movement.move_unit(game, unit, target))


def _board(game: Game, player, action: Board) -> Result:
    unit = _own_unit(game, player, action.unit_id)
    ship = _own_unit(game, player, action.ship_id)
    if unit is None or ship is None:
        return _refuse("no such unit")
    return OK if movement.board(game, unit, ship) else _refuse("cannot board this ship")


def _disembark(game: Game, player, action: Disembark) -> Result:
    unit = _own_unit(game, player, action.unit_id)
    if unit is None:
        return _refuse("no such unit")
    return OK if movement.disembark(game, unit) else _refuse("cannot leave the ship here")


def _found_city(game: Game, player, action: FoundCity) -> Result:
    unit = _own_unit(game, player, action.unit_id)
    if unit is None:
        return _refuse("no such unit")
    if not game.rules.units[unit.type].can("found_city"):
        return _refuse("unit cannot found a city")
    if unit.moves_left <= 0:
        return _refuse("no movement left")
    tile = game.tile_of(unit)
    if not cities.can_found_city(game, tile):
        return _refuse("a city cannot be founded here")
    game.remove_unit(unit)
    cities.found_city(game, player, tile)
    return OK


def _join_city(game: Game, player, action: JoinCity) -> Result:
    unit = _own_unit(game, player, action.unit_id)
    if unit is None:
        return _refuse("no such unit")
    return OK if movement.join_city(game, unit) else _refuse("cannot join a city here")


def _set_order(game: Game, player, action: SetOrder) -> Result:
    unit = _own_unit(game, player, action.unit_id)
    if unit is None:
        return _refuse("no such unit")
    return OK if movement.set_order(game, unit, action.order) else _refuse("order refused")


def _disband(game: Game, player, action: Disband) -> Result:
    unit = _own_unit(game, player, action.unit_id)
    if unit is None:
        return _refuse("no such unit")
    movement.disband(game, unit)
    cities.check_elimination(game, player)
    return OK


def _rehome(game: Game, player, action: Rehome) -> Result:
    unit = _own_unit(game, player, action.unit_id)
    if unit is None:
        return _refuse("no such unit")
    return OK if movement.rehome(game, unit) else _refuse("not in one of your cities")


def _help_wonder(game: Game, player, action: HelpBuildWonder) -> Result:
    unit = _own_unit(game, player, action.unit_id)
    if unit is None:
        return _refuse("no such unit")
    return OK if trade.help_build_wonder(game, unit) else _refuse("no wonder to help here")


def _trade_route(game: Game, player, action: EstablishTradeRoute) -> Result:
    unit = _own_unit(game, player, action.unit_id)
    if unit is None:
        return _refuse("no such unit")
    return OK if trade.establish_route(game, unit) else _refuse("no trade route possible here")


def _set_production(game: Game, player, action: SetProduction) -> Result:
    city = _own_city(game, player, action.city_id)
    if city is None:
        return _refuse("no such city")
    item = Item(action.kind, action.id)
    if not production.can_build(game, city, item):
        return _refuse("the city cannot build that")
    city.production = item
    return OK


def _buy(game: Game, player, action: Buy) -> Result:
    city = _own_city(game, player, action.city_id)
    if city is None:
        return _refuse("no such city")
    return OK if production.buy(game, city) else _refuse("cannot buy")


def _arrange(game: Game, player, action: ArrangeWorkers) -> Result:
    city = _own_city(game, player, action.city_id)
    if city is None:
        return _refuse("no such city")
    city_rules.auto_arrange(game, city)
    return OK


def _set_research(game: Game, player, action: SetResearch) -> Result:
    if action.tech_id not in game.rules.techs:
        return _refuse("no such advance")
    if not research.can_research(game.rules, player, action.tech_id):
        return _refuse("advance not available")
    player.researching = action.tech_id
    return OK


def _set_rates(game: Game, player, action: SetRates) -> Result:
    if government.set_rates(game, player, action.tax, action.luxury, action.science):
        return OK
    return _refuse("invalid rates")


def _revolution(game: Game, player, action: Revolution) -> Result:
    if government.start_revolution(game, player, action.government):
        return OK
    return _refuse("government not available")


def _declare_war(game: Game, player, action: DeclareWar) -> Result:
    if not 0 <= action.target < len(game.players):
        return _refuse("no such player")
    return OK if diplomacy.declare_war(game, player.id, action.target) else _refuse("cannot declare war")


def _propose_peace(game: Game, player, action: ProposePeace) -> Result:
    if not 0 <= action.target < len(game.players):
        return _refuse("no such player")
    target = game.players[action.target]
    controller = game.controllers.get(target.id)

    def accepts() -> bool:
        return controller is not None and controller.accepts_peace(game, target, player.id)

    if diplomacy.propose_peace(game, player.id, target.id, accepts):
        return OK
    return _refuse("peace refused")


def _launch(game: Game, player, action: LaunchSpaceship) -> Result:
    return OK if spaceship.launch(game, player) else _refuse("the spaceship is not ready")


_HANDLERS = {
    MoveUnit: _move_unit, Board: _board, Disembark: _disembark, LaunchSpaceship: _launch,
    FoundCity: _found_city, JoinCity: _join_city, SetOrder: _set_order,
    Disband: _disband, Rehome: _rehome, HelpBuildWonder: _help_wonder,
    EstablishTradeRoute: _trade_route, SetProduction: _set_production, Buy: _buy,
    ArrangeWorkers: _arrange, SetResearch: _set_research, SetRates: _set_rates,
    Revolution: _revolution, DeclareWar: _declare_war, ProposePeace: _propose_peace,
}
