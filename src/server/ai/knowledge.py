"""The AI's picture of the world at the start of its turn.

Everything here is derived from the PlayerView: explored tiles, own cities and units,
foreign cities remembered and foreign units in sight.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..engine.model.entities import City, CityMemory, Unit
from ..engine.model.worldmap import Tile
from ..engine.view import PlayerView


@dataclass
class Region:
    """A land mass as far as the player knows it: explored land tiles that touch each other."""
    id: int
    size: int = 0
    my_cities: list[City] = field(default_factory=list)
    foreign_cities: list[CityMemory] = field(default_factory=list)
    frontier: list[Tile] = field(default_factory=list)      # explored tiles next to the unknown
    sites: list[tuple[float, Tile]] = field(default_factory=list)   # (appeal, tile), best first


@dataclass
class Sea:
    """A body of water as far as the player knows it: explored sea tiles that touch."""
    id: int
    size: int = 0
    frontier: list[Tile] = field(default_factory=list)     # explored tiles next to the unknown
    ports: list[City] = field(default_factory=list)        # own cities on its shore
    regions: set[int] = field(default_factory=set)         # land regions on its shore


@dataclass
class Threat:
    """Enemy units seen close to a city."""
    units: list[Unit]
    strength: int           # sum of their attack strengths
    nearest: int            # distance of the closest one, in steps


class Knowledge:
    def __init__(self, view: PlayerView) -> None:
        self.view = view
        self.rules = view.rules
        world = view.map
        self.region_of: list[int] = [0] * len(world.tiles)   # 0 = sea or unexplored
        self.regions: dict[int, Region] = {}
        self.sea_of: list[int] = [0] * len(world.tiles)      # 0 = land or unexplored
        self.seas: dict[int, Sea] = {}
        self.cities = view.my_cities()
        self.units = view.my_units()
        self.enemy_units = view.visible_enemy_units()
        self.foreign_cities = view.known_foreign_cities()
        self.threats: dict[int, Threat] = {}
        self._label_regions()
        self._label_seas()
        self._locate_cities()
        self._find_threats()
        self._find_sites()

    # ── Regions ───────────────────────────────────────────────────────────────

    def _label_regions(self) -> None:
        """Flood fill of the explored land. A foreign city closes the way: the land behind
        it is another region, even on the same continent."""
        view, world = self.view, self.view.map

        def closed(tile: Tile) -> bool:
            return view.foreign_city_at(tile) is not None \
                and view.my_city_at(tile.x, tile.y) is None

        next_id = 1
        for start in world.tiles:
            if self.region_of[start.index] or not view.explored(start) or not view.is_land(start):
                continue
            if closed(start):
                continue                       # joins the region that reaches it first
            region = Region(next_id)
            stack = [start]
            self.region_of[start.index] = next_id
            while stack:
                tile = stack.pop()
                region.size += 1
                on_frontier = False
                for other in world.neighbors(tile):
                    if not view.explored(other):
                        on_frontier = True
                    elif not self.region_of[other.index] and view.is_land(other):
                        self.region_of[other.index] = next_id
                        if closed(other):
                            region.size += 1
                        else:
                            stack.append(other)
                if on_frontier:
                    region.frontier.append(tile)
            self.regions[next_id] = region
            next_id += 1
        # Foreign cities seen from the sea only, with no land explored around them.
        for tile in world.tiles:
            if not self.region_of[tile.index] and view.explored(tile) and view.is_land(tile):
                self.region_of[tile.index] = next_id
                self.regions[next_id] = Region(next_id, size=1)
                next_id += 1

    def _label_seas(self) -> None:
        view, world = self.view, self.view.map
        next_id = 1
        for start in world.tiles:
            if self.sea_of[start.index] or not view.explored(start) or view.is_land(start):
                continue
            sea = Sea(next_id)
            stack = [start]
            self.sea_of[start.index] = next_id
            while stack:
                tile = stack.pop()
                sea.size += 1
                on_frontier = False
                for other in world.neighbors(tile):
                    if not view.explored(other):
                        on_frontier = True
                    elif view.is_land(other):
                        region = self.region_of[other.index]
                        if region:
                            sea.regions.add(region)
                    elif not self.sea_of[other.index]:
                        self.sea_of[other.index] = next_id
                        stack.append(other)
                if on_frontier:
                    sea.frontier.append(tile)
            self.seas[next_id] = sea
            next_id += 1

    def seas_at(self, tile: Tile) -> set[int]:
        """Seas a unit on this tile can sail: the one it is on, or those along the shore."""
        own = self.sea_of[tile.index]
        if own:
            return {own}
        return {self.sea_of[t.index] for t in self.view.map.neighbors(tile)
                if self.sea_of[t.index]}

    def shore(self, region_id: int, sea_id: int, near: Tile, count: int = 4) -> list[Tile]:
        """Sea tiles of `sea_id` along the coast of a region, the closest to `near` first."""
        world = self.view.map
        result = []
        for tile in world.tiles_within(near.x, near.y, 8):
            if self.sea_of[tile.index] != sea_id:
                continue
            if any(self.region_of[t.index] == region_id for t in world.neighbors(tile)):
                result.append(tile)
        result.sort(key=lambda t: (world.steps(t.x, t.y, near.x, near.y), t.index))
        return result[:count]

    def region_at(self, x: int, y: int) -> Optional[Region]:
        tile = self.view.map.tile(x, y)
        if tile is None:
            return None
        return self.regions.get(self.region_of[tile.index])

    def same_region(self, a: Tile, b: Tile) -> bool:
        ra = self.region_of[a.index]
        return ra != 0 and ra == self.region_of[b.index]

    def _locate_cities(self) -> None:
        for city in self.cities:
            region = self.region_at(city.x, city.y)
            if region is not None:
                region.my_cities.append(city)
            for sea_id in sorted(self.seas_at(self.view.tile_of(city))):
                self.seas[sea_id].ports.append(city)
        for memory in self.foreign_cities:
            region = self.region_at(memory.x, memory.y)
            if region is not None:
                region.foreign_cities.append(memory)

    # ── Threats ───────────────────────────────────────────────────────────────

    def _find_threats(self) -> None:
        radius = int(self.rules.ai.get("strategy", "threat_radius"))
        world = self.view.map
        for city in self.cities:
            near = []
            for unit in self.enemy_units:
                definition = self.rules.units[unit.type]
                if definition.attack <= 0:
                    continue
                if world.steps(city.x, city.y, unit.x, unit.y) <= radius:
                    near.append(unit)
            if near:
                self.threats[city.id] = Threat(
                    units=near,
                    strength=sum(self.rules.units[u.type].attack for u in near),
                    nearest=min(world.steps(city.x, city.y, u.x, u.y) for u in near))

    def threatened(self, city: City) -> bool:
        return city.id in self.threats

    # ── City sites ────────────────────────────────────────────────────────────

    def _find_sites(self) -> None:
        """Explored tiles worth a city, ranked by quality and closeness to our cities."""
        view, world = self.view, self.view.map
        get = lambda name: self.rules.ai.get("strategy", name)
        min_score = get("min_site_score")
        min_distance = int(get("site_distance_min"))
        ideal = get("site_distance_ideal")
        radius = int(get("site_search_radius"))
        penalty = get("site_distance_penalty")

        anchors = [(c.x, c.y) for c in self.cities]
        if not anchors:
            # No city yet: the settlers look around themselves, and the closer the better
            # (an ideal distance would make them hesitate between two neighbouring tiles).
            anchors = [(u.x, u.y) for u in self.units
                       if self.rules.units[u.type].can("found_city")]
            ideal, penalty = 0, 0.0
        known_cities = view.known_city_positions()
        foreign = [(m.x, m.y) for m in self.foreign_cities]

        seen: set[int] = set()
        for ax, ay in anchors:
            for tile in world.tiles_within(ax, ay, radius):
                if tile.index in seen:
                    continue
                seen.add(tile.index)
                region_id = self.region_of[tile.index]
                if not region_id or tile.hut:
                    continue
                score = view.site_score(tile)
                if score < min_score:
                    continue
                if any(world.steps(tile.x, tile.y, x, y) < min_distance for x, y in known_cities):
                    continue
                # Leave the land around foreign cities to their owners.
                if any(world.steps(tile.x, tile.y, x, y) <= 3 for x, y in foreign):
                    continue
                if view.foreign_units_at(tile):
                    continue
                nearest = min((world.steps(tile.x, tile.y, x, y) for x, y in anchors), default=0)
                appeal = score - penalty * abs(nearest - ideal) - 0.15 * nearest
                self.regions[region_id].sites.append((appeal, tile))
        for region in self.regions.values():
            region.sites.sort(key=lambda s: (-s[0], s[1].index))

    def best_sites(self, region: Region, count: int, taken: list[Tile]) -> list[Tile]:
        """The best `count` sites of a region that leave room between each other."""
        min_distance = int(self.rules.ai.get("strategy", "site_distance_min"))
        world = self.view.map
        chosen: list[Tile] = []
        for _, tile in region.sites:
            if len(chosen) >= count:
                break
            if any(world.steps(tile.x, tile.y, t.x, t.y) < min_distance for t in chosen + taken):
                continue
            chosen.append(tile)
        return chosen

    # ── Forces ────────────────────────────────────────────────────────────────

    def units_with_role(self, role: str) -> list[Unit]:
        return [u for u in self.units if self.rules.units[u.type].role == role]

    def defenders_in(self, city: City) -> list[Unit]:
        """Military land units standing in the city."""
        tile = self.view.tile_of(city)
        return [u for u in self.view.my_units_at(tile)
                if self.rules.units[u.type].defense > 0 and self.rules.units[u.type].is_military
                and self.rules.units[u.type].domain == "land" and u.aboard is None]

    def own_power(self) -> float:
        """Comparable to PlayerView.known_strength for other civilizations."""
        return sum(c.size for c in self.cities)
