"""Minor tribe huts.

Source: OpenCivOne UnitManagement.cs F0_1866_1931_FoundMinorTribeHut. The "advanced tribe"
outcome is decided by the quality of the site instead of the original land-ownership value.
"""
from __future__ import annotations

from ..mapgen.sites import site_score
from ..model.entities import Unit
from ..model.game import Game
from ..model.worldmap import DIRECTIONS, Tile
from . import cities, research, visibility


def enter_hut(game: Game, unit: Unit, tile: Tile) -> None:
    tile.hut = False
    game.mark_tile(tile)
    player = game.players[unit.owner]
    if player.is_barbarian or game.rules.units[unit.type].domain == "air":
        return
    distance = min((game.map.distance(tile.x, tile.y, c.x, c.y) for c in game.cities.values()),
                   default=99)
    settings = game.rules.game.huts
    outcome = game.rng.randrange(5)
    if outcome == 0:
        if distance > 3:
            if site_score(game.rules, game.map, tile) >= settings.advanced_tribe_min_site_score \
                    and cities.can_found_city(game, tile):
                _advanced_tribe(game, unit, tile)
            else:
                _gold(game, unit, tile)
        else:
            _mercenaries(game, unit, tile)
    elif outcome == 1:
        if game.turn == 0 or game.year > settings.wisdom_until_year:
            _gold(game, unit, tile)
        else:
            _wisdom(game, unit, tile)
    elif outcome == 2:
        _gold(game, unit, tile)
    elif outcome == 3:
        if distance < 4 or not game.player_cities(player.id):
            _mercenaries(game, unit, tile)
        else:
            _barbarians(game, unit, tile)
    else:
        _mercenaries(game, unit, tile)


def _gold(game: Game, unit: Unit, tile: Tile) -> None:
    player = game.players[unit.owner]
    amount = game.rules.game.huts.gold
    player.gold += amount
    game.emit("hut", f"The {player.civ.nation} find metal deposits worth {amount} gold.",
              player=player.id, x=tile.x, y=tile.y, outcome="gold")


def _advanced_tribe(game: Game, unit: Unit, tile: Tile) -> None:
    player = game.players[unit.owner]
    city = cities.found_city(game, player, tile, quiet=True)
    game.emit("hut", f"An advanced tribe joins the {player.civ.nation}: {city.name} is founded.",
              player=player.id, x=tile.x, y=tile.y, outcome="city", city=city.id)


def _mercenaries(game: Game, unit: Unit, tile: Tile) -> None:
    player = game.players[unit.owner]
    choices = game.rules.game.huts.mercenaries
    unit_type = choices[game.rng.randrange(len(choices))]
    new_unit = game.add_unit(unit_type, player.id, tile.x, tile.y)
    visibility.reveal_unit(game, new_unit)
    name = game.rules.units[unit_type].name
    game.emit("hut", f"A tribe of mercenaries ({name}) joins the {player.civ.nation}.",
              player=player.id, x=tile.x, y=tile.y, outcome="mercenaries")


def _wisdom(game: Game, unit: Unit, tile: Tile) -> None:
    player = game.players[unit.owner]
    options = sorted(research.research_options(game, player))
    if not options:
        _gold(game, unit, tile)
        return
    tech_id = options[game.rng.randrange(len(options))]
    research.give_tech(game, player, tech_id, "hut")


def _barbarians(game: Game, unit: Unit, tile: Tile) -> None:
    player = game.players[unit.owner]
    barbarians = game.barbarians
    if barbarians is None:
        return
    settings = game.rules.game.huts.barbarian_units
    step = max(1, min(4, 4 - len(game.player_cities(player.id))))
    spawned = 0
    for index in range(0, 8, step):
        dx, dy = DIRECTIONS[index]
        other = game.map.tile(tile.x + dx, tile.y + dy)
        if other is None or other.unit_ids or other.city_id is not None:
            continue
        terrain = game.terrain(other)
        if not terrain.is_land:
            continue
        unit_type = settings.open if terrain.move_cost < 3 else settings.rough
        game.add_unit(unit_type, barbarians.id, other.x, other.y)
        spawned += 1
    game.emit("hut", f"The {player.civ.nation} unleash a horde of barbarians!",
              player=player.id, x=tile.x, y=tile.y, outcome="barbarians", count=spawned)
