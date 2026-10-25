"""Territory: the tiles each civilization holds around its cities.

A city claims tiles around it (`City.claims`, a mask over TERRITORY_OFFSETS): its whole area
without culture; with it, its inner ring and then the tiles its culture wins, as far as its
third ring (systems/culture.py). A tile claimed by several cities belongs to the oldest of
them (the smallest id).
"""
from __future__ import annotations

from typing import Mapping, Optional

from ..model.entities import City, CityMemory
from ..model.game import Game
from ..model.worldmap import CLAIM_BITS, TERRITORY_OFFSETS, Tile, WorldMap

AROUND = ((0, 0), *TERRITORY_OFFSETS)


def claims(city: City | CityMemory, offset: tuple[int, int]) -> bool:
    """The tile at `offset` from the city is part of what it claims (its own tile always).
    `offset` is the shortest one, x wrapping around the world."""
    return offset == (0, 0) or bool(city.claims & CLAIM_BITS.get(offset, 0))


def territory_owner(world: WorldMap, tile: Tile,
                    known_cities: Mapping[int, City | CityMemory]) -> Optional[int]:
    """Match the map's territory overlay: claimed tiles, oldest city id wins overlaps."""
    claim = min((city_id for city_id, city in known_cities.items()
                 if claims(city, (world.dx(city.x, tile.x), tile.y - city.y))),
                default=None)
    return known_cities[claim].owner if claim is not None else None


def claiming_city(game: Game, tile: Tile) -> Optional[City]:
    """The city whose territory holds the tile, from the cities of the world: the same answer
    as territory_owner(game.map, tile, game.cities), looking only at the tiles around."""
    best: Optional[City] = None
    for dx, dy in AROUND:
        other = game.map.tile(tile.x - dx, tile.y - dy)
        if other is None or other.city_id is None:
            continue
        city = game.cities[other.city_id]
        if (best is None or city.id < best.id) and claims(city, (dx, dy)):
            best = city
    return best


def owner_of(game: Game, tile: Tile) -> Optional[int]:
    """Whose territory the tile is in."""
    city = claiming_city(game, tile)
    return city.owner if city is not None else None
