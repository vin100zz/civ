"""Culture (Golden Ages): what a city makes each turn, and the borders it wins with it.

A city claims the inner ring of its area at its founding. Its culture, made each turn and
never spent, wins it the 12 tiles of its outer ring one by one: the n-th needs n x tile_cost
more culture than the one before, so all twelve take 78 x tile_cost. Each goes to the best
tile nobody holds; a tile another civilization holds stays theirs. Buildings and wonders
add culture (`culture` effects: `amount` per turn, `percent` on the whole), and every wonder
gives its city `per_wonder` more.
"""
from __future__ import annotations

from typing import Optional

from .. import effects as fx
from ..model.entities import City
from ..model.game import Game
from ..model.worldmap import CITY_RING_OUTER, CLAIM_BITS, Tile
from . import city as city_rules
from .territory import claiming_city

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


def culture_for(game: Game, claimed: int) -> int:
    """The culture a city needs to hold `claimed` tiles of its outer ring."""
    return game.rules.game.culture.tile_cost * claimed * (claimed + 1) // 2


def next_tile_cost(game: Game, city: City) -> Optional[int]:
    """The culture the city needs for its next tile; None once its whole ring is claimed."""
    claimed = outer_claims(city)
    return culture_for(game, claimed + 1) if claimed < OUTER_TILES else None


def free_tiles(game: Game, city: City) -> list[tuple[tuple[int, int], Tile]]:
    """Tiles of the outer ring the city could claim: in nobody's territory."""
    result = []
    for offset in CITY_RING_OUTER:
        if city.claims & CLAIM_BITS[offset]:
            continue
        tile = game.map.tile(city.x + offset[0], city.y + offset[1])
        if tile is not None and claiming_city(game, tile) is None:
            result.append((offset, tile))
    return result


def best_free_tile(game: Game, city: City) -> Optional[tuple[int, int]]:
    """The tile the city claims next: what it would yield once worked, food first, then the
    order of the ring (the four tiles straight out first)."""
    effects = fx.city_effects(game, city)

    def worth(entry) -> tuple[int, int]:
        offset, tile = entry
        y = city_rules.tile_yields(game, city, tile, effects)
        return (3 * y.food + 2 * y.shields + y.trade, -CITY_RING_OUTER.index(offset))

    candidates = free_tiles(game, city)
    return max(candidates, key=worth)[0] if candidates else None


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
