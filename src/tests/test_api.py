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
    assert client.get("/js/main.js").status_code == 200
    assert client.get("/resources/terrain/grassland.png").status_code == 200
    rules = client.get("/api/rules").json()
    assert len(rules["units"]) == 28 and len(rules["terrains"]) == 12
    assert {"id", "name", "color"} <= set(rules["civs"][0])


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
