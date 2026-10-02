"""Unit movement on land, at sea and in the air; zones of control, orders, terrain work.

Source: OpenCivOne CheckPlayerTurn.cs (movement cost around line 1599, boarding and attack
restrictions around line 1400, ships carrying units around line 1800, fuel and ships lost
at sea around line 2370, settler work in the 'i', 'm', 'r', 'f', 'p' commands).

Transport: a land unit that steps onto a ship is `aboard` it and travels with it; it leaves
by stepping onto land. Aircraft land the same way on a carrier. A ship entering a city puts
its passengers ashore.
"""
from __future__ import annotations

from typing import Optional

from .. import effects as fx
from ..mapgen.generator import set_terrain
from ..model.entities import (ORDER_FORTIFIED, ORDER_FORTIFY, ORDER_NONE, ORDER_SENTRY,
                              WORK_ORDERS, Player, Unit)
from ..model.game import Game
from ..model.worldmap import Tile
from . import cities, combat, huts, nuclear, visibility

# Results of a move
MOVED = "moved"
STALLED = "stalled"            # not enough movement left to enter the tile; the turn is spent
ATTACK_WON = "attack_won"
ATTACK_LOST = "attack_lost"
CAPTURED = "captured"
NUKED = "nuked"
ILLEGAL = "illegal"


# ── Costs ─────────────────────────────────────────────────────────────────────

def full_moves(game: Game, unit: Unit) -> int:
    """Movement points of the unit at the start of a turn, in thirds of a move."""
    definition = game.rules.units[unit.type]
    player = game.players[unit.owner]
    # Several wonders giving the same bonus do not add up (Lighthouse, Magellan's Expedition).
    bonus = max((effect.amount for effect in fx.player_effects(game, player, "unit_moves")
                 if effect.domain == definition.domain), default=0)
    return (definition.moves + bonus) * game.rules.game.movement.points_per_move


def move_cost(game: Game, unit: Unit, origin: Tile, target: Tile) -> int:
    """Movement points needed to step from origin to target."""
    settings = game.rules.game.movement
    if game.rules.units[unit.type].domain != "land":
        return settings.points_per_move
    if origin.railroad and target.railroad:
        return settings.railroad_cost
    if origin.road and target.road:
        return settings.road_cost
    return game.terrain(target).move_cost * settings.points_per_move


# ── Zones of control ──────────────────────────────────────────────────────────

def in_enemy_zone(game: Game, player_id: int, tile: Tile) -> bool:
    """True if an enemy land unit stands next to the tile."""
    for other in game.map.neighbors(tile):
        if not other.unit_ids or not game.terrain(other).is_land:
            continue
        owner = game.units[other.unit_ids[0]].owner
        if owner != player_id and game.at_war(player_id, owner):
            return True
    return False


# ── Transport ─────────────────────────────────────────────────────────────────

def room_left(game: Game, ship: Unit) -> int:
    """Units the ship can still take aboard."""
    return game.rules.units[ship.type].capacity - len(game.cargo_of(ship))


def transport_at(game: Game, unit: Unit, tile: Tile) -> Optional[Unit]:
    """A ship of the unit's owner on the tile that can take the unit aboard."""
    domain = game.rules.units[unit.type].domain
    for other in game.units_at(tile):
        if other.owner == unit.owner and other.id != unit.id \
                and game.rules.units[other.type].carries == domain and room_left(game, other) > 0:
            return other
    return None


def board(game: Game, unit: Unit, ship: Unit) -> bool:
    """The unit goes aboard a ship standing on the same tile (in port, usually)."""
    if unit.owner != ship.owner or unit.pos != ship.pos or unit.aboard == ship.id:
        return False
    if game.rules.units[ship.type].carries != game.rules.units[unit.type].domain \
            or room_left(game, ship) <= 0:
        return False
    cancel_order(unit)
    unit.aboard = ship.id
    unit.order = ORDER_SENTRY
    return True


def disembark(game: Game, unit: Unit) -> bool:
    """The unit leaves its ship without moving: only possible where it can stand (a city)."""
    if unit.aboard is None or not game.terrain(game.tile_of(unit)).is_land:
        return False
    unit.aboard = None
    return True


# ── Legality ──────────────────────────────────────────────────────────────────

def why_cannot_enter(game: Game, unit: Unit, target: Tile) -> Optional[str]:
    """None if the unit may step, attack or capture into the tile, else the reason."""
    definition = game.rules.units[unit.type]
    origin = game.tile_of(unit)
    if target is origin or target not in game.map.neighbors(origin):
        return "not adjacent"
    if unit.moves_left <= 0:
        return "no movement left"
    terrain = game.terrain(target)

    occupant = game.tile_owner(target)
    if occupant is not None and occupant != unit.owner:
        if not game.at_war(unit.owner, occupant):
            return "at peace with the occupant"
        if definition.can("nuclear"):
            return None
        if target.unit_ids:
            return combat.why_cannot_attack(game, unit, target)
        if definition.attack <= 0 or definition.domain != "land":
            return "unit cannot capture a city"
        return None

    if definition.domain == "land":
        if not terrain.is_land:
            if transport_at(game, unit, target) is None:
                return "land units cannot enter the sea"
        elif unit.aboard is None and not definition.can("ignore_zoc") and occupant is None:
            if in_enemy_zone(game, unit.owner, origin) and in_enemy_zone(game, unit.owner, target):
                return "zone of control"
    elif definition.domain == "sea":
        if terrain.is_land and target.city_id is None:
            return "ships cannot enter land"
    return None


def can_enter(game: Game, unit: Unit, target: Tile) -> bool:
    return why_cannot_enter(game, unit, target) is None


# ── Moving ────────────────────────────────────────────────────────────────────

def move_unit(game: Game, unit: Unit, target: Tile) -> str:
    """Moves, attacks or captures, depending on what stands on the target tile."""
    if why_cannot_enter(game, unit, target) is not None:
        return ILLEGAL
    origin = game.tile_of(unit)
    occupant = game.tile_owner(target)
    cancel_order(unit)

    definition = game.rules.units[unit.type]
    hostile = occupant is not None and occupant != unit.owner
    if hostile and definition.can("nuclear"):
        nuclear.strike(game, unit, target)
        return NUKED
    if hostile and target.unit_ids:
        won = combat.attack(game, unit, target)
        return ATTACK_WON if won else ATTACK_LOST

    cost = move_cost(game, unit, origin, target)
    one_move = game.rules.game.movement.points_per_move
    if unit.moves_left < cost:
        # Entering terrain that costs more than what is left succeeds only sometimes,
        # except with exactly one full move left (so slow units can always advance).
        if unit.moves_left != one_move and game.rng.randrange(cost) > unit.moves_left:
            unit.moves_left = 0
            return STALLED
    unit.moves_left = max(0, unit.moves_left - cost)
    _relocate(game, unit, target)

    if hostile and target.city_id is not None:
        cities.capture_city(game, unit, game.cities[target.city_id])
        unit.moves_left = 0
        return CAPTURED
    if target.hut and definition.domain == "land":
        huts.enter_hut(game, unit, target)
    return MOVED


def _relocate(game: Game, unit: Unit, target: Tile) -> None:
    """Puts the unit on the tile, with what it carries, and settles who is aboard what."""
    definition = game.rules.units[unit.type]
    passengers = game.cargo_of(unit) if definition.capacity else []
    unit.aboard = None
    game.place_unit(unit, target.x, target.y)
    for passenger in passengers:
        game.place_unit(passenger, target.x, target.y)
    in_own_city = target.city_id is not None and game.cities[target.city_id].owner == unit.owner
    on_land = game.terrain(target).is_land

    if definition.domain == "land" and not on_land:
        unit.aboard = transport_at(game, unit, target).id
        unit.order = ORDER_SENTRY
    elif definition.domain == "air":
        carrier = None if in_own_city else transport_at(game, unit, target)
        if carrier is not None:
            unit.aboard = carrier.id
        if in_own_city or carrier is not None:
            unit.moves_left = 0                 # landed: the flight is over for this turn
    elif on_land:
        for passenger in passengers:            # a ship in port puts everybody ashore
            passenger.aboard = None
    visibility.reveal_unit(game, unit)


# ── Orders ────────────────────────────────────────────────────────────────────

def cancel_order(unit: Unit) -> None:
    unit.order = ORDER_NONE
    unit.work = 0


def work_turns(game: Game, unit: Unit, order: str) -> Optional[int]:
    """Turns the work takes on the unit's tile, or None if it is not possible there."""
    if not game.rules.units[unit.type].can("terraform"):
        return None
    return work_turns_at(game, game.players[unit.owner], game.tile_of(unit), order)


def work_turns_at(game: Game, player: Player, tile: Tile, order: str) -> Optional[int]:
    """Turns a terraforming unit of the player would need for this work on this tile."""
    terrain = game.terrain(tile)
    settings = game.rules.game.movement
    if not terrain.is_land:
        return None
    if order == "road":
        if tile.road:
            return None
        needed = settings.road_requires_tech_on.get(tile.terrain)
        if needed is not None and needed not in player.techs:
            return None
        return settings.road_turns_factor * terrain.move_cost + 1
    if order == "railroad":
        if not tile.road or tile.railroad or tile.city_id is not None:
            return None
        if settings.railroad_tech not in player.techs:
            return None
        return settings.railroad_turns_factor * terrain.move_cost + 1
    if order == "irrigate":
        work = terrain.irrigation
        if work is None or tile.city_id is not None:
            return None
        if work.becomes is None and tile.irrigation:
            return None
        if work.needs_water and not has_water_source(game, tile):
            return None
        return work.turns
    if order == "mine":
        work = terrain.mine
        if work is None or tile.city_id is not None:
            return None
        if work.becomes is None and tile.mine:
            return None
        return work.turns
    if order == "fortress":
        if tile.fortress or tile.city_id is not None:
            return None
        if settings.fortress_tech not in player.techs:
            return None
        return terrain.move_cost + settings.fortress_turns_base
    if order == "clean":
        return settings.pollution_clean_turns if tile.pollution else None
    return None


def has_water_source(game: Game, tile: Tile) -> bool:
    """Irrigation needs water next to the tile: sea, river or an irrigated field."""
    for other in game.map.cardinal_neighbors(tile):
        if other.city_id is not None:
            continue
        terrain = game.terrain(other)
        if not terrain.is_land or terrain.is_water_source or other.irrigation:
            return True
    return False


def set_order(game: Game, unit: Unit, order: str) -> bool:
    if order == ORDER_NONE:
        cancel_order(unit)
        return True
    if order in (ORDER_FORTIFY, ORDER_SENTRY):
        if order == ORDER_FORTIFY and game.rules.units[unit.type].domain != "land":
            return False
        if unit.order == ORDER_FORTIFIED and order == ORDER_FORTIFY:
            return True
        unit.order = order
        unit.work = 0
        unit.moves_left = 0
        return True
    if order in WORK_ORDERS:
        if unit.moves_left <= 0 or work_turns(game, unit, order) is None:
            return False
        if unit.order != order:
            unit.order = order
            unit.work = 0
        _work_one_turn(game, unit)
        return True
    return False


def _work_one_turn(game: Game, unit: Unit) -> None:
    turns = work_turns(game, unit, unit.order)
    if turns is None:
        cancel_order(unit)
        return
    unit.work += 1
    unit.moves_left = 0
    if unit.work >= turns:
        _finish_work(game, unit)


def _finish_work(game: Game, unit: Unit) -> None:
    tile = game.tile_of(unit)
    terrain = game.terrain(tile)
    order = unit.order
    if order == "road":
        tile.road = True
    elif order == "railroad":
        tile.railroad = True
    elif order == "fortress":
        tile.fortress = True
    elif order == "clean":
        tile.pollution = False
    elif order == "irrigate":
        if terrain.irrigation.becomes is not None:
            set_terrain(game.map, tile, terrain.irrigation.becomes)
        else:
            tile.irrigation = True
            tile.mine = False
    elif order == "mine":
        if terrain.mine.becomes is not None:
            set_terrain(game.map, tile, terrain.mine.becomes)
        else:
            tile.mine = True
            tile.irrigation = False
    game.mark_tile(tile)
    cancel_order(unit)


def start_turn(game: Game, player: Player) -> None:
    """Restores movement and carries on with the orders given on previous turns."""
    for unit in game.player_units(player.id):
        unit.moves_left = full_moves(game, unit)
        if unit.order == ORDER_FORTIFY:
            unit.order = ORDER_FORTIFIED
        if unit.order in WORK_ORDERS:
            _work_one_turn(game, unit)


def end_turn(game: Game, player: Player) -> None:
    """Aircraft out of fuel crash; ships that cannot leave the coast may be lost at sea."""
    settings = game.rules.game.movement
    for unit in sorted(game.player_units(player.id), key=lambda u: u.id):
        if unit.id not in game.units:
            continue                            # went down with its ship
        definition = game.rules.units[unit.type]
        tile = game.tile_of(unit)
        if definition.domain == "air":
            in_city = tile.city_id is not None and game.cities[tile.city_id].owner == player.id
            if in_city or unit.aboard is not None:
                unit.fuel = definition.fuel
                continue
            unit.fuel -= 1
            if unit.fuel <= 0:
                game.remove_unit(unit)
                game.emit("unit_lost", f"{player.civ.name} {definition.name} runs out of fuel "
                          f"and crashes.", player=player.id, x=tile.x, y=tile.y, unit=unit.type)
        elif definition.can("coastal") and not game.terrain(tile).is_land:
            near_land = any(game.terrain(t).is_land for t in game.map.neighbors(tile))
            if not near_land and game.rng.random() < settings.lost_at_sea_chance:
                game.remove_unit(unit)
                game.emit("unit_lost", f"{player.civ.name} {definition.name} is lost at sea.",
                          player=player.id, x=tile.x, y=tile.y, unit=unit.type)


def disband(game: Game, unit: Unit) -> None:
    game.remove_unit(unit)


def join_city(game: Game, unit: Unit) -> bool:
    """A Settlers unit adds itself to the population of the city it stands in."""
    from . import city as city_rules
    definition = game.rules.units[unit.type]
    city = game.city_at(unit.x, unit.y)
    if city is None or city.owner != unit.owner or not definition.pop_cost:
        return False
    limit = city_rules.max_size(game, city)
    if limit is not None and city.size + definition.pop_cost > limit:
        return False
    city.size += definition.pop_cost
    game.remove_unit(unit)
    city_rules.auto_arrange(game, city)
    return True


def rehome(game: Game, unit: Unit) -> bool:
    """Makes the city the unit stands in its new home."""
    city = game.city_at(unit.x, unit.y)
    if city is None or city.owner != unit.owner:
        return False
    game.set_home(unit, city.id)
    return True
