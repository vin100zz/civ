"""The web layer: static pages, rules, and the observer's WebSocket."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.api.app import create_app


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
    assert {"id", "name", "color"} <= set(rules["civs"][0])
    assert rules["defaults"]["map"] == {"shape": "continents", "relief": 1, "climate": 1}
    assert {"continents", "small_islands", "pangaea"} <= {s["id"] for s in rules["map_shapes"]}


def test_observer_session(client):
    with client.websocket_connect("/ws") as socket:
        init = socket.receive_json()
        assert init["type"] == "init"
        tiles = init["map"]["width"] * init["map"]["height"]
        assert len(init["map"]["terrain"]) == tiles == len(init["map"]["flags"])
        assert init["state"]["turn"] == 0 and init["state"]["pov"] is None

        socket.send_json({"cmd": "new_game", "seed": 42, "players": 4})
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
        socket.send_json({"cmd": "new_game", "seed": 9, "players": 3})
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
        assert socket.receive_json() == {"type": "saves", "saves": ["my-game"]}

        socket.send_json({"cmd": "new_game", "seed": 10, "players": 3})
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


def test_new_game_with_a_chosen_map(client):
    def land_masses(init):
        return len({c for c in init["map"]["continent"] if c > 0})

    with client.websocket_connect("/ws") as socket:
        socket.receive_json()
        socket.send_json({"cmd": "new_game", "seed": 5, "players": 3})
        default = socket.receive_json()
        socket.send_json({"cmd": "new_game", "seed": 5, "players": 3,
                          "map": {"shape": "small_islands", "relief": 2, "climate": 0}})
        islands = socket.receive_json()
        assert islands["state"]["seed"] == 5
        assert islands["map"]["terrain"] != default["map"]["terrain"]
        # Invalid choices fall back on the defaults of the rules.
        socket.send_json({"cmd": "new_game", "seed": 5, "players": 3,
                          "map": {"shape": ["atlantis"], "relief": 9, "climate": 1.0}})
        assert socket.receive_json()["map"]["terrain"] == default["map"]["terrain"]


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
    socket.send_json({"cmd": "new_game", "seed": 42, "players": 4, "mode": "play",
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
        assert state["units"] and all(u[2] == 1 and len(u) == 10 for u in state["units"])

        settlers = next(u for u in state["units"] if u[1] == "settlers")
        socket.send_json({"cmd": "unit", "id": settlers[0]})
        detail = socket.receive_json()
        assert detail["type"] == "unit" and detail["unit"]["moves_left"] > 0
        assert "found_city" in {o["id"] for o in detail["unit"]["orders"]}

        update = order(socket, action="found_city", unit=settlers[0])
        assert update["type"] == "update" and update["ok"] and update["unit_detail"] is None
        city = update["state"]["cities"][0]
        assert city["owner"] == 1 and city["idle"] and city["capital"]
        assert update["events"] and update["events"][0]["type"] == "city_founded"

        update = order(socket, action="production", city=city["id"], kind="unit", id="militia")
        assert update["ok"] and update["city_detail"]["manage"]["current"] == ["unit", "militia"]
        assert not update["state"]["cities"][0]["idle"]
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
                    assert player["met"] or player["nation"] == "Unknown"
        assert state["turn"] == 40 and exploring
        assert sum(mark != "0" for mark in explored) > 80, "the explorers uncovered the land"


def test_play_save_and_load(client):
    with client.websocket_connect("/ws") as socket:
        init = start_playing(socket)
        settlers = next(u for u in init["state"]["units"] if u[1] == "settlers")
        order(socket, action="found_city", unit=settlers[0])
        for _ in range(5):
            socket.send_json({"cmd": "end_turn"})
            message = socket.receive_json()
        # Turn 5: the game was saved by itself, in the middle of the person's turn.
        assert message["state"]["turn"] == 5
        assert "autosave" in socket.receive_json()["saves"]
        cities = message["state"]["cities"]

        socket.send_json({"cmd": "new_game", "seed": 10, "players": 3})
        observed = socket.receive_json()
        assert observed["state"]["play"] is None and observed["state"]["pov"] is None

        socket.send_json({"cmd": "load", "name": "autosave"})
        loaded = socket.receive_json()
        assert loaded["type"] == "init" and loaded["state"]["turn"] == 5
        assert loaded["state"]["play"] == {"human": 1, "active": True}
        assert loaded["state"]["cities"] == cities
        assert socket.receive_json()["ok"] is True
        socket.send_json({"cmd": "end_turn"})
        assert socket.receive_json()["state"]["turn"] == 6


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
