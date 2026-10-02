"""Pollution, global warming, nuclear weapons, the space race, victory and saved games (M7)."""
from __future__ import annotations

import json

import pytest

from server.engine import actions, persistence
from server.engine import effects as fx
from server.engine.model.entities import Item
from server.ai.controller import AIController
from server.engine.systems import (cities, city as city_rules, movement, nuclear, pollution,
                                   production, spaceship, turn, visibility)
from server.sim.runner import create_game, restore_game

from .conftest import add_city, make_game
from .test_ai import check_consistency, play
from .test_units import RiggedRandom, start


# ── Pollution ─────────────────────────────────────────────────────────────────

def test_industry_and_population_pollute(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=16)
    settings = rules.game.pollution

    def index(shields=80):
        return pollution.pollution_index(game, city, shields, fx.city_effects(game, city))

    assert index(15) == 0                                   # a small industry is harmless
    assert index() == 80 - settings.tolerance
    game.players[1].techs.update({"industrialization", "automobile"})
    assert index() == 80 - settings.tolerance + city.size * 2 // 4
    city.buildings.add("mass_transit")
    assert index() == 80 - settings.tolerance
    city.buildings.update({"factory", "hydro_plant"})
    assert index() == 40 - settings.tolerance
    city.buildings.add("recycling_cntr")                    # the cleanest building wins
    assert index() == int(80 * 34 / 100) - settings.tolerance
    assert city_rules.compute_city(game, city).pollution == \
        index(city_rules.compute_city(game, city).shields)


def test_small_cities_do_not_pollute(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=3)
    assert city.stats.pollution == 0
    pollution.pollute(game, city)
    assert not any(t.pollution for t in game.map.tiles)


def test_pollution_spoils_a_tile_and_settlers_clean_it(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=3)
    city.stats.pollution = 40
    game.rng = RiggedRandom([0, 0])                # the roll, then the tile
    pollution.pollute(game, city)
    polluted = [t for t in game.map.tiles if t.pollution]
    assert len(polluted) == 1 and [e["type"] for e in game.events] == ["pollution"]
    tile = polluted[0]

    spoiled = city_rules.tile_yields(game, city, tile)
    tile.pollution = False
    assert spoiled.food < city_rules.tile_yields(game, city, tile).food
    tile.pollution = True

    settlers = game.add_unit("settlers", 1, tile.x, tile.y)
    start(game, 1)
    assert actions.apply(game, 1, actions.SetOrder(settlers.id, "clean"))
    for _ in range(rules.game.movement.pollution_clean_turns):
        start(game, 1)
    assert not tile.pollution and settlers.order == "none"
    assert not actions.apply(game, 1, actions.SetOrder(settlers.id, "clean"))


def test_pollution_lowers_the_score(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=3)
    turn.update_scores(game)
    before = game.players[1].score
    game.map.tile(6, 5).pollution = True
    turn.update_scores(game)
    assert game.players[1].score == max(0, before + rules.game.score.polluted_tile)


def test_global_warming_floods_the_coast(rules):
    ocean = {(x, y): "ocean" for x in range(8, 16) for y in range(12)}
    game = make_game(rules, patches=ocean)
    settings = rules.game.pollution
    peninsula = game.map.tile(7, 5)
    for other in game.map.neighbors(peninsula):
        other.terrain = "ocean"                    # surrounded by the sea
    for tile in game.map.tiles[:12]:
        tile.pollution = True
    turns = 0
    while game.warming_count == 0 and turns < 60:
        pollution.global_warming(game)
        turns += 1
    assert game.warming_count == 1 and game.warming_level == 0
    assert turns == settings.warming_threshold + 1          # one degree a turn
    assert peninsula.terrain == settings.warming_coastal["grassland"]
    changed = [t for t in game.map.tiles if t.terrain not in ("grassland", "ocean")]
    assert len(changed) > 1                                 # part of the inland dried up
    assert [e["type"] for e in game.events] == ["global_warming"]


def test_clean_planet_does_not_warm(rules):
    game = make_game(rules)
    for _ in range(50):
        pollution.global_warming(game)
    assert game.warming_level == 0 and game.warming_count == 0


# ── Nuclear weapons ───────────────────────────────────────────────────────────

def test_nuclear_weapons_need_the_manhattan_project(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5)
    other = add_city(game, 2, 10, 5)
    game.players[1].techs.add("rocketry")
    bomb = Item("unit", "nuclear")
    assert not production.can_build(game, city, bomb)
    other.buildings.add("manhattan_project")       # built by anybody
    game.wonders["manhattan_project"] = other.id
    assert production.can_build(game, city, bomb)


def test_nuclear_strike(rules):
    game = make_game(rules)
    target = add_city(game, 2, 8, 5, size=9)
    garrison = [game.add_unit("riflemen", 2, 8, 5), game.add_unit("armor", 2, 9, 5)]
    far = game.add_unit("riflemen", 2, 11, 5)
    missile = game.add_unit("nuclear", 1, 7, 5)
    game.rng = RiggedRandom([], chance=0.0)        # fallout everywhere
    start(game, 1)
    result = actions.apply(game, 1, actions.MoveUnit(missile.id, 8, 5))
    assert result.ok and result.outcome == "nuked"
    assert missile.id not in game.units
    assert all(u.id not in game.units for u in garrison) and far.id in game.units
    assert target.size == 5                                         # half the city is gone
    assert len(target.worked) + target.specialist_count == target.size
    around = game.map.neighbors(game.map.tile(8, 5))
    assert all(t.pollution for t in around) and not game.map.tile(8, 5).pollution
    assert [e["type"] for e in game.events] == ["nuclear"]


def test_sdi_defense_stops_a_nuclear_strike(rules):
    game = make_game(rules)
    target = add_city(game, 2, 8, 5, size=9)
    target.buildings.add("sdi_defense")
    defender = game.add_unit("riflemen", 2, 8, 5)
    missile = game.add_unit("nuclear", 1, 7, 5)
    start(game, 1)
    assert actions.apply(game, 1, actions.MoveUnit(missile.id, 8, 5)).outcome == "nuked"
    assert missile.id not in game.units and defender.id in game.units and target.size == 9
    assert game.events[0]["stopped"] is True


def test_nuclear_plant_melts_down_during_disorder(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=8)
    city.buildings.update({"factory", "nuclear_plant"})
    unit = game.add_unit("riflemen", 1, 5, 5)
    game.rng = RiggedRandom([], chance=0.0)
    assert not nuclear.maybe_meltdown(game, city)            # no disorder, no accident
    city.disorder = True
    assert nuclear.maybe_meltdown(game, city)
    assert "nuclear_plant" not in city.buildings and city.size == 4
    assert unit.id not in game.units
    assert game.events[0]["type"] == "meltdown"

    city.buildings.add("nuclear_plant")
    game.players[1].techs.add("fusion_power")                # fusion makes the plant safe
    assert not nuclear.maybe_meltdown(game, city)


def test_ai_uses_its_nuclear_weapons(rules):
    game = make_game(rules, width=24)
    add_city(game, 1, 5, 5)
    game.add_unit("riflemen", 1, 5, 5)
    missile = game.add_unit("nuclear", 1, 5, 5)
    target = add_city(game, 2, 13, 5, size=8)
    visibility.remember_city(game, game.players[1], target)      # seen earlier in the war
    game.controllers[1] = AIController()
    player = game.players[1]
    turn.begin_player_turn(game, player)
    game.controllers[1].play_turn(game, player)
    turn.end_player_turn(game, player)
    assert missile.id not in game.units and target.size == 4
    assert "nuclear" in [e["type"] for e in game.events]


# ── The space race ────────────────────────────────────────────────────────────

def space_game(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=8)
    other = add_city(game, 2, 12, 5)
    game.players[1].techs.update({"space_flight", "plastics", "robotics"})
    return game, city, other


def test_spaceship_parts_need_the_apollo_program(rules):
    game, city, other = space_game(rules)
    part = Item("building", "ss_structural")
    assert not production.can_build(game, city, part)
    other.buildings.add("apollo_program")
    game.wonders["apollo_program"] = other.id
    assert production.can_build(game, city, part)

    city.production = part
    city.shields = rules.buildings["ss_structural"].cost
    assert production.complete_if_ready(game, city) == part
    assert game.players[1].spaceship.parts == {"structural": 1}
    assert "ss_structural" not in city.buildings             # it goes to the ship, not the city
    assert production.can_build(game, city, part)            # and can be built again


def test_apollo_program_reveals_the_world(rules):
    game, city, other = space_game(rules)
    player = game.players[1]
    assert not all(player.explored)
    city.production = Item("building", "apollo_program")
    city.shields = rules.buildings["apollo_program"].cost
    production.complete_if_ready(game, city)
    assert all(player.explored) and other.id in player.known_cities


def test_spaceship_launch_and_victory(rules):
    game, city, other = space_game(rules)
    player = game.players[1]
    settings = rules.game.spaceship
    game.current_player = 1
    assert not actions.apply(game, 1, actions.LaunchSpaceship())      # nothing built yet

    player.spaceship.parts = dict(settings.min_parts)
    game.year, game.turn = 1990, 540
    assert spaceship.flight_years(game, player) == settings.flight_years
    player.spaceship.parts["component"] += 2
    faster = spaceship.flight_years(game, player)
    assert faster == settings.flight_years - 2 * settings.years_per_component

    assert actions.apply(game, 1, actions.LaunchSpaceship())
    assert player.spaceship.arrival_turn == game.turn + faster        # one year a turn by then
    assert not actions.apply(game, 1, actions.LaunchSpaceship())      # only one ship
    assert not production.can_build(game, city, Item("building", "ss_structural"))

    game.turn = player.spaceship.arrival_turn - 1
    turn.check_end(game)
    assert not game.finished
    game.turn += 1
    turn.update_scores(game)
    turn.check_end(game)
    assert game.finished and game.winner == 1 and game.victory == "spaceship"
    assert game.events[-1]["type"] == "game_over"


def test_spaceship_is_lost_with_the_capital(rules):
    game, city, other = space_game(rules)
    player = game.players[1]
    add_city(game, 1, 2, 2)                                  # so the civilization survives
    player.spaceship.parts = dict(rules.game.spaceship.min_parts)
    game.current_player = 1
    assert actions.apply(game, 1, actions.LaunchSpaceship())
    invader = game.add_unit("armor", 2, 6, 5)
    start(game, 2)
    assert movement.move_unit(game, invader, game.map.tile(5, 5)) == movement.CAPTURED
    assert not player.spaceship.launched and player.spaceship.parts == {}
    assert "spaceship_lost" in [e["type"] for e in game.events]


# ── Victory and score ─────────────────────────────────────────────────────────

def test_conquest_victory(rules):
    game = make_game(rules)
    add_city(game, 1, 5, 5)
    last = add_city(game, 2, 8, 5)
    cities.destroy_city(game, last, "test")
    assert not game.players[2].alive
    turn.check_end(game)
    assert game.finished and game.winner == 1 and game.victory == "conquest"


def test_best_score_wins_at_the_end_of_the_calendar(rules):
    game = make_game(rules)
    add_city(game, 1, 5, 5, size=3)
    add_city(game, 2, 10, 5, size=8)
    game.turn = rules.game.calendar.max_turns
    turn.update_scores(game)
    turn.check_end(game)
    assert game.finished and game.winner == 2 and game.victory == "score"


def test_score_counts_citizens_wonders_and_advances(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=3)
    weights = rules.game.score
    turn.update_scores(game)
    base = game.players[1].score
    assert base == 3 * weights.content_citizen               # three content citizens, no advance
    city.buildings.add("pyramids")
    game.wonders["pyramids"] = city.id
    game.players[1].techs.add("masonry")
    game.players[1].future_techs = 2
    turn.update_scores(game)
    assert game.players[1].score == base + weights.wonder + weights.advance + 2 * weights.future_tech


# ── Saved games ───────────────────────────────────────────────────────────────

def summary(game):
    return {
        "turn": game.turn, "year": game.year,
        "players": [(p.civ.id, p.alive, p.gold, sorted(p.techs), p.research_progress, p.government,
                     p.score) for p in game.players],
        "cities": [(c.id, c.name, c.owner, c.x, c.y, c.size, c.food, c.shields, c.production,
                    sorted(c.buildings)) for c in game.cities.values()],
        "units": [(u.id, u.type, u.owner, u.x, u.y, u.order, u.aboard) for u in game.units.values()],
        "tiles": [(t.terrain, t.road, t.irrigation, t.mine, t.pollution, t.worked_by)
                  for t in game.map.tiles],
    }


@pytest.fixture(scope="module")
def saved(rules):
    game = play(create_game(rules, 11), 90)
    return game, json.loads(json.dumps(persistence.game_to_data(game)))


def test_a_saved_game_is_restored_exactly(rules, saved):
    game, data = saved
    copy = restore_game(rules, data)
    assert summary(copy) == summary(game)
    check_consistency(copy)
    for player in game.players:
        twin = copy.players[player.id]
        assert twin.explored == player.explored and twin.visible == player.visible
        assert twin.known_cities == player.known_cities
    assert copy.controllers[1].memory == game.controllers[1].memory
    assert copy.controllers[1].unit_missions == game.controllers[1].unit_missions


def test_a_loaded_game_continues_like_the_original(rules, saved):
    game, data = saved
    copy = restore_game(rules, data)
    play(game, 25)
    play(copy, 25)
    assert summary(copy) == summary(game)


def test_save_file_round_trip(rules, saved, tmp_path):
    game, _ = saved
    path = tmp_path / "saves" / "game.json"
    persistence.save_game(game, path, extra={"note": "hello"})
    data = persistence.read_save(path)
    assert data["extra"] == {"note": "hello"}
    assert summary(restore_game(rules, data))["turn"] == game.turn


def test_bad_saves_are_refused(rules, tmp_path):
    with pytest.raises(persistence.SaveError):
        persistence.game_from_data(rules, {"version": 999})
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(persistence.SaveError):
        persistence.read_save(path)
    with pytest.raises(persistence.SaveError):
        persistence.read_save(tmp_path / "missing.json")
