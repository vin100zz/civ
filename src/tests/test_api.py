"""The web layer: static pages, rules, and the observer's WebSocket."""
from __future__ import annotations

import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient

from server.api import serialize
from server.api.app import create_app
from server.api.replay import HEADLINES, Replay
from server.api.session import Session, base_name, year_tag
from server.engine import persistence
from server.engine.model.entities import NO_CONTACT, Item
from server.engine.systems import pollution, spaceship
from server.human.controller import HumanController

from .conftest import add_city, make_game


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    saves = tmp_path_factory.mktemp("saves")
    with TestClient(create_app(saves_dir=saves)) as test_client:
        yield test_client


def test_static_files_and_rules(client):
    assert "Civilization" in client.get("/").text
    script = client.get("/js/main.js")
    assert script.status_code == 200 and script.headers["cache-control"] == "no-cache"
    assert client.get("/resources/terrain/grassland.png").status_code == 200
    rules = client.get("/api/rules").json()
    assert len(rules["units"]) == 28 and len(rules["terrains"]) == 12
    assert rules["ruleset"]["id"] == "civ1"
    assert {"id", "name", "color"} <= set(rules["civs"][0])
    assert rules["defaults"]["map"] == {"shape": "continents", "land": 20, "relief": 1,
                                        "climate": 1, "temperature": 1, "age": 1, "huts": 1,
                                        "historical_starts": True}
    assert rules["land_steps"] == [20, 30, 40, 50, 60, 70, 80]
    shapes = {s["id"]: s for s in rules["map_shapes"]}
    assert {"continents", "small_islands", "pangaea", "isthmus", "earth"} <= set(shapes)
    assert shapes["continents"]["land"] == 20 and shapes["world_belt"]["land"] == 40
    earth = shapes["earth"]
    assert earth["land"] is None and len(earth["fixed"]["rows"]) == 50
    assert "fixed" not in shapes["pangaea"]


def test_observer_session(client):
    with client.websocket_connect("/ws") as socket:
        init = socket.receive_json()
        assert init["type"] == "init"
        tiles = init["map"]["width"] * init["map"]["height"]
        assert len(init["map"]["terrain"]) == tiles == len(init["map"]["flags"])
        assert init["state"]["turn"] == 0 and init["state"]["pov"] is None

        socket.send_json({"cmd": "new_game", "name": "game", "seed": 42, "players": 4})
        init = socket.receive_json()
        assert init["type"] == "init" and init["state"]["seed"] == 42
        assert len([p for p in init["state"]["players"] if not p["barbarian"]]) == 4

        socket.send_json({"cmd": "step"})
        message = socket.receive_json()
        assert message["type"] == "turn" and message["state"]["turn"] == 1
        assert message["state"]["cities"], "every civilization founds its capital on turn one"
        assert socket.receive_json()["type"] == "status"

        city = message["state"]["cities"][0]
        socket.send_json({"cmd": "city", "id": city["id"]})
        detail = socket.receive_json()
        assert detail["type"] == "city" and detail["city"]["name"] == city["name"]
        assert len(detail["city"]["tiles"]) == 21
        assert detail["city"]["decision"]["candidates"]

        socket.send_json({"cmd": "player", "id": city["owner"]})
        detail = socket.receive_json()
        assert detail["type"] == "player" and "needs" in detail["player"]["ai"]

        # Looking through one civilization's eyes hides most of the world.
        socket.send_json({"cmd": "pov", "player": city["owner"]})
        state = socket.receive_json()["state"]
        assert state["pov"] == city["owner"]
        assert state["explored"].count("0") > tiles * 0.8
        assert all(unit[2] == city["owner"] or state["explored"][unit[4] * init["map"]["width"] + unit[3]] == "2"
                   for unit in state["units"])


def test_save_and_load(client):
    with client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["saves"] == []
        socket.send_json({"cmd": "new_game", "name": "game", "seed": 9, "players": 3})
        socket.receive_json()
        for _ in range(3):
            socket.send_json({"cmd": "step"})
            turn_message = socket.receive_json()
            socket.receive_json()
        cities = turn_message["state"]["cities"]

        socket.send_json({"cmd": "save", "name": "bad name!"})
        assert socket.receive_json()["ok"] is False

        socket.send_json({"cmd": "save", "name": "my-game"})
        assert socket.receive_json() == {"type": "notice", "text": "Game saved as my-game.", "ok": True}
        assert socket.receive_json() == {"type": "saves", "saves": ["my-game"],
                                         "save_name": "my-game"}

        socket.send_json({"cmd": "new_game", "name": "game", "seed": 10, "players": 3})
        assert socket.receive_json()["state"]["turn"] == 0

        socket.send_json({"cmd": "load", "name": "my-game"})
        init = socket.receive_json()
        assert init["type"] == "init" and init["state"]["seed"] == 9 and init["state"]["turn"] == 3
        assert init["state"]["cities"] == cities
        assert len(init["history"]) == 4 and init["saves"] == ["my-game"]
        assert socket.receive_json()["ok"] is True

        socket.send_json({"cmd": "step"})                    # the loaded game goes on
        assert socket.receive_json()["state"]["turn"] == 4
        socket.receive_json()

        socket.send_json({"cmd": "load", "name": "unknown"})
        assert socket.receive_json()["ok"] is False


def test_a_new_game_needs_a_name(client):
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        for name in (None, "", "bad name!", "x" * 41):
            socket.send_json({"cmd": "new_game", "name": name, "seed": 3, "players": 3})
            assert socket.receive_json() == {
                "type": "notice", "text": "Name the new game: letters, digits, - and _.", "ok": False}
        socket.send_json({"cmd": "new_game", "name": "first", "seed": 3, "players": 3})
        assert socket.receive_json()["type"] == "init"
        assert client.app.state.session.save_name == "first"


def test_new_game_with_a_chosen_map(client):
    def land_masses(init):
        return len({c for c in init["map"]["continent"] if c > 0})

    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        socket.send_json({"cmd": "new_game", "name": "game", "seed": 5, "players": 3})
        default = socket.receive_json()
        socket.send_json({"cmd": "new_game", "name": "game", "seed": 5, "players": 3,
                          "map": {"shape": "small_islands", "relief": 2, "climate": 0}})
        islands = socket.receive_json()
        assert islands["state"]["seed"] == 5
        assert islands["map"]["terrain"] != default["map"]["terrain"]
        # Invalid choices fall back on the defaults of the rules.
        socket.send_json({"cmd": "new_game", "name": "game", "seed": 5, "players": 3,
                          "map": {"shape": ["atlantis"], "relief": 9, "climate": 1.0,
                                  "land": 25, "huts": True, "historical_starts": 1}})
        assert socket.receive_json()["map"]["terrain"] == default["map"]["terrain"]
        socket.send_json({"cmd": "new_game", "name": "game", "seed": 5, "players": 3,
                          "map": {"shape": "continents", "land": 60}})
        more = socket.receive_json()["map"]["terrain"]
        assert more != default["map"]["terrain"]


def test_surprise_world(client, rules):
    session = client.app.state.session
    choices = {"shape": "continents", "land": 20, "relief": 1, "huts": 2, "surprise": True}
    drawn = [session._map_settings(rules, choices, seed) for seed in range(1, 30)]
    assert drawn[0] == session._map_settings(rules, choices, 1)        # the seed decides
    assert len({s.shape for s in drawn}) > 4 and len({s.land for s in drawn}) > 3
    assert all(s.huts == 2 and rules.game.map.shapes[s.shape].fixed is None for s in drawn)
    assert len({(s.relief, s.climate, s.temperature, s.age) for s in drawn}) > 10
    # Only the listed settings are drawn, with the values the seed gives them all.
    choices["surprise"] = ["shape", "climate"]
    partial = [session._map_settings(rules, choices, seed) for seed in range(1, 30)]
    assert [(s.shape, s.climate) for s in partial] == [(s.shape, s.climate) for s in drawn]
    assert all((s.land, s.relief, s.huts) == (20, 1, 2) for s in partial)
    defaults = rules.game.map
    assert all((s.temperature, s.age) == (defaults.temperature, defaults.age) for s in partial)
    choices["surprise"] = []
    assert session._map_settings(rules, choices, 1).shape == "continents"


# ── A person leads a civilization ─────────────────────────────────────────────

WORLD_NEWS = {"wonder", "civ_destroyed", "spaceship_launched", "spaceship_lost", "nuclear",
              "global_warming", "game_over", "war", "peace"}


def receive(socket, kind):
    """The next message of this kind (others, like the list of saves, may come in between)."""
    message = socket.receive_json()
    while message["type"] != kind:
        message = socket.receive_json()
    return message


def order(socket, **message):
    socket.send_json({"cmd": "action", **message})
    return receive(socket, "update")


def start_playing(socket, **options):
    socket.receive_json()
    socket.send_json({"cmd": "new_game", "name": "game", "seed": 42, "players": 4, "mode": "play",
                      "civ": "romans", **options})
    return socket.receive_json()


def test_play_session(client):
    with client.websocket_connect("/ws") as socket:
        init = start_playing(socket, level="king")
        state = init["state"]
        assert init["type"] == "init" and state["play"] == {"human": 1, "active": True}
        assert state["pov"] == 1 and state["players"][1]["civ"] == "romans"
        assert state["me"]["level"] == "king" and state["me"]["research_options"]

        # Nothing is known of the civilizations not met yet.
        others = [p for p in state["players"] if p["id"] > 1]
        assert len(others) == 3
        assert all(not p["met"] and p["nation"] == "Unknown" and p["gold"] is None for p in others)
        # The browser only holds the land the person has explored.
        sea = next(i for i, t in enumerate(init["rules"]["terrains"]) if not t["land"])
        hidden = [i for i, mark in enumerate(state["explored"]) if mark == "0"]
        assert hidden and all(init["map"]["terrain"][i] == sea and init["map"]["flags"][i] == 0
                              for i in hidden)
        assert state["units"] and all(u[2] == 1 and len(u) == 12 for u in state["units"])

        settlers = next(u for u in state["units"] if u[1] == "settlers")
        socket.send_json({"cmd": "unit", "id": settlers[0]})
        detail = socket.receive_json()
        assert detail["type"] == "unit" and detail["unit"]["moves_left"] > 0
        assert "found_city" in {o["id"] for o in detail["unit"]["orders"]}

        update = order(socket, action="found_city", unit=settlers[0])
        assert update["type"] == "update" and update["ok"] and update["unit_detail"] is None
        city = update["state"]["cities"][0]
        assert city["owner"] == 1 and city["idle"] and city["capital"]
        assert city["trade"] >= 0 and city["unhappy"] == 0 and not city["growth_disorder"]
        # What the cities panel shows of it.
        assert city["item"] is None and city["food"] == 0 and city["food_box"] > 0
        assert city["max_size"] == 10 and city["units_away"] == 0 and city["trade_routes"] == 0
        assert city["specialists"] == {"entertainer": 0, "taxman": 0, "scientist": 0}
        assert city["pollution_risk"] == 0 and city["building_upkeep"] >= 0
        assert city["tax"] + city["luxury"] + city["science"] == city["trade"]
        assert update["events"] and update["events"][0]["type"] == "city_founded"

        update = order(socket, action="production", city=city["id"], kind="unit", id="militia")
        assert update["ok"] and update["city_detail"]["manage"]["current"] == ["unit", "militia"]
        assert not update["state"]["cities"][0]["idle"]
        assert update["state"]["cities"][0]["item"] == ["unit", "militia"]
        refused = order(socket, action="production", city=city["id"], kind="unit", id="battleship")
        assert not refused["ok"] and refused["reason"]
        assert not order(socket, action="teleport")["ok"]
        assert not order(socket, action="move", unit="1", x=0, y=0)["ok"]

        # The observer's controls do nothing while a person plays; its view is the person's.
        socket.send_json({"cmd": "step"})
        assert socket.receive_json()["type"] == "status"
        socket.send_json({"cmd": "pov", "player": 2})
        assert socket.receive_json()["state"]["pov"] == 1

        socket.send_json({"cmd": "end_turn"})
        message = socket.receive_json()
        assert message["type"] == "turn" and message["state"]["turn"] == 1
        assert list(message["history"]["players"]) == ["1"]
        assert message["state"]["cities"][0]["shields"] > 0

        # A second request to end the turn that is already over (another window) changes nothing.
        socket.send_json({"cmd": "end_turn", "turn": 0})
        socket.send_json({"cmd": "pov", "player": 1})
        assert socket.receive_json()["state"]["turn"] == 1
        socket.send_json({"cmd": "end_turn", "turn": 1})
        assert receive(socket, "turn")["state"]["turn"] == 2


def test_the_steps_of_an_order(client):
    with client.websocket_connect("/ws") as socket:
        init = start_playing(socket)
        unit = next(u for u in init["state"]["units"] if u[1] == "settlers")
        around = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
        for dx, dy in around:
            update = order(socket, action="move", unit=unit[0], x=unit[3] + dx, y=unit[4] + dy)
            if update["ok"]:
                break
        assert update["ok"] and update["outcome"] == "moved"
        there = [unit[3] + dx, unit[4] + dy]
        (step,) = update["steps"]
        assert (step["unit"], step["owner"], step["outcome"]) == (unit[0], 1, "moved")
        assert (step["from"], step["to"]) == ([unit[3], unit[4]], there)
        assert [tile[:2] for tile in step["tiles"]] == [[unit[3], unit[4]], there]
        assert unit[0] in [row[0] for row in step["tiles"][1][2]]

        # A refused order, or one that moves nothing, tells of no step.
        assert order(socket, action="move", unit=unit[0], x=unit[3], y=unit[4])["steps"] == []
        socket.send_json({"cmd": "end_turn"})
        assert isinstance(receive(socket, "turn")["steps"], list)


def test_a_person_only_hears_what_it_may_know(client):
    with client.websocket_connect("/ws") as socket:
        init = start_playing(socket)
        width = init["map"]["width"]
        settlers = next(u for u in init["state"]["units"] if u[1] == "settlers")
        city = order(socket, action="found_city", unit=settlers[0])["state"]["cities"][0]
        order(socket, action="production", city=city["id"], kind="unit", id="militia")
        exploring = set()

        for _ in range(40):
            socket.send_json({"cmd": "end_turn"})
            message = receive(socket, "turn")
            # Every militia the city delivers is sent exploring by itself.
            for unit in message["state"]["units"]:
                if unit[2] == 1 and unit[1] == "militia" and unit[0] not in exploring:
                    exploring.add(unit[0])
                    socket.send_json({"cmd": "automate", "unit": unit[0], "mode": "explore"})
                    assert receive(socket, "update")["ok"]
            state = message["state"]
            explored = state["explored"]
            for unit in state["units"]:
                assert unit[2] == 1 or explored[unit[4] * width + unit[3]] == "2"
            for other in state["cities"]:
                assert other["owner"] == 1 or other["foreign"]
            for index, _, _ in message["tile_changes"]:
                assert explored[index] != "0"
            for event in message["events"]:
                mine = event.get("player") == 1 or event.get("other") == 1
                assert mine or event["type"] in WORLD_NEWS or "x" in event, event
            for player in state["players"]:
                if player["id"] != 1:
                    assert player["gold"] is None and player["researching"] is None
                    assert player["met"] or not player["alive"] or player["nation"] == "Unknown"
        assert state["turn"] == 40 and exploring
        assert sum(mark != "0" for mark in explored) > 80, "the explorers uncovered the land"


def test_play_save_and_load(client):
    # The saves the tests before left being written would tell their list in the middle.
    client.portal.call(client.app.state.session.flush)
    with client.websocket_connect("/ws") as socket:
        init = start_playing(socket, name="rome")
        settlers = next(u for u in init["state"]["units"] if u[1] == "settlers")
        order(socket, action="found_city", unit=settlers[0])
        for _ in range(5):
            socket.send_json({"cmd": "end_turn"})
            message = socket.receive_json()
        # Turn 5: the game was saved by itself, under its name, in the middle of the person's turn.
        assert message["state"]["turn"] == 5
        saves = socket.receive_json()
        assert saves["saves"][0] == "rome" and saves["save_name"] == "rome"
        cities = message["state"]["cities"]

        socket.send_json({"cmd": "new_game", "name": "game", "seed": 10, "players": 3})
        observed = socket.receive_json()
        assert observed["state"]["play"] is None and observed["state"]["pov"] is None

        socket.send_json({"cmd": "load", "name": "rome"})
        loaded = socket.receive_json()
        assert loaded["type"] == "init" and loaded["state"]["turn"] == 5
        assert loaded["state"]["play"] == {"human": 1, "active": True}
        assert loaded["state"]["cities"] == cities
        assert socket.receive_json()["ok"] is True
        socket.send_json({"cmd": "end_turn"})
        assert socket.receive_json()["state"]["turn"] == 6

        # Once named, the game saves itself under that name; the save it replaces is kept.
        socket.send_json({"cmd": "save", "name": "mine"})
        assert socket.receive_json()["ok"] is True
        assert socket.receive_json()["save_name"] == "mine"
        for _ in range(4):
            socket.send_json({"cmd": "end_turn"})
            message = socket.receive_json()
        assert message["state"]["turn"] == 10
        saves = socket.receive_json()
        assert saves["save_name"] == "mine" and saves["saves"][:2] == ["mine", "mine-3880BC"]


def test_a_destroyed_person_becomes_an_observer(client):
    with client.websocket_connect("/ws") as socket:
        init = start_playing(socket)
        units = init["state"]["units"]
        for unit in units[:-1]:
            assert order(socket, action="disband", unit=unit[0])["type"] == "update"
        socket.send_json({"cmd": "action", "action": "disband", "unit": units[-1][0]})
        over = socket.receive_json()
        assert over["type"] == "init" and over["state"]["play"] == {"human": 1, "active": False}
        assert over["state"]["pov"] is None and not over["state"]["players"][1]["alive"]
        assert over["state"]["players"][2]["gold"] is not None, "nothing is hidden any more"
        socket.send_json({"cmd": "step"})
        assert socket.receive_json()["type"] == "turn"


def test_map_units_include_home_city_without_revealing_enemy_support(rules):
    game = make_game(rules)
    capital = add_city(game, 1, 5, 5)
    enemy_city = add_city(game, 2, 10, 5)
    supported = game.add_unit("militia", 1, 5, 5, home_city=capital.id)
    independent = game.add_unit("settlers", 1, 6, 5)
    enemy = game.add_unit("legion", 2, 5, 6, home_city=enemy_city.id)
    game.players[1].visible[game.tile_of(enemy).index] = True

    observed = {u[0]: u for u in serialize.state_payload(game)["units"]}
    assert observed[supported.id][8] == capital.id
    assert observed[independent.id][8] is None
    assert observed[enemy.id][8] == enemy_city.id

    played = serialize.state_payload(game, pov=1, controller=HumanController())
    units = {u[0]: u for u in played["units"]}
    assert units[supported.id][8:] == [capital.id, supported.moves_left, "", 0]
    assert units[independent.id][8] is None
    assert units[enemy.id][8] is None


def test_city_sheet_tells_where_things_go(rules):
    """What the city sheet shows beyond the totals: who eats, what the units cost, where
    the pollution comes from, and which city supports the units standing in it."""
    game = make_game(rules)
    player = game.players[1]
    player.government = "monarchy"                   # every supported unit costs a shield
    player.techs.update({"industrialization", "automobile"})
    capital = add_city(game, 1, 5, 5, size=8)
    other = add_city(game, 1, 10, 5)
    capital.buildings.update({"colossus", "temple", "palace", "granary"})
    militia = game.add_unit("militia", 1, 5, 5, home_city=capital.id)
    settlers = game.add_unit("settlers", 1, 6, 5, home_city=capital.id)
    guest = game.add_unit("legion", 1, 5, 5, home_city=other.id)
    away = game.add_unit("legion", 1, 10, 5, home_city=capital.id)

    detail = serialize.city_detail(game, capital)
    stats = detail["stats"]
    # Buildings come in the order the production list offers them, wonders last.
    assert detail["buildings"] == ["palace", "granary", "temple", "colossus"]
    assert detail["upkeeps"]["temple"] == 1 and detail["upkeeps"]["palace"] == 0
    assert detail["item"] is None
    assert stats["food_settlers"] == game.government(player).settlers_food == 2
    assert stats["food_eaten"] == 8 * rules.game.city.food_per_citizen + 2
    assert detail["support"] == {"units": 3, "free": 0, "shields": 3, "food": 2, "unhappy": 0}
    assert detail["unit_costs"] == {militia.id: [1, 0, 0], settlers.id: [1, 2, 0], away.id: [1, 0, 0]}
    assert detail["homes"] == {militia.id: capital.name, guest.id: other.name}
    # The Settlers stand in the open: only the units in a city have a place to tell.
    assert detail["places"] == {militia.id: capital.name, away.id: other.name}

    # Pollution: the industry and the citizens, less what the land tolerates.
    sources = detail["pollution"]
    assert sources["citizens"] == 8 * 2 // 4 and sources["tolerance"] == 20
    assert sources["industry"] == stats["shields"]
    assert stats["pollution"] == max(0, sources["industry"] + 4 - 20)
    assert sources["risk"] == pollution.pollution_risk(game, player, stats["pollution"])
    roll = rules.game.pollution.roll - player.tech_count * rules.game.pollution.roll_per_tech
    assert pollution.pollution_risk(game, player, 0) == 0
    assert pollution.pollution_risk(game, player, 18) == round(100 * 36 / roll)
    assert pollution.pollution_risk(game, player, 1000) == 100

    # Under despotism the city keeps as many units as it has citizens for free.
    player.government = "despotism"
    assert serialize.city_detail(game, capital)["support"] == {
        "units": 3, "free": 3, "shields": 0, "food": 1, "unhappy": 0}


def test_city_sheet_tells_what_each_unit_costs(rules):
    """Each supported unit with what it costs its city: the units the government keeps for
    free are the first ones, and military units away make the citizens unhappy."""
    game = make_game(rules)
    player = game.players[1]
    player.government = "despotism"
    city = add_city(game, 1, 5, 5, size=2)
    add_city(game, 1, 10, 5)
    militia = game.add_unit("militia", 1, 5, 5, home_city=city.id)
    settlers = game.add_unit("settlers", 1, 6, 5, home_city=city.id)
    legion = game.add_unit("legion", 1, 10, 5, home_city=city.id)
    diplomat = game.add_unit("diplomat", 1, 7, 5, home_city=city.id)

    # Despotism keeps two units for free (the size of the city): the Militia and the Settlers,
    # which still eat. The Diplomat needs no support at all.
    detail = serialize.city_detail(game, city)
    assert detail["unit_costs"] == {militia.id: [0, 0, 0], settlers.id: [0, 1, 0],
                                    legion.id: [1, 0, 0], diplomat.id: [0, 0, 0]}
    assert detail["support"] == {"units": 3, "free": 2, "shields": 1, "food": 1, "unhappy": 0}
    assert detail["stats"]["unhappy"] == 0

    # Democracy keeps none for free, and the Legion, away in another city, makes two citizens
    # unhappy; the Militia at home and the units without attack make none.
    player.government = "democracy"
    detail = serialize.city_detail(game, city)
    assert detail["unit_costs"] == {militia.id: [1, 0, 0], settlers.id: [1, 2, 0],
                                    legion.id: [1, 0, 2], diplomat.id: [0, 0, 0]}
    assert detail["support"] == {"units": 3, "free": 0, "shields": 3, "food": 2, "unhappy": 2}
    assert detail["stats"]["unhappy"] == 2

    # Women's Suffrage: one unhappy citizen less for each.
    city.buildings.add("womens_suffrage")
    game.wonders["womens_suffrage"] = city.id
    detail = serialize.city_detail(game, city)
    assert detail["unit_costs"][legion.id] == [1, 0, 1]
    assert detail["support"]["unhappy"] == 1 and detail["stats"]["unhappy"] == 1


def test_spaceship_payload(rules):
    game = make_game(rules, civ_ids=("romans", "greeks", "russians"))
    add_city(game, 1, 2, 2)
    athens = add_city(game, 2, 10, 5, size=8)
    add_city(game, 3, 6, 9)
    game.relation(1, 3).state = NO_CONTACT
    for player in game.players[1:]:
        player.techs.update({"space_flight", "plastics", "robotics"})
    game.wonders["apollo_program"] = athens.id
    game.year, game.turn = 1990, 540
    greeks, russians = game.players[2], game.players[3]
    greeks.spaceship.parts = {"structural": 4, "component": 2, "module": 2}
    russians.spaceship.parts = {"structural": 4, "component": 2, "module": 3}
    athens.production = Item("building", "ss_module")
    athens.shields = 300
    spaceship.launch(game, russians)

    observer = serialize.state_payload(game)
    assert observer["space"] == {"earliest_landing": 546, "earliest_landing_year": 1996}
    ship = observer["players"][2]["spaceship"]
    assert ship["parts"] == greeks.spaceship.parts and ship["flight_years"] == 15
    assert [(row["part"], row["city"], row["cost"]) for row in ship["making"]] == [
        ("module", athens.name, rules.buildings["ss_module"].cost)]
    turns = ship["making"][0]["turns"]
    assert ship["projection"]["launch_turn"] == 540 + turns
    flying = observer["players"][3]["spaceship"]
    assert flying["launched_year"] == 1990 and flying["arrival_year"] == 2005
    assert flying["projection"] is None

    # The Romans, played by a person: they know the parts of the Greeks they have met, not
    # what their cities make; of the Russians, never met, only the launch the world heard of.
    played = serialize.state_payload(game, pov=1, controller=HumanController())
    ship = played["players"][2]["spaceship"]
    assert ship["parts"] == greeks.spaceship.parts and ship["making"] == []
    assert ship["projection"] is None                    # a module missing, its making unknown
    flying = played["players"][3]["spaceship"]
    assert flying["parts"] == {} and flying["arrival_year"] == 2005
    assert flying["flight_years"] == 15


def test_wonders_payload(rules):
    game = make_game(rules)
    rome = add_city(game, 1, 5, 5)
    athens = add_city(game, 2, 10, 5)
    game.wonders.update({"colossus": rome.id, "pyramids": athens.id, "oracle": None})
    game.wonder_origins["colossus"] = (-1500, 2, "Athens")   # built by the Greeks, taken since
    game.wonder_origins["oracle"] = (-900, 1, "Antium")      # lost with its city
    game.players[2].techs.add("communism")                   # the Pyramids work no more
    rows = {row["id"]: row for row in serialize.wonders_payload(game)}
    assert list(rows) == [wonder.id for wonder in rules.wonders]
    assert rows["colossus"] == {"id": "colossus", "built": True, "obsolete": False,
                                "year": -1500, "builder": 2, "lost": False, "city": rome.name,
                                "city_id": rome.id, "owner": 1, "x": 5, "y": 5}
    assert rows["pyramids"]["obsolete"] and rows["pyramids"]["year"] is None
    assert rows["oracle"] == {"id": "oracle", "built": True, "obsolete": False, "year": -900,
                              "builder": 1, "lost": True, "city": "Antium"}
    assert rows["great_wall"] == {"id": "great_wall", "built": False, "obsolete": False}
    assert serialize.state_payload(game)["wonders"] == list(rows.values())


def test_a_save_keeps_the_one_it_replaces(rules, tmp_path):
    session = Session({rules.ruleset.id: rules}, saves_dir=tmp_path)
    game = session.game

    def save_in(year: int) -> set[str]:
        game.turn, game.year = game.turn + 1, year
        session.save("french")
        return {path.stem for path in tmp_path.glob("*.json")}

    (tmp_path / "french-2.json").write_text("{}")          # a save of its own, not a backup
    assert save_in(1915) == {"french", "french-2"}
    assert save_in(1925) == {"french", "french-1915", "french-2"}
    assert save_in(1935) == {"french", "french-1925", "french-2"}
    assert persistence.save_header(tmp_path / "french-1925.json")["year"] == 1925
    assert persistence.save_header(tmp_path / "french.json")["year"] == 1935

    session.save("french")                                 # the same turn again
    assert {path.stem for path in tmp_path.glob("*.json")} == {"french", "french-1925", "french-2"}
    assert not list(tmp_path.glob("*.tmp"))

    # A backup, once loaded, saves itself under the name of its game.
    session.load("french-1925")
    assert session.game.year == 1925 and session.save_name == "french"
    assert base_name("french-2", 1925) == "french-2"
    assert year_tag(-3000) == "3000BC" and base_name("rome-3000BC", -3000) == "rome"
    assert base_name("3000BC", -3000) == "3000BC"


def test_the_server_can_start_on_the_save_written_last(rules, tmp_path):
    session = Session({rules.ruleset.id: rules}, saves_dir=tmp_path)
    assert session.resume() is None                        # nothing saved yet
    session.game.turn = 12
    session.save("rome")
    session.game.turn = 30
    session.save("athens")
    (tmp_path / "broken.json").write_text("{}")            # not a game: passed over
    for age, name in enumerate(("broken", "athens", "rome")):
        os.utime(tmp_path / f"{name}.json", (1e9 - 60 * age,) * 2)

    with TestClient(create_app(saves_dir=tmp_path, resume=True)) as test_client:
        with test_client.websocket_connect("/ws") as socket:
            init = socket.receive_json()
    assert init["state"]["turn"] == 30 and init["save_name"] == "athens"

    with TestClient(create_app(saves_dir=tmp_path)) as test_client:
        with test_client.websocket_connect("/ws") as socket:
            init = socket.receive_json()
    assert init["state"]["turn"] == 0 and init["save_name"] is None


def test_wonder_origins_are_saved(rules, tmp_path):
    session = Session({rules.ruleset.id: rules}, saves_dir=tmp_path)
    game = session.game
    land = next(tile for tile in game.map.tiles if game.terrain(tile).is_land)
    city = add_city(game, 1, land.x, land.y)
    game.wonders["colossus"] = city.id
    game.wonder_origins["colossus"] = (-1500, city.owner, city.name)
    game.wonders["oracle"] = None
    session.save("new")
    session.load("new")
    assert session.game.wonder_origins == {"colossus": (-1500, city.owner, city.name)}
    assert session.game.wonders["oracle"] is None

    # An older save kept no origins: the chronicle tells of the wonders it still holds.
    data = json.loads((tmp_path / "new.json").read_text())
    del data["wonder_origins"]
    data["extra"]["log"] = [
        {"type": "wonder", "turn": 9, "year": -3000, "player": city.owner, "wonder": "colossus",
         "city": city.id + 1000},                          # a city destroyed since
        {"type": "wonder", "turn": 30, "year": -1200, "player": city.owner, "wonder": "colossus",
         "city": city.id}]
    (tmp_path / "old.json").write_text(json.dumps(data))
    session.load("old")
    assert session.game.wonder_origins == {"colossus": (-1200, city.owner, city.name)}


def test_each_game_has_its_rules(rulesets, tmp_path):
    session = Session(rulesets, saves_dir=tmp_path)
    assert session.rules is rulesets["civ1"]
    init = session.init_message(None)
    assert init["rules"]["ruleset"]["id"] == "civ1"
    assert [entry["id"] for entry in init["rulesets"]] == list(rulesets)

    # The rules are chosen with the new game, and recorded in its saves.
    asyncio.run(session._new_game(None, {"cmd": "new_game", "name": "game", "seed": 7, "ruleset": "golden_ages"}))
    assert session.rules is rulesets["golden_ages"] and session.game.seed == 7
    session.save("other")
    assert json.loads((tmp_path / "other.json").read_text())["ruleset"] == "golden_ages"
    session.new_game(8, ruleset="civ1")
    session.load("other")
    assert session.rules is rulesets["golden_ages"] and session.game.seed == 7
    session.new_game(9)                                # no choice: the rules of the last game
    assert session.rules is rulesets["golden_ages"]

    # Saves made before the choice existed are games of Civilization I.
    data = json.loads((tmp_path / "other.json").read_text())
    del data["ruleset"]
    (tmp_path / "old.json").write_text(json.dumps(data))
    session.load("old")
    assert session.rules is rulesets["civ1"]
    data["ruleset"] = "lost_rules"
    (tmp_path / "lost.json").write_text(json.dumps(data))
    with pytest.raises(persistence.SaveError, match="lost_rules"):
        session.load("lost")


# ── The replay ────────────────────────────────────────────────────────────────

def cities_in(replay: dict, turn: int) -> dict[int, dict]:
    """The cities as the replay draws them when `turn` begins."""
    cities: dict[int, dict] = {}
    for change in replay["cities"]:
        kind, when, city_id = change[:3]
        if when > turn:
            break
        if kind == "found":
            cities[city_id] = dict(zip(("owner", "x", "y", "name", "size"), change[3:]))
        elif kind == "owner":
            cities[city_id]["owner"] = change[3]
        elif kind == "size":
            cities[city_id]["size"] = change[3]
        else:
            del cities[city_id]
    return cities


def test_the_replay_notes_what_changes_in_the_cities(rules):
    game = make_game(rules)
    replay = Replay()
    rome = add_city(game, 1, 2, 2)
    replay.note_cities(game)
    game.turn = 1
    athens = add_city(game, 2, 8, 6, size=3)
    rome.size = 2
    replay.note_cities(game)
    game.turn = 2
    rome.owner = 2
    del game.cities[athens.id]
    replay.note_cities(game)
    game.turn = 3
    replay.note_cities(game)                               # nothing changed
    assert replay.cities == [
        ["found", 0, rome.id, 1, 2, 2, rome.name, 1],
        ["size", 1, rome.id, 2],
        ["found", 1, athens.id, 2, 8, 6, athens.name, 3],
        ["owner", 2, rome.id, 2],
        ["gone", 2, athens.id]]

    # Battles and great events are kept, the routine of the cities is not.
    replay.note_events([
        {"type": "combat", "turn": 3, "year": -3940, "text": "Roman Legion attacks...",
         "player": 1, "other": 2, "x": 4, "y": 5, "attacker": "legion", "defender": "phalanx",
         "attacker_won": True, "attack": 4, "defense": 2, "winner": 1, "loser": 2},
        {"type": "building", "turn": 3, "year": -3940, "text": "Rome builds Barracks.",
         "player": 2, "x": 2, "y": 2},
        {"type": "wonder", "turn": 3, "year": -3940, "text": "Rome (Greek) completes Colossus.",
         "player": 2, "x": 2, "y": 2, "wonder": "colossus", "city": rome.id}])
    assert replay.battles == [[3, 4, 5, 1, 2]]
    assert replay.events == [{"type": "wonder", "turn": 3, "year": -3940, "player": 2, "x": 2,
                              "y": 2, "text": "Rome (Greek) completes Colossus."}]

    # Taken back from a save, it goes on where it stopped.
    again = Replay.restore(json.loads(json.dumps(replay.payload())), game, [])
    assert again.payload() == replay.payload()
    game.turn = 4
    rome.size = 5
    again.note_cities(game)
    assert again.cities[-1] == ["size", 4, rome.id, 5] and len(again.cities) == 6


def test_the_replay_of_an_observed_game(client):
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        socket.send_json({"cmd": "new_game", "name": "game", "seed": 11, "players": 3})
        socket.receive_json()
        for _ in range(25):
            socket.send_json({"cmd": "step"})
            message = receive(socket, "turn")
        state = message["state"]
        socket.send_json({"cmd": "replay"})
        replay = receive(socket, "replay")
    assert replay["since"] == 0 and replay["cities"][0][:2] == ["found", 1]
    assert cities_in(replay, state["turn"]) == {
        c["id"]: {"owner": c["owner"], "x": c["x"], "y": c["y"], "name": c["name"], "size": c["size"]}
        for c in state["cities"]}
    turns = [change[1] for change in replay["cities"]]
    assert turns == sorted(turns)


def test_no_replay_while_a_person_plays(client):
    with client.websocket_connect("/ws") as socket:
        start_playing(socket)
        socket.send_json({"cmd": "replay"})
        assert receive(socket, "notice") == {
            "type": "notice", "text": "The replay opens once the game is over.", "ok": False}


def test_a_person_can_end_the_game_and_see_everything(client):
    with client.websocket_connect("/ws") as socket:
        init = start_playing(socket)
        explored = init["state"]["explored"]
        assert "0" in explored and init["state"]["players"][2]["gold"] is None
        socket.send_json({"cmd": "end_turn"})
        receive(socket, "turn")
        socket.send_json({"cmd": "retire"})
        over = receive(socket, "init")
        state = over["state"]
        assert state["finished"] and state["victory"] == "retired" and state["winner"] is None
        assert state["play"] == {"human": 1, "active": False} and state["pov"] is None
        assert state["players"][2]["gold"] is not None and state["players"][2]["nation"] != "Unknown"
        assert over["log"][-1]["type"] == "game_over" and over["log"][-1]["player"] == 1
        # The whole map, and the replay of the game.
        sea = {i for i, t in enumerate(over["rules"]["terrains"]) if not t["land"]}
        assert any(t not in sea for i, t in enumerate(over["map"]["terrain"]) if explored[i] == "0")
        socket.send_json({"cmd": "replay"})
        assert receive(socket, "replay")["since"] == 0
        # Once over, the game stays over: no second end, no more turns.
        socket.send_json({"cmd": "retire"})
        socket.send_json({"cmd": "end_turn"})
        socket.send_json({"cmd": "step"})
        assert socket.receive_json()["type"] == "status"


def test_the_replay_is_saved_with_the_game(rules, tmp_path):
    session = Session({rules.ruleset.id: rules}, saves_dir=tmp_path)
    session.new_game(7, players=3)
    for _ in range(12):
        asyncio.run(session.step())
    noted = session.replay.payload()
    assert noted["cities"] and noted["events"]
    session.save("replayed")
    session.load("replayed")
    assert session.replay.payload() == noted
    asyncio.run(session.step())
    founded = [change[2] for change in session.replay.cities if change[0] == "found"]
    assert len(founded) == len(set(founded)), "a city goes on being followed, not founded again"

    # A game saved before replays were noted: its cities as they are now, from the turn
    # each was founded, and the great events its chronicle still holds.
    data = json.loads((tmp_path / "replayed.json").read_text())
    del data["extra"]["replay"]
    (tmp_path / "older.json").write_text(json.dumps(data))
    session.load("older")
    game = session.game
    replay = session.replay.payload()
    assert replay["since"] == game.turn == 12
    assert cities_in(replay, game.turn) == {
        c.id: {"owner": c.owner, "x": c.x, "y": c.y, "name": c.name, "size": c.size}
        for c in game.cities.values()}
    told = [e["text"] for e in data["extra"]["log"] if e["type"] in HEADLINES]
    assert told and [e["text"] for e in replay["events"]] == told


def test_destroyed_civilizations_are_named_even_unmet(rules):
    game = make_game(rules, civ_ids=("romans", "greeks", "russians"))
    game.relation(1, 2).state = NO_CONTACT
    game.relation(1, 3).state = NO_CONTACT
    game.players[3].alive = False
    greeks, russians = (serialize.public_player_payload(game, game.players[i], game.players[1])
                        for i in (2, 3))
    assert not greeks["met"] and greeks["nation"] == "Unknown"
    assert not russians["met"] and russians["nation"] == game.players[3].civ.nation
    assert russians["government"] is None
