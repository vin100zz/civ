"""Barbarian raids.

As in Civ 1 barbarians land from the sea near a coastal city. They also (own addition, so
that inland cities are not safe) gather in the wilderness, out of sight of every
civilization.
"""
from __future__ import annotations

from typing import Optional

from ..model.entities import City
from ..model.game import Game
from ..model.worldmap import Tile
from ..rules.schema import BarbarianTier
from . import production


def maybe_spawn(game: Game) -> None:
    settings = game.rules.game.barbarians
    barbarians = game.barbarians
    if not settings.enabled or barbarians is None or game.turn < settings.first_turn:
        return
    if game.rng.random() >= settings.spawn_chance_per_turn:
        return
    targets = [c for c in game.cities.values() if not game.players[c.owner].is_barbarian]
    tier = production.barbarian_tier(game)
    if not targets or tier is None or not tier.units:
        return
    city = targets[game.rng.randrange(len(targets))]
    low, high = settings.group_size
    count = game.rng.randint(low, high)
    by_sea = (tier.ship is not None and "sea" in game.rules.game.enabled_unit_domains
              and game.rng.random() < settings.sea_raid_chance)
    if by_sea and _sea_raid(game, city, tier, count):
        return
    tile = _find_camp(game, city.x, city.y)
    if tile is None:
        return
    for _ in range(count):
        game.add_unit(tier.units[game.rng.randrange(len(tier.units))], barbarians.id,
                      tile.x, tile.y)
    game.emit("barbarians", f"Barbarians gather near {city.name}.", player=barbarians.id,
              x=tile.x, y=tile.y, city=city.id, count=count)


def _sea_raid(game: Game, city: City, tier: BarbarianTier, count: int) -> bool:
    """A ship full of raiders appears off the coast of the city. False if it has no coast."""
    barbarians = game.barbarians
    tile = _find_anchorage(game, city)
    if tile is None:
        return False
    ship = game.add_unit(tier.ship, barbarians.id, tile.x, tile.y)
    count = min(count, game.rules.units[tier.ship].capacity)
    for _ in range(count):
        raider = game.add_unit(tier.units[game.rng.randrange(len(tier.units))], barbarians.id,
                               tile.x, tile.y)
        raider.aboard = ship.id
    game.emit("barbarians", f"Barbarian ships are sighted off {city.name}.",
              player=barbarians.id, x=tile.x, y=tile.y, city=city.id, count=count)
    return True


def _find_anchorage(game: Game, city: City) -> Optional[Tile]:
    """A free, unseen sea tile at raiding distance, on a sea that reaches the city."""
    settings = game.rules.game.barbarians
    seas = {t.continent for t in game.map.neighbors(game.tile_of(city))
            if not game.terrain(t).is_land}
    if not seas:
        return None
    candidates = []
    for tile in game.map.tiles_within(city.x, city.y, settings.max_distance_from_city):
        if tile.continent not in seas or tile.unit_ids or game.terrain(tile).is_land:
            continue
        if game.map.steps(tile.x, tile.y, city.x, city.y) < settings.min_distance_from_city:
            continue
        if any(p.visible[tile.index] for p in game.civilizations):
            continue
        candidates.append(tile)
    if not candidates:
        return None
    return candidates[game.rng.randrange(len(candidates))]


def _find_camp(game: Game, x: int, y: int) -> Optional[Tile]:
    """A free land tile on the same continent, far enough from every city and unseen."""
    settings = game.rules.game.barbarians
    origin = game.map.tile(x, y)
    candidates = []
    for tile in game.map.tiles_within(x, y, settings.max_distance_from_city):
        if tile.continent != origin.continent or tile.unit_ids or tile.city_id is not None:
            continue
        if not game.terrain(tile).is_land:
            continue
        nearest = min(game.map.steps(tile.x, tile.y, c.x, c.y) for c in game.cities.values())
        if nearest < settings.min_distance_from_city:
            continue
        if any(p.visible[tile.index] for p in game.civilizations):
            continue
        candidates.append(tile)
    if not candidates:
        return None
    return candidates[game.rng.randrange(len(candidates))]
