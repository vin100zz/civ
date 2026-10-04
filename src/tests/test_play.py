"""A person at the table: the turn that waits for it, its orders, what it delegates and
what it is allowed to know."""
from __future__ import annotations

import json

from server.ai.controller import AIController
from server.engine import actions, persistence
from server.engine.model.entities import PEACE, WAR
from server.engine.systems import cities, city as city_rules, movement, research, turn
from server.engine.view import PlayerView
from server.human import orders, report
from server.human.controller import ARRIVED, BLOCKED, MOVING, HumanController
from server.sim.runner import create_game, restore_game

from .conftest import add_city, make_game


def lead(game, player_id=1, knows_the_map=True):
    """Puts a person in charge of a player of a hand-made game, at the start of its turn."""
    controller = HumanController()
    game.controllers[player_id] = controller
    player = game.players[player_id]
    if knows_the_map:
        player.explored = bytearray([1]) * len(game.map.tiles)
    turn.begin_player_turn(game, player)
    return controller, PlayerView(game, player)


def end_turn_script(game, human):
    """A person who only founds its capital, keeps its cities busy and ends its turns."""
    view = PlayerView(game, game.players[human])
    for unit in view.my_units():
        if view.rules.units[unit.type].can("found_city") and not view.my_cities():
            view.do(actions.FoundCity(unit.id))
    for city in view.my_cities():
        if city.production is None:
            view.do(actions.SetProduction(city.id, "unit", "militia"))


# ── The turn ──────────────────────────────────────────────────────────────────

def test_the_game_waits_for_the_person(rules):
    game = create_game(rules, 3, player_count=4, human_civ="french")
    human = next(p for p in game.players if p.civ.id == "french")
    assert human.id == 1 and human.level == rules.game.difficulty.default_level
    assert turn.is_interactive(game, human)

    waiting = turn.advance(game)
    assert waiting is human and game.current_player == human.id and game.turn == 0
    settlers = next(u for u in game.player_units(human.id) if u.type == "settlers")
    assert settlers.moves_left > 0
    assert actions.apply(game, human.id, actions.FoundCity(settlers.id))
    assert len(game.player_cities(human.id)) == 1

    # The others only play once the person is done; then its next turn begins.
    assert not game.player_cities(2)
    assert turn.advance(game) is human
    assert game.turn == 1 and game.current_player == human.id
    assert game.player_cities(2), "the AI civilizations played their turn"
    assert game.player_cities(human.id)[0].food > 0, "the person's city was processed"


def test_advance_plays_like_play_turn(rules):
    """Without a person, `advance` plays one round per call, exactly as `play_turn` does."""
    one, two = create_game(rules, 11, player_count=4), create_game(rules, 11, player_count=4)
    for _ in range(25):
        turn.play_turn(one)
        assert turn.advance(two) is None
    assert one.turn == two.turn == 25
    assert persistence.game_to_data(one) == persistence.game_to_data(two)


def test_a_dead_person_no_longer_stops_the_game(rules):
    game = create_game(rules, 3, player_count=3, human_civ="romans")
    human = turn.advance(game)
    for unit in list(game.player_units(human.id)):
        actions.apply(game, human.id, actions.Disband(unit.id))
    assert not human.alive
    assert turn.advance(game) is None and game.turn == 1 and not game.finished
    turn.play_turn(game)                      # the game goes on, observed
    assert game.turn == 2


def test_saved_in_the_middle_of_a_turn(rules, tmp_path):
    game = create_game(rules, 5, player_count=4, human_civ="greeks")
    human = turn.advance(game).id
    for _ in range(6):
        end_turn_script(game, human)
        turn.advance(game)
    end_turn_script(game, human)              # half-way through the person's turn
    path = tmp_path / "mid-turn.json"
    persistence.save_game(game, path)
    copy = restore_game(rules, persistence.read_save(path))
    assert copy.current_player == human and turn.is_interactive(copy, copy.players[human])

    for _ in range(12):
        for each in (game, copy):
            end_turn_script(each, human)
            assert turn.advance(each).id == human
    assert json.dumps(persistence.game_to_data(game)) == json.dumps(persistence.game_to_data(copy))


# ── Units ─────────────────────────────────────────────────────────────────────

def test_go_to_goes_on_turn_after_turn(rules):
    game = make_game(rules, relation=PEACE)
    unit = game.add_unit("militia", 1, 2, 5)
    controller, view = lead(game)
    goal = game.map.tile(7, 5)
    assert controller.send(view, unit, goal) == MOVING
    assert controller.task(unit.id) == "goto" and controller.destination(unit.id) == [7, 5]
    assert game.map.steps(unit.x, unit.y, 7, 5) == 4, "one step this turn"
    for _ in range(10):
        turn.end_player_turn(game, game.players[1])
        turn.begin_player_turn(game, game.players[1])
        controller.begin_turn(game, game.players[1])
    assert unit.pos == (7, 5) and controller.task(unit.id) == ""

    assert controller.send(view, unit, game.map.tile(7, 5)) == ARRIVED


def test_go_to_never_starts_a_fight(rules):
    game = make_game(rules, relation=WAR)
    unit = game.add_unit("chariot", 1, 2, 5)
    enemy = game.add_unit("phalanx", 2, 4, 5)
    controller, view = lead(game)
    assert controller.send(view, unit, game.map.tile(4, 5)) == BLOCKED
    assert game.map.steps(unit.x, unit.y, 4, 5) == 1 and enemy.id in game.units
    assert not [e for e in game.events if e["type"] == "combat"]
    assert controller.task(unit.id) == ""


def test_any_order_takes_the_unit_back_in_hand(rules):
    game = make_game(rules, relation=PEACE)
    unit = game.add_unit("militia", 1, 2, 5)
    controller, view = lead(game)
    controller.send(view, unit, game.map.tile(9, 5))
    assert controller.task(unit.id) == "goto"
    controller.release(unit.id)
    assert controller.task(unit.id) == ""


def test_a_sentry_wakes_when_the_enemy_is_near(rules):
    game = make_game(rules, relation=WAR)
    sentry = game.add_unit("phalanx", 1, 5, 5)
    asleep = game.add_unit("phalanx", 1, 10, 9)
    controller, view = lead(game)
    for unit in (sentry, asleep):
        assert view.do(actions.SetOrder(unit.id, "sentry"))
    game.add_unit("legion", 2, 6, 6)
    turn.end_player_turn(game, game.players[1])
    turn.begin_player_turn(game, game.players[1])
    controller.begin_turn(game, game.players[1])
    assert sentry.order == "none" and asleep.order == "sentry"
    assert any("wakes up" in note["text"] for note in controller.notes)


def test_orders_open_to_a_unit(rules):
    game = make_game(rules, relation=WAR)
    add_city(game, 1, 10, 5)
    settlers = game.add_unit("settlers", 1, 4, 5)
    guard = game.add_unit("phalanx", 1, 10, 5)
    controller, view = lead(game)

    names = {o["id"]: o for o in orders.unit_orders(view, controller, settlers)}
    assert {"found_city", "road", "goto", "explore", "auto_work", "disband"} <= set(names)
    assert names["road"]["turns"] == movement.work_turns(game, settlers, "road")
    assert "fortress" not in names, "needs an advance the player does not have"

    names = {o["id"] for o in orders.unit_orders(view, controller, guard)}
    assert "fortify" in names and "found_city" not in names and "auto_work" not in names

    view.do(actions.SetOrder(guard.id, "fortify"))
    names = {o["id"] for o in orders.unit_orders(view, controller, guard)}
    assert "wake" in names and "fortify" not in names


def test_preview_of_a_move(rules):
    game = make_game(rules, relation=WAR)
    chariot = game.add_unit("chariot", 1, 4, 5)
    game.add_unit("phalanx", 2, 5, 5)
    controller, view = lead(game)

    fight = orders.preview(view, chariot, game.map.tile(5, 5))
    assert fight["kind"] == "attack" and fight["defender"] == "Phalanx"
    assert fight["attack"] == 4 and 0 < fight["win"] < 1
    assert orders.preview(view, chariot, game.map.tile(3, 5))["kind"] == "move"
    held = orders.preview(view, chariot, game.map.tile(4, 6))
    assert held["kind"] == "refused" and held["reason"] == "zone of control"

    far = orders.preview(view, chariot, game.map.tile(4, 1))
    assert far["kind"] == "route" and far["steps"][-1][:2] == [4, 1]
    assert far["turns"] == 2, "four tiles for a unit with two moves"

    ship = game.add_unit("trireme", 1, 0, 0)
    assert orders.preview(view, ship, game.map.tile(8, 8))["kind"] == "no_route"


def test_units_left_to_themselves(rules):
    game = make_game(rules, relation=PEACE, width=24, height=16)
    city = add_city(game, 1, 6, 6, size=3)
    explorer = game.add_unit("militia", 1, 6, 6)
    worker = game.add_unit("settlers", 1, 6, 6)
    controller, view = lead(game, knows_the_map=False)
    known = sum(game.players[1].explored)

    assert controller.automate(view, explorer, "explore")
    assert not controller.automate(view, explorer, "work")
    assert controller.automate(view, worker, "work")
    for _ in range(6):
        turn.end_player_turn(game, game.players[1])
        turn.begin_player_turn(game, game.players[1])
        controller.begin_turn(game, game.players[1])
    assert sum(game.players[1].explored) > known, "the explorer uncovered new land"
    area = [tile for _, tile in game.map.city_area(city.x, city.y)]
    assert worker.order in ("road", "irrigate", "mine") or any(
        t.road or t.irrigation or t.mine for t in area), "the worker improves the land"


def test_a_governor_chooses_for_the_city(rules):
    game = make_game(rules, relation=PEACE)
    city = add_city(game, 1, 6, 6, size=3)
    controller, view = lead(game)
    assert city.production is None
    controller.govern(view, city, True)
    assert city.production is not None and controller.governed(city.id)
    assert any(city.name in note["text"] for note in controller.notes)
    controller.govern(view, city, False)
    assert not controller.governed(city.id)


def test_delegations_are_saved(rules):
    controller = HumanController()
    controller.memory["goto"]["12"] = [3, 4]
    controller.memory["auto"]["7"] = "explore"
    controller.memory["governed"] = [2]
    controller.work_missions = {9: ("improve", 1, 2, "road")}
    state = json.loads(json.dumps(controller.save_state()))
    restored = HumanController()
    restored.load_state(state)
    assert restored.task(12) == "goto" and restored.task(7) == "explore" and restored.governed(2)
    assert restored.work_missions == controller.work_missions


# ── Cities ────────────────────────────────────────────────────────────────────

def test_citizens_placed_by_hand(rules):
    game = make_game(rules, relation=PEACE)
    city = add_city(game, 1, 6, 6, size=3)
    game.current_player = 1
    assert len(city.worked) == 3
    off = city.worked[0]
    free = next(o for o, _ in city_rules.workable_tiles(game, city) if o not in city.worked)

    assert actions.apply(game, 1, actions.ToggleTile(city.id, *off))
    assert off not in city.worked and city.specialists["entertainer"] == 1
    assert actions.apply(game, 1, actions.ToggleTile(city.id, *free))
    assert free in city.worked and city.specialist_count == 0
    assert game.map.tile(city.x + free[0], city.y + free[1]).worked_by == city.id
    refused = actions.apply(game, 1, actions.ToggleTile(city.id, *off))
    assert not refused and "citizen" in refused.reason

    # Taxmen and scientists need a large city.
    actions.apply(game, 1, actions.ToggleTile(city.id, *free))
    assert not actions.apply(game, 1, actions.ChangeSpecialist(city.id, "entertainer"))
    city.size = rules.game.city.specialist_min_size
    city_rules.auto_arrange(game, city)
    actions.apply(game, 1, actions.ToggleTile(city.id, *city.worked[0]))
    entertainers = city.specialists["entertainer"]
    science = city_rules.compute_city(game, city).science
    assert actions.apply(game, 1, actions.ChangeSpecialist(city.id, "entertainer"))
    assert city.specialists["taxman"] == 1
    assert actions.apply(game, 1, actions.ChangeSpecialist(city.id, "taxman"))
    assert city.specialists == {"entertainer": entertainers - 1, "taxman": 0, "scientist": 1}
    assert city_rules.compute_city(game, city).science == science + rules.game.city.specialist_yield


def test_selling_a_building(rules):
    game = make_game(rules, relation=PEACE)
    city = add_city(game, 1, 6, 6, size=3)
    city.buildings.update({"temple", "barracks"})
    game.current_player = 1
    gold = game.players[1].gold

    assert actions.apply(game, 1, actions.SellBuilding(city.id, "temple"))
    assert "temple" not in city.buildings
    assert game.players[1].gold == gold + rules.buildings["temple"].cost
    assert not actions.apply(game, 1, actions.SellBuilding(city.id, "barracks")), "one per turn"
    cities.process_city(game, city)
    assert not actions.apply(game, 1, actions.SellBuilding(city.id, "palace"))
    assert actions.apply(game, 1, actions.SellBuilding(city.id, "barracks"))


def test_a_level_only_changes_the_person(rules):
    game = make_game(rules, relation=PEACE, width=24)
    mine, theirs = add_city(game, 1, 5, 6, size=6), add_city(game, 2, 15, 6, size=6)
    base = [city_rules.compute_city(game, c).unhappy for c in (mine, theirs)]
    cost = research.research_cost(game, game.players[1])

    game.players[1].level = "emperor"
    assert city_rules.compute_city(game, mine).unhappy > base[0]
    assert city_rules.compute_city(game, theirs).unhappy == base[1]
    assert research.research_cost(game, game.players[1]) > cost
    assert research.research_cost(game, game.players[2]) == cost
    game.players[1].level = "chieftain"
    assert city_rules.compute_city(game, mine).unhappy < base[0]


# ── Diplomacy ─────────────────────────────────────────────────────────────────

def test_a_peace_proposal_waits_for_the_person(rules):
    game = make_game(rules, relation=WAR)
    game.controllers[1] = HumanController()
    game.controllers[2] = AIController()
    relation = game.relation(1, 2)

    game.current_player = 2
    assert not actions.apply(game, 2, actions.ProposePeace(1)), "no answer yet"
    assert relation.pending_from == 2 and relation.state == WAR
    game.current_player = 1
    assert PlayerView(game, game.players[1]).peace_proposals() == [2]
    assert actions.apply(game, 1, actions.AnswerPeace(2, True))
    assert relation.state == PEACE and relation.pending_from is None
    assert not actions.apply(game, 1, actions.AnswerPeace(2, True)), "nothing left to answer"

    # A proposal left unanswered is refused when the person ends its turn.
    relation.state = WAR
    game.current_player = 2
    actions.apply(game, 2, actions.ProposePeace(1))
    turn.end_player_turn(game, game.players[2])
    assert relation.pending_from == 2
    turn.end_player_turn(game, game.players[1])
    assert relation.pending_from is None and relation.state == WAR

    game.current_player = 2
    actions.apply(game, 2, actions.ProposePeace(1))
    game.current_player = 1
    assert actions.apply(game, 1, actions.AnswerPeace(2, False))
    assert relation.state == WAR


# ── What the person may know ──────────────────────────────────────────────────

def test_events_the_person_hears_of(rules):
    game = make_game(rules, civ_ids=("romans", "greeks", "germans"), relation=WAR, width=30)
    add_city(game, 1, 4, 5)
    view = PlayerView(game, game.players[1])
    turn.begin_player_turn(game, game.players[1])

    assert view.knows_event({"type": "tech", "text": "", "player": 1})
    assert view.knows_event({"type": "combat", "text": "", "player": 2, "other": 1, "x": 20, "y": 5})
    assert view.knows_event({"type": "wonder", "text": "", "player": 2, "x": 20, "y": 5})
    assert view.knows_event({"type": "combat", "text": "", "player": 2, "other": 3, "x": 5, "y": 5})
    assert not view.knows_event({"type": "combat", "text": "", "player": 2, "other": 3, "x": 20, "y": 5})
    assert not view.knows_event({"type": "tech", "text": "", "player": 2})
    assert not view.knows_event({"type": "city_founded", "text": "", "player": 3, "x": 22, "y": 8})
    # A war between two civilizations is news only to those who know both of them.
    assert view.knows_event({"type": "war", "text": "", "player": 2, "other": 3})
    game.relation(1, 3).state = "no_contact"
    assert not view.knows_event({"type": "war", "text": "", "player": 2, "other": 3})


def test_alerts(rules):
    game = make_game(rules, relation=WAR)
    city = add_city(game, 1, 6, 6)
    game.add_unit("legion", 2, 8, 6)
    game.add_unit("legion", 2, 8, 6)
    view = PlayerView(game, game.players[1])
    turn.begin_player_turn(game, game.players[1])
    alerts = report.alerts(view)
    assert [a["kind"] for a in alerts] == ["threat"]
    assert alerts[0]["text"] == f"2 Greek Legion near {city.name}" and alerts[0]["city"] == city.id
