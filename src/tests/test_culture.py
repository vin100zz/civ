"""Culture (Renaissance): what a city makes, the borders it wins, the land its citizens work."""
import json

from server.api.replay import Replay
from server.engine import persistence
from server.engine.model.worldmap import (ALL_CLAIMS, CITY_CORNERS, CITY_RING_INNER,
                                          CITY_RING_OUTER, CITY_RING_THIRD, CLAIM_BITS,
                                          INNER_CLAIMS)
from server.engine.systems import city as city_rules
from server.engine.systems import cities, culture, territory, turn

from .conftest import add_city, make_game


def renaissance(rulesets, **options):
    return make_game(rulesets["renaissance"], **options)


def test_new_city_claims_its_inner_ring_with_culture_only(rulesets):
    assert add_city(renaissance(rulesets), 1, 5, 5).claims == INNER_CLAIMS
    for ruleset in ("civ1", "golden_ages"):
        assert not rulesets[ruleset].game.culture.enabled
        assert add_city(make_game(rulesets[ruleset]), 1, 5, 5).claims == ALL_CLAIMS


def test_citizens_only_work_their_territory(rulesets):
    game = renaissance(rulesets)
    city = add_city(game, 1, 5, 5)
    offsets = {offset for offset, _ in city_rules.workable_tiles(game, city)}
    assert offsets == set(CITY_RING_INNER)
    civ1 = make_game(rulesets["civ1"])
    other = add_city(civ1, 1, 5, 5)
    assert len(city_rules.workable_tiles(civ1, other)) == len(CITY_RING_INNER + CITY_RING_OUTER)


def test_own_territory_of_another_city_may_be_worked(rulesets):
    game = renaissance(rulesets)
    add_city(game, 1, 5, 5)
    second = add_city(game, 1, 8, 5)
    # (6, 5) is in the inner ring of the first city, the outer ring of the second.
    assert (-2, 0) in {offset for offset, _ in city_rules.workable_tiles(game, second)}


def test_culture_per_turn_from_buildings_and_wonders(rulesets):
    game = renaissance(rulesets)
    city = add_city(game, 1, 5, 5)
    assert culture.culture_per_turn(game, city) == 1
    city.buildings |= {"temple", "theatre"}
    assert culture.culture_per_turn(game, city) == 5
    city.buildings.add("museum")
    assert culture.culture_per_turn(game, city) == (5 + 2) * 3 // 2
    city.buildings.add("colossus")
    game.wonders["colossus"] = city.id
    assert culture.culture_per_turn(game, city) == (5 + 2 + 3) * 3 // 2
    assert culture.culture_per_turn(make_game(rulesets["civ1"]),
                                    add_city(make_game(rulesets["civ1"]), 1, 5, 5)) == 0


def test_player_wide_wonders_reach_every_city(rulesets):
    game = renaissance(rulesets)
    capital = add_city(game, 1, 3, 5)
    other = add_city(game, 1, 9, 5)
    capital.buildings.add("parthenon")
    game.wonders["parthenon"] = capital.id
    assert culture.culture_per_turn(game, other) == 1 + 2
    capital.buildings.add("louvre")
    game.wonders["louvre"] = capital.id
    assert culture.culture_per_turn(game, other) == (1 + 2 + 2) * 3 // 2


def test_borders_grow_tile_by_tile(rulesets):
    game = renaissance(rulesets, patches={(5, 3): "hills", (7, 4): "ocean"})
    city = add_city(game, 1, 5, 5)
    city.culture = 4
    culture.add_culture(game, city)                 # 5: the first tile
    assert culture.outer_claims(city) == 1
    assert not city.claims & CLAIM_BITS[(0, -2)]     # the hills: a poorer tile
    culture.add_culture(game, city)
    assert culture.outer_claims(city) == 1          # the second needs 15
    city.culture = 5 * 78 - 1
    culture.add_culture(game, city)
    assert city.claims == ALL_CLAIMS                 # the outer ring first
    assert culture.next_tile_cost(game, city) == 5 * 13 * 14 // 2
    assert any(e["type"] == "borders" for e in game.events)


def test_beyond_its_area_the_corners_come_before_the_third_ring(rulesets):
    game = renaissance(rulesets)
    city = add_city(game, 1, 8, 6)
    city.claims, city.culture = ALL_CLAIMS, 5 * 78
    for _ in CITY_CORNERS:
        city.culture = culture.next_tile_cost(game, city) - 1
        culture.add_culture(game, city)
    assert all(city.claims & CLAIM_BITS[offset] for offset in CITY_CORNERS)
    assert not any(city.claims & CLAIM_BITS[offset] for offset in CITY_RING_THIRD)
    city.culture = 5 * 666
    culture.add_culture(game, city)
    assert all(city.claims & CLAIM_BITS[offset] for offset in CITY_RING_THIRD)
    assert culture.next_tile_cost(game, city) is None
    assert territory.owner_of(game, game.map.tile(8, 3)) == 1
    assert not territory.owner_of(game, game.map.tile(11, 9))      # a corner of the 7 x 7


def test_tiles_beyond_the_area_touch_the_territory(rulesets):
    game = renaissance(rulesets)
    city = add_city(game, 1, 8, 6)
    # Its outer ring held, but for the three tiles north of it.
    city.claims = ALL_CLAIMS & ~sum(CLAIM_BITS[o] for o in ((0, -2), (1, -2), (-1, -2)))
    reach = {offset for offset, _ in culture.far_free_tiles(game, city)}
    assert (0, -3) not in reach and (3, 0) in reach and (2, -2) in reach


def test_no_city_reaches_beyond_its_area_for_land_a_foreign_city_could_work(rulesets):
    game = renaissance(rulesets, width=24)
    mine = add_city(game, 1, 8, 6)
    theirs = add_city(game, 2, 13, 6)      # its area reaches x = 11, the third ring of mine
    mine.claims = ALL_CLAIMS
    reach = {offset for offset, _ in culture.far_free_tiles(game, mine)}
    assert (3, 0) not in reach and (-3, 0) in reach
    mine.culture = 5 * 666
    culture.add_culture(game, mine)
    assert territory.owner_of(game, game.map.tile(11, 6)) is None
    assert (-2, 0) in {offset for offset, _ in culture.free_tiles(game, theirs)}


def test_nobody_founds_a_city_beyond_the_area_of_a_cultured_city(rulesets):
    game = renaissance(rulesets, width=24)
    city = add_city(game, 2, 8, 6)
    city.claims = ALL_CLAIMS | sum(CLAIM_BITS[o] for o in CITY_CORNERS + CITY_RING_THIRD)
    assert not cities.can_found_city(game, game.map.tile(11, 6), 1)
    assert cities.can_found_city(game, game.map.tile(12, 6), 1)


def test_the_best_free_tile_is_claimed_first(rulesets):
    game = renaissance(rulesets, terrain="desert", patches={(7, 6): "grassland"})
    game.map.tile(7, 6).special = True
    city = add_city(game, 1, 5, 5)
    assert culture.best_free_tile(game, city) == (2, 1)


def test_foreign_territory_is_never_claimed(rulesets):
    game = renaissance(rulesets)
    mine = add_city(game, 1, 5, 5)
    theirs = add_city(game, 2, 8, 5)
    # The inner ring of the foreign city covers the tiles 2 steps east of mine.
    taken = {offset for offset, _ in game.map.city_area(mine.x, mine.y)
             if territory.owner_of(game, game.map.tile(mine.x + offset[0], mine.y + offset[1]))
             == theirs.owner}
    assert taken and not taken & {offset for offset, _ in culture.free_tiles(game, mine)}
    mine.culture = 5 * 78
    culture.add_culture(game, mine)
    assert culture.outer_claims(mine) == len(CITY_RING_OUTER) - len(taken & set(CITY_RING_OUTER))


def test_territory_owner_agrees_with_the_fast_lookup(rulesets):
    game = renaissance(rulesets)
    add_city(game, 1, 5, 5).claims = ALL_CLAIMS | CLAIM_BITS[(0, 3)] | CLAIM_BITS[(-3, -1)]
    add_city(game, 2, 8, 6).claims |= CLAIM_BITS[(3, 2)] | CLAIM_BITS[(2, -2)]
    add_city(game, 1, 1, 8).claims |= CLAIM_BITS[(-3, 0)]      # across the edge of the world
    for tile in game.map:
        assert territory.owner_of(game, tile) == cities.territory_owner(game.map, tile, game.cities)


def test_a_city_makes_culture_each_turn(rulesets):
    game = renaissance(rulesets)
    city = add_city(game, 1, 5, 5)
    cities.process_city(game, city)
    cities.process_city(game, city)
    assert city.culture == 2


def test_score_counts_culture(rulesets):
    game = renaissance(rulesets)
    city = add_city(game, 1, 5, 5)
    turn.update_scores(game)
    before = game.players[1].score
    city.culture = 1000
    turn.update_scores(game)
    assert game.players[1].score == before + 1000 // game.rules.game.score.culture_per_point


def test_saves_keep_culture_and_borders(rulesets):
    game = renaissance(rulesets)
    city = add_city(game, 1, 5, 5)
    city.culture, city.claims = 42, INNER_CLAIMS | CLAIM_BITS[(0, -2)]
    data = json.loads(json.dumps(persistence.game_to_data(game)))
    again = persistence.game_from_data(rulesets["renaissance"], data)
    assert (again.cities[city.id].culture, again.cities[city.id].claims) == (42, city.claims)
    # A save from before culture: its cities hold their whole area.
    for saved in data["cities"]:
        del saved["culture"], saved["claims"]
    old = persistence.game_from_data(rulesets["renaissance"], data)
    assert old.cities[city.id].claims == ALL_CLAIMS


def test_replay_notes_the_borders(rulesets):
    game = renaissance(rulesets)
    city = add_city(game, 1, 5, 5)
    replay = Replay()
    replay.note_cities(game)
    assert replay.cities[-1] == ["claims", game.turn, city.id, INNER_CLAIMS]
    city.claims |= CLAIM_BITS[(2, 0)]
    game.turn += 1
    replay.note_cities(game)
    assert replay.cities[-1] == ["claims", game.turn, city.id, city.claims]
    again = Replay.restore(json.loads(json.dumps(replay.payload())), game, [])
    game.turn += 1
    again.note_cities(game)
    assert again.cities == replay.cities


def test_renaissance_is_golden_ages_with_culture(rulesets):
    """Its files are a copy of those of Golden Ages: they only add culture."""
    golden, renaissance_rules = rulesets["golden_ages"], rulesets["renaissance"]
    assert renaissance_rules.units == golden.units
    assert renaissance_rules.governments == golden.governments
    assert set(renaissance_rules.techs) - set(golden.techs) == {"drama", "humanism"}
    assert set(golden.techs) <= set(renaissance_rules.techs)
    assert set(renaissance_rules.buildings) - set(golden.buildings) == {
        "theatre", "museum", "parthenon", "louvre"}
    for building_id, building in golden.buildings.items():
        other = renaissance_rules.buildings[building_id]
        assert [e for e in other.effects if e.type != "culture"] == list(building.effects)
        assert (other.cost, other.upkeep, other.requires) == (building.cost, building.upkeep,
                                                               building.requires)
    for tech_id, tech in golden.techs.items():
        assert renaissance_rules.techs[tech_id] == tech
