"""Player-level rules: research, governments, diplomacy, wonders, the calendar."""
from __future__ import annotations

from server.engine import actions
from server.engine.model.entities import PEACE, WAR
from server.engine.systems import cities, city as city_rules, diplomacy, government, research, turn
from server.engine.systems import visibility

from .conftest import add_city, make_game


def test_research_cost(rules):
    game = make_game(rules)
    player = game.players[1]
    assert research.research_cost(game, player) == 10
    player.techs.update({"alphabet", "pottery", "masonry", "writing", "bronze_working"})
    assert research.research_cost(game, player) == 60
    game.year = 1
    assert research.research_cost(game, player) == 120       # doubled from 1 AD


def test_discovery(rules):
    game = make_game(rules)
    player = game.players[1]
    game.current_player = 1
    assert actions.apply(game, 1, actions.SetResearch("alphabet"))
    assert not actions.apply(game, 1, actions.SetResearch("writing"))   # needs alphabet
    player.research_progress = 10
    assert research.check_discovery(game, player) is None                # must exceed the cost
    player.research_progress = 11
    assert research.check_discovery(game, player) == "alphabet"
    assert "alphabet" in player.techs and player.research_progress == 0
    assert "writing" in research.research_options(game, player)


def test_calendar(rules):
    game = make_game(rules)
    years = []
    for _ in range(203):
        turn.advance_calendar(game)
        years.append(game.year)
    assert years[0] == -3980
    assert years[198:203] == [-20, 1, 20, 40, 60]            # no year 0
    game.year = 1490
    turn.advance_calendar(game)
    turn.advance_calendar(game)
    assert game.year == 1505                                  # 10 years, then 5


def test_revolution_goes_through_anarchy(rules):
    game = make_game(rules)
    player = game.players[1]
    assert not government.start_revolution(game, player, "monarchy")     # unknown
    player.techs.add("monarchy")
    game.turn = 5
    assert government.start_revolution(game, player, "monarchy")
    assert player.government == "anarchy"
    game.turn = 7
    government.tick(game, player)
    assert player.government == "anarchy"
    game.turn = 8                                             # next multiple of 4
    government.tick(game, player)
    assert player.government == "monarchy"


def test_pyramids_allow_any_government_at_once(rules):
    game = make_game(rules)
    player = game.players[1]
    city = add_city(game, 1, 5, 5)
    city.buildings.add("pyramids")
    game.wonders["pyramids"] = city.id
    assert government.start_revolution(game, player, "democracy")
    assert player.government == "democracy"
    # ... until somebody discovers what makes them obsolete.
    game.players[2].techs.add("communism")
    assert "monarchy" not in government.available_governments(game, player)


def test_rates_respect_the_government(rules):
    game = make_game(rules)
    player = game.players[1]
    assert not government.set_rates(game, player, 0, 0, 100)     # despotism: 60% at most
    assert government.set_rates(game, player, 40, 0, 60)
    assert not government.set_rates(game, player, 45, 0, 55)     # steps of 10
    player.tax_rate, player.luxury_rate, player.science_rate = 0, 0, 100
    government.clamp_rates(game, player)
    assert (player.tax_rate, player.luxury_rate, player.science_rate) == (40, 0, 60)


def test_war_and_peace(rules):
    game = make_game(rules, relation=WAR)
    assert game.at_war(1, 2)
    assert diplomacy.propose_peace(game, 1, 2, lambda: False) is False
    assert diplomacy.propose_peace(game, 1, 2, lambda: True) is True
    assert game.at_peace(1, 2) and not game.at_war(1, 2)
    assert diplomacy.declare_war(game, 2, 1)
    assert game.at_war(1, 2)


def test_senate(rules):
    game = make_game(rules, relation=PEACE)
    game.players[1].government = "republic"
    assert not diplomacy.declare_war(game, 1, 2)                 # the senate forbids it
    assert diplomacy.declare_war(game, 2, 1)
    assert diplomacy.propose_peace(game, 2, 1, lambda: False)    # and forces peace


def test_barbarians_are_always_enemies(rules):
    game = make_game(rules, relation=PEACE)
    assert game.at_war(0, 1) and game.at_war(2, 0)
    assert not diplomacy.propose_peace(game, 1, 0, lambda: True)


def test_contact_happens_on_sight(rules):
    game = make_game(rules)
    game.relations.clear()
    game.add_unit("militia", 2, 6, 5)
    unit = game.add_unit("militia", 1, 3, 5)
    visibility.reveal_unit(game, unit)
    assert not game.in_contact(1, 2)
    game.place_unit(unit, 5, 5)
    visibility.reveal_unit(game, unit)
    assert game.in_contact(1, 2) and game.at_war(1, 2)          # no treaty yet
    assert any(e["type"] == "contact" for e in game.events)


def test_great_library_shares_knowledge(rules):
    game = make_game(rules, civ_ids=("romans", "greeks", "french"))
    city = add_city(game, 1, 5, 5)
    city.buildings.add("great_library")
    game.wonders["great_library"] = city.id
    game.players[2].techs.add("pottery")
    research.share_knowledge(game, game.players[1])
    assert "pottery" not in game.players[1].techs               # known by one other only
    game.players[3].techs.add("pottery")
    research.share_knowledge(game, game.players[1])
    assert "pottery" in game.players[1].techs


def test_wonder_effects_reach_the_right_cities(rules):
    # Two seas (the world wraps) split the land in two continents.
    game = make_game(rules, width=40,
                     patches={(x, y): "ocean" for x in (20, 39) for y in range(12)})
    home = add_city(game, 1, 5, 5, size=6)
    same_land = add_city(game, 1, 10, 5, size=6)
    overseas = add_city(game, 1, 25, 5, size=6)
    for city in (home, same_land, overseas):
        city_rules.set_worked(game, city, [(0, -1), (1, 0), (0, 1), (-1, 0), (1, 1), (-1, -1)])
        city.specialists = {"entertainer": 0, "taxman": 0, "scientist": 0}
    before = [city_rules.compute_city(game, c).unhappy for c in (home, same_land, overseas)]
    home.buildings.add("js_bachs_cathedral")
    game.wonders["js_bachs_cathedral"] = home.id
    after = [city_rules.compute_city(game, c).unhappy for c in (home, same_land, overseas)]
    assert after[0] == max(0, before[0] - 2) and after[1] == max(0, before[1] - 2)
    assert after[2] == before[2]                                # another continent


def test_maintenance_sells_what_cannot_be_paid(rules):
    game = make_game(rules)
    city = add_city(game, 1, 5, 5)
    city.buildings.update({"temple", "library"})
    game.players[1].gold = 0
    game.players[1].tax_rate, game.players[1].science_rate = 0, 100
    cities.process_city(game, city)
    assert len(city.buildings & {"temple", "library"}) < 2
    assert any(e["type"] == "sold" for e in game.events)
