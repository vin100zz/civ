"""City rules: yields, trade, mood, growth."""
from __future__ import annotations

import json

from server.engine import actions, effects as fx, persistence
from server.engine.model.entities import Item
from server.engine.rules.schema import Effect, Yields
from server.engine.systems import cities, city as city_rules, government, production

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


def test_railroad_bonus_comes_before_the_government(rules):
    """Shield grassland (2/1/0) with road and irrigation: the railroad adds 50% of the yield
    before the government's penalty or bonus, as in the original."""
    game = make_game(rules)
    city = add_city(game, 1, 5, 5)
    tile = game.map.tile(6, 5)
    tile.pattern = tile.road = tile.irrigation = True
    expected = {"despotism": ((2, 1, 1), (3, 1, 1)),
                "monarchy": ((3, 1, 1), (4, 1, 1)),
                "democracy": ((3, 1, 2), (4, 1, 2))}
    for government_id, (without_railroad, with_railroad) in expected.items():
        game.players[1].government = government_id
        tile.railroad = False
        assert city_rules.tile_yields(game, city, tile) == Yields(*without_railroad)
        tile.railroad = True
        assert city_rules.tile_yields(game, city, tile) == Yields(*with_railroad)


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


def test_growth_brings_disorder(rules):
    """Four content citizens: the fifth would be unhappy and throw the city into disorder."""
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=4)
    city_rules.set_worked(game, city, [(0, -1), (1, 0), (0, 1), (-1, 0)])
    city.specialists = {"entertainer": 0, "taxman": 0, "scientist": 0}
    assert not city_rules.compute_city(game, city).disorder
    assert city_rules.growth_brings_disorder(game, city)
    assert city.size == 4 and len(city.worked) == 4         # the city itself is left alone

    city.buildings.add("temple")
    assert not city_rules.growth_brings_disorder(game, city)
    city.buildings.discard("temple")

    city.size = city_rules.max_size(game, city)             # no aqueduct: it cannot grow
    assert not city_rules.growth_brings_disorder(game, city)


def _farmland_city(rules, government_id: str, size: int, luxury: int):
    """A city on irrigated grassland with roads, under the given government and luxury rate."""
    game = make_game(rules)
    player = game.players[1]
    player.government = government_id
    player.tax_rate, player.luxury_rate, player.science_rate = 100 - luxury, luxury, 0
    for _, tile in game.map.city_area(5, 5):
        tile.road = tile.irrigation = True
    return game, add_city(game, 1, 5, 5, size=size)


def test_mayor_makes_the_city_celebrate_under_democracy(rules):
    """A celebrating city grows by one each turn under Democracy: the mayor gives up two
    tiles for it, the food surplus stays positive."""
    game, city = _farmland_city(rules, "democracy", size=6, luxury=60)
    stats = city_rules.compute_city(game, city)
    assert stats.celebrating and stats.food_surplus > 0
    assert city.specialists["entertainer"] == 2
    free = next(o for o, _ in city_rules.workable_tiles(game, city) if o not in city.worked)
    city_rules.toggle_tile(game, city, free)                # one of them back to work
    assert not city_rules.compute_city(game, city).celebrating

    # Under Monarchy celebrating brings no growth: everybody works.
    game, city = _farmland_city(rules, "monarchy", size=6, luxury=60)
    assert city.specialists["entertainer"] == 0
    assert not city_rules.compute_city(game, city).celebrating


def test_luxury_change_rearranges_the_cities(rules):
    game, city = _farmland_city(rules, "democracy", size=10, luxury=30)
    city.buildings.add("aqueduct")
    city_rules.auto_arrange(game, city)
    assert city.specialists["entertainer"] == 4             # needed against disorder
    player = game.players[1]

    city_rules.toggle_tile(game, city, city.worked[0])      # placed by hand
    hand_placed = (list(city.worked), dict(city.specialists))
    assert government.set_rates(game, player, 50, 30, 20)   # same luxury: left alone
    assert (city.worked, city.specialists) == hand_placed

    assert government.set_rates(game, player, 40, 60, 0)
    assert city.specialists["entertainer"] == 0             # all back to work
    assert not city.stats.disorder


def test_new_government_rearranges_the_cities(rules):
    game, city = _farmland_city(rules, "monarchy", size=6, luxury=60)
    assert city.specialists["entertainer"] == 0
    player = game.players[1]
    player.techs.add("democracy")
    game.turn = 5
    assert government.start_revolution(game, player, "democracy")
    assert player.government == "anarchy"
    assert len(city.worked) + city.specialist_count == city.size
    game.turn = 8
    government.tick(game, player)
    assert player.government == "democracy"
    assert city.specialists["entertainer"] == 2             # celebrating for rapture growth
    assert city.stats.celebrating


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
    assert game.wonder_origins == {"colossus": (game.year, 1, first.name)}
    assert rival.production is None                  # the race is lost
    assert any(e["type"] == "wonder" for e in game.events)
    # A wonder goes down with its city: it works no more, and nobody can build it again.
    cities.destroy_city(game, first, "test")
    assert game.wonders == {"colossus": None}
    assert fx.active_wonders(game, 1) == [] and fx.wonder_owner(game, "colossus") is None
    assert not production.can_build(game, rival, Item("building", "colossus"))


# ── The production queue ─────────────────────────────────────────────────────

def test_the_queue_takes_over_when_an_item_is_finished(rules):
    game = make_game(rules)
    game.current_player = 1
    city = add_city(game, 1, 5, 5)
    militia, barracks = Item("unit", "militia"), Item("building", "barracks")
    act = lambda action: actions.apply(game, 1, action)
    assert act(actions.SetProduction(city.id, "unit", "militia"))
    assert act(actions.QueueProduction(city.id, "unit", "militia"))
    assert act(actions.QueueProduction(city.id, "building", "barracks"))
    assert not act(actions.QueueProduction(city.id, "building", "barracks")), "a building once"
    assert act(actions.QueueProduction(city.id, "unit", "militia")), "a unit again and again"
    assert city.queue == [militia, barracks, militia]

    cost = rules.units["militia"].cost
    city.shields = 2 * cost
    cities.process_city(game, city)
    assert city.last_completed == militia and city.production == militia and city.from_queue
    assert city.queue == [barracks, militia]
    assert city.shields >= cost, "what is left over goes to the next item"
    cities.process_city(game, city)
    assert city.production == barracks and city.queue == [militia]

    # A click builds something else now: the queue stays, a building chosen leaves it.
    assert act(actions.SetProduction(city.id, "unit", "settlers"))
    assert city.production == Item("unit", "settlers") and not city.from_queue
    assert city.queue == [militia]
    city.queue.append(barracks)
    assert act(actions.SetProduction(city.id, "building", "barracks"))
    assert city.queue == [militia]
    assert act(actions.UnqueueProduction(city.id, 0)) and city.queue == []
    assert not act(actions.UnqueueProduction(city.id, 0))

    # Without a queue a unit is built again, as in Civ 1; a building leaves the city idle.
    city.production, city.shields = militia, cost
    cities.process_city(game, city)
    assert city.production == militia and not city.from_queue
    # A city with nothing to build starts on what is queued at once.
    city.production = None
    assert act(actions.QueueProduction(city.id, "building", "barracks"))
    assert city.production == barracks and city.queue == []


def test_the_queue_drops_what_can_no_longer_be_built(rules):
    game = make_game(rules)
    for player in game.players[1:]:
        player.techs.add("bronze_working")
    city = add_city(game, 1, 5, 5)
    rival = add_city(game, 2, 12, 5)
    city.production = Item("unit", "militia")
    city.queue = [Item("building", "colossus"), Item("building", "barracks")]
    game.wonders["colossus"] = rival.id                # built elsewhere meanwhile
    rival.buildings.add("colossus")
    city.shields = rules.units["militia"].cost
    cities.process_city(game, city)
    assert city.production == Item("building", "barracks") and city.queue == []


def test_the_queue_is_saved_and_lost_with_the_city(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5, size=3)
    city.production = Item("unit", "militia")
    city.queue = [Item("unit", "militia"), Item("building", "barracks")]
    saved = json.loads(json.dumps(persistence.game_to_data(game)))
    assert persistence.game_from_data(rules, saved).cities[city.id].queue == city.queue
    cities.capture_city(game, game.add_unit("legion", 2, 6, 5), city)
    assert city.owner == 2 and city.queue == []
