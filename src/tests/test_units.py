"""Movement, zones of control, terrain work, combat and city capture."""
from __future__ import annotations

import pytest

from server.engine import actions
from server.engine.model.entities import ORDER_FORTIFIED, PEACE
from server.engine.systems import combat, movement

from .conftest import add_city, make_game


class RiggedRandom:
    """Stands in for the game's random generator with chosen results."""

    def __init__(self, rolls, chance=0.99):
        self.rolls = list(rolls)
        self.chance = chance

    def randrange(self, limit):
        return min(self.rolls.pop(0), limit - 1) if self.rolls else 0

    def random(self):
        return self.chance


def start(game, player_id):
    game.current_player = player_id
    movement.start_turn(game, game.players[player_id])


# ── Movement ──────────────────────────────────────────────────────────────────

def test_land_units_stay_on_land(rules):
    game = make_game(rules, patches={(6, 5): "ocean"})
    unit = game.add_unit("militia", 1, 5, 5)
    assert movement.why_cannot_enter(game, unit, game.map.tile(6, 5)) is not None
    assert movement.why_cannot_enter(game, unit, game.map.tile(5, 6)) is None
    assert movement.why_cannot_enter(game, unit, game.map.tile(8, 5)) == "not adjacent"


def test_roads_make_movement_cheap(rules):
    game = make_game(rules)
    for x in range(3, 8):
        game.map.tile(x, 5).road = True
    unit = game.add_unit("militia", 1, 3, 5)
    for x in (4, 5, 6):
        assert movement.move_unit(game, unit, game.map.tile(x, 5)) == movement.MOVED
    assert unit.moves_left == 0 and (unit.x, unit.y) == (6, 5)


def test_slow_unit_always_enters_rough_terrain(rules):
    game = make_game(rules, patches={(6, 5): "mountains"})
    unit = game.add_unit("militia", 1, 5, 5)
    assert movement.move_unit(game, unit, game.map.tile(6, 5)) == movement.MOVED
    assert unit.moves_left == 0


def test_world_wraps_east_west(rules):
    game = make_game(rules)
    unit = game.add_unit("militia", 1, 0, 5)
    west = game.map.tile(-1, 5)
    assert west.x == game.map.width - 1
    assert movement.move_unit(game, unit, west) == movement.MOVED


def test_zone_of_control(rules):
    game = make_game(rules)
    game.add_unit("phalanx", 2, 5, 5)
    unit = game.add_unit("militia", 1, 4, 4)
    assert movement.why_cannot_enter(game, unit, game.map.tile(4, 5)) == "zone of control"
    assert movement.why_cannot_enter(game, unit, game.map.tile(3, 4)) is None
    caravan = game.add_unit("caravan", 1, 4, 4)       # traders ignore zones of control
    assert movement.why_cannot_enter(game, caravan, game.map.tile(4, 5)) is None


def test_no_attack_in_peace_time(rules):
    game = make_game(rules, relation=PEACE)
    game.add_unit("phalanx", 2, 5, 5)
    unit = game.add_unit("legion", 1, 4, 5)
    assert movement.why_cannot_enter(game, unit, game.map.tile(5, 5)) == "at peace with the occupant"


# ── Orders and terrain work ───────────────────────────────────────────────────

def test_fortify_takes_effect_next_turn(rules):
    game = make_game(rules)
    unit = game.add_unit("phalanx", 1, 5, 5)
    assert movement.set_order(game, unit, "fortify")
    assert not unit.fortified
    start(game, 1)
    assert unit.order == ORDER_FORTIFIED


def test_irrigation_needs_water_and_time(rules):
    game = make_game(rules, patches={(6, 5): "ocean"})
    dry = game.add_unit("settlers", 1, 2, 2)
    assert not movement.set_order(game, dry, "irrigate")
    settlers = game.add_unit("settlers", 1, 5, 5)
    tile = game.map.tile(5, 5)
    assert movement.set_order(game, settlers, "irrigate")      # first of 5 turns
    for _ in range(3):
        start(game, 1)
        assert not tile.irrigation
    start(game, 1)
    assert tile.irrigation and settlers.order == "none"


def test_road_and_mine(rules):
    game = make_game(rules, patches={(5, 5): "hills"})
    settlers = game.add_unit("settlers", 1, 5, 5)
    assert movement.work_turns(game, settlers, "road") == 5    # 2 x move cost 2, +1
    assert movement.work_turns(game, settlers, "mine") == 10
    assert movement.work_turns(game, settlers, "railroad") is None   # no road, no tech
    assert game.add_unit("militia", 1, 5, 5) and \
        movement.work_turns(game, game.units_at(game.map.tile(5, 5))[1], "road") is None


def test_mining_grassland_grows_a_forest(rules):
    game = make_game(rules)
    settlers = game.add_unit("settlers", 1, 5, 5)
    movement.set_order(game, settlers, "mine")
    for _ in range(9):
        start(game, 1)
    assert game.map.tile(5, 5).terrain == "forest"


# ── Combat ────────────────────────────────────────────────────────────────────

def test_combat_strengths(rules):
    game = make_game(rules, patches={(6, 5): "hills"})
    attacker = game.add_unit("militia", 1, 5, 5)
    defender = game.add_unit("phalanx", 2, 5, 6)
    tile = game.map.tile(5, 6)
    odds = combat.odds(game, attacker, tile)
    assert (odds.attack, odds.defense) == (8, 16)
    assert odds.win_chance == pytest.approx(28 / 128)

    defender.order = ORDER_FORTIFIED
    assert combat.odds(game, attacker, tile).defense == 24
    defender.veteran = True
    assert combat.odds(game, attacker, tile).defense == 36
    attacker.veteran = True
    assert combat.odds(game, attacker, tile).attack == 12

    on_hills = game.add_unit("phalanx", 2, 6, 5)
    assert combat.odds(game, attacker, game.map.tile(6, 5)).defense == 32
    on_hills.order = ORDER_FORTIFIED
    assert combat.odds(game, attacker, game.map.tile(6, 5)).defense == 48


def test_tired_attacker_is_weaker(rules):
    game = make_game(rules)
    attacker = game.add_unit("cavalry", 1, 5, 5)
    game.add_unit("phalanx", 2, 5, 6)
    attacker.moves_left = 1
    assert combat.odds(game, attacker, game.map.tile(5, 6)).attack == 16 // 3


def test_city_walls_triple_defense_except_against_artillery(rules):
    game = make_game(rules)
    city = add_city(game, 2, 5, 6)
    city.buildings.add("city_walls")
    game.add_unit("phalanx", 2, 5, 6)
    tile = game.map.tile(5, 6)
    catapult = game.add_unit("catapult", 1, 5, 5)
    artillery = game.add_unit("artillery", 1, 5, 5)
    assert combat.odds(game, catapult, tile).defense == 48
    assert combat.odds(game, artillery, tile).defense == 16


def test_losing_stack_dies_in_the_open(rules):
    game = make_game(rules)
    attacker = game.add_unit("legion", 1, 5, 5)
    game.add_unit("phalanx", 2, 5, 6)
    game.add_unit("settlers", 2, 5, 6)
    game.add_unit("settlers", 2, 9, 9)                 # keeps the civilization alive
    game.rng = RiggedRandom([23, 0])
    assert movement.move_unit(game, attacker, game.map.tile(5, 6)) == movement.ATTACK_WON
    assert not game.map.tile(5, 6).unit_ids
    assert (attacker.x, attacker.y) == (5, 5)          # the winner does not advance


def test_city_protects_the_stack_but_shrinks(rules):
    game = make_game(rules)
    city = add_city(game, 2, 5, 6, size=3)
    game.add_unit("phalanx", 2, 5, 6)
    game.add_unit("militia", 2, 5, 6)
    attacker = game.add_unit("legion", 1, 5, 5)
    game.rng = RiggedRandom([23, 0])
    assert movement.move_unit(game, attacker, game.map.tile(5, 6)) == movement.ATTACK_WON
    assert [u.type for u in game.units_at(game.map.tile(5, 6))] == ["militia"]
    assert city.size == 2


def test_losing_attacker_dies(rules):
    game = make_game(rules)
    attacker = game.add_unit("militia", 1, 5, 5)
    defender = game.add_unit("phalanx", 2, 5, 6)
    game.add_unit("settlers", 1, 9, 9)
    game.rng = RiggedRandom([0, 5], chance=0.0)
    assert movement.move_unit(game, attacker, game.map.tile(5, 6)) == movement.ATTACK_LOST
    assert attacker.id not in game.units
    assert defender.veteran                            # promoted (chance forced)


def test_capture_undefended_city(rules):
    game = make_game(rules)
    game.players[2].techs.update({"alphabet", "pottery"})
    game.players[2].gold = 100
    add_city(game, 2, 10, 2, size=3)
    city = add_city(game, 2, 5, 6, size=3)
    city.buildings.add("temple")
    supported = game.add_unit("militia", 2, 8, 8, home_city=city.id)
    attacker = game.add_unit("legion", 1, 5, 5)
    assert movement.move_unit(game, attacker, game.map.tile(5, 6)) == movement.CAPTURED
    assert city.owner == 1 and city.size == 2
    assert game.players[1].gold == 50 and game.players[2].gold == 50      # half the population
    assert len(game.players[1].techs) == 1                                # one advance stolen
    assert supported.id not in game.units
    assert "palace" not in city.buildings


def test_civilization_dies_with_its_last_city(rules):
    game = make_game(rules)
    city = add_city(game, 2, 5, 6, size=1)
    attacker = game.add_unit("legion", 1, 5, 5)
    movement.move_unit(game, attacker, game.map.tile(5, 6))
    assert city.id not in game.cities                  # a size-1 city is destroyed
    assert not game.players[2].alive


# ── Actions ───────────────────────────────────────────────────────────────────

def test_only_the_current_player_acts(rules):
    game = make_game(rules)
    settlers = game.add_unit("settlers", 1, 5, 5)
    game.current_player = 2
    assert not actions.apply(game, 1, actions.FoundCity(settlers.id))
    game.current_player = 1
    assert not actions.apply(game, 1, actions.FoundCity(999))
    assert actions.apply(game, 1, actions.FoundCity(settlers.id))
    assert len(game.cities) == 1 and settlers.id not in game.units


def test_cities_cannot_touch(rules):
    game = make_game(rules)
    add_city(game, 1, 5, 5)
    settlers = game.add_unit("settlers", 1, 6, 6)
    game.current_player = 1
    result = actions.apply(game, 1, actions.FoundCity(settlers.id))
    assert not result.ok and "cannot be founded" in result.reason


def test_production_must_be_available(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5)
    game.current_player = 1
    assert actions.apply(game, 1, actions.SetProduction(city.id, "unit", "militia"))
    assert not actions.apply(game, 1, actions.SetProduction(city.id, "unit", "legion"))   # no tech
    assert not actions.apply(game, 1, actions.SetProduction(city.id, "unit", "trireme"))  # sea: later
    assert not actions.apply(game, 1, actions.SetProduction(city.id, "building", "palace"))  # has one
