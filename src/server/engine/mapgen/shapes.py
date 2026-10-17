"""Land of the map shapes that are not the original continents: islands, a single continent...

Each land mass gets its own region of the map, a rough ellipse that stays clear of the
regions of the others, so the sea always separates two masses. Land then grows inside the
region with the same random-walk "clouds" as the original generator, which gives the
coasts their irregular look. The land is left flat (plains): the relief comes afterwards.

Some groups are then reshaped: their masses joined by a neck of land (bridge), split by
straits (rifts), or strung as small islands along arcs (chains).
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
NEAR_CANDIDATES = 20        # free regions compared when a mass must be close to another
NECK_WIDENING = 0.35        # chance that a tile of a neck of land gets a neighbour of land
NECK_LENGTH = 6             # sea at least between two masses joined by a neck of land
NECK_SEA = 3                # the sea this close to a neck of land stays sea
CHAIN_GAP = 2.5             # sea between two islands of a chain, beyond their radii
# Share of the map the masses are laid out on; when more land is wanted, they then spread
# out, coast after coast (a crowded map leaves no room for regions with the sea around them).
LAYOUT_LAND = 0.25
SPREAD_PACE = 0.5           # share of the coast that a mass takes at each pass


def raise_shaped_land(world: WorldMap, shape: MapShape, land: float, rng: random.Random) -> None:
    """Raises the masses of the shape, scaled so that together they cover the share `land`."""
    scale = min(land, LAYOUT_LAND) / sum(group.land for group in shape.masses)
    wanted = []                                       # (land tiles, group number) of every mass
    for number, group in enumerate(shape.masses):
        if group.chains:
            continue                                  # laid out along their arcs, below
        average = group.land * scale * len(world.tiles) / group.count
        spread = SIZE_SPREAD if group.count > 1 else 0.0
        for _ in range(group.count):
            size = average * (1 + spread * (2 * rng.random() - 1))
            wanted.append((max(6, round(size)), number))
    wanted.sort(key=lambda mass: -mass[0])            # the largest first, while there is room

    taken: set[int] = set()                           # regions so far, with the sea around them
    kept_seas: set[int] = set()                       # inner seas, and the sea along the necks
    previous: dict[int, list[int]] = {}               # group number -> land of its last mass
    for size, number in wanted:
        group = shape.masses[number]
        fill = CLOSED_FILL if group.hollow or group.belt else REGION_FILL
        near, avoid = None, taken
        if group.bridge and number in previous:       # close, but far enough for a long neck
            near = _centre(world, previous[number])
            avoid = taken | _reach(world, previous[number], NECK_LENGTH)
        found = _find_region(world, size / fill, group, avoid, rng, near)
        if found is None:
            continue                                  # no room left on this world
        region, hole = found
        kept_seas.update(hole)
        mass = _grow_land(world, region, size, rng)
        if group.belt:
            mass += _close_belt(world, region)
        _take(world, taken, region)
        if near is not None:
            neck = _join(world, previous[number], mass, rng)
            _take(world, taken, neck)
            kept_seas.update(i for i in _reach(world, neck, NECK_SEA)
                             if world.tiles[i].terrain == OCEAN)
        if group.rifts:
            _split(world, region, group.rifts, rng)
        if not group.settled:
            world.no_start.update(region)
        previous[number] = mass

    for group in shape.masses:
        if group.chains:
            _string_islands(world, group, group.land * scale, taken, rng)
    _spread(world, land, kept_seas, rng)
    if shape.lakes > 0:
        _dig_lakes(world, shape.lakes, rng)


def _take(world: WorldMap, taken: set[int], tiles: list[int]) -> None:
    """Keeps those tiles and the sea around them for the mass they belong to."""
    for index in tiles:
        taken.add(index)
        taken.update(t.index for t in world.neighbors(world.tiles[index]))


def _centre(world: WorldMap, tiles: list[int]) -> tuple[int, int]:
    """The middle of some tiles, across the date line when the world wraps."""
    y = sum(world.tiles[i].y for i in tiles) / len(tiles)
    if not world.wrap_x:
        return round(sum(world.tiles[i].x for i in tiles) / len(tiles)), round(y)
    angles = [math.tau * world.tiles[i].x / world.width for i in tiles]
    angle = math.atan2(sum(map(math.sin, angles)), sum(map(math.cos, angles)))
    return round(angle / math.tau * world.width) % world.width, round(y)


def _find_region(world: WorldMap, area: float, group: LandMasses, taken: set[int],
                 rng: random.Random, near: Optional[tuple[int, int]] = None
                 ) -> Optional[tuple[list[int], list[int]]]:
    """A free region of about `area` tiles, and the hole in its middle when it is hollow.

    Smaller and smaller when the map gets crowded. With `near`, the free region closest to
    that point among the first ones found.
    """
    for _ in range(6):
        best, best_distance, candidates = None, 0, 0
        for _ in range(PLACEMENT_TRIES):
            hole: list[int] = []
            if group.belt:
                region = _belt_region(world, area, rng)
            else:
                region = _random_region(world, area, group.hollow, rng, hole, taken)
            if not region or not taken.isdisjoint(region):
                continue
            if near is None:
                return region, hole
            distance = world.distance(*near, *_centre(world, region))
            if best is None or distance < best_distance:
                best, best_distance = (region, hole), distance
            candidates += 1
            if candidates >= NEAR_CANDIDATES:
                break
        if best is not None:
            return best
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


def _close_belt(world: WorldMap, region: list[int]) -> list[int]:
    """Raises the spine of a belt, the middle of its region from west to east, so that a thin
    belt never breaks; returns the tiles raised."""
    rows: dict[int, list[int]] = {}
    for index in region:
        tile = world.tiles[index]
        rows.setdefault(tile.x, []).append(tile.y)
    middle = {x: round(sum(ys) / len(ys)) for x, ys in rows.items()}
    raised = []
    for x in range(world.width):
        if x not in middle or (x + 1) % world.width not in middle:
            continue
        here, there = middle[x], middle[(x + 1) % world.width]
        step = 1 if there >= here else -1
        for y in range(here, there + step, step):     # down to the next column's middle
            tile = world.tile(x, y)
            if tile.terrain == OCEAN:
                tile.terrain = PLAINS
                raised.append(tile.index)
    return raised


def _random_region(world: WorldMap, area: float, hollow: float, rng: random.Random,
                   hole: Optional[list[int]] = None, taken: Optional[set[int]] = None
                   ) -> list[int]:
    """A lumpy ellipse, wider than tall, somewhere between the polar margins.

    A hollow one leaves out its middle, whose tiles go into `hole`. Empty when its middle
    is `taken` already: on a crowded map, most tries end there, before the costly outline.
    """
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
    if taken and world.tile(cx, cy).index in taken:
        return []

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
            elif distance < hollow * outline and hole is not None:
                hole.append(world.tile(cx + dx, y).index)
    return region


def _grow_land(world: WorldMap, region: list[int], size: int, rng: random.Random) -> list[int]:
    """Drops clouds of land in the region until `size` tiles are raised; returns them."""
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
    return land


def _spread(world: WorldMap, land: float, kept_seas: set[int], rng: random.Random) -> None:
    """Widens the masses, coast after coast, until land covers the share `land` of the map.

    A sea tile joins a mass only when no other mass is around it: two masses never touch,
    a strait of one tile at least stays between them. `kept_seas` stay sea, and what joins
    a mass where nobody may start is out of bounds for the starts as well.
    """
    mass = _number_masses(world)                      # land tile -> number of its mass
    wanted = round(land * len(world.tiles))
    if len(mass) >= wanted:
        return
    unsettled = {mass[i] for i in world.no_start if i in mass}
    top, bottom = POLAR_MARGIN, world.height - 1 - POLAR_MARGIN

    def owner(tile) -> Optional[int]:
        """The one mass around a sea tile, None when there is none or several."""
        around = {mass[n.index] for n in world.neighbors(tile) if n.index in mass}
        return around.pop() if len(around) == 1 else None

    while len(mass) < wanted:
        coast = [t for t in world.tiles if t.terrain == OCEAN and top <= t.y <= bottom
                 and t.index not in kept_seas and owner(t) is not None]
        if not coast:
            return                                    # every strait is as narrow as can be
        rng.shuffle(coast)
        for tile in coast[:max(1, int(len(coast) * SPREAD_PACE))]:
            number = owner(tile)                      # the coasts moved during this pass
            if number is None:
                continue
            tile.terrain = PLAINS
            mass[tile.index] = number
            if number in unsettled:
                world.no_start.add(tile.index)
            if len(mass) >= wanted:
                return


def _main_body(world: WorldMap, mass: list[int]) -> list[int]:
    """The largest piece of a mass, without the islets off its coasts."""
    left, pieces = set(mass), []
    while left:
        piece, stack = [], [left.pop()]
        while stack:
            index = stack.pop()
            piece.append(index)
            for near in world.neighbors(world.tiles[index]):
                if near.index in left:
                    left.discard(near.index)
                    stack.append(near.index)
        pieces.append(piece)
    return max(pieces, key=len)


def _reach(world: WorldMap, tiles: list[int], reach: int) -> set[int]:
    """The tiles at most `reach` steps from those tiles (diagonals included)."""
    found: set[int] = set()
    for index in tiles:
        tile = world.tiles[index]
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                near = world.tile(tile.x + dx, tile.y + dy)
                if near is not None:
                    found.add(near.index)
    return found


def _number_masses(world: WorldMap) -> dict[int, int]:
    """Each land tile with the number of its mass (tiles that touch, diagonals included)."""
    mass: dict[int, int] = {}
    number = 0
    for start in world.tiles:
        if start.terrain == OCEAN or start.index in mass:
            continue
        number += 1
        mass[start.index] = number
        stack = [start]
        while stack:
            for near in world.neighbors(stack.pop()):
                if near.terrain != OCEAN and near.index not in mass:
                    mass[near.index] = number
                    stack.append(near)
    return mass


def _join(world: WorldMap, one: list[int], other: list[int], rng: random.Random) -> list[int]:
    """A neck of land, one or two tiles wide, between the nearest coasts of two masses.

    It goes by north-south and east-west steps only, so no ship slips through it diagonally.
    """
    def coast(mass: list[int]) -> list:
        tiles = [world.tiles[i] for i in _main_body(world, mass)]   # not an islet off its coast
        return [t for t in tiles if any(n.terrain == OCEAN for n in world.neighbors(t))] or tiles

    start, end = min(((a, b) for a in coast(one) for b in coast(other)),
                     key=lambda pair: world.distance(pair[0].x, pair[0].y, pair[1].x, pair[1].y))
    neck: list[int] = []
    x, y = start.x, start.y
    while True:
        dx, dy = world.dx(x, end.x), end.y - y
        if not dx and not dy:
            return neck
        if dx and (not dy or rng.random() < abs(dx) / (abs(dx) + abs(dy))):
            x = (x + (1 if dx > 0 else -1)) % world.width
        else:
            y += 1 if dy > 0 else -1
        tiles = [world.tile(x, y)]
        if rng.random() < NECK_WIDENING:
            ax, ay = CARDINALS[rng.randrange(4)]
            tiles.append(world.tile(x + ax, y + ay))
        for near in tiles:
            if (near is not None and near.terrain == OCEAN
                    and POLAR_MARGIN <= near.y < world.height - POLAR_MARGIN):
                near.terrain = PLAINS
                neck.append(near.index)


def _split(world: WorldMap, region: list[int], rifts: int, rng: random.Random) -> None:
    """Cuts the land of a region with winding straits, two tiles wide, from coast to coast."""
    inside = set(region)
    land = [i for i in region if world.tiles[i].terrain != OCEAN]
    if not land:
        return
    for _ in range(rifts):
        start = world.tiles[land[rng.randrange(len(land))]]
        # Mostly north-south: between 17 and 69 degrees away from the meridian.
        heading = math.pi / 2 + rng.uniform(0.3, 1.2) * rng.choice((-1, 1))
        for way in (0.0, math.pi):                    # from the start tile, both ways
            x, y, angle = float(start.x), float(start.y), heading + way
            beyond = 0                                # steps since the rift left the region
            for _ in range(world.width + world.height):
                if beyond >= 3:
                    break
                angle += rng.uniform(-0.25, 0.25)
                x, y = x + math.cos(angle), y + math.sin(angle)
                beyond += 1
                for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                    tile = world.tile(round(x) + dx, round(y) + dy)
                    if tile is not None and tile.index in inside:
                        tile.terrain = OCEAN
                        beyond = 0


def _string_islands(world: WorldMap, group: LandMasses, share: float, taken: set[int],
                    rng: random.Random) -> None:
    """The masses of the group as small islands along curved arcs, a short hop apart."""
    top, bottom = POLAR_MARGIN + 1, world.height - 2 - POLAR_MARGIN
    average = share * len(world.tiles) / group.count
    per_chain = math.ceil(group.count / group.chains)
    for _ in range(group.chains):
        x, y = rng.randrange(world.width), rng.uniform(top + 4, bottom - 4)
        heading, bend = rng.uniform(0, math.tau), rng.uniform(-0.12, 0.12)
        for _ in range(per_chain):
            size = max(6, round(average * (1 + SIZE_SPREAD * (2 * rng.random() - 1))))
            radius = math.sqrt(size / REGION_FILL / math.pi)
            for _ in range(3):                        # a crowded spot: try a little further
                region = _island_region(world, x, y, radius, top, bottom)
                free = bool(region) and taken.isdisjoint(region)
                if free:
                    _grow_land(world, region, size, rng)
                    _take(world, taken, region)
                step = 2 * radius + CHAIN_GAP
                heading += bend * step
                x, y = x + math.cos(heading) * step, y + math.sin(heading) * step * 0.7
                if not top + 2 <= y <= bottom - 2:    # bounce off the polar seas
                    heading = -heading
                    y = min(max(y, top + 2), bottom - 2)
                if free:
                    break


def _island_region(world: WorldMap, x: float, y: float, radius: float, top: int,
                   bottom: int) -> list[int]:
    """A small ellipse, wider than tall, around (x, y)."""
    cx, cy = round(x), round(y)
    reach_x, reach_y = math.ceil(radius * 1.3), math.ceil(radius)
    region = []
    for dy in range(-reach_y, reach_y + 1):
        for dx in range(-reach_x, reach_x + 1):
            tile = world.tile(cx + dx, cy + dy)
            if tile is not None and top <= tile.y <= bottom and math.hypot(dx / 1.3, dy) <= radius:
                region.append(tile.index)
    return region


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
