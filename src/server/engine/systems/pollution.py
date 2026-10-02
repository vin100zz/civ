"""Pollution of the land around cities, and global warming.

Source: OpenCivOne CityWorker.cs around line 3700 (pollution of a city) and Segment_1238.cs
F0_1238_1767 / F7_0000_1be3 (global warming). The original spares the computer players;
here every civilization pollutes.
"""
from __future__ import annotations

from .. import effects as fx
from ..mapgen.generator import set_terrain
from ..model.entities import City
from ..model.game import Game
from ..rules.schema import Effect
from . import city as city_rules


def pollution_index(game: Game, city: City, shields: int, effects: list[Effect]) -> int:
    """How much the city pollutes: its industry, plus its citizens once they drive cars."""
    settings = game.rules.game.pollution
    if not settings.enabled:
        return 0
    player = game.players[city.owner]
    percent = min((e.percent for e in effects if e.type == "pollution_percent"), default=100)
    index = int(shields * percent / 100) - settings.tolerance
    if not fx.has_effect(effects, "no_population_pollution"):
        known = sum(1 for tech in settings.population_techs if tech in player.techs)
        index += city.size * known // 4
    return max(0, index)


def pollute(game: Game, city: City) -> None:
    """Each turn a polluting city may spoil one tile of its area."""
    settings = game.rules.game.pollution
    index = city.stats.pollution
    if index <= 0:
        return
    player = game.players[city.owner]
    roll = max(1, settings.roll - player.tech_count * settings.roll_per_tech)
    if index * 2 <= game.rng.randrange(roll):
        return
    area = game.map.city_area(city.x, city.y)
    _, tile = area[game.rng.randrange(len(area))]
    if not game.terrain(tile).is_land or tile.pollution or tile.city_id is not None:
        return
    tile.pollution = True
    game.mark_tile(tile)
    game.emit("pollution", f"Pollution near {city.name}.", player=player.id,
              x=tile.x, y=tile.y, city=city.id)


def polluted_tiles(game: Game) -> int:
    return sum(1 for tile in game.map.tiles if tile.pollution)


def global_warming(game: Game) -> None:
    """Once per turn: polluted land heats the planet until the ice caps melt."""
    settings = game.rules.game.pollution
    if not settings.enabled:
        return
    target = polluted_tiles(game) * settings.warming_per_tile \
        - game.warming_count * settings.warming_recovery
    if target > game.warming_level:
        game.warming_level = min(99, game.warming_level + 1)
    elif target < game.warming_level:
        game.warming_level = max(0, game.warming_level - 1)
    if game.warming_level > settings.warming_threshold:
        changed = _melt_ice_caps(game)
        game.warming_count += 1
        game.warming_level = 0
        game.emit("global_warming", f"Global warming: the ice caps melt and {changed} "
                  f"regions turn to swamp or desert.", changed=changed)


def _melt_ice_caps(game: Game) -> int:
    """Coasts are flooded, and part of the inland dries up; each warming reaches further."""
    settings = game.rules.game.pollution
    severity = game.warming_count
    changes: list[tuple] = []
    for tile in game.map.tiles:
        if tile.terrain not in settings.warming_coastal and tile.terrain not in settings.warming_inland:
            continue
        sea = sum(1 for other in game.map.neighbors(tile) if not game.terrain(other).is_land)
        if 7 - severity <= sea:
            new_terrain = settings.warming_coastal.get(tile.terrain)
        elif (11 * tile.x + 13 * tile.y) & 7 == severity & 7:
            new_terrain = settings.warming_inland.get(tile.terrain)
        else:
            continue
        if new_terrain is not None and new_terrain != tile.terrain:
            changes.append((tile, new_terrain))
    for tile, new_terrain in changes:
        set_terrain(game.map, tile, new_terrain)
        tile.irrigation = False
        tile.mine = False
        game.mark_tile(tile)
    for city in game.cities.values():
        city_rules.ensure_valid_assignment(game, city)
    return len(changes)
