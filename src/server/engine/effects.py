"""Effects of buildings and wonders.

Buildings and wonders declare typed effects in the config. The rules code never tests for
a building by name: it asks this module which effects apply to a city or to a player.
"""
from __future__ import annotations

from typing import Optional

from .model.entities import City, Player
from .model.game import Game
from .rules.schema import BuildingDef, Effect


def wonder_obsolete(game: Game, wonder: BuildingDef) -> bool:
    """A wonder stops working once any living civilization knows its obsolescence advance."""
    if wonder.obsolete_by is None:
        return False
    return any(wonder.obsolete_by in p.techs for p in game.civilizations)


def wonder_owner(game: Game, wonder_id: str) -> Optional[int]:
    city_id = game.wonders.get(wonder_id)
    if city_id is None or city_id not in game.cities:
        return None
    return game.cities[city_id].owner


def active_wonders(game: Game, player_id: int) -> list[tuple[BuildingDef, City]]:
    """Working wonders owned by the player, with the city holding each."""
    result = []
    for wonder_id, city_id in game.wonders.items():
        city = game.cities.get(city_id)
        if city is None or city.owner != player_id:
            continue
        wonder = game.rules.buildings[wonder_id]
        if not wonder_obsolete(game, wonder):
            result.append((wonder, city))
    return result


def _wonder_effect_reaches(game: Game, effect: Effect, wonder_city: City, city: City) -> bool:
    if effect.scope == "player":
        return True
    if effect.scope == "continent":
        return game.tile_of(wonder_city).continent == game.tile_of(city).continent
    return wonder_city.id == city.id


def effective_buildings(game: Game, city: City) -> set[str]:
    """Buildings of the city, plus those a wonder provides (acts_as_building)."""
    buildings = set(city.buildings)
    for wonder, wonder_city in active_wonders(game, city.owner):
        for effect in wonder.effects:
            if effect.type == "acts_as_building" and effect.building \
                    and _wonder_effect_reaches(game, effect, wonder_city, city):
                buildings.add(effect.building)
    return buildings


def city_effects(game: Game, city: City) -> list[Effect]:
    """Every effect that currently applies to the city, from its buildings and from wonders."""
    player = game.players[city.owner]
    buildings = effective_buildings(game, city)
    result: list[Effect] = []

    def applies(effect: Effect) -> bool:
        if effect.requires_tech is not None and effect.requires_tech not in player.techs:
            return False
        if effect.requires_building is not None and effect.requires_building not in buildings:
            return False
        return True

    for building_id in buildings:
        definition = game.rules.buildings[building_id]
        if definition.wonder:
            continue
        result.extend(e for e in definition.effects if applies(e))
    for wonder, wonder_city in active_wonders(game, city.owner):
        for effect in wonder.effects:
            if _wonder_effect_reaches(game, effect, wonder_city, city) and applies(effect):
                result.append(effect)
    return result


def player_effects(game: Game, player: Player, effect_type: str) -> list[Effect]:
    """Player-wide effects of a given type (from wonders with scope: player)."""
    result = []
    for wonder, _ in active_wonders(game, player.id):
        for effect in wonder.effects:
            if effect.type == effect_type and effect.scope == "player":
                if effect.requires_tech is None or effect.requires_tech in player.techs:
                    result.append(effect)
    return result


def has_player_effect(game: Game, player: Player, effect_type: str) -> bool:
    return bool(player_effects(game, player, effect_type))


def of_type(effects: list[Effect], effect_type: str) -> list[Effect]:
    return [e for e in effects if e.type == effect_type]


def has_effect(effects: list[Effect], effect_type: str) -> bool:
    return any(e.type == effect_type for e in effects)


def is_capital(game: Game, city: City) -> bool:
    return any(game.rules.buildings[b].has_effect("capital") for b in city.buildings)
