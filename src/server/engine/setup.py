"""Creation of a new game: world, players and starting positions."""
from __future__ import annotations

import random
from typing import Optional, Sequence

from .mapgen.generator import generate_world
from .mapgen.sites import site_scores
from .model.entities import Player
from .model.game import Game
from .model.worldmap import Tile, WorldMap
from .rules.schema import Rules
from .systems import visibility

BARBARIANS = "barbarians"


def new_game(rules: Rules, seed: int, civ_ids: Optional[Sequence[str]] = None,
             player_count: Optional[int] = None) -> Game:
    """Builds a game ready for turn 0. The same seed always gives the same game."""
    world = generate_world(rules, seed)
    game = Game(rules, seed, world)
    rng = game.rng

    if civ_ids is None:
        count = player_count or rules.game.players.count
        playable = [c.id for c in rules.playable_civs]
        civ_ids = rng.sample(playable, min(count, len(playable)))

    settings = rules.game.players
    # Player 0 is always the barbarians, as in the original.
    for civ_id in [BARBARIANS, *civ_ids]:
        civ = rules.civs[civ_id]
        player = Player(id=len(game.players), civ=civ, is_barbarian=(civ_id == BARBARIANS),
                        gold=settings.start_gold, government=settings.start_government,
                        tax_rate=settings.start_rates.tax,
                        luxury_rate=settings.start_rates.luxury,
                        science_rate=settings.start_rates.science)
        visibility.init_player(game, player)
        game.players.append(player)

    starts = choose_start_positions(rules, world, len(civ_ids), rng)
    civilizations = [p for p in game.players if not p.is_barbarian]
    for player, tile in zip(civilizations, starts):
        for unit_type in settings.start_units:
            unit = game.add_unit(unit_type, player.id, tile.x, tile.y)
            visibility.reveal_unit(game, unit)
    for player in civilizations[len(starts):]:
        player.alive = False                      # no room on this world
    game.events.clear()
    return game


def choose_start_positions(rules: Rules, world: WorldMap, count: int,
                           rng: random.Random) -> list[Tile]:
    """Good city sites, far from each other, on continents with room to grow.

    Same idea as the original (StartGameMenu.cs F5_0000_07c7): draw random tiles and relax
    the requirements as the attempts pile up.
    """
    settings = rules.game.players
    scores = site_scores(rules, world)
    sites_per_continent: dict[int, int] = {}
    for tile, score in zip(world.tiles, scores):
        if score > 0:
            sites_per_continent[tile.continent] = sites_per_continent.get(tile.continent, 0) + 1

    margin_x, margin_y = world.width // 10, world.height * 4 // 25
    starts: list[Tile] = []
    for _ in range(count):
        chosen: Optional[Tile] = None
        for attempt in range(1, 4001):
            x = rng.randrange(world.width - 2 * margin_x) + margin_x
            y = rng.randrange(world.height - 2 * margin_y) + margin_y
            tile = world.tile(x, y)
            if not rules.terrains[tile.terrain].is_land or tile.hut:
                continue
            if scores[tile.index] < settings.start_min_site_score - attempt // 32:
                continue
            nearest = min((world.distance(x, y, s.x, s.y) for s in starts), default=99)
            if nearest < settings.start_min_distance - attempt // 64:
                continue
            if nearest < 3:
                continue
            room = sites_per_continent.get(tile.continent, 0)
            if room < max(4, settings.start_min_continent_sites - attempt // 32):
                continue
            chosen = tile
            break
        if chosen is None:
            break
        starts.append(chosen)
    return starts
