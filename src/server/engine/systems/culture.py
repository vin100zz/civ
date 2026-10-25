"""Culture (Golden Ages): what a city makes each turn, and the borders it wins with it.

A city claims the inner ring of its area at its founding. Its culture, made each turn and
never spent, wins it more tiles one by one, the n-th needing n x tile_cost more culture than
the one before: first the 12 tiles of its outer ring, the best one nobody holds first (all
twelve take 78 x tile_cost); then, beyond the tiles it works, the corners of its 5 x 5 square
and its third ring, the nearest first, each next to a tile it already holds (all 36 take
666 x tile_cost). A tile another civilization holds stays theirs, and the city never reaches
beyond its area for a tile another civilization's city could work. Buildings and wonders add
culture (`culture` effects: `amount` per turn, `percent` on the whole), and every wonder
gives its city `per_wonder` more.
"""
from __future__ import annotations

from typing import Optional

from .. import effects as fx
from ..model.entities import City
from ..model.game import Game
from ..model.worldmap import (CITY_CORNERS, CITY_OFFSETS, CITY_RING_OUTER, CITY_RING_THIRD,
                              CLAIM_BITS, DIRECTIONS, Tile)
from . import city as city_rules
from .territory import claiming_city

# The tiles a city's culture wins, in the order it reaches for them.
FAR_TILES = CITY_CORNERS + CITY_RING_THIRD
GROWTH_TILES = CITY_RING_OUTER + FAR_TILES
OUTER_TILES = len(CITY_RING_OUTER)


def culture_per_turn(game: Game, city: City) -> int:
    """Culture the city makes each turn (out of civil disorder), 0 without culture rules."""
    settings = game.rules.game.culture
    if not settings.enabled:
        return 0
    effects = fx.of_type(fx.city_effects(game, city), "culture")
    wonders = sum(1 for building in city.buildings if game.rules.buildings[building].wonder)
    base = settings.per_city + settings.per_wonder * wonders + sum(e.amount for e in effects)
    return int(base * (100 + sum(e.percent for e in effects)) / 100)


def outer_claims(city: City) -> int:
    """Tiles of its outer ring the city holds."""
    return sum(1 for offset in CITY_RING_OUTER if city.claims & CLAIM_BITS[offset])


def won_tiles(city: City) -> int:
    """Tiles the city's culture has won it: of its outer ring, its corners, its third ring."""
    return sum(1 for offset in GROWTH_TILES if city.claims & CLAIM_BITS[offset])


def culture_for(game: Game, claimed: int) -> int:
    """The culture a city needs to have won `claimed` tiles."""
    return game.rules.game.culture.tile_cost * claimed * (claimed + 1) // 2


def next_tile_cost(game: Game, city: City) -> Optional[int]:
    """The culture the city needs for its next tile; None once it holds all it may win."""
    won = won_tiles(city)
    return culture_for(game, won + 1) if won < len(GROWTH_TILES) else None


def free_tiles(game: Game, city: City, offsets=CITY_RING_OUTER) -> list[tuple[tuple[int, int], Tile]]:
    """Tiles among `offsets` (by default its outer ring) the city could claim: in nobody's
    territory."""
    result = []
    for offset in offsets:
        if city.claims & CLAIM_BITS[offset]:
            continue
        tile = game.map.tile(city.x + offset[0], city.y + offset[1])
        if tile is not None and claiming_city(game, tile) is None:
            result.append((offset, tile))
    return result


def _worked_by_foreigners(game: Game, city: City, tile: Tile) -> bool:
    """The tile is in the area of a city of another civilization, which could work it."""
    for dx, dy in CITY_OFFSETS:
        other = game.map.tile(tile.x - dx, tile.y - dy)
        if other is not None and other.city_id is not None \
                and game.cities[other.city_id].owner != city.owner:
            return True
    return False


def far_free_tiles(game: Game, city: City) -> list[tuple[tuple[int, int], Tile]]:
    """Tiles beyond its area the city could claim: free, next to a tile it holds, and out of
    the reach of the cities of other civilizations."""
    held = {(0, 0)} | {offset for offset, bit in CLAIM_BITS.items() if city.claims & bit}
    return [(offset, tile) for offset, tile in free_tiles(game, city, FAR_TILES)
            if any((offset[0] + dx, offset[1] + dy) in held for dx, dy in DIRECTIONS)
            and not _worked_by_foreigners(game, city, tile)]


def best_free_tile(game: Game, city: City) -> Optional[tuple[int, int]]:
    """The tile the city claims next. In its outer ring, what it would yield once worked,
    food first, then the order of the ring (the four tiles straight out first). Beyond, once
    its outer ring is held or taken, the nearest tile, then the order of the rings."""
    candidates = free_tiles(game, city)
    if candidates:
        effects = fx.city_effects(game, city)

        def worth(entry) -> tuple[int, int]:
            offset, tile = entry
            y = city_rules.tile_yields(game, city, tile, effects)
            return (3 * y.food + 2 * y.shields + y.trade, -CITY_RING_OUTER.index(offset))

        return max(candidates, key=worth)[0]
    far = [offset for offset, _ in far_free_tiles(game, city)]
    if not far:
        return None
    return min(far, key=lambda o: (max(abs(o[0]), abs(o[1])), o[0] ** 2 + o[1] ** 2,
                                   FAR_TILES.index(o)))


def add_culture(game: Game, city: City) -> None:
    """One turn of culture: the city adds what it makes, then takes the tiles it has earned."""
    gained = culture_per_turn(game, city)
    if gained <= 0:
        return
    city.culture += gained
    grown = False
    while True:
        cost = next_tile_cost(game, city)
        if cost is None or city.culture < cost:
            break
        offset = best_free_tile(game, city)
        if offset is None:
            break
        city.claims |= CLAIM_BITS[offset]
        game.mark_tile(game.map.tile(city.x + offset[0], city.y + offset[1]))
        grown = True
    if grown:
        game.emit("borders", f"The borders of {city.name} grow.", player=city.owner,
                  x=city.x, y=city.y, city=city.id)
        # Citizens out of work for lack of land go to the new tiles.
        if city.specialists.get("entertainer", 0):
            city_rules.auto_arrange(game, city)


def civilization_culture(game: Game, player_id: int) -> int:
    """Culture of the cities the civilization holds (the score counts it)."""
    return sum(city.culture for city in game.player_cities(player_id))
