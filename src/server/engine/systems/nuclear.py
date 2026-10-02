"""Nuclear weapons and nuclear accidents.

Source: OpenCivOne Segment_29f3.cs F0_29f3_0d4d / F0_29f3_0ec3 (the blast) and CityWorker.cs
(meltdown of a Nuclear Plant during civil disorder).
"""
from __future__ import annotations

from typing import Optional

from .. import effects as fx
from ..model.entities import City, Unit
from ..model.game import Game
from ..model.worldmap import Tile
from . import cities
from . import city as city_rules


def shielded(game: Game, tile: Tile) -> bool:
    """A city with a nuclear shield (SDI Defense) protects its own tile."""
    if tile.city_id is None:
        return False
    return fx.has_effect(fx.city_effects(game, game.cities[tile.city_id]), "nuclear_shield")


def strike(game: Game, missile: Unit, target: Tile) -> None:
    """A nuclear unit hits a tile: it is consumed, and the tile and its surroundings burn."""
    attacker = game.players[missile.owner]
    victim_id = game.tile_owner(target)
    name = game.rules.units[missile.type].name
    city = game.cities.get(target.city_id) if target.city_id is not None else None
    where = city.name if city is not None else "enemy troops"
    game.remove_unit(missile)
    if shielded(game, target):
        game.emit("nuclear", f"{attacker.civ.name} {name} is shot down over {where}.",
                  player=attacker.id, other=victim_id, x=target.x, y=target.y, stopped=True)
        return
    game.emit("nuclear", f"The {attacker.civ.nation} strike {where} with a {name}!",
              player=attacker.id, other=victim_id, x=target.x, y=target.y, stopped=False)
    blast(game, target)


def blast(game: Game, center: Tile) -> None:
    """Destroys the units on the tile and the 8 around it, halves the cities, spreads fallout."""
    settings = game.rules.game.nuclear
    owners = set()
    for tile in (center, *game.map.neighbors(center)):
        if shielded(game, tile):
            continue
        for unit in list(game.units_at(tile)):
            owners.add(unit.owner)
            game.remove_unit(unit)
        if tile.city_id is not None:
            city = game.cities[tile.city_id]
            city.size -= city.size * settings.city_loss_percent // 100
            city_rules.auto_arrange(game, city)
        elif game.terrain(tile).is_land and not tile.pollution \
                and game.rng.random() < settings.fallout_chance:
            tile.pollution = True
            game.mark_tile(tile)
    for owner in sorted(owners):
        cities.check_elimination(game, game.players[owner])


def meltdown_building(game: Game, city: City) -> Optional[str]:
    """The building of the city that may melt down, if its owner lacks the safe technology."""
    player = game.players[city.owner]
    for building_id in sorted(city.buildings):
        for effect in game.rules.buildings[building_id].effects:
            if effect.type == "meltdown_risk" and effect.safe_tech not in player.techs:
                return building_id
    return None


def maybe_meltdown(game: Game, city: City) -> bool:
    """Civil disorder in a city with a risky plant can end in a nuclear accident."""
    if not city.disorder:
        return False
    building_id = meltdown_building(game, city)
    if building_id is None or game.rng.random() >= game.rules.game.nuclear.meltdown_chance:
        return False
    city.buildings.discard(building_id)
    game.emit("meltdown", f"Nuclear meltdown in {city.name}!", player=city.owner,
              x=city.x, y=city.y, city=city.id)
    blast(game, game.tile_of(city))
    return True
