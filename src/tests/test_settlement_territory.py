"""Alternative rules prevent settling inside another civilization's map territory.

Renaissance cities win their outer ring with culture: these tests give them their whole area,
as a city whose borders have grown (see test_culture.py for the growth)."""
import pytest

from server.engine import actions
from server.engine.model.entities import PEACE, WAR
from server.engine.model.worldmap import ALL_CLAIMS
from server.engine.systems import cities, visibility
from server.engine.view import PlayerView
from server.human.controller import HumanController
from server.human.orders import unit_orders

from .conftest import add_city, make_game


@pytest.mark.parametrize("ruleset", ["civ1", "golden_ages", "renaissance"])
@pytest.mark.parametrize("relation", [PEACE, WAR])
@pytest.mark.parametrize("city_x, target", [(5, (7, 5)), (5, (7, 6)), (0, (14, 5))])
def test_foreign_territory_founding(rulesets, ruleset, relation, city_x, target):
    game = make_game(rulesets[ruleset], relation=relation)
    game.current_player = 1
    foreign = add_city(game, 2, city_x, 5)
    foreign.claims = ALL_CLAIMS
    player = game.players[1]
    visibility.remember_city(game, player, foreign)
    unit = game.add_unit("settlers", player.id, *target)
    tile = game.tile_of(unit)
    view = PlayerView(game, player)
    allowed = ruleset == "civ1"
    assert cities.can_found_city(game, tile, player.id) == allowed
    assert view.can_found_city(tile) == allowed
    orders = {order["id"] for order in unit_orders(view, HumanController(), unit)}
    assert ("found_city" in orders) == allowed
    moves = unit.moves_left
    result = view.do(actions.FoundCity(unit.id))
    assert bool(result) == allowed
    if allowed:
        assert game.city_at(*target).owner == player.id
    else:
        assert result.reason == "a city cannot be founded here"
        assert tile.city_id is None
        assert game.units[unit.id] is unit
        assert unit.moves_left == moves
        assert len(game.cities) == 1


@pytest.mark.parametrize("owner, target", [(1, (7, 5)), (2, (7, 7)), (2, (8, 5))])
def test_own_territory_and_unclaimed_land_remain_open(rulesets, owner, target):
    game = make_game(rulesets["golden_ages"])
    game.current_player = 1
    city = add_city(game, owner, 5, 5)
    if owner != 1:
        visibility.remember_city(game, game.players[1], city)
    unit = game.add_unit("settlers", 1, *target)
    view = PlayerView(game, game.players[1])
    assert view.can_found_city(game.tile_of(unit))
    assert view.do(actions.FoundCity(unit.id))


@pytest.mark.parametrize("first_owner", [1, 2])
def test_overlap_belongs_to_oldest_city(rulesets, first_owner):
    game = make_game(rulesets["golden_ages"])
    add_city(game, first_owner, 5, 5)
    add_city(game, 3 - first_owner, 9, 5)
    for city in game.cities.values():
        city.claims = ALL_CLAIMS
    player = game.players[1]
    for city in game.player_cities(2):
        visibility.remember_city(game, player, city)
    tile = game.map.tile(7, 5)
    assert cities.territory_owner(game.map, tile, game.cities) == first_owner
    assert cities.can_found_city(game, tile, 1) == (first_owner == 1)
    assert PlayerView(game, player).can_found_city(tile) == (first_owner == 1)


def test_unknown_territory_is_still_enforced_by_engine(rulesets):
    game = make_game(rulesets["golden_ages"])
    game.current_player = 1
    add_city(game, 2, 5, 5).claims = ALL_CLAIMS
    unit = game.add_unit("settlers", 1, 7, 5)
    view = PlayerView(game, game.players[1])
    assert not view.known_foreign_cities()
    assert view.can_found_city(game.tile_of(unit))  # No hidden city revealed to the AI.
    result = view.do(actions.FoundCity(unit.id))
    assert not result and result.reason == "a city cannot be founded here"
    assert unit.id in game.units
