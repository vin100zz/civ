"""What a city can build, what it costs, and what happens when it is finished.

Source: OpenCivOne CityWorker.cs (completion around line 780, purchase at L4bf7).
"""
from __future__ import annotations

from typing import Optional

from .. import effects as fx
from ..model.entities import City, Item, Unit
from ..model.game import Game
from ..rules.schema import BarbarianTier
from . import city as city_rules
from . import research, spaceship, visibility


def barbarian_tier(game: Game) -> Optional[BarbarianTier]:
    """What the barbarians field, by how advanced the world is."""
    best = max((p.tech_count for p in game.civilizations), default=0)
    chosen = None
    for tier in game.rules.game.barbarians.units_by_tech_count:
        if best >= tier.min_techs:
            chosen = tier
    return chosen


def barbarian_unit_types(game: Game) -> tuple[str, ...]:
    tier = barbarian_tier(game)
    return tier.units if tier is not None else ()


def can_build(game: Game, city: City, item: Item) -> bool:
    rules = game.rules
    player = game.players[city.owner]
    if item.kind == "unit":
        unit = rules.units.get(item.id)
        if unit is None or not unit.enabled:
            return False
        if unit.domain not in rules.game.enabled_unit_domains:
            return False
        if player.is_barbarian:
            return item.id in barbarian_unit_types(game)
        if unit.requires is not None and unit.requires not in player.techs:
            return False
        if unit.obsolete_by is not None and unit.obsolete_by in player.techs:
            return False
        if unit.requires_wonder is not None and unit.requires_wonder not in game.wonders:
            return False
        if unit.domain == "sea" and not city_rules.is_coastal(game, city):
            return False
        return True
    if item.kind == "building":
        building = rules.buildings.get(item.id)
        if building is None or not building.enabled or player.is_barbarian:
            return False
        if building.requires is not None and building.requires not in player.techs:
            return False
        if item.id in city.buildings:
            return False
        if building.requires_building is not None \
                and building.requires_building not in city.buildings:
            return False
        if building.requires_wonder is not None and building.requires_wonder not in game.wonders:
            return False
        if building.spaceship_part is not None:
            return spaceship.can_add_part(game, player, building.spaceship_part)
        if building.wonder:
            if item.id in game.wonders:
                return False
            if fx.wonder_obsolete(game, building):
                return False
        return True
    return False


def production_options(game: Game, city: City) -> list[Item]:
    options = [Item("unit", u) for u in game.rules.units]
    options += [Item("building", b) for b in game.rules.buildings]
    return [item for item in options if can_build(game, city, item)]


def item_cost(game: Game, item: Item) -> int:
    if item.kind == "unit":
        return game.rules.units[item.id].cost
    return game.rules.buildings[item.id].cost


def item_name(game: Game, item: Item) -> str:
    if item.kind == "unit":
        return game.rules.units[item.id].name
    return game.rules.buildings[item.id].name


def buy_cost(game: Game, city: City) -> Optional[int]:
    """Gold needed to finish the current production now, or None if nothing to buy."""
    if city.production is None:
        return None
    settings = game.rules.game.production
    remaining = max(0, item_cost(game, city.production) - city.shields)
    if remaining == 0:
        return None
    if city.production.kind == "unit":
        cost = remaining * remaining // settings.buy_unit.quadratic_divisor \
            + remaining * settings.buy_unit.linear
    elif game.rules.buildings[city.production.id].wonder:
        cost = remaining * settings.buy_wonder
    else:
        cost = remaining * settings.buy_building
    if city.shields == 0:
        cost *= settings.buy_from_scratch_multiplier
    return cost


def can_buy(game: Game, city: City) -> bool:
    cost = buy_cost(game, city)
    return (cost is not None and not city.disorder and not city.bought_this_turn
            and game.players[city.owner].gold >= cost)


def buy(game: Game, city: City) -> bool:
    if not can_buy(game, city):
        return False
    player = game.players[city.owner]
    player.gold -= buy_cost(game, city)
    city.shields = item_cost(game, city.production)
    city.bought_this_turn = True
    return True


def can_sell(game: Game, city: City, building_id: str) -> bool:
    """One building per turn, never a wonder nor the palace."""
    building = game.rules.buildings.get(building_id)
    return (building is not None and building_id in city.buildings and not building.wonder
            and not building.has_effect("capital") and not city.sold_this_turn)


def sell(game: Game, city: City, building_id: str) -> bool:
    """Sells a building for one gold per shield it cost (as a forced sale does)."""
    if not can_sell(game, city, building_id):
        return False
    building = game.rules.buildings[building_id]
    player = game.players[city.owner]
    player.gold += building.cost
    city.buildings.discard(building_id)
    city.sold_this_turn = True
    city.stats = city_rules.compute_city(game, city)
    game.emit("sold", f"{city.name} sells its {building.name} for {building.cost} gold.",
              player=player.id, x=city.x, y=city.y, city=city.id)
    return True


def complete_if_ready(game: Game, city: City) -> Optional[Item]:
    """Delivers the current production if the city has gathered enough shields."""
    item = city.production
    if item is None:
        return None
    if not can_build(game, city, item):
        city.production = None          # the wonder was built elsewhere, the unit is obsolete...
        return None
    cost = item_cost(game, item)
    if city.shields < cost:
        return None
    if item.kind == "unit":
        unit_def = game.rules.units[item.id]
        if unit_def.pop_cost and city.size <= unit_def.pop_cost:
            city.shields = cost         # wait until the city is large enough
            return None
        city.shields -= cost
        _deliver_unit(game, city, item.id)
    else:
        city.shields -= cost
        _deliver_building(game, city, item.id)
    return item


def _deliver_unit(game: Game, city: City, unit_id: str) -> Unit:
    unit_def = game.rules.units[unit_id]
    veteran = fx.has_effect(fx.city_effects(game, city), "veteran_units")
    unit = game.add_unit(unit_id, city.owner, city.x, city.y, veteran=veteran, home_city=city.id)
    if unit_def.pop_cost:
        city.size -= unit_def.pop_cost
        city_rules.auto_arrange(game, city)
    visibility.reveal_unit(game, unit)
    return unit


def _deliver_building(game: Game, city: City, building_id: str) -> None:
    building = game.rules.buildings[building_id]
    player = game.players[city.owner]
    if building.spaceship_part is not None:
        spaceship.add_part(game, player, building.spaceship_part)
        game.emit("spaceship_part", f"{city.name} builds a {building.name}.",
                  player=player.id, x=city.x, y=city.y, building=building_id, city=city.id)
        return
    if building.has_effect("capital"):
        for other in game.player_cities(city.owner):
            for existing in list(other.buildings):
                if game.rules.buildings[existing].has_effect("capital"):
                    other.buildings.discard(existing)
        player.capital_id = city.id
    city.buildings.add(building_id)
    if building.wonder:
        game.wonders[building_id] = city.id
        game.emit("wonder", f"{city.name} ({player.civ.name}) completes {building.name}.",
                  player=player.id, x=city.x, y=city.y, wonder=building_id, city=city.id)
        for effect in building.effects:
            if effect.type == "free_techs":
                for _ in range(effect.count):
                    research.give_free_tech(game, player, "wonder")
            elif effect.type == "reveal_map":
                visibility.reveal_world(game, player)
        for other in game.cities.values():
            if other.id != city.id and other.production == Item("building", building_id):
                other.production = None
    else:
        game.emit("building", f"{city.name} builds {building.name}.",
                  player=player.id, x=city.x, y=city.y, building=building_id, city=city.id)
