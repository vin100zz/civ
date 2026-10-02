"""The AI plays whole games: they must run, stay consistent and show signs of life."""
from __future__ import annotations

import pytest

from server.ai.controller import AIController
from server.ai.knowledge import Knowledge
from server.ai import pathfinding
from server.engine.model.entities import SPECIALISTS
from server.engine.systems import turn
from server.engine.view import PlayerView
from server.sim.metrics import Metrics
from server.sim.runner import create_game

from .conftest import add_city, make_game


def play(game, turns, metrics=None):
    for _ in range(turns):
        if game.finished:
            break
        game.events.clear()
        turn.play_turn(game)
        if metrics is not None:
            metrics.record(game)
    return game


def check_consistency(game):
    """Invariants of the game state that no sequence of actions may break."""
    for unit in game.units.values():
        tile = game.tile_of(unit)
        assert unit.id in tile.unit_ids
        assert game.players[unit.owner].alive
        definition = game.rules.units[unit.type]
        on_land = game.rules.terrains[tile.terrain].is_land
        if unit.aboard is not None:
            ship = game.units[unit.aboard]                  # the ship exists and is right here
            assert ship.pos == unit.pos and ship.owner == unit.owner
            assert game.rules.units[ship.type].carries == definition.domain
            assert len(game.cargo_of(ship)) <= game.rules.units[ship.type].capacity
        if definition.domain == "land":
            assert on_land or unit.aboard is not None       # nobody walks on water
        elif definition.domain == "sea":
            assert not on_land or tile.city_id is not None  # ships stay at sea or in port
        if unit.home_city is not None and unit.home_city in game.cities:
            assert game.cities[unit.home_city].owner == unit.owner
    for tile in game.map.tiles:
        owners = {game.units[uid].owner for uid in tile.unit_ids}
        assert len(owners) <= 1, f"mixed stack at {tile.pos}"
        if tile.city_id is not None and owners:
            assert owners == {game.cities[tile.city_id].owner}
    for city in game.cities.values():
        assert game.tile_of(city).city_id == city.id
        assert city.size >= 1
        assert len(city.worked) + city.specialist_count == city.size
        assert set(city.specialists) == set(SPECIALISTS)
        assert len(set(city.worked)) == len(city.worked)
        for dx, dy in city.worked:
            assert game.map.tile(city.x + dx, city.y + dy).worked_by == city.id
    for wonder_id, city_id in game.wonders.items():
        assert wonder_id in game.cities[city_id].buildings
    for player in game.players:
        assert player.gold >= 0
        assert player.tax_rate + player.luxury_rate + player.science_rate == 100


@pytest.fixture(scope="module")
def played(rules):
    """One game played for 180 turns, shared by the tests below."""
    game = create_game(rules, 42)
    metrics = Metrics()
    play(game, 180, metrics)
    return game, metrics


def test_game_stays_consistent(rules):
    game = create_game(rules, 7)
    for _ in range(12):
        play(game, 10)
        check_consistency(game)


@pytest.mark.slow
def test_late_game_stays_consistent(rules):
    """Ships, aircraft, pollution and the space race: a whole game to its end."""
    game = create_game(rules, 3)
    while not game.finished:
        play(game, 25)
        check_consistency(game)
    assert game.winner is not None and game.victory in ("spaceship", "conquest", "score")
    assert any(rules.units[u.type].domain == "sea" for u in game.units.values())


def test_same_seed_same_game(rules):
    def summary(game):
        return [(p.civ.id, len(game.player_cities(p.id)), p.tech_count, p.gold)
                for p in game.players]
    assert summary(play(create_game(rules, 5), 60)) == summary(play(create_game(rules, 5), 60))


def test_civilizations_develop(played):
    game, metrics = played
    civilizations = game.civilizations
    assert len(civilizations) >= 5
    assert all(game.player_cities(p.id) for p in civilizations)
    city_counts = sorted(len(game.player_cities(p.id)) for p in civilizations)
    assert city_counts[len(city_counts) // 2] >= 3          # the median civ has expanded
    assert sum(p.tech_count for p in civilizations) / len(civilizations) >= 8
    assert metrics.event_counts["city_founded"] >= 20
    assert metrics.event_counts["building"] >= 20


def test_no_stuck_ai(played):
    game, metrics = played
    assert metrics.problems(game) == []


def test_decisions_are_explained(played):
    game, _ = played
    for player in game.civilizations:
        controller = game.controllers[player.id]
        assert isinstance(controller, AIController)
        assert controller.debug["turn"] == game.turn - 1
        assert controller.decisions
        for decision in controller.decisions.values():
            assert decision.candidates and decision.chosen is decision.candidates[0]
            assert all(c.reason for c in decision.candidates)


def test_ai_only_plans_through_explored_land(rules):
    game = make_game(rules, width=30)
    add_city(game, 1, 5, 5)
    unit = game.add_unit("militia", 1, 5, 5)
    player = game.players[1]
    view = PlayerView(game, player)
    far = game.map.tile(20, 5)
    assert not view.explored(far)
    assert pathfinding.find_path(view, unit, far) is None
    assert view.site_score(far) == 0
    know = Knowledge(view)
    explored_land = sum(1 for t in game.map.tiles if view.explored(t))
    assert sum(r.size for r in know.regions.values()) == explored_land
    for region in know.regions.values():
        assert all(view.explored(tile) for _, tile in region.sites)


def test_view_hides_what_is_out_of_sight(rules):
    game = make_game(rules, width=30)
    add_city(game, 1, 5, 5)
    hidden = game.add_unit("legion", 2, 20, 5)
    seen = game.add_unit("legion", 2, 6, 6)
    view = PlayerView(game, game.players[1])
    visible_ids = {u.id for u in view.visible_foreign_units()}
    assert seen.id in visible_ids and hidden.id not in visible_ids
    assert view.attack_odds(game.add_unit("militia", 1, 5, 5), game.tile_of(hidden)) is None
    foreign_city = add_city(game, 2, 22, 5)
    assert foreign_city.id not in {m.city_id for m in view.known_foreign_cities()}


def test_railroads_do_not_trap_explorers(rules):
    """Railroads cost no movement: a wandering unit must still end its turn."""
    game = make_game(rules, width=30, patches={(x, 4): "ocean" for x in range(30)})
    for tile in game.map.tiles:
        tile.road = tile.railroad = True
    add_city(game, 1, 5, 8)
    game.add_unit("cavalry", 1, 5, 8)
    game.add_unit("cavalry", 1, 6, 8)
    game.controllers[1] = AIController()
    player = game.players[1]
    for _ in range(5):
        turn.begin_player_turn(game, player)
        game.controllers[1].play_turn(game, player)
        turn.end_player_turn(game, player)
        game.turn += 1
    assert sum(player.explored) > 60
