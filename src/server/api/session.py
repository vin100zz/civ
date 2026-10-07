"""The running game and the browsers connected to it.

One game at a time, in one of two modes. Observed: the AI plays every civilization, the
session plays turns on demand or in a loop and each browser picks its point of view.
Played: a person leads one civilization; the session waits for its orders, applies them one
by one, and lets the AI play the others when the person ends its turn. Every browser then
sees the game through that person's eyes, and only what it is supposed to know. That
includes the steps the units take in its sight: its own, and those of the others while they
play, which the browser shows one after the other.

Turns are played in a worker thread, so the web server stays responsive. The session also
saves the game to the `saves` folder and loads it back.
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

from ..engine import actions, persistence
from ..engine.model.entities import Player, Unit
from ..engine.model.game import Game
from ..engine.model.worldmap import Tile
from ..engine.rules.loader import PROJECT_ROOT
from ..engine.rules.schema import MapSettings, Rules
from ..engine.systems import turn
from ..engine.view import PlayerView
from ..human import orders
from ..human.controller import BLOCKED, HumanController
from ..sim.runner import create_game, restore_game
from . import commands, serialize

MAX_LOG = 600
HISTORY_FIELDS = ("cities", "population", "techs", "score", "gold", "units")
DEFAULT_SAVES_DIR = PROJECT_ROOT / "saves"
SAVE_NAME = re.compile(r"[A-Za-z0-9_-]{1,40}")
AUTOSAVE = "autosave"
AUTOSAVE_EVERY = 5                             # turns between two automatic saves of a played game


class Session:
    def __init__(self, rules: Rules, saves_dir: Optional[Path] = None) -> None:
        self.rules = rules
        self.saves_dir = Path(saves_dir) if saves_dir else DEFAULT_SAVES_DIR
        self.game: Optional[Game] = None
        self.human: Optional[int] = None       # the player a person leads (or led), if any
        self.playing = False
        self.delay = 0.4                       # seconds between two turns while playing
        self.clients: dict[WebSocket, Optional[int]] = {}    # socket -> point of view
        self.history: list[dict] = []
        self.log: deque[dict] = deque(maxlen=MAX_LOG)           # everything that happened
        self.heard: deque[dict] = deque(maxlen=MAX_LOG)         # what the person heard of
        self._events_read = 0                  # events of game.events already in the logs
        self._known = bytearray()              # tiles the person's browser already holds
        self._steps: list[dict] = []           # steps the person saw since its last order
        self._busy = asyncio.Lock()
        self.new_game(random.randrange(1, 100000))

    # ── Who is at the table ───────────────────────────────────────────────────

    def in_play(self) -> bool:
        """True while a person gives the orders of a living civilization."""
        game = self.game
        return (self.human is not None and game is not None and not game.finished
                and game.players[self.human].alive)

    def _leader(self) -> Player:
        return self.game.players[self.human]

    def _controller(self) -> HumanController:
        return self.game.controllers[self.human]

    def _view(self) -> PlayerView:
        return PlayerView(self.game, self._leader())

    def _pov(self, client: WebSocket) -> Optional[int]:
        return self.human if self.in_play() else self.clients.get(client)

    def _state(self, pov: Optional[int]) -> dict:
        controller = self._controller() if self.in_play() else None
        state = serialize.state_payload(self.game, pov, controller)
        # The browser shows who "you" are, even once the game is over or lost.
        state["play"] = ({"human": self.human, "active": self.in_play()}
                         if self.human is not None else None)
        return state

    # ── Game control ──────────────────────────────────────────────────────────

    def new_game(self, seed: int, players: Optional[int] = None,
                 map_settings: Optional[MapSettings] = None,
                 civ: Optional[str] = None, level: Optional[str] = None) -> None:
        """Starts a game. With `civ`, a person leads that civilization at this `level`."""
        self.playing = False
        self.game = create_game(self.rules, seed, player_count=players,
                                map_settings=map_settings, human_civ=civ, level=level)
        self._reset(humans=[p.id for p in self.game.players if turn.is_interactive(self.game, p)])
        self.history = [self._history_row()]
        if self.in_play():
            self._advance()                    # up to the person's first turn
            self._read_events()

    def _reset(self, humans: list[int]) -> None:
        """A game has just been started or loaded: nobody has been told anything yet."""
        game = self.game
        self.human = humans[0] if humans and game.players[humans[0]].alive else None
        game.changed_tiles.clear()
        self.log.clear()
        self.heard.clear()
        self._events_read = len(game.events)
        self._known = bytearray(self._leader().explored) if self.human is not None else bytearray()
        game.watcher = self._watch if self.human is not None else None
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

    def _shown(self, row: dict) -> dict:
        """A history row as the browsers may see it: a person only follows its own figures."""
        if not self.in_play():
            return row
        return {**row, "players": {self.human: row["players"][self.human]}}

    # ── Saved games ───────────────────────────────────────────────────────────

    def saved_games(self) -> list[str]:
        if not self.saves_dir.is_dir():
            return []
        files = sorted(self.saves_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        return [f.stem for f in files if SAVE_NAME.fullmatch(f.stem)]

    def save(self, name: str) -> None:
        """Writes the game, with the charts and the logs."""
        persistence.save_game(self.game, self.saves_dir / f"{name}.json",
                              extra={"history": self.history, "log": list(self.log),
                                     "heard": list(self.heard)})

    def load(self, name: str) -> None:
        data = persistence.read_save(self.saves_dir / f"{name}.json")
        game = restore_game(self.rules, data)
        self.playing = False
        self.game = game
        self._reset(humans=data.get("humans", []))
        extra = data.get("extra", {})
        self.history = extra.get("history") or [self._history_row()]
        # JSON turned the player ids of the history rows into text.
        for row in self.history:
            row["players"] = {int(pid): values for pid, values in row["players"].items()}
        self.log.extend(extra.get("log", []))
        self.heard.extend(extra.get("heard", []))
        if self.in_play() and game.current_player != self.human:
            self._advance()                    # saved between two turns: on to the person's
            self._read_events()

    # ── Playing turns ─────────────────────────────────────────────────────────

    def _read_events(self) -> tuple[list[dict], list[dict]]:
        """The events not reported yet: all of them, and those the person hears of."""
        game = self.game
        fresh = game.events[self._events_read:]
        self._events_read = len(game.events)
        self.log.extend(fresh)
        if self.human is None:
            return fresh, fresh
        view = self._view()
        known = [event for event in fresh if view.knows_event(event)]
        self.heard.extend(known)
        return fresh, known

    def _watch(self, unit: Unit, origin: Tile, target: Tile, outcome: str) -> None:
        """A unit has just stepped (the engine tells): kept if the person saw it."""
        if not self.in_play():
            return
        step = serialize.step_payload(self.game, self._leader(), self._controller(),
                                      unit, origin, target, outcome)
        if step is not None:
            self._steps.append(step)

    def _tiles(self) -> list[list[int]]:
        """The tiles the browsers must redraw: those that changed and, for a person, those
        its civilization has just discovered (and only tiles it has explored)."""
        game = self.game
        changed = set(game.changed_tiles)
        game.changed_tiles.clear()
        if not self.in_play():
            return serialize.tile_rows(game, changed)
        explored = self._leader().explored
        fresh = {i for i in range(len(explored)) if explored[i] and not self._known[i]}
        self._known = bytearray(explored)
        return serialize.tile_rows(game, fresh | {i for i in changed if explored[i]})

    def _play_one_turn(self) -> None:
        self.game.events.clear()
        self._events_read = 0
        turn.play_turn(self.game)
        self.history.append(self._history_row())

    def _advance(self) -> None:
        """Lets the AI play until the person's next turn (or the end of the game). The
        events of that stretch are left for the caller to read."""
        game = self.game
        before = game.turn
        self._read_events()                    # nothing told so far is lost
        game.events.clear()
        self._events_read = 0
        turn.advance(game)
        if game.turn != before:
            self.history.append(self._history_row())

    async def step(self) -> None:
        """Plays one turn of an observed game and tells everybody."""
        async with self._busy:
            game = self.game
            if game is None or game.finished or self.in_play():
                self.playing = False
                return
            await asyncio.to_thread(self._play_one_turn)
            events, _ = self._read_events()
            changes = self._tiles()
            if game.finished:
                self.playing = False
            await self._broadcast(lambda pov: {
                "type": "turn", "state": self._state(pov),
                "tile_changes": changes, "events": events, "history": self.history[-1],
                "playing": self.playing})

    async def end_turn(self, turn_number: Any = None) -> None:
        """The person has finished: the others play, then its next turn begins.

        A browser says which turn it is ending. Two browsers open on the same game may both
        ask (the turn ends by itself after the last unit's order): the second request names
        a turn that is already over and is ignored.
        """
        async with self._busy:
            if not self.in_play():
                return
            game = self.game
            if turn_number is not None and turn_number != game.turn:
                return
            before = game.turn
            self._steps = []
            await asyncio.to_thread(self._advance)
            if not self.in_play():
                # Destroyed, or the game is over: nothing is hidden any more.
                self._read_events()
                game.changed_tiles.clear()
                await self.broadcast_init()
                return
            _, known = self._read_events()
            changes = self._tiles()
            row = self._shown(self.history[-1]) if game.turn != before else None
            await self._broadcast(lambda pov: {
                "type": "turn", "state": self._state(pov), "tile_changes": changes,
                "events": known, "steps": self._steps, "history": row, "playing": False})
            if game.turn != before and game.turn % AUTOSAVE_EVERY == 0:
                await asyncio.to_thread(self.save, AUTOSAVE)
                await self._broadcast(lambda pov: {"type": "saves", "saves": self.saved_games()})

    async def run(self) -> None:
        """Background loop: plays turns while the game is in "play" mode."""
        while True:
            if self.playing and self.game is not None and not self.game.finished \
                    and not self.in_play():
                await self.step()
                await asyncio.sleep(self.delay)
            else:
                await asyncio.sleep(0.05)

    # ── Orders of the person ──────────────────────────────────────────────────

    async def _report(self, result: dict[str, Any], unit_id: Optional[int] = None,
                      city_id: Optional[int] = None) -> None:
        """Tells every browser what an order changed."""
        game = self.game
        if not self.in_play():
            # The order ended the person's game (its last settlers disbanded...).
            await asyncio.to_thread(self._advance)
            self._read_events()
            game.changed_tiles.clear()
            await self.broadcast_init()
            return
        view, controller = self._view(), self._controller()
        _, known = self._read_events()
        unit = view.unit(unit_id) if unit_id is not None else None
        city = view.city(city_id) if city_id is not None else None
        message = {
            "type": "update", **result, "unit": unit_id, "city": city_id,
            "state": self._state(self.human), "tile_changes": self._tiles(), "events": known,
            "steps": self._steps,
            "unit_detail": serialize.unit_detail(view, controller, unit) if unit else None,
            "city_detail": serialize.city_detail(game, city, controller=controller)
            if city else None,
        }
        await self._broadcast(lambda pov: message)

    async def act(self, message: dict) -> None:
        """One order of the person, applied by the engine like any AI action."""
        async with self._busy:
            if not self.in_play():
                return
            action = commands.parse(message)
            name = message.get("action")
            self._steps = []
            if action is None:
                await self._report({"ok": False, "action": name, "outcome": "",
                                    "reason": "unknown order"})
                return
            unit_id = getattr(action, "unit_id", None)
            if unit_id is not None:
                self._controller().release(unit_id)       # the person takes the unit in hand
            result = actions.apply(self.game, self.human, action)
            await self._report({"ok": result.ok, "action": name, "outcome": result.outcome,
                                "reason": result.reason},
                               unit_id, getattr(action, "city_id", None))

    async def delegate(self, message: dict) -> None:
        """Go to, automatic units, city governors: what the person leaves to its controller."""
        async with self._busy:
            if not self.in_play():
                return
            game, view, controller = self.game, self._view(), self._controller()
            command = message["cmd"]
            self._steps = []
            unit = view.unit(message.get("unit")) if type(message.get("unit")) is int else None
            result = {"ok": False, "action": command, "outcome": "", "reason": "no such unit"}
            if command == "govern":
                city = view.city(message.get("city")) if type(message.get("city")) is int else None
                if city is None:
                    result["reason"] = "no such city"
                else:
                    controller.govern(view, city, bool(message.get("on")))
                    result.update(ok=True, reason="")
                await self._report(result, city_id=city.id if city else None)
                return
            if unit is not None and command == "goto":
                x, y = message.get("x"), message.get("y")
                goal = game.map.tile(x, y) if type(x) is int and type(y) is int else None
                status = controller.send(view, unit, goal) if goal is not None else BLOCKED
                result.update(ok=status != BLOCKED, outcome=status,
                              reason="no known way there" if status == BLOCKED else "")
            elif unit is not None and command == "automate":
                mode = message.get("mode")
                if mode == "none":
                    controller.release(unit.id)
                    result.update(ok=True, reason="")
                elif controller.automate(view, unit, mode):
                    result.update(ok=True, reason="")
                else:
                    result["reason"] = "this unit cannot do that by itself"
            await self._report(result, unit.id if unit else None)

    # ── Clients ───────────────────────────────────────────────────────────────

    def init_message(self, pov: Optional[int]) -> dict:
        game = self.game
        in_play = self.in_play()
        if in_play:
            pov = self.human
        return {
            "type": "init",
            "rules": serialize.rules_payload(self.rules),
            "map": serialize.map_payload(game, self._leader() if in_play else None),
            "state": self._state(pov),
            "history": [self._shown(row) for row in self.history],
            "history_fields": HISTORY_FIELDS,
            "log": list(self.heard if in_play else self.log),
            "playing": self.playing,
            "delay": self.delay,
            "saves": self.saved_games(),
        }

    async def _broadcast(self, build) -> None:
        cache: dict[Optional[int], dict] = {}
        for client in list(self.clients):
            pov = self._pov(client)
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

    # ── Commands from the browsers ────────────────────────────────────────────

    async def handle(self, client: WebSocket, message: dict) -> None:
        command = message.get("cmd")
        game = self.game
        if command == "new_game":
            await self._new_game(client, message)
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
        elif command == "end_turn":
            await self.end_turn(message.get("turn"))
        elif command == "action":
            await self.act(message)
        elif command in ("goto", "automate", "govern"):
            await self.delegate(message)
        elif command in ("unit", "preview"):
            async with self._busy:
                await self._answer(client, message)
        elif command == "play":
            self.playing = not self.in_play()
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
            await self._send(client, {"type": "state", "state": self._state(self._pov(client))})
        elif command == "city":
            async with self._busy:
                await self._city(client, message.get("id"))
        elif command == "player":
            async with self._busy:
                await self._player(client, message.get("id"))

    async def _new_game(self, client: WebSocket, message: dict) -> None:
        seed = message.get("seed")
        if not isinstance(seed, int):
            seed = random.randrange(1, 100000)
        players = message.get("players")
        if not isinstance(players, int) or not 2 <= players <= len(self.rules.playable_civs):
            players = None
        map_settings = self._map_settings(message.get("map"))
        civ = level = None
        if message.get("mode") == "play":
            playable = [c.id for c in self.rules.playable_civs]
            civ = message.get("civ")
            if civ not in playable:
                civ = random.choice(playable)
            level = message.get("level")
            if level not in self.rules.game.difficulty.levels:
                level = None
        async with self._busy:
            await asyncio.to_thread(self.new_game, seed, players, map_settings, civ, level)
        await self.broadcast_init()
        if civ is not None and not self.in_play():
            await self._notice(client, "No room on this world for your civilization: "
                                       "you are watching the game instead.", False)

    async def _answer(self, client: WebSocket, message: dict) -> None:
        """Questions of the person about one of its units: its orders, or what a move would do."""
        if not self.in_play():
            return
        view = self._view()
        unit_id = message.get("id") if message["cmd"] == "unit" else message.get("unit")
        unit = view.unit(unit_id) if type(unit_id) is int else None
        if unit is None:
            return
        if message["cmd"] == "unit":
            await self._send(client, {"type": "unit", "unit": serialize.unit_detail(
                view, self._controller(), unit)})
            return
        x, y = message.get("x"), message.get("y")
        target = self.game.map.tile(x, y) if type(x) is int and type(y) is int else None
        if target is not None:
            await self._send(client, {"type": "preview", **orders.preview(view, unit, target)})

    async def _city(self, client: WebSocket, city_id: Any) -> None:
        game = self.game
        city = game.cities.get(city_id)
        if not self.in_play():
            if city is not None:
                controller = game.controllers.get(city.owner)
                decision = getattr(controller, "decisions", {}).get(city.id)
                await self._send(client, {"type": "city",
                                          "city": serialize.city_detail(game, city, decision)})
            return
        # A person sees its own cities in full, and of the others only what it remembers.
        if city is not None and city.owner == self.human:
            detail = serialize.city_detail(game, city, controller=self._controller())
        elif city_id in self._leader().known_cities:
            detail = serialize.remembered_city_payload(self._leader().known_cities[city_id])
        else:
            return
        await self._send(client, {"type": "city", "city": detail})

    async def _player(self, client: WebSocket, player_id: Any) -> None:
        game = self.game
        if not isinstance(player_id, int) or not 0 <= player_id < len(game.players):
            return
        player = game.players[player_id]
        if not self.in_play():
            detail = serialize.player_detail(game, player, game.controllers.get(player.id))
        elif player_id == self.human:
            detail = serialize.own_detail(self._view(), game)
        else:
            detail = serialize.public_player_payload(game, player, self._leader())
        await self._send(client, {"type": "player", "player": detail})
