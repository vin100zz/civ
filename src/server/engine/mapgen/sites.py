"""How good a tile is as a city site.

Based on the original formula (OpenCivOne MapInitAndIntro.cs, stage 7): every tile of the
city area is worth trade + 3 x food + 2 x shields, plus what irrigation or a mine could add;
the inner ring counts double and the city tile four times. The result is scaled to 8..15
like the original, so the thresholds of the original AI keep their meaning. Only river,
grassland and plains tiles are considered suitable.

Unlike the original, the centre tile is the one that counts four times (the original gives
that weight to the tile north of the city, an indexing slip).
"""
from __future__ import annotations

from typing import Callable, Optional

from ..model.worldmap import CITY_RING_INNER, CITY_RING_OUTER, Tile, WorldMap
from ..rules.schema import Rules

SUITABLE_TERRAINS = ("river", "grassland", "plains")
MIN_SCORE, MAX_SCORE = 8, 15


def tile_value(rules: Rules, tile: Tile) -> int:
    """Worth of one tile for a city working it."""
    terrain = rules.terrains[tile.terrain]
    yields = terrain.special.yields if (tile.special and terrain.special) else terrain.yields
    value = yields.trade + 3 * yields.food + 2 * yields.shields
    if terrain.pattern_bonus is not None and tile.pattern:
        value += 2
    if terrain.mine is not None and terrain.mine.bonus:
        value += terrain.mine.bonus
    elif terrain.irrigation is not None and terrain.irrigation.bonus:
        value += 2 * terrain.irrigation.bonus
    return value


def site_score(rules: Rules, world: WorldMap, tile: Tile,
               known: Optional[Callable[[Tile], bool]] = None) -> int:
    """Score of a city site, 0 if unsuitable, otherwise MIN_SCORE..MAX_SCORE.

    `known` restricts the evaluation to the tiles a player has explored: unknown tiles
    count as worthless, so an honest AI prefers sites it can actually see.
    """
    if tile.terrain not in SUITABLE_TERRAINS:
        return 0
    if tile.y < 2 or tile.y >= world.height - 2:
        return 0
    total = 4 * tile_value(rules, tile)
    for ring, weight in ((CITY_RING_INNER, 2), (CITY_RING_OUTER, 1)):
        for dx, dy in ring:
            other = world.tile(tile.x + dx, tile.y + dy)
            if other is None or (known is not None and not known(other)):
                continue
            total += weight * tile_value(rules, other)
    terrain = rules.terrains[tile.terrain]
    if terrain.pattern_bonus is not None and not tile.pattern:
        total -= 16
    scaled = max(1, min(15, (total - 120) // 8))
    return scaled // 2 + MIN_SCORE


def site_scores(rules: Rules, world: WorldMap) -> list[int]:
    """Score of every tile of the map, indexed like world.tiles."""
    return [site_score(rules, world, tile) for tile in world.tiles]
