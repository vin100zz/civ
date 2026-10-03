"""The running game and its observers.

One game at a time. The session plays turns (in a worker thread, so the web server stays
responsive) and pushes the new state to every connected browser. It also saves the game to
the `saves` folder and loads it back.
"""
from __future__ import annotations

import asyncio
import dataclasses
import random
import re
from collections import deque
from pathlib import Path
from typing import Any, Optional

from fastapi import WebSocket

from ..engine import persistence
from ..engine.model.game import Game
from ..engine.rules.loader import PROJECT_ROOT
from ..engine.rules.schema import MapSettings, Rules
from ..engine.systems import turn
from ..sim.runner import create_game, restore_game
from . import serialize

MAX_LOG = 600
HISTORY_FIELDS = ("cities", "population", "techs", "score", "gold", "units")
DEFAULT_SAVES_DIR = PROJECT_ROOT / "saves"
SAVE_NAME = re.compile(r"[A-Za-z0-9_-]{1,40}")


class Session:
    def __init__(self, rules: Rules, saves_dir: Optional[Path] = None) -> None:
        self.rules = rules
        self.saves_dir = Path(saves_dir) if saves_dir else DEFAULT_SAVES_DIR
        self.game: Optional[Game] = None
        self.playing = False
        self.delay = 0.4                       # seconds between two turns while playing
        self.clients: dict[WebSocket, Optional[int]] = {}    # socket -> point of view
        self.history: list[dict] = []
        self.log: deque[dict] = deque(maxlen=MAX_LOG)
        self._busy = asyncio.Lock()
        self.new_game(random.randrange(1, 100000))

    # ── Game control ──────────────────────────────────────────────────────────

    def new_game(self, seed: int, players: Optional[int] = None,
                 map_settings: Optional[MapSettings] = None) -> None:
        self.playing = False
        self.game = create_game(self.rules, seed, player_count=players,
                                map_settings=map_settings)
        self.game.changed_tiles.clear()
        self.history = [self._history_row()]
        self.log.clear()
        for client in self.clients:
            self.clients[client] = None

    def _map_settings(self, choices: Any) -> MapSettings:
        """The map settings of the rules, with the valid choices of the observer."""
        settings = self.rules.game.map
        if not isinstance(choices, dict):
            return settings
        changes: dict[str, Any] = {}
        shape = choices.get("shape")
        if isinstance(shape, str) and shape in settings.shapes:
            changes["shape"] = shape
        for name in serialize.MAP_LEVELS:
            level = choices.get(name)
            if type(level) is int and 0 <= level <= 2:
                changes[name] = level
        return dataclasses.replace(settings, **changes)

    def _history_row(self) -> dict:
        game = self.game
        row: dict[str, Any] = {"turn": game.turn, "year": game.year, "players": {}}
        for player in game.players:
            if player.is_barbarian:
                continue
            cities = game.player_cities(player.id)
            row["players"][player.id] = [
                len(cities), sum(c.size for c in cities), player.tech_count, player.score,
                player.gold, len(game.player_units(player.id))]
        return row

    # ── Saved games ───────────────────────────────────────────────────────────

    def saved_games(self) -> list[str]:
        if not self.saves_dir.is_dir():
            return []
        files = sorted(self.saves_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        return [f.stem for f in files if SAVE_NAME.fullmatch(f.stem)]

    def save(self, name: str) -> None:
        """Writes the game, with the charts and the log of the observer."""
        persistence.save_game(self.game, self.saves_dir / f"{name}.json",
                              extra={"history": self.history, "log": list(self.log)})

    def load(self, name: str) -> None:
        data = persistence.read_save(self.saves_dir / f"{name}.json")
        game = restore_game(self.rules, data)
        self.playing = False
        self.game = game
        extra = data.get("extra", {})
        self.history = extra.get("history") or [self._history_row()]
        # JSON turned the player ids of the history rows into text.
        for row in self.history:
            row["players"] = {int(pid): values for pid, values in row["players"].items()}
        self.log.clear()
        self.log.extend(extra.get("log", []))
        for client in self.clients:
            self.clients[client] = None

    def _play_one_turn(self) -> None:
        self.game.events.clear()
        turn.play_turn(self.game)

    async def step(self) -> None:
        """Plays one turn and tells everybody."""
        async with self._busy:
            game = self.game
            if game is None or game.finished:
                self.playing = False
                return
            await asyncio.to_thread(self._play_one_turn)
            events = list(game.events)
            self.log.extend(events)
            row = self._history_row()
            self.history.append(row)
            changes = serialize.tile_changes(game)
            game.changed_tiles.clear()
            if game.finished:
                self.playing = False
            await self._broadcast(lambda pov: {
                "type": "turn", "state": serialize.state_payload(game, pov),
                "tile_changes": changes, "events": events, "history": row,
                "playing": self.playing})

    async def run(self) -> None:
        """Background loop: plays turns while the game is in "play" mode."""
        while True:
            if self.playing and self.game is not None and not self.game.finished:
                await self.step()
                await asyncio.sleep(self.delay)
            else:
                await asyncio.sleep(0.05)

    # ── Clients ───────────────────────────────────────────────────────────────

    def init_message(self, pov: Optional[int]) -> dict:
        game = self.game
        return {
            "type": "init",
            "rules": serialize.rules_payload(self.rules),
            "map": serialize.map_payload(game),
            "state": serialize.state_payload(game, pov),
            "history": self.history,
            "history_fields": HISTORY_FIELDS,
            "log": list(self.log),
            "playing": self.playing,
            "delay": self.delay,
            "saves": self.saved_games(),
        }

    async def _broadcast(self, build) -> None:
        cache: dict[Optional[int], dict] = {}
        for client, pov in list(self.clients.items()):
            if pov not in cache:
                cache[pov] = build(pov)
            await self._send(client, cache[pov])

    async def _send(self, client: WebSocket, message: dict) -> None:
        try:
            await client.send_json(message)
        except Exception:
            self.clients.pop(client, None)

    async def broadcast_init(self) -> None:
        await self._broadcast(self.init_message)

    async def _notice(self, client: WebSocket, text: str, ok: bool) -> None:
        await self._send(client, {"type": "notice", "text": text, "ok": ok})

    async def broadcast_status(self) -> None:
        await self._broadcast(lambda pov: {"type": "status", "playing": self.playing,
                                           "delay": self.delay})

    # ── Commands from the observer ────────────────────────────────────────────

    async def handle(self, client: WebSocket, message: dict) -> None:
        command = message.get("cmd")
        game = self.game
        if command == "new_game":
            seed = message.get("seed")
            if not isinstance(seed, int):
                seed = random.randrange(1, 100000)
            players = message.get("players")
            if not isinstance(players, int) or not 2 <= players <= len(self.rules.playable_civs):
                players = None
            map_settings = self._map_settings(message.get("map"))
            async with self._busy:
                self.new_game(seed, players, map_settings)
            await self.broadcast_init()
        elif command == "save":
            name = message.get("name")
            if not isinstance(name, str) or not SAVE_NAME.fullmatch(name):
                await self._notice(client, "Use letters, digits, - and _ for the name.", False)
                return
            async with self._busy:
                await asyncio.to_thread(self.save, name)
            await self._notice(client, f"Game saved as {name}.", True)
            await self._broadcast(lambda pov: {"type": "saves", "saves": self.saved_games()})
        elif command == "load":
            name = message.get("name")
            if not isinstance(name, str) or name not in self.saved_games():
                await self._notice(client, "No such saved game.", False)
                return
            try:
                async with self._busy:
                    await asyncio.to_thread(self.load, name)
            except persistence.SaveError as error:
                await self._notice(client, f"Cannot load {name}: {error}", False)
                return
            await self.broadcast_init()
            await self._notice(client, f"Game {name} loaded.", True)
        elif command == "play":
            self.playing = True
            await self.broadcast_status()
        elif command == "pause":
            self.playing = False
            await self.broadcast_status()
        elif command == "step":
            self.playing = False
            await self.step()
            await self.broadcast_status()
        elif command == "speed":
            delay = message.get("delay")
            if isinstance(delay, (int, float)):
                self.delay = max(0.0, min(5.0, float(delay)))
            await self.broadcast_status()
        elif command == "pov":
            pov = message.get("player")
            self.clients[client] = pov if isinstance(pov, int) and 0 <= pov < len(game.players) else None
            await self._send(client, {"type": "state",
                                      "state": serialize.state_payload(game, self.clients[client])})
        elif command == "city":
            city = game.cities.get(message.get("id"))
            if city is not None:
                controller = game.controllers.get(city.owner)
                decision = getattr(controller, "decisions", {}).get(city.id)
                await self._send(client, {"type": "city",
                                          "city": serialize.city_detail(game, city, decision)})
        elif command == "player":
            player_id = message.get("id")
            if isinstance(player_id, int) and 0 <= player_id < len(game.players):
                player = game.players[player_id]
                await self._send(client, {"type": "player", "player": serialize.player_detail(
                    game, player, game.controllers.get(player.id))})
