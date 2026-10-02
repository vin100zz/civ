"""Caravans: help with wonders and trade routes.

Source for the trade route income: OpenCivOne CityWorker.cs (around line 1325). The one-off
payment on arrival follows the well-known Civ 1 rule: (distance + 10) x (trade of both
cities) / 24.
"""
from __future__ import annotations

from typing import Optional

from ..model.entities import City, Unit
from ..model.game import Game


def help_build_wonder(game: Game, unit: Unit) -> bool:
    definition = game.rules.units[unit.type]
    city = game.city_at(unit.x, unit.y)
    if not definition.can("trade") or city is None or city.owner != unit.owner:
        return False
    item = city.production
    if item is None or item.kind != "building" or not game.rules.buildings[item.id].wonder:
        return False
    city.shields += definition.cost
    game.remove_unit(unit)
    return True


def route_target(game: Game, unit: Unit) -> Optional[City]:
    """The city a caravan could open a route with from where it stands, if any.

    One of its owner's cities when it stands in it, or a foreign city next to it
    (units cannot enter the cities of another civilization in peace time).
    """
    definition = game.rules.units[unit.type]
    if not definition.can("trade") or unit.home_city is None:
        return None
    home = game.cities.get(unit.home_city)
    if home is None:
        return None
    candidates = []
    here = game.city_at(unit.x, unit.y)
    if here is not None:
        candidates.append(here)
    for tile in game.map.neighbors(game.tile_of(unit)):
        if tile.city_id is not None:
            candidates.append(game.cities[tile.city_id])
    minimum = game.rules.game.city.trade_route_min_distance
    for city in candidates:
        if city.id == home.id or city.id in home.trade_routes:
            continue
        if city.owner != unit.owner and game.at_war(unit.owner, city.owner):
            continue
        if game.map.distance(home.x, home.y, city.x, city.y) >= minimum:
            return city
    return None


def establish_route(game: Game, unit: Unit) -> bool:
    city = route_target(game, unit)
    if city is None:
        return False
    home = game.cities[unit.home_city]
    player = game.players[unit.owner]
    distance = game.map.distance(home.x, home.y, city.x, city.y)
    bonus = (distance + 10) * (home.stats.trade + city.stats.trade) // 24
    player.gold += bonus
    home.trade_routes.append(city.id)
    limit = game.rules.game.city.max_trade_routes
    if len(home.trade_routes) > limit:
        # Keep the most profitable routes.
        home.trade_routes.sort(key=lambda cid: -game.cities[cid].base_trade
                               if cid in game.cities else 0)
        home.trade_routes = home.trade_routes[:limit]
    game.remove_unit(unit)
    game.emit("trade_route", f"Trade route between {home.name} and {city.name} (+{bonus} gold).",
              player=player.id, x=city.x, y=city.y, city=home.id)
    return True
