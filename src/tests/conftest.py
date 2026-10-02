"""Shared fixtures: the real rules, and small hand-made worlds for rule tests."""
from __future__ import annotations

import pytest

from server.engine.mapgen.continents import label_continents
from server.engine.model.entities import PEACE, WAR, Player
from server.engine.model.game import Game
from server.engine.model.worldmap import WorldMap
from server.engine.rules.loader import load_rules
from server.engine.systems import cities, visibility


@pytest.fixture(scope="session")
def rules():
    return load_rules()


def make_world(rules, width=16, height=12, terrain="grassland", patches=None):
    """A flat world of one terrain, with optional (x, y) -> terrain overrides."""
    world = WorldMap(width, height, True, terrain)
    for (x, y), terrain_id in (patches or {}).items():
        world.tile(x, y).terrain = terrain_id
    label_continents(world, rules)
    return world


def make_game(rules, civ_ids=("romans", "greeks"), relation=WAR, **world_options) -> Game:
    """A game on a hand-made world: barbarians as player 0, then the given civilizations."""
    game = Game(rules, seed=1, world=make_world(rules, **world_options))
    for civ_id in ("barbarians", *civ_ids):
        player = Player(id=len(game.players), civ=rules.civs[civ_id],
                        is_barbarian=(civ_id == "barbarians"))
        visibility.init_player(game, player)
        game.players.append(player)
    for a in range(1, len(game.players)):
        for b in range(a + 1, len(game.players)):
            game.relation(a, b).state = relation
    return game


def add_city(game: Game, player_id: int, x: int, y: int, size: int = 1):
    city = cities.found_city(game, game.players[player_id], game.map.tile(x, y), size=size)
    game.events.clear()
    return city


@pytest.fixture
def game(rules):
    return make_game(rules)


__all__ = ["make_game", "make_world", "add_city", "WAR", "PEACE"]
