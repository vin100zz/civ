"""The world map: a grid of tiles, cylindrical (wraps east-west)."""
from __future__ import annotations

from typing import Iterator, Optional

# The 8 neighbours, clockwise from north. Odd indexes are diagonals.
DIRECTIONS: tuple[tuple[int, int], ...] = (
    (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1),
)
CARDINALS: tuple[tuple[int, int], ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))

# The 20 tiles a city can work (the "fat cross"), inner ring first. The city tile itself
# (0, 0) is always worked and is not part of this list.
CITY_RING_INNER: tuple[tuple[int, int], ...] = (
    (0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, 1), (-1, -1),
)
CITY_RING_OUTER: tuple[tuple[int, int], ...] = (
    (0, -2), (2, 0), (0, 2), (-2, 0), (-1, -2), (1, -2), (2, -1), (2, 1),
    (1, 2), (-1, 2), (-2, 1), (-2, -1),
)
CITY_OFFSETS: tuple[tuple[int, int], ...] = CITY_RING_INNER + CITY_RING_OUTER


class Tile:
    __slots__ = ("x", "y", "index", "terrain", "special", "pattern", "hut", "road", "railroad",
                 "irrigation", "mine", "fortress", "pollution", "continent", "city_id",
                 "unit_ids", "worked_by")

    def __init__(self, x: int, y: int, index: int, terrain: str) -> None:
        self.x = x
        self.y = y
        self.index = index
        self.terrain = terrain
        self.special = False        # carries the terrain's special resource
        self.pattern = False        # on the fixed "shield" pattern (grassland, river)
        self.hut = False
        self.road = False
        self.railroad = False
        self.irrigation = False
        self.mine = False
        self.fortress = False
        self.pollution = False
        self.continent = 0          # land mass or ocean body id (see mapgen.continents)
        self.city_id: Optional[int] = None
        self.unit_ids: list[int] = []
        self.worked_by: Optional[int] = None   # id of the city working this tile

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    def __repr__(self) -> str:
        return f"Tile({self.x},{self.y} {self.terrain})"


class WorldMap:
    def __init__(self, width: int, height: int, wrap_x: bool, default_terrain: str) -> None:
        self.width = width
        self.height = height
        self.wrap_x = wrap_x
        self.tiles: list[Tile] = [
            Tile(x, y, y * width + x, default_terrain)
            for y in range(height) for x in range(width)
        ]
        self._neighbors: list[tuple[Tile, ...]] = []
        self.continent_sizes: dict[int, int] = {}
        self._build_adjacency()

    # ── Access ────────────────────────────────────────────────────────────────

    def tile(self, x: int, y: int) -> Optional[Tile]:
        """Tile at (x, y); x wraps around the world, y does not."""
        if y < 0 or y >= self.height:
            return None
        if self.wrap_x:
            x %= self.width
        elif x < 0 or x >= self.width:
            return None
        return self.tiles[y * self.width + x]

    def __iter__(self) -> Iterator[Tile]:
        return iter(self.tiles)

    def neighbors(self, tile: Tile) -> tuple[Tile, ...]:
        """The up to 8 tiles around `tile`."""
        return self._neighbors[tile.index]

    def cardinal_neighbors(self, tile: Tile) -> list[Tile]:
        result = []
        for dx, dy in CARDINALS:
            other = self.tile(tile.x + dx, tile.y + dy)
            if other is not None:
                result.append(other)
        return result

    def city_area(self, x: int, y: int) -> list[tuple[tuple[int, int], Tile]]:
        """((dx, dy), tile) for the 20 tiles a city at (x, y) can work."""
        result = []
        for offset in CITY_OFFSETS:
            other = self.tile(x + offset[0], y + offset[1])
            if other is not None:
                result.append((offset, other))
        return result

    def tiles_within(self, x: int, y: int, radius: int) -> list[Tile]:
        """All tiles in the square of the given radius around (x, y), centre included."""
        result = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                other = self.tile(x + dx, y + dy)
                if other is not None:
                    result.append(other)
        return result

    # ── Geometry ──────────────────────────────────────────────────────────────

    def dx(self, x1: int, x2: int) -> int:
        """Signed shortest horizontal offset from x1 to x2."""
        d = x2 - x1
        if self.wrap_x:
            half = self.width // 2
            if d > half:
                d -= self.width
            elif d < -half:
                d += self.width
        return d

    def steps(self, x1: int, y1: int, x2: int, y2: int) -> int:
        """Number of moves between two tiles ignoring terrain (diagonals count as one)."""
        return max(abs(self.dx(x1, x2)), abs(y2 - y1))

    def distance(self, x1: int, y1: int, x2: int, y2: int) -> int:
        """Distance as Civ 1 measures it: longest axis plus half the shortest.

        Source: OpenCivOne GameTools.cs F0_2dc4_0289_GetShortestDistance.
        """
        w = abs(self.dx(x1, x2))
        h = abs(y2 - y1)
        return w + h // 2 if w > h else h + w // 2

    # ── Internals ─────────────────────────────────────────────────────────────

    def _build_adjacency(self) -> None:
        self._neighbors = []
        for tile in self.tiles:
            around = []
            for dx, dy in DIRECTIONS:
                other = self.tile(tile.x + dx, tile.y + dy)
                if other is not None and other is not tile:
                    around.append(other)
            self._neighbors.append(tuple(around))
