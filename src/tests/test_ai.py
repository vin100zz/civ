"""The AI plays whole games: they must run, stay consistent and show signs of life."""
from __future__ import annotations

import pytest

import json

from server.ai.controller import AIController
from server.ai.knowledge import Knowledge
from server.ai import diplomacy as ai_diplomacy, missions as M, pathfinding, strategic
from server.engine import persistence
from server.engine.model.entities import NO_CONTACT, PEACE, SPECIALISTS, WAR
from server.engine.systems import cities, diplomacy, turn, visibility
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


# ── Terrain work ──────────────────────────────────────────────────────────────

def settler_jobs(game, for_person=False, player_id=1):
    """The terrain work the strategy posts for a player who knows the map: (x, y) -> order,
    best job first. An AI only posts as many jobs as it wants workers."""
    player = game.players[player_id]
    player.explored = bytearray([1]) * len(game.map.tiles)
    view = PlayerView(game, player)
    plan = strategic.Plan()
    strategic.improve_missions(view, Knowledge(view), plan, for_person=for_person)
    return {(m.x, m.y): m.order for m in plan.missions}


def test_settlers_clear_jungle_and_swamp_but_not_forest(rules):
    patches = {(6, 4): "jungle", (8, 6): "swamp", (4, 6): "forest", (6, 8): "jungle"}
    game = make_game(rules, width=16, height=12, patches=patches)
    city = add_city(game, 1, 6, 6)
    game.map.tile(6, 8).special = True                     # gems are kept
    for _, tile in game.map.city_area(city.x, city.y):
        tile.road = tile.irrigation = tile.terrain == "grassland"

    jobs = settler_jobs(game, for_person=True)
    assert jobs == {(6, 4): "irrigate", (8, 6): "irrigate"}, "jungle and swamp to grassland"
    assert rules.terrains["jungle"].irrigation.turns > 12, "however long it takes"
    assert list(settler_jobs(game).values()) == ["irrigate"], "an AI clears them too"


def test_settlers_lay_railroads_wherever_the_land_yields_more(rules):
    game = make_game(rules, width=16, height=12, terrain="forest")
    city = add_city(game, 1, 6, 6, size=2)
    game.players[1].techs.add(rules.game.movement.railroad_tech)
    for _, tile in game.map.city_area(city.x, city.y):
        tile.road = True

    jobs = settler_jobs(game, for_person=True)
    area = {tile.pos for _, tile in game.map.city_area(city.x, city.y)}
    assert jobs == {pos: "railroad" for pos in area}, "worked or not"
    worked = {(city.x + dx, city.y + dy) for dx, dy in city.worked}
    assert set(list(jobs)[:len(worked)]) == worked, "the worked tiles first"


def test_settlers_link_the_cities_by_road_then_railroad(rules):
    # Forest everywhere: a road there only helps to move.
    game = make_game(rules, width=40, height=12, terrain="forest")
    add_city(game, 1, 4, 6)
    add_city(game, 1, 10, 6)
    add_city(game, 1, 25, 6)                               # too far to be linked
    between = {(x, 6) for x in range(5, 10)}

    jobs = settler_jobs(game, for_person=True)
    assert set(jobs) == between and set(jobs.values()) == {"road"}
    ai_jobs = settler_jobs(game)
    assert ai_jobs and set(ai_jobs) <= between, "an AI links its cities first"

    # A road already laid nearby is followed; once there, the railroad comes.
    for x in range(5, 10):
        game.map.tile(x, 7).road = True
    game.players[1].techs.add(rules.game.movement.railroad_tech)
    jobs = settler_jobs(game, for_person=True)
    assert {(x, 7) for x in range(5, 10)} <= set(jobs) and set(jobs.values()) == {"railroad"}
    assert not set(jobs) & between


# ── War and peace ─────────────────────────────────────────────────────────────

def test_a_broken_treaty_is_remembered(rules):
    game = make_game(rules, civ_ids=("romans", "greeks", "germans", "english"), relation=PEACE)
    game.relation(1, 4).state = NO_CONTACT                 # the English never met the Romans
    game.relation(1, 2).since_turn = 25
    game.turn = 30
    greeks, germans, english = (PlayerView(game, game.players[i]) for i in (2, 3, 4))
    trusting = ai_diplomacy.peace_willingness(greeks, Knowledge(greeks), 1)

    assert diplomacy.declare_war(game, 1, 2)
    assert game.players[1].broken_treaties == [[2, 30, 5]]
    assert ai_diplomacy.distrust(greeks, 1) == 2.0, "broken with them, five turns after signing"
    assert ai_diplomacy.distrust(germans, 1) == pytest.approx(0.7), "they heard of it"
    assert ai_diplomacy.distrust(english, 1) == 0.0, "they know nothing of the Romans"
    game.relation(1, 2).since_turn = 0                     # the same war weariness as before
    assert ai_diplomacy.peace_willingness(greeks, Knowledge(greeks), 1) < trusting

    game.turn += int(rules.ai.get("diplomacy", "distrust_memory"))
    assert ai_diplomacy.distrust(greeks, 1) == 0.0, "forgotten in time"
    saved = json.loads(json.dumps(persistence.game_to_data(game)))
    assert persistence.game_from_data(rules, saved).players[1].broken_treaties == [[2, 30, 5]]


def test_the_others_close_ranks_against_a_dominant_civilization(rules):
    game = make_game(rules, civ_ids=("romans", "greeks", "germans"), relation=WAR)
    add_city(game, 1, 2, 2, size=3)
    add_city(game, 2, 8, 2, size=3)
    for x in (2, 6, 10):
        add_city(game, 3, x, 8, size=12)
    romans = game.players[1]
    for city in game.cities.values():
        if city.owner != 1:
            visibility.remember_city(game, romans, city)
    view = PlayerView(game, romans)
    know = Knowledge(view)
    assert ai_diplomacy.dominant(view, know) == 3
    willing = lambda other, leader: ai_diplomacy.peace_willingness(view, know, other, leader)
    assert willing(3, 3) < willing(3, None), "no peace with the dominant civilization"
    assert willing(2, 3) > willing(2, None), "peace with its other enemy"


def test_a_war_is_prepared_then_declared(rules):
    """The attack force is raised and gathered on the border before the war is declared."""
    game = make_game(rules, width=24, relation=PEACE)
    home = add_city(game, 1, 4, 5, size=8)
    add_city(game, 1, 4, 9, size=8)
    theirs = add_city(game, 2, 12, 5, size=2)
    romans = game.players[1]
    romans.explored = bytearray([1]) * len(game.map.tiles)
    visibility.remember_city(game, romans, theirs)
    game.turn, game.current_player = 50, 1
    memory = {"war_plan": [2, game.turn]}

    def review():
        view = PlayerView(game, romans)
        notes = ai_diplomacy.review(view, Knowledge(view), memory)
        return view, notes, strategic.make_plan(view, Knowledge(view), {}, memory)

    view, notes, plan = review()
    assert game.relation(1, 2).state == PEACE and memory["war_plan"] == [2, 50]
    assert any(note.startswith("preparing war on") for note in notes)
    assert [m.city_id for m in plan.war_targets] == [theirs.id]
    assert [m.stage for m in plan.missions if m.kind == M.ATTACK_CITY] == ["rally"]
    assert plan.attackers_wanted == ai_diplomacy.attack_force_wanted(view, Knowledge(view), True)

    ready = max(plan.attackers_wanted, int(rules.ai.get("strategy", "siege_group_size")))
    for _ in range(ready):
        game.add_unit("legion", 1, home.x, home.y)
    _, notes, plan = review()
    assert game.relation(1, 2).state == WAR and "war_plan" not in memory
    assert "war on Greeks" in notes


def test_a_war_that_goes_well_goes_on(rules):
    game = make_game(rules, relation=PEACE)
    add_city(game, 1, 2, 2, size=4)
    theirs = add_city(game, 2, 8, 2, size=4)
    romans, greeks = game.players[1], game.players[2]
    visibility.remember_city(game, romans, theirs)
    game.turn = 40
    assert diplomacy.declare_war(game, 1, 2)
    view = PlayerView(game, romans)
    assert ai_diplomacy.peace_willingness(view, Knowledge(view), 2) == 0.0, "our war, just begun"

    # The Romans take a Greek city: they remember it, and the Greeks remember their loss.
    controller = AIController()
    foreign = {m.city_id: m.owner for m in view.known_foreign_cities()}
    cities.capture_city(game, game.add_unit("legion", 1, 7, 2), theirs)
    controller._note_conquests(view, foreign)
    assert controller.memory["conquests"] == [[theirs.id, 40, 2]]

    game.turn += int(rules.ai.get("diplomacy", "war_min_turns"))
    know = Knowledge(view)
    assert ai_diplomacy.peace_willingness(view, know, 2, memory=controller.memory) \
        < ai_diplomacy.peace_willingness(view, know, 2, memory={}), "winning"
    victim = PlayerView(game, greeks)
    lost = {"lost_cities": [[theirs.id, 40]]}
    assert ai_diplomacy.peace_willingness(victim, Knowledge(victim), 1, memory=lost) \
        > ai_diplomacy.peace_willingness(victim, Knowledge(victim), 1, memory={}), "losing"


# ── Counter-attack ────────────────────────────────────────────────────────────

def test_ai_goes_back_for_a_city_it_lost(rules):
    game = make_game(rules, width=24)
    home = add_city(game, 1, 4, 5, size=4)
    lost = add_city(game, 1, 8, 5, size=2)
    other = add_city(game, 2, 8, 9, size=4)                # bigger, and just as close
    ai = game.players[1]
    ai.explored = bytearray([1]) * len(game.map.tiles)
    visibility.remember_city(game, ai, other)
    controller = AIController()
    controller.memory["my_cities"] = [home.id, lost.id]
    cities.capture_city(game, game.add_unit("legion", 2, 9, 5), lost)
    game.add_unit("phalanx", 2, lost.x, lost.y)            # and now defended

    def target():
        view = PlayerView(game, ai)
        controller._note_losses(view)
        return strategic.make_plan(view, Knowledge(view), {}, controller.memory).war_targets[0]

    assert controller.memory.get("lost_cities") is None
    assert target().city_id == lost.id
    assert controller.memory["lost_cities"] == [[lost.id, game.turn]]
    controller.memory = {"my_cities": [home.id]}           # had it never been ours
    assert target().city_id == other.id


def test_invaders_call_for_a_counter_attack(rules):
    """An enemy that lands next to a city is fought, even with no enemy city within reach."""
    width, height = 24, 12
    patches = {(x, y): "ocean" for x in range(width) for y in range(height)}
    patches.update({(x, y): "grassland" for x in range(2, 9) for y in range(2, 9)})     # home
    patches.update({(x, y): "grassland" for x in range(15, 20) for y in range(3, 8)})  # the enemy
    game = make_game(rules, width=width, height=height, patches=patches)
    city = add_city(game, 1, 5, 5, size=4)
    add_city(game, 2, 17, 5, size=4)
    ai = game.players[1]
    ai.explored = bytearray([1]) * len(game.map.tiles)

    def plan():
        visibility.refresh(game, ai)
        view = PlayerView(game, ai)
        return strategic.make_plan(view, Knowledge(view), {}, {})

    calm = plan()
    assert calm.invaders == 0 and not calm.war_targets
    for _ in range(2):
        game.add_unit("legion", 2, 6, 6)
    landed = plan()
    assert landed.invaders == 2
    assert landed.attackers_wanted == calm.attackers_wanted + 2

    # A strong defender with comrades to hold the city goes for an invader it can beat.
    for _ in range(3):
        game.add_unit("mech_inf", 1, city.x, city.y)
    landed = plan()
    hunters = [m for m in landed.assignment.values() if m.kind == M.ATTACK_UNIT]
    assert hunters and all(game.units[uid].type == "mech_inf" for m in hunters for uid in m.assigned)
