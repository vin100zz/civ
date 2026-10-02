"""City rules: yields, trade, mood, growth."""
from __future__ import annotations

from server.engine.model.entities import Item
from server.engine.rules.schema import Effect, Yields
from server.engine.systems import cities, city as city_rules

from .conftest import add_city, make_game


def test_city_tile_under_despotism(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5)
    # Grassland 2/0/0: the city tile is irrigated (+1 food, cut back to 2 by despotism),
    # yields at least one shield and has a road (+1 trade).
    assert city_rules.tile_yields(game, city, game.tile_of(city)) == Yields(2, 1, 1)


def test_government_changes_tile_yields(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5)
    center = game.tile_of(city)
    game.players[1].government = "monarchy"
    assert city_rules.tile_yields(game, city, center) == Yields(3, 1, 1)
    game.players[1].government = "republic"          # +1 trade where there is trade
    assert city_rules.tile_yields(game, city, center) == Yields(3, 1, 2)


def test_improvements_and_specials(rules):
    game = make_game(rules, patches={(6, 5): "hills", (4, 5): "forest", (5, 4): "plains"})
    game.players[1].government = "monarchy"
    city = add_city(game, 1, 5, 5)
    hills, forest, plains = game.map.tile(6, 5), game.map.tile(4, 5), game.map.tile(5, 4)
    assert city_rules.tile_yields(game, city, hills) == Yields(1, 0, 0)
    hills.mine = True
    assert city_rules.tile_yields(game, city, hills) == Yields(1, 3, 0)
    forest.special = True                            # game
    assert city_rules.tile_yields(game, city, forest) == Yields(3, 2, 0)
    plains.irrigation = True
    plains.road = True
    assert city_rules.tile_yields(game, city, plains) == Yields(2, 1, 1)
    plains.railroad = True                           # +50%, rounded down
    assert city_rules.tile_yields(game, city, plains) == Yields(3, 1, 1)
    game.players[1].government = "despotism"         # more than 2 loses 1
    assert city_rules.tile_yields(game, city, hills) == Yields(1, 2, 0)


def test_worker_assignment_is_consistent(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=4)
    assert len(city.worked) + city.specialist_count == city.size
    for dx, dy in city.worked:
        assert game.map.tile(city.x + dx, city.y + dy).worked_by == city.id
    stats = city_rules.compute_city(game, city)
    assert stats.food_surplus >= 0
    assert stats.happy + stats.content + stats.unhappy + city.specialist_count == city.size


def test_two_cities_do_not_share_tiles(rules):
    game = make_game(rules)
    first = add_city(game, 1, 5, 5, size=8)
    second = add_city(game, 1, 7, 5, size=8)
    used_first = {(first.x + dx, first.y + dy) for dx, dy in first.worked}
    used_second = {(second.x + dx, second.y + dy) for dx, dy in second.worked}
    assert not used_first & used_second
    assert (second.x, second.y) not in used_first


def test_fifth_citizen_is_unhappy(rules):
    """At this difficulty four citizens are born content; the fifth riots unless calmed."""
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=5)
    city_rules.set_worked(game, city, [(0, -1), (1, 0), (0, 1), (-1, 0), (1, 1)])
    city.specialists = {"entertainer": 0, "taxman": 0, "scientist": 0}
    stats = city_rules.compute_city(game, city)
    assert (stats.happy, stats.unhappy, stats.disorder) == (0, 1, True)

    city.buildings.add("temple")
    assert not city_rules.compute_city(game, city).disorder
    city.buildings.discard("temple")

    game.add_unit("militia", 1, city.x, city.y)      # martial law under despotism
    assert not city_rules.compute_city(game, city).disorder


def test_auto_arrange_avoids_disorder(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=6)
    assert city.specialists["entertainer"] >= 1
    assert not city_rules.compute_city(game, city).disorder


def test_corruption_grows_with_distance(rules):
    game = make_game(rules, width=40)
    add_city(game, 1, 5, 5)                          # capital
    far = add_city(game, 1, 15, 5)
    assert city_rules.capital_distance(game, far) == 10
    assert city_rules._corruption(game, far, 20, []) == 20 * 10 * 3 // 100
    courthouse = rules.buildings["courthouse"].effects
    assert city_rules._corruption(game, far, 20, list(courthouse)) == 3
    game.players[1].government = "democracy"
    assert city_rules._corruption(game, far, 20, []) == 0


def test_yield_bonuses_stack_like_the_original():
    market = Effect(type="yield_bonus", yield_kind="tax", percent=50, mode="compound")
    library = Effect(type="yield_bonus", yield_kind="science", percent=50, mode="additive")
    assert city_rules._apply_yield_bonus(10, [market, market], "tax") == 22       # 10 -> 15 -> 22
    assert city_rules._apply_yield_bonus(10, [library, library], "science") == 20  # 10 + 5 + 5
    power = Effect(type="yield_bonus", yield_kind="shields", percent=50, exclusive_group="power")
    assert city_rules._apply_yield_bonus(10, [power, power], "shields") == 15      # only one plant


def test_growth_and_granary(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5)
    city.food = 19
    cities.process_city(game, city)
    assert city.size == 2 and city.food == 0

    city.buildings.add("granary")
    city.food = 29
    cities.process_city(game, city)
    assert city.size == 3 and city.food == 20        # half of the new 40-food box


def test_aqueduct_limit(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=10)
    assert city_rules.max_size(game, city) == 10
    city.food = 500
    cities.process_city(game, city)
    assert city.size == 10
    city.buildings.add("aqueduct")
    assert city_rules.max_size(game, city) is None


def test_production_completes(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5)
    city.production = Item("unit", "militia")
    city.shields = 9
    cities.process_city(game, city)                  # +1 shield from the city tile
    units = game.units_at(game.tile_of(city))
    assert [u.type for u in units] == ["militia"]
    assert units[0].home_city == city.id and city.last_completed == Item("unit", "militia")


def test_settlers_take_a_citizen(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=3)
    city.production = Item("unit", "settlers")
    city.shields = 40
    cities.process_city(game, city)
    assert city.size == 2
    assert any(u.type == "settlers" for u in game.units_at(game.tile_of(city)))


def test_wonder_is_unique(rules):
    game = make_game(rules)
    game.players[1].techs.add("bronze_working")
    game.players[2].techs.add("bronze_working")
    first = add_city(game, 1, 5, 5)
    rival = add_city(game, 2, 10, 5)
    first.production = rival.production = Item("building", "colossus")
    first.shields = 200
    cities.process_city(game, first)
    assert game.wonders == {"colossus": first.id}
    assert rival.production is None                  # the race is lost
    assert any(e["type"] == "wonder" for e in game.events)
