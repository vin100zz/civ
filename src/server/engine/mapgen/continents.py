"""Numbers land masses and ocean bodies.

Land tiles get positive ids (1 = largest continent), ocean tiles negative ids (-1 = largest
ocean). Two land tiles belong to the same continent when a land unit can walk from one to
the other (8 directions).
"""
from __future__ import annotations

from ..model.worldmap import WorldMap
from ..rules.schema import Rules


def label_continents(world: WorldMap, rules: Rules) -> None:
    for tile in world.tiles:
        tile.continent = 0

    groups: dict[bool, list[list[int]]] = {True: [], False: []}
    seen = [False] * len(world.tiles)
    for start in world.tiles:
        if seen[start.index]:
            continue
        is_land = rules.terrains[start.terrain].is_land
        members = []
        stack = [start]
        seen[start.index] = True
        while stack:
            tile = stack.pop()
            members.append(tile.index)
            for other in world.neighbors(tile):
                if not seen[other.index] and rules.terrains[other.terrain].is_land == is_land:
                    seen[other.index] = True
                    stack.append(other)
        groups[is_land].append(members)

    world.continent_sizes = {}
    for is_land, sign in ((True, 1), (False, -1)):
        ordered = sorted(groups[is_land], key=lambda m: (-len(m), m[0]))
        for rank, members in enumerate(ordered, start=1):
            for index in members:
                world.tiles[index].continent = sign * rank
            world.continent_sizes[sign * rank] = len(members)
