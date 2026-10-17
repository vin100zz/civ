"""The Golden Ages rules, and the engine features they brought: the Harbour, buildings given by
a wonder, a movement bonus limited to a continent, and siege engines against walls."""
from __future__ import annotations

import pytest

from server.ai.city_governor import Governor
from server.ai.knowledge import Knowledge
from server.ai import strategic
from server.api import serialize
from server.engine import effects as fx
from server.engine.model.entities import Item
from server.engine.rules.loader import load_rules
from server.engine.systems import city as city_rules
from server.engine.systems import movement, production, visibility
from server.engine.view import PlayerView
from server.human.controller import HumanController

from .conftest import add_city, make_game

# Each line of units: every unit becomes obsolete with the advance that brings the next one,
# or the AI, which weighs units by strength for the cost, would keep building the older one.
LINES = [
    ["phalanx", "musketeers", "riflemen", "mech_inf"],
    ["horsemen", "knights", "dragoons", "cavalry", "armor"],
    ["chariot", "knights"],
    ["catapult", "cannon", "artillery", "howitzer"],
    ["trireme", "caravel", "galleon", "transport"],
    ["galley", "frigate", "ironclad", "destroyer", "cruiser", "battleship"],
]


@pytest.fixture(scope="module")
def golden():
    return load_rules(ruleset="golden_ages")


def test_golden_ages_rules(golden):
    known: set[str] = set()
    progress = True
    while progress:
        progress = False
        for tech in golden.techs.values():
            if tech.id not in known and all(p in known for p in tech.prerequisites):
                known.add(tech.id)
                progress = True
    assert known == set(golden.techs)
    assert not [w.id for w in golden.wonders if w.obsolete_by is not None]
    for line in LINES:
        for older, newer in zip(line, line[1:]):
            assert golden.units[older].obsolete_by == golden.units[newer].requires, (older, newer)
    assert golden.units["battleship"].attack == 12
    assert {"mfg_plant", "hydro_plant", "nuclear_plant", "seti_program"}.isdisjoint(golden.buildings)


def test_harbour_feeds_ocean_tiles(golden):
    patches = {(x, y): "ocean" for x in range(16) for y in range(7, 12)}
    game = make_game(golden, patches=patches)
    city = add_city(game, 1, 5, 5, size=3)
    ocean, grass = game.map.tile(5, 7), game.map.tile(4, 5)
    before = (city_rules.tile_yields(game, city, ocean).food,
              city_rules.tile_yields(game, city, grass).food)
    city.buildings.add("harbour")
    after = (city_rules.tile_yields(game, city, ocean).food,
             city_rules.tile_yields(game, city, grass).food)
    assert after == (before[0] + 1, before[1])


def test_buildings_given_by_a_wonder(golden):
    game = make_game(golden, width=30, height=20)
    home = add_city(game, 1, 3, 3)
    other = add_city(game, 1, 12, 8, size=8)
    player = game.players[1]
    player.techs |= {"pottery", "sanitation", "construction"}
    assert production.can_build(game, other, Item("building", "granary"))
    assert not production.can_build(game, other, Item("building", "sewer_system"))

    game.wonders["pyramids"] = home.id
    game.wonders["statue_of_liberty"] = home.id
    assert fx.given_buildings(game, other) == {"granary": "pyramids", "aqueduct": "statue_of_liberty"}
    # Not built a second time, a prerequisite all the same, and nothing to pay for.
    assert not production.can_build(game, other, Item("building", "granary"))
    assert production.can_build(game, other, Item("building", "sewer_system"))
    assert city_rules.compute_city(game, other).building_upkeep == 0
    assert city_rules.max_size(game, other) == 20
    payload = serialize.own_city_payload(game, other, HumanController())
    assert payload["given"] == {"granary": "pyramids", "aqueduct": "statue_of_liberty"}
    assert payload["buildings"] == []

    # A city that built its own Granary keeps it, and is not told it was given one.
    other.buildings.add("granary")
    assert "granary" not in fx.given_buildings(game, other)


def test_great_wall_and_royal_road_stay_on_their_continent(golden):
    patches = {(x, 5): "ocean" for x in range(16)}         # two continents, north and south
    game = make_game(golden, patches=patches)
    north = add_city(game, 1, 4, 2)
    south = add_city(game, 1, 4, 9)
    game.wonders["great_wall"] = north.id
    game.wonders["royal_road"] = north.id
    assert "city_walls" in fx.effective_buildings(game, north)
    assert "city_walls" not in fx.effective_buildings(game, south)
    near, far = game.add_unit("musketeers", 1, 6, 2), game.add_unit("musketeers", 1, 6, 9)
    points = golden.game.movement.points_per_move
    assert movement.full_moves(game, near) == 2 * points
    assert movement.full_moves(game, far) == 1 * points


@pytest.mark.parametrize("walls, expected", [(True, "cannon"), (False, "dragoons")])
def test_ai_brings_cannons_to_walled_cities(golden, walls, expected):
    game = make_game(golden, width=24)
    city = add_city(game, 1, 4, 5, size=6)
    enemy = add_city(game, 2, 12, 5, size=4)
    if walls:
        enemy.buildings.add("city_walls")
    ai = game.players[1]
    ai.techs |= {"bronze_working", "gunpowder", "chivalry", "leadership", "metallurgy"}
    ai.explored = bytearray([1]) * len(game.map.tiles)
    city.shields = 30                                      # every attacker is a few turns away
    game.add_unit("musketeers", 1, city.x, city.y)
    visibility.remember_city(game, ai, enemy)
    view = PlayerView(game, ai)
    know = Knowledge(view)
    plan = strategic.make_plan(view, know, {}, {})
    assert plan.war_targets and plan.attackers_wanted > 0
    governor = Governor(view, know, plan)
    offense = [c for c in governor.evaluate(city, view.city_stats(city)) if c.reason.startswith("offense")]
    assert offense and offense[0].item.id == expected
