"""Life of a city: founding, the yearly cycle, capture and destruction.

Source: OpenCivOne CityWorker.cs (F0_1d12_0045_ProcessCityState) for the yearly cycle.
"""
from __future__ import annotations

from typing import Optional

from .. import effects as fx
from ..model.entities import City, Player, Unit
from ..model.game import Game
from ..model.worldmap import Tile
from . import city as city_rules
from . import government, nuclear, pollution, production, research, spaceship, visibility


# ── Founding ──────────────────────────────────────────────────────────────────

def can_found_city(game: Game, tile: Tile) -> bool:
    if not game.terrain(tile).is_land or tile.city_id is not None:
        return False
    min_distance = game.rules.game.city.min_distance
    for other in game.cities.values():
        if game.map.steps(tile.x, tile.y, other.x, other.y) < min_distance:
            return False
    return True


def next_city_name(game: Game, player: Player) -> str:
    names = player.civ.city_names
    used = {c.name for c in game.cities.values()}
    for _ in range(len(names)):
        name = names[player.next_city_name % len(names)]
        player.next_city_name += 1
        if name not in used:
            return name
    index = player.next_city_name
    player.next_city_name += 1
    return f"{names[index % len(names)]} {index // len(names) + 1}"


def found_city(game: Game, player: Player, tile: Tile, *, size: int = 1,
               quiet: bool = False) -> City:
    city = City(id=game.new_city_id(), name=next_city_name(game, player), owner=player.id,
                x=tile.x, y=tile.y, size=size, founded_turn=game.turn, founder=player.id)
    game.cities[city.id] = city
    tile.city_id = city.id
    tile.hut = False
    tile.road = True
    tile.irrigation = False
    tile.mine = False
    tile.fortress = False
    game.mark_tile(tile)
    if player.capital_id is None and not player.is_barbarian:
        palace = _capital_building(game)
        if palace is not None:
            city.buildings.add(palace)
            player.capital_id = city.id
    city_rules.auto_arrange(game, city)
    city.stats = city_rules.compute_city(game, city)
    visibility.reveal_city(game, city)
    for other in game.players:
        if other.id != player.id and other.alive and visibility.can_see(other, tile):
            visibility.remember_city(game, other, city)
    if not quiet:
        game.emit("city_founded", f"The {player.civ.nation} found {city.name}.",
                  player=player.id, x=city.x, y=city.y, city=city.id)
    return city


def _capital_building(game: Game) -> Optional[str]:
    for building in game.rules.buildings.values():
        if building.has_effect("capital"):
            return building.id
    return None


# ── The yearly cycle ──────────────────────────────────────────────────────────

def process_city(game: Game, city: City) -> None:
    """One turn of a city: food, production, money, science, mood."""
    player = game.players[city.owner]
    government_def = game.government(player)
    settings = game.rules.game.city
    city.bought_this_turn = False
    city.sold_this_turn = False

    city_rules.ensure_valid_assignment(game, city)
    stats = city_rules.compute_city(game, city)
    was_in_disorder = city.disorder

    # Mood first: a city in disorder produces nothing and pays no taxes.
    if stats.disorder and not was_in_disorder:
        # Citizens become entertainers until order returns (the mayor's reflex).
        city_rules.auto_arrange(game, city)
        stats = city_rules.compute_city(game, city)
    city.disorder = stats.disorder
    if city.disorder and not was_in_disorder:
        game.emit("disorder", f"Civil disorder in {city.name}.",
                  player=player.id, x=city.x, y=city.y, city=city.id)
    elif was_in_disorder and not city.disorder:
        game.emit("order", f"Order restored in {city.name}.",
                  player=player.id, x=city.x, y=city.y, city=city.id)
    if city.disorder and was_in_disorder and government_def.falls_on_disorder:
        government.collapse(game, player)
    if nuclear.maybe_meltdown(game, city):
        stats = city_rules.compute_city(game, city)

    # Food.
    city.food += stats.food_surplus
    if city.food < 0:
        _starve(game, city)
        if city.id not in game.cities:
            return
    elif city.food >= stats.food_box:
        _grow(game, city)

    # Shields.
    if stats.shield_surplus < 0:
        _disband_unsupported(game, city, -stats.shield_surplus)
        stats = city_rules.compute_city(game, city)
    if not city.disorder or settings.disorder_shields:
        city.shields += max(0, stats.shield_surplus)
    city.last_completed = production.complete_if_ready(game, city)
    if city.id not in game.cities:
        return

    # Money and science.
    if not city.disorder:
        player.gold += stats.tax
        player.income += stats.tax
    research.add_science(game, player, stats.science)
    player.science_income += stats.science
    if government_def.collects_taxes:
        _pay_maintenance(game, city)

    # Celebration ("We love the king day").
    if stats.celebrating and not city.disorder:
        if city.celebrating and government_def.rapture_growth and stats.food_surplus > 0:
            limit = city_rules.max_size(game, city)
            if limit is None or city.size < limit:
                city.size += 1
                city_rules.auto_arrange(game, city)
        city.celebrating = True
    else:
        city.celebrating = False

    city.stats = city_rules.compute_city(game, city)
    city.base_trade = city.stats.base_trade
    pollution.pollute(game, city)


def _grow(game: Game, city: City) -> None:
    settings = game.rules.game.city
    limit = city_rules.max_size(game, city)
    keep = max((e.percent for e in fx.city_effects(game, city) if e.type == "food_box_keep"),
               default=0)
    if limit is not None and city.size >= limit:
        city.food = int((city.size + 1) * settings.food_box_per_size * keep / 100)
        return
    city.size += 1
    city.food = int((city.size + 1) * settings.food_box_per_size * keep / 100)
    city_rules.auto_arrange(game, city)


def _starve(game: Game, city: City) -> None:
    """Food box empty: a Settlers unit is lost if the city supports one, else a citizen."""
    player = game.players[city.owner]
    city.food = 0
    for unit in game.units_of_city(city):
        if game.rules.units[unit.type].can("found_city"):
            game.remove_unit(unit)
            game.emit("famine", f"Famine in {city.name}: Settlers lost.",
                      player=player.id, x=city.x, y=city.y, city=city.id)
            return
    city.size -= 1
    game.emit("famine", f"Famine in {city.name}.", player=player.id, x=city.x, y=city.y,
              city=city.id)
    if city.size <= 0:
        destroy_city(game, city, "starved")
    else:
        city_rules.auto_arrange(game, city)


def _disband_unsupported(game: Game, city: City, shortage: int) -> None:
    """The city cannot pay for its units: the farthest ones are disbanded."""
    player = game.players[city.owner]
    units = [u for u in game.units_of_city(city) if game.rules.units[u.type].needs_support]
    units.sort(key=lambda u: (-game.map.distance(city.x, city.y, u.x, u.y), u.id))
    for unit in units[:shortage]:
        name = game.rules.units[unit.type].name
        game.remove_unit(unit)
        game.emit("disband", f"{city.name} cannot support {name}: unit disbanded.",
                  player=player.id, x=city.x, y=city.y, city=city.id)


def _pay_maintenance(game: Game, city: City) -> None:
    """Building upkeep. A building the treasury cannot pay for is sold."""
    player = game.players[city.owner]
    for building_id in sorted(city.buildings):
        cost = city_rules.building_upkeep(game, city, building_id)
        if cost == 0:
            continue
        player.gold -= cost
        player.expenses += cost
        if player.gold < 0:
            building = game.rules.buildings[building_id]
            if building.wonder or building.has_effect("capital"):
                player.gold = 0
                continue
            city.buildings.discard(building_id)
            player.gold = building.cost
            game.emit("sold", f"{city.name} cannot maintain {building.name}: sold.",
                      player=player.id, x=city.x, y=city.y, city=city.id)


# ── Capture and destruction ───────────────────────────────────────────────────

def destroy_city(game: Game, city: City, reason: str) -> None:
    player = game.players[city.owner]
    city_rules.release_tiles(game, city)
    tile = game.tile_of(city)
    tile.city_id = None
    game.mark_tile(tile)
    for unit in list(game.units_of_city(city)):
        game.set_home(unit, None)
    for wonder_id in [w for w, c in game.wonders.items() if c == city.id]:
        del game.wonders[wonder_id]
    for other in game.cities.values():
        if city.id in other.trade_routes:
            other.trade_routes.remove(city.id)
    del game.cities[city.id]
    if player.capital_id == city.id:
        player.capital_id = None
        spaceship.lose(game, player)
    for other in game.players:
        other.known_cities.pop(city.id, None)
    game.emit("city_destroyed", f"{city.name} is destroyed.", player=player.id,
              x=city.x, y=city.y, reason=reason)
    check_elimination(game, player)


def capture_city(game: Game, unit: Unit, city: City) -> None:
    """A unit walks into an undefended enemy city."""
    settings = game.rules.game
    winner = game.players[unit.owner]
    loser = game.players[city.owner]

    # Plunder: a share of the treasury in proportion to the city's population.
    population = sum(c.size for c in game.player_cities(loser.id)) or 1
    plunder = loser.gold * city.size // population
    loser.gold -= plunder
    winner.gold += plunder

    game.emit("city_captured",
              f"The {winner.civ.nation} capture {city.name} from the {loser.civ.nation}"
              f"{f' and plunder {plunder} gold' if plunder else ''}.",
              player=winner.id, other=loser.id, x=city.x, y=city.y, city=city.id)

    if settings.research.capture_steals_tech and not winner.is_barbarian:
        research.steal_tech(game, winner, loser)

    # Units supported by the city are lost with it.
    for supported in list(game.units_of_city(city)):
        game.remove_unit(supported)

    city.size -= 1
    if city.size <= 0:
        destroy_city(game, city, "captured")
        return

    city_rules.release_tiles(game, city)
    for building_id in sorted(city.buildings):
        building = game.rules.buildings[building_id]
        if building.wonder:
            continue
        if building.has_effect("capital") or game.rng.random() < settings.city.capture_building_loss:
            city.buildings.discard(building_id)
    if loser.capital_id == city.id:
        loser.capital_id = None
        spaceship.lose(game, loser)
    city.owner = winner.id
    city.production = None
    city.shields = 0
    city.disorder = False
    city.celebrating = False
    city.trade_routes = []
    for other in game.cities.values():
        if city.id in other.trade_routes:
            other.trade_routes.remove(city.id)
    winner.known_cities.pop(city.id, None)
    city_rules.auto_arrange(game, city)
    city.stats = city_rules.compute_city(game, city)
    visibility.reveal_city(game, city)
    visibility.remember_city(game, loser, city)
    check_elimination(game, loser)


def check_elimination(game: Game, player: Player) -> None:
    """A civilization with no city and no Settlers is destroyed."""
    if not player.alive or player.is_barbarian:
        return
    if game.player_cities(player.id):
        return
    if any(game.rules.units[u.type].can("found_city") for u in game.player_units(player.id)):
        return
    player.alive = False
    player.destroyed_turn = game.turn
    for unit in game.player_units(player.id):
        game.remove_unit(unit)
    game.emit("civ_destroyed", f"The {player.civ.name} civilization is destroyed.",
              player=player.id)
