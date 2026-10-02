"""Random world generation, following the eight stages of the original game.

Source: OpenCivOne MapInitAndIntro.cs F7_0000_0012_GenerateMap, and MapManagement.cs for the
special resource and hut patterns. The stages are kept in the original order; only the
continent numbering (stage 6) is our own, because it has no gameplay effect.
"""
from __future__ import annotations

import random

from ..model.worldmap import CARDINALS, DIRECTIONS, Tile, WorldMap
from ..rules.schema import MapSettings, Rules
from .continents import label_continents

OCEAN, PLAINS, GRASSLAND, FOREST, HILLS, MOUNTAINS = (
    "ocean", "plains", "grassland", "forest", "hills", "mountains")
DESERT, TUNDRA, ARCTIC, SWAMP, JUNGLE, RIVER = (
    "desert", "tundra", "arctic", "swamp", "jungle", "river")

# Neighbourhood used when a new river turns nearby forests into jungle: every tile
# within two steps of the river source except the corners (MoveDirections[1..20]).
_RIVER_SOURCE_AREA = [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3)
                      if (dx, dy) != (0, 0) and not (abs(dx) == 2 and abs(dy) == 2)]


def generate_world(rules: Rules, seed: int) -> WorldMap:
    settings = rules.game.map
    rng = random.Random(seed)
    world = WorldMap(settings.width, settings.height, settings.wrap_x, OCEAN)

    _raise_land(world, settings, rng)
    _apply_temperature(world, settings, rng)
    _apply_climate(world, settings, rng)
    _apply_age(world, settings, rng)
    _carve_rivers(world, settings, rng)
    _add_polar_caps(world, rng)
    label_continents(world, rules)
    _place_resources_and_huts(world, rules, seed)
    return world


# ── Stage 1: continents ───────────────────────────────────────────────────────

def _raise_land(world: WorldMap, settings: MapSettings, rng: random.Random) -> None:
    """Drops random-walk "clouds" of land; overlaps become hills, then mountains."""
    w, h = world.width, world.height
    target = (settings.land_mass + 2) * (w * h * 2 // 25)       # land_mass * 320 + 640 on 80x50
    margin_x, margin_y = max(2, w // 20), max(4, h // 6)
    raised = 0
    while raised < target:
        cloud: set[int] = set()
        x = rng.randrange(w - 2 * margin_x) + margin_x
        y = rng.randrange(h - 2 * margin_y) + margin_y
        size = rng.randrange(64) + 1
        while True:
            for dx, dy in ((0, 0),) + CARDINALS:
                tile = world.tile(x + dx, y + dy)
                if tile is not None:
                    cloud.add(tile.index)
            dx, dy = CARDINALS[rng.randrange(4)]
            x = (x + dx) % w
            y += dy
            size -= 1
            if not (size > 0 and 4 < y < h - 5):
                break
        for index in cloud:
            tile = world.tiles[index]
            if tile.terrain == OCEAN:
                tile.terrain = PLAINS
            elif tile.terrain == PLAINS:
                tile.terrain = HILLS
            elif tile.terrain == HILLS:
                tile.terrain = MOUNTAINS
        raised += len(cloud)


# ── Stage 2: temperature ──────────────────────────────────────────────────────

def _apply_temperature(world: WorldMap, settings: MapSettings, rng: random.Random) -> None:
    """Plains become desert near the equator, tundra and arctic near the poles."""
    equator = world.height * 29 // 50
    band = max(1, world.height * 6 // 50)
    for x in range(world.width):
        for y in range(world.height):
            tile = world.tile(x, y)
            if tile.terrain != PLAINS:
                continue
            zone = (abs(rng.randrange(8) + y - equator) + (1 - settings.temperature)) // band + 1
            if zone <= 1:
                tile.terrain = DESERT
            elif zone in (4, 5):
                tile.terrain = TUNDRA
            elif zone >= 6:
                tile.terrain = ARCTIC


# ── Stage 3: climate (rain carried by the winds) ──────────────────────────────

def _apply_climate(world: WorldMap, settings: MapSettings, rng: random.Random) -> None:
    dryness = max(1, 7 - settings.climate * 2)
    middle = world.height // 2
    for y in range(world.height):
        latitude = abs(middle - y)

        # West to east.
        wet = 0
        for x in range(world.width):
            tile = world.tile(x, y)
            if tile.terrain == OCEAN:
                if abs(12 - latitude) + settings.climate * 4 > wet:
                    wet += 1
            elif wet > 0:
                wet -= rng.randrange(dryness)
                if tile.terrain == PLAINS:
                    tile.terrain = GRASSLAND
                elif tile.terrain == TUNDRA:
                    tile.terrain = ARCTIC
                elif tile.terrain == HILLS:
                    tile.terrain = FOREST
                elif tile.terrain == MOUNTAINS:
                    wet -= 3
                elif tile.terrain == DESERT:
                    tile.terrain = PLAINS

        # East to west.
        wet = 0
        for x in range(world.width - 1, -1, -1):
            tile = world.tile(x, y)
            if tile.terrain == OCEAN:
                if latitude // 2 + settings.climate > wet:
                    wet += 1
            elif wet > 0:
                wet -= rng.randrange(dryness)
                if tile.terrain in (SWAMP, HILLS):
                    tile.terrain = FOREST
                elif tile.terrain == PLAINS:
                    tile.terrain = GRASSLAND
                elif tile.terrain == GRASSLAND:
                    tile.terrain = JUNGLE if latitude < 10 else SWAMP
                    wet = -2
                elif tile.terrain == MOUNTAINS:
                    wet -= 3
                    tile.terrain = FOREST
                elif tile.terrain == DESERT:
                    tile.terrain = PLAINS


# ── Stage 4: age (erosion) ────────────────────────────────────────────────────

_AGING = {
    FOREST: JUNGLE, SWAMP: GRASSLAND, PLAINS: HILLS, TUNDRA: HILLS, GRASSLAND: FOREST,
    JUNGLE: SWAMP, HILLS: MOUNTAINS, ARCTIC: MOUNTAINS, DESERT: PLAINS,
}


def _apply_age(world: WorldMap, settings: MapSettings, rng: random.Random) -> None:
    x = y = 0
    for i in range(800 + 800 * settings.age):
        if i & 1:
            dx, dy = DIRECTIONS[rng.randrange(8)]
            x, y = x + dx, y + dy
        else:
            x, y = rng.randrange(world.width), rng.randrange(world.height)
        tile = world.tile(x, y)
        if tile is None:
            continue
        if tile.terrain == MOUNTAINS:
            # An old mountain surrounded by land collapses into a lake.
            corners = [world.tile(x + dx, y + dy) for dx, dy in ((-1, -1), (-1, 1), (1, -1), (1, 1))]
            if all(c is not None and c.terrain != OCEAN for c in corners):
                tile.terrain = OCEAN
        elif tile.terrain in _AGING:
            tile.terrain = _AGING[tile.terrain]


# ── Stage 5: rivers ───────────────────────────────────────────────────────────

def _carve_rivers(world: WorldMap, settings: MapSettings, rng: random.Random) -> None:
    """Rivers start on hills and wander until they reach the sea or another river."""
    wanted = (settings.land_mass + settings.climate) * 2 + 6
    made = 0
    for _ in range(256):
        if made > wanted:
            break
        hills = [t for t in world.tiles if t.terrain == HILLS]
        if not hills:
            break
        backup = [t.terrain for t in world.tiles]
        source = hills[rng.randrange(len(hills))]
        x, y = source.x, source.y
        direction = rng.randrange(4) * 2           # index into DIRECTIONS: N, E, S, W
        length = 0
        reached_sea = False
        while True:
            world.tile(x, y).terrain = RIVER
            for dx, dy in CARDINALS:
                near = world.tile(x + dx, y + dy)
                if near is not None and near.terrain == OCEAN:
                    reached_sea = True
            direction = ((rng.randrange(2) - (length & 1)) * 2 + direction) & 7
            dx, dy = DIRECTIONS[direction]
            x, y = x + dx, y + dy
            length += 1
            ahead = world.tile(x, y)
            ahead_terrain = ahead.terrain if ahead is not None else OCEAN
            if reached_sea or ahead_terrain in (OCEAN, RIVER, MOUNTAINS):
                break
        if (not reached_sea and ahead_terrain != RIVER) or length < 5:
            for tile, terrain in zip(world.tiles, backup):
                tile.terrain = terrain
            continue
        made += 1
        for dx, dy in _RIVER_SOURCE_AREA:
            near = world.tile(source.x + dx, source.y + dy)
            if near is not None and near.terrain == FOREST:
                near.terrain = JUNGLE


# ── Stage 8: polar caps ───────────────────────────────────────────────────────

def _add_polar_caps(world: WorldMap, rng: random.Random) -> None:
    last = world.height - 1
    for x in range(world.width):
        world.tile(x, 0).terrain = ARCTIC
        world.tile(x, last).terrain = ARCTIC
    for _ in range(world.width // 4):
        world.tile(rng.randrange(world.width), 0).terrain = TUNDRA
        world.tile(rng.randrange(world.width), 1).terrain = TUNDRA
        x = rng.randrange(world.width)
        # Keep the southern cap from merging with a continent.
        if all(world.tile(x + dx, last - 2).terrain == OCEAN for dx in (-1, 0, 1)):
            world.tile(x, last - 1).terrain = TUNDRA
        world.tile(rng.randrange(world.width), last).terrain = TUNDRA


# ── Special resources, shield pattern, huts ───────────────────────────────────

def has_shield_pattern(x: int, y: int) -> bool:
    """Tiles of the fixed pattern that gives grassland and rivers one extra shield."""
    return ((7 * x + 11 * y) & 2) == 0


def _place_resources_and_huts(world: WorldMap, rules: Rules, seed: int) -> None:
    """One special resource per 4x4 block and one hut every other block, from the seed.

    Source: OpenCivOne MapManagement.cs CellHasSpecialResource / CellHasMinorTribeHut.
    """
    huts = rules.game.huts.enabled
    for tile in world.tiles:
        x, y = tile.x, tile.y
        tile.pattern = has_shield_pattern(x, y)
        tile.special = False
        tile.hut = False
        if not 1 < y < world.height - 2:
            continue
        slot = (x & 3) * 4 + (y & 3)
        block = (x // 4) * 13 + (y // 4) * 11 + seed
        terrain = rules.terrains[tile.terrain]
        if slot == (block & 0xF) and terrain.special is not None:
            tile.special = True
        if huts and terrain.is_land and slot == ((block + 8) & 0x1F):
            tile.hut = True


def set_terrain(world: WorldMap, tile: Tile, terrain_id: str) -> None:
    """Changes a tile's terrain after generation (irrigation or mining that transforms it)."""
    tile.terrain = terrain_id
    tile.irrigation = False
    tile.mine = False
