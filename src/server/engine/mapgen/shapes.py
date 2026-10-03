"""Land of the map shapes that are not the original continents: islands, a single continent...

Each land mass gets its own region of the map, a rough ellipse that stays clear of the
regions of the others, so the sea always separates two masses. Land then grows inside the
region with the same random-walk "clouds" as the original generator, which gives the
coasts their irregular look. The land is left flat (plains): the relief comes afterwards.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from ..model.worldmap import CARDINALS, WorldMap
from ..rules.schema import LandMasses, MapShape

OCEAN, PLAINS = "ocean", "plains"

POLAR_MARGIN = 4            # rows kept free of land near each pole, as in the original
REGION_FILL = 0.72          # share of its region that a land mass covers
CLOSED_FILL = 0.92          # the same for a ring or a belt of land, which must not break up
OUTLINE_REACH = 1.25        # how far the lumpy outline of a region goes beyond its ellipse
SIZE_SPREAD = 0.3           # masses of a group differ in size by up to +/- 30 %
PLACEMENT_TRIES = 300


def raise_shaped_land(world: WorldMap, shape: MapShape, rng: random.Random) -> None:
    wanted = []                                       # (land tiles, group) of every mass
    for group in shape.masses:
        average = group.land * len(world.tiles) / group.count
        spread = SIZE_SPREAD if group.count > 1 else 0.0
        for _ in range(group.count):
            size = average * (1 + spread * (2 * rng.random() - 1))
            wanted.append((max(6, round(size)), group))
    wanted.sort(key=lambda mass: -mass[0])            # the largest first, while there is room

    taken: set[int] = set()                           # regions so far, with the sea around them
    for size, group in wanted:
        fill = CLOSED_FILL if group.hollow or group.belt else REGION_FILL
        region = _find_region(world, size / fill, group, taken, rng)
        if region is None:
            continue                                  # no room left on this world
        _grow_land(world, region, size, rng)
        for index in region:
            taken.add(index)
            taken.update(t.index for t in world.neighbors(world.tiles[index]))

    if shape.lakes > 0:
        _dig_lakes(world, shape.lakes, rng)


def _find_region(world: WorldMap, area: float, group: LandMasses, taken: set[int],
                 rng: random.Random) -> Optional[list[int]]:
    """A free region of about `area` tiles; smaller and smaller when the map gets crowded."""
    for _ in range(6):
        for _ in range(PLACEMENT_TRIES):
            if group.belt:
                region = _belt_region(world, area, rng)
            else:
                region = _random_region(world, area, group.hollow, rng)
            if region and taken.isdisjoint(region):
                return region
        area *= 0.75
    return None


def _belt_region(world: WorldMap, area: float, rng: random.Random) -> list[int]:
    """A band around the world that winds and gets wider and narrower on its way."""
    w, h = world.width, world.height
    top, bottom = POLAR_MARGIN, h - 1 - POLAR_MARGIN
    rows = bottom - top + 1
    half = min(area / w, rows * 0.8) / 2

    def wave(amount: float, turns: tuple[int, ...]):
        parts = [(k, amount * rng.random(), math.tau * rng.random()) for k in turns]
        return lambda x: sum(a * math.sin(k * math.tau * x / w + phase) for k, a, phase in parts)

    winding, swelling = wave(rows * 0.08, (1, 2, 3)), wave(0.2, (2, 3, 5))
    middle = (top + bottom) / 2 + (rng.random() - 0.5) * max(0.0, rows - 2.6 * half) * 0.5
    region = []
    for x in range(w):
        centre, reach = middle + winding(x), half * (1 + swelling(x))
        for y in range(top, bottom + 1):
            if abs(y - centre) <= reach:
                region.append(world.tile(x, y).index)
    return region


def _random_region(world: WorldMap, area: float, hollow: float,
                   rng: random.Random) -> list[int]:
    """A lumpy ellipse, wider than tall, somewhere between the polar margins."""
    w, h = world.width, world.height
    top, bottom = POLAR_MARGIN, h - 1 - POLAR_MARGIN
    area /= 1 - hollow * hollow
    stretch = 1 + 0.6 * rng.random()
    ry = math.sqrt(area / (math.pi * stretch))
    ry = min(ry, (bottom - top + 1) / 2 / OUTLINE_REACH)       # a large mass gets wider instead
    rx = min(area / (math.pi * ry), w / 2 - 2)
    # The outline moves in and out with the direction, to avoid perfect ellipses.
    waves = [(k, (OUTLINE_REACH - 1) / 3 * rng.random(), math.tau * rng.random())
             for k in (2, 3, 5)]

    reach_x, reach_y = math.ceil(rx * OUTLINE_REACH), math.ceil(ry * OUTLINE_REACH)
    if world.wrap_x:
        cx = rng.randrange(w)
    else:
        cx = rng.randrange(min(reach_x, w // 2), max(w - reach_x, w // 2) + 1)
    low, high = top + reach_y, bottom - reach_y
    cy = rng.randrange(low, high + 1) if low < high else (top + bottom) // 2

    region = []
    for dy in range(-reach_y, reach_y + 1):
        y = cy + dy
        if not top <= y <= bottom:
            continue
        for dx in range(-reach_x, reach_x + 1):
            if not world.wrap_x and not 1 <= cx + dx < w - 1:
                continue
            distance = math.hypot(dx / rx, dy / ry)
            angle = math.atan2(dy / ry, dx / rx)
            outline = 1 + sum(amount * math.sin(k * angle + phase) for k, amount, phase in waves)
            if hollow * outline <= distance <= outline:
                region.append(world.tile(cx + dx, y).index)
    return region


def _grow_land(world: WorldMap, region: list[int], size: int, rng: random.Random) -> None:
    """Drops clouds of land in the region until `size` tiles are raised."""
    inside = set(region)
    land: list[int] = []
    longest_walk = max(4, min(64, size // 5))
    for _ in range(size * 4):
        if len(land) >= size:
            break
        # Most clouds start from the land already there, which keeps the mass in one piece;
        # the others make the islets off its coasts.
        start = land if land and rng.random() < 0.9 else region
        tile = world.tiles[start[rng.randrange(len(start))]]
        x, y = tile.x, tile.y
        for _ in range(rng.randrange(longest_walk) + 1):
            for dx, dy in ((0, 0),) + CARDINALS:
                near = world.tile(x + dx, y + dy)
                if near is not None and near.index in inside and near.terrain == OCEAN:
                    near.terrain = PLAINS
                    land.append(near.index)
            dx, dy = CARDINALS[rng.randrange(4)]
            x, y = x + dx, y + dy
            if world.tile(x, y) is None:
                break


def _dig_lakes(world: WorldMap, share: float, rng: random.Random) -> None:
    """Turns that share of the land into lakes, which never reach the sea."""
    land = [t for t in world.tiles if t.terrain != OCEAN]
    lake: set[int] = set()

    def is_inland(tile) -> bool:
        return all(n.terrain != OCEAN or n.index in lake for n in world.neighbors(tile))

    to_dig = int(share * len(land))
    for _ in range(to_dig * 20):
        if to_dig <= 0:
            break
        tile = land[rng.randrange(len(land))]
        for _ in range(rng.randrange(14) + 2):
            if tile is None or len(world.neighbors(tile)) < 8 or not is_inland(tile):
                break
            if tile.terrain != OCEAN:
                tile.terrain = OCEAN
                lake.add(tile.index)
                to_dig -= 1
            dx, dy = CARDINALS[rng.randrange(4)]
            tile = world.tile(tile.x + dx, tile.y + dy)
