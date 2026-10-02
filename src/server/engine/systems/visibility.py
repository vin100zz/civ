"""What each player has explored and currently sees.

`explored` never shrinks. `visible` is rebuilt at the start of the player's turn and only
grows while the player moves, like the screen of the original game. Seeing a foreign unit
or city establishes contact between the two civilizations.
"""
from __future__ import annotations

from ..model.entities import NO_CONTACT, WAR, City, CityMemory, Player, Unit
from ..model.game import Game
from ..model.worldmap import Tile
from .. import effects as fx

CITY_SIGHT = 2


def init_player(game: Game, player: Player) -> None:
    size = len(game.map.tiles)
    player.explored = bytearray(size)
    player.visible = bytearray(size)


def reveal(game: Game, player: Player, x: int, y: int, radius: int) -> None:
    for tile in game.map.tiles_within(x, y, radius):
        player.explored[tile.index] = 1
        player.visible[tile.index] = 1
        _notice(game, player, tile)


def reveal_unit(game: Game, unit: Unit) -> None:
    reveal(game, game.players[unit.owner], unit.x, unit.y, game.rules.units[unit.type].sight)


def reveal_city(game: Game, city: City) -> None:
    reveal(game, game.players[city.owner], city.x, city.y, CITY_SIGHT)


def refresh(game: Game, player: Player) -> None:
    """Rebuilds the visible area from the player's cities and units."""
    player.visible = bytearray(len(game.map.tiles))
    for city in game.player_cities(player.id):
        reveal_city(game, city)
    for unit in game.player_units(player.id):
        reveal_unit(game, unit)
    # Forget cities that no longer exist where they were last seen.
    for city_id in list(player.known_cities):
        memory = player.known_cities[city_id]
        tile = game.map.tile(memory.x, memory.y)
        if player.visible[tile.index] and tile.city_id != city_id:
            del player.known_cities[city_id]


def reveal_world(game: Game, player: Player) -> None:
    """The player learns the whole map and where every city is (Apollo Program)."""
    for index in range(len(player.explored)):
        player.explored[index] = 1
    for city in game.cities.values():
        if city.owner != player.id:
            remember_city(game, player, city)


def can_see(player: Player, tile: Tile) -> bool:
    return bool(player.visible[tile.index])


def has_explored(player: Player, tile: Tile) -> bool:
    return bool(player.explored[tile.index])


def remember_city(game: Game, player: Player, city: City) -> None:
    walls = any(e.type == "defense_multiplier" for e in fx.city_effects(game, city))
    player.known_cities[city.id] = CityMemory(
        city_id=city.id, name=city.name, owner=city.owner, x=city.x, y=city.y,
        size=city.size, seen_turn=game.turn, has_walls=walls)


def _notice(game: Game, player: Player, tile: Tile) -> None:
    """Records what stands on a tile the player has just seen."""
    if tile.city_id is not None:
        city = game.cities[tile.city_id]
        if city.owner != player.id:
            remember_city(game, player, city)
            make_contact(game, player.id, city.owner)
    if tile.unit_ids:
        owner = game.units[tile.unit_ids[0]].owner
        if owner != player.id:
            make_contact(game, player.id, owner)


def make_contact(game: Game, a: int, b: int) -> None:
    """First meeting of two civilizations. Without a treaty they are at war, as in Civ 1."""
    if a == b or game.players[a].is_barbarian or game.players[b].is_barbarian:
        return
    relation = game.relation(a, b)
    if relation.state != NO_CONTACT:
        return
    relation.state = WAR
    relation.since_turn = game.turn
    first, second = game.players[a], game.players[b]
    game.emit("contact", f"The {first.civ.nation} and the {second.civ.nation} meet.",
              player=a, other=b)
