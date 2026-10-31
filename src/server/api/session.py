"""The running game and the browsers connected to it.

One game at a time, in one of two modes. Observed: the AI plays every civilization, the
session plays turns on demand or in a loop and each browser picks its point of view.
Played: a person leads one civilization; the session waits for its orders, applies them one
by one, and lets the AI play the others when the person ends its turn. Every browser then
sees the game through that person's eyes, and only what it is supposed to know. That
includes the steps the units take in its sight: its own, and those of the others while they
play, which the browser shows one after the other.

Each turn, the session notes the figures of the History and what the replay shows (replay.py).
The replay is sent to a browser that asks, once nothing is hidden any more.

Turns are played in a worker thread, so the web server stays responsive. The session also
saves the game to the `saves` folder and loads it back. A played game saves itself every few
turns under the name it was loaded or saved under; the save it replaces is kept as
`name-<its year>`, and the backup before that one goes. Only the copy of the game holds the
others up: the files are written, renamed and deleted in the background. When the server
starts, the session can take up the save written last instead of a new game.

Each game is played with one of the sets of rules of config/rulesets/, chosen when it starts;
its saves record which, and a loaded game takes the rules it was played with.
"""
from __future__ import annotations

import asyncio
import dataclasses
import random
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any, Optional

from fastapi import WebSocket

from ..engine import actions, persistence
from ..engine.model.entities import Player, Unit
from ..engine.model.game import Game
from ..engine.model.worldmap import Tile
from ..engine.rules.loader import PROJECT_ROOT
from ..engine.rules.schema import LAND_STEPS, MapSettings, Rules
from ..engine.systems import turn
from ..engine.view import PlayerView
from ..human import orders
from ..human.controller import BLOCKED, HumanController
from ..sim.runner import create_game, restore_game
from . import commands, serialize
from .replay import Replay

MAX_LOG = 600
HISTORY_FIELDS = ("cities", "population", "techs", "score", "gold", "units")
DEFAULT_SAVES_DIR = PROJECT_ROOT / "saves"
SAVE_NAME = re.compile(r"[A-Za-z0-9_-]{1,40}")
SAVED_NAME = re.compile(r"[A-Za-z0-9_-]{1,48}")    # a backup adds the year to the name
AUTOSAVE = "autosave"                          # where a game that has no name saves itself (the first one)
AUTOSAVE_EVERY = 5                             # turns between two automatic saves of a played game


def year_tag(year: int) -> str:
    """The year of the game a backup holds, as its name ends: 1915, 3000BC."""
    return f"{-year}BC" if year < 0 else str(year)


def base_name(name: str, year: int) -> str:
    """The name a loaded game goes on saving itself under: that of the game, for a backup."""
    suffix = f"-{year_tag(year)}"
    return name[:-len(suffix)] if name.endswith(suffix) and len(name) > len(suffix) else name


class Session:
    def __init__(self, rulesets: dict[str, Rules], saves_dir: Optional[Path] = None) -> None:
        self.rulesets = rulesets               # by id, the first one for the first game
        self.saves_dir = Path(saves_dir) if saves_dir else DEFAULT_SAVES_DIR
        self.game: Optional[Game] = None
        self.human: Optional[int] = None       # the player a person leads (or led), if any
        self.playing = False
        self.delay = 0.4                       # seconds between two turns while playing
        self.clients: dict[WebSocket, Optional[int]] = {}    # socket -> point of view
        self.history: list[dict] = []
        self.replay = Replay()
        self.log: deque[dict] = deque(maxlen=MAX_LOG)           # everything that happened
        self.heard: deque[dict] = deque(maxlen=MAX_LOG)         # what the person heard of
        self._events_read = 0                  # events of game.events already in the logs
        self._known = bytearray()              # tiles the person's browser already holds
        self._steps: list[dict] = []           # steps the person saw since its last order
        self.save_name: Optional[str] = None   # the name the game was loaded or saved under
        self._writing: Optional[asyncio.Task] = None    # the last save asked for
        self._busy = asyncio.Lock()
        self.new_game(random.randrange(1, 100000))

    @property
    def rules(self) -> Rules:
        """The rules of the game being played."""
        return self.game.rules

    def _ruleset(self, ruleset: Any) -> Rules:
        """The rules of that id, or else those of the current game (the first ones at start)."""
        if isinstance(ruleset, str) and ruleset in self.rulesets:
            return self.rulesets[ruleset]
        return self.game.rules if self.game is not None else next(iter(self.rulesets.values()))

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
                 civ: Optional[str] = None, level: Optional[str] = None,
                 ruleset: Optional[str] = None, name: Optional[str] = None) -> None:
        """Starts a game with the rules `ruleset` (those of the current game if None). With
        `civ`, a person leads that civilization at this `level`. The game saves itself as
        `name`."""
        rules = self._ruleset(ruleset)
        self.playing = False
        self.game = create_game(rules, seed, player_count=players,
                                map_settings=map_settings, human_civ=civ, level=level)
        self.save_name = name
        self._reset(humans=[p.id for p in self.game.players if turn.is_interactive(self.game, p)])
        self.history = []
        self.replay = Replay()
        self._note_turn()
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

    def _map_settings(self, rules: Rules, choices: Any, seed: int) -> MapSettings:
        """The map settings of the rules, with the valid choices of the new-game dialog.

        A surprise world draws its shape, land and nature from the seed (never a fixed
        world), and keeps the huts chosen.
        """
        settings = rules.game.map
        if not isinstance(choices, dict):
            return settings
        changes: dict[str, Any] = {}
        shape = choices.get("shape")
        if isinstance(shape, str) and shape in settings.shapes:
            changes["shape"] = shape
        land = choices.get("land")
        if type(land) is int and land in LAND_STEPS:
            changes["land"] = land
        for name in serialize.MAP_LEVELS:
            level = choices.get(name)
            if type(level) is int and 0 <= level <= 2:
                changes[name] = level
        if type(choices.get("historical_starts")) is bool:
            changes["historical_starts"] = choices["historical_starts"]
        if choices.get("surprise") is True:
            draw = random.Random(seed)
            changes["shape"] = draw.choice(
                [shape_id for shape_id, s in settings.shapes.items() if s.fixed is None])
            changes["land"] = draw.choice(LAND_STEPS)
            for name in serialize.NATURE_LEVELS:
                changes[name] = draw.randrange(3)
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

    def _note_turn(self) -> None:
        """A turn begins: its figures go to the History, its cities to the replay."""
        self.history.append(self._history_row())
        self.replay.note_cities(self.game)

    def _shown(self, row: dict) -> dict:
        """A history row as the browsers may see it: a person only follows its own figures."""
        if not self.in_play():
            return row
        return {**row, "players": {self.human: row["players"][self.human]}}

    # ── Saved games ───────────────────────────────────────────────────────────

    def saved_games(self) -> list[str]:
        if not self.saves_dir.is_dir():
            return []
        files = []
        for path in self.saves_dir.glob("*.json"):
            try:
                files.append((path.stat().st_mtime, path.stem))
            except OSError:
                continue                       # just renamed or deleted by a save being written
        return [stem for _, stem in sorted(files, reverse=True) if SAVED_NAME.fullmatch(stem)]

    def _path(self, name: str) -> Path:
        return self.saves_dir / f"{name}.json"

    def save(self, name: str) -> None:
        """Writes the game, with the charts and the logs (what `_save` does in two steps)."""
        self._write(name, *self._snapshot())

    def _snapshot(self) -> tuple[str, dict[str, int]]:
        """The game as the text of its save, and the turn it is at."""
        game = self.game
        text = persistence.dump_game(game, extra={"history": self.history, "log": list(self.log),
                                                  "heard": list(self.heard),
                                                  "replay": self.replay.payload()})
        return text, {"seed": game.seed, "turn": game.turn, "year": game.year}

    def _write(self, name: str, text: str, moment: dict[str, int]) -> None:
        """Writes a save over the one of that name, which is kept as `name-<its year>`
        (unless it holds the same turn of the same game); the backup before it goes."""
        path = self._path(name)
        if not path.exists():
            persistence.write_save(path, text)
            return
        previous = persistence.save_header(path)
        if previous is None:                   # not a game this one can date: set aside as is
            persistence.write_save(path, text, keep=self._path(f"{name}-old"))
        elif (previous["seed"], previous["turn"]) == (moment["seed"], moment["turn"]):
            persistence.write_save(path, text)  # the same turn again: the backup stays
        else:
            keep = self._path(f"{name}-{year_tag(previous['year'])}")
            persistence.write_save(path, text, keep)
            for backup in self._backups(name):
                if backup != keep:
                    backup.unlink(missing_ok=True)

    def _backups(self, name: str) -> list[Path]:
        """The backups of a save: the files `name-<year>` holding the game of that year."""
        backups = []
        for path in self.saves_dir.glob(f"{name}-*.json"):
            header = persistence.save_header(path)
            if header is not None and path.stem == f"{name}-{year_tag(header['year'])}":
                backups.append(path)
        return backups

    async def _save(self, name: str, client: Optional[WebSocket] = None) -> None:
        """Saves the game; the caller holds `_busy`. Only the copy of the game is waited
        for: the files are written after the saves asked for before, in the background."""
        text, moment = await asyncio.to_thread(self._snapshot)
        self._writing = asyncio.create_task(self._store(self._writing, name, text, moment, client))

    async def _store(self, previous: Optional[asyncio.Task], name: str, text: str,
                     moment: dict[str, int], client: Optional[WebSocket]) -> None:
        if previous is not None:
            await asyncio.wait([previous])
        try:
            await asyncio.to_thread(self._write, name, text, moment)
        except OSError as error:
            notice = {"type": "notice", "text": f"Cannot save {name}: {error}", "ok": False}
            if client is not None:
                await self._send(client, notice)
            else:
                await self._broadcast(lambda pov: notice)
            return
        if client is not None:
            await self._notice(client, f"Game saved as {name}.", True)
        await self._broadcast(lambda pov: self._saves_message())

    async def flush(self) -> None:
        """Waits until the saves asked for so far are on disk."""
        if self._writing is not None:
            await asyncio.wait([self._writing])

    def _saves_message(self) -> dict:
        return {"type": "saves", "saves": self.saved_games(), "save_name": self.save_name}

    def load(self, name: str) -> None:
        data = persistence.read_save(self._path(name))
        ruleset = persistence.saved_ruleset(data)
        if ruleset not in self.rulesets:
            raise persistence.SaveError(f"it is played with the rules '{ruleset}', "
                                        f"which are not in config/rulesets/")
        game = restore_game(self.rulesets[ruleset], data)
        self.playing = False
        self.game = game
        self.save_name = base_name(name, game.year)
        self._reset(humans=data.get("humans", []))
        extra = data.get("extra", {})
        self.history = extra.get("history") or [self._history_row()]
        # JSON turned the player ids of the history rows into text.
        for row in self.history:
            row["players"] = {int(pid): values for pid, values in row["players"].items()}
        self.log.extend(extra.get("log", []))
        self.heard.extend(extra.get("heard", []))
        self.replay = Replay.restore(extra.get("replay"), game, self.log)
        # Saves made before the origins of the wonders were kept: the chronicle still tells
        # when and by whom its latest wonders were completed.
        told = {event["wonder"]: event for event in self.log if event.get("type") == "wonder"}
        for wonder_id, event in told.items():
            if game.wonders.get(wonder_id) == event.get("city"):
                game.wonder_origins.setdefault(wonder_id, (event["year"], event["player"],
                                                           game.cities[event["city"]].name))
        if self.in_play() and game.current_player != self.human:
            self._advance()                    # saved between two turns: on to the person's
            self._read_events()

    def resume(self) -> Optional[str]:
        """Loads the save written last that this version can read, and returns its name;
        None when there is none, and the game on the table stays."""
        for name in self.saved_games():
            try:
                self.load(name)
            except persistence.SaveError as error:
                print(f"Cannot load {name}: {error}", file=sys.stderr)
                continue
            return name
        return None

    # ── Playing turns ─────────────────────────────────────────────────────────

    def _read_events(self) -> tuple[list[dict], list[dict]]:
        """The events not reported yet: all of them, and those the person hears of."""
        game = self.game
        fresh = game.events[self._events_read:]
        self._events_read = len(game.events)
        self.log.extend(fresh)
        self.replay.note_events(fresh)
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
        self._note_turn()

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
            self._note_turn()

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
                await self._save(self.save_name or AUTOSAVE)

    async def retire(self) -> None:
        """The game ends now, as asked from a browser: nothing is hidden any more, and every
        browser gets the whole world, the scores of all and the replay. The save on disk is
        left as it was."""
        async with self._busy:
            game = self.game
            if game is None or game.finished:
                return
            self.playing = False
            self._steps = []
            turn.retire(game, self.human if self.in_play() else None)
            self._read_events()
            game.changed_tiles.clear()
            await self.broadcast_init()

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
                elif not controller.automate(view, unit, mode):
                    result["reason"] = "this unit cannot do that by itself"
                elif controller.task(unit.id) != mode:
                    # Nothing to do on its own: it is back in the person's hands, and says why.
                    result["reason"] = next((note["text"] for note in reversed(controller.notes)
                                             if note.get("unit") == unit.id), "nothing to do")
                else:
                    result.update(ok=True, reason="")
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
            "rulesets": [serialize.ruleset_payload(rules) for rules in self.rulesets.values()],
            "map": serialize.map_payload(game, self._leader() if in_play else None),
            "state": self._state(pov),
            "history": [self._shown(row) for row in self.history],
            "history_fields": HISTORY_FIELDS,
            "log": list(self.heard if in_play else self.log),
            "playing": self.playing,
            "delay": self.delay,
            "saves": self.saved_games(),
            "save_name": self.save_name,
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
                self.save_name = name          # the game now saves itself there
                await self._save(name, client)
        elif command == "load":
            name = message.get("name")
            async with self._busy:
                await self.flush()             # the saves asked for before it are on disk
                if not isinstance(name, str) or name not in self.saved_games():
                    await self._notice(client, "No such saved game.", False)
                    return
                try:
                    await asyncio.to_thread(self.load, name)
                except persistence.SaveError as error:
                    await self._notice(client, f"Cannot load {name}: {error}", False)
                    return
            await self.broadcast_init()
            await self._notice(client, f"Game {name} loaded.", True)
        elif command == "end_turn":
            await self.end_turn(message.get("turn"))
        elif command == "retire":
            await self.retire()
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
        elif command == "replay":
            async with self._busy:
                await self._replay(client)

    async def _new_game(self, client: WebSocket, message: dict) -> None:
        # A new game is named: it never saves itself over the game played before it.
        name = message.get("name")
        if not isinstance(name, str) or not SAVE_NAME.fullmatch(name):
            await self._notice(client, "Name the new game: letters, digits, - and _.", False)
            return
        seed = message.get("seed")
        if not isinstance(seed, int):
            seed = random.randrange(1, 100000)
        rules = self._ruleset(message.get("ruleset"))
        players = message.get("players")
        if not isinstance(players, int) or not 2 <= players <= len(rules.playable_civs):
            players = None
        map_settings = self._map_settings(rules, message.get("map"), seed)
        civ = level = None
        if message.get("mode") == "play":
            playable = [c.id for c in rules.playable_civs]
            civ = message.get("civ")
            if civ not in playable:
                civ = random.choice(playable)
            level = message.get("level")
            if level not in rules.game.difficulty.levels:
                level = None
        async with self._busy:
            await asyncio.to_thread(self.new_game, seed, players, map_settings, civ, level,
                                    rules.ruleset.id, name)
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

    async def _replay(self, client: WebSocket) -> None:
        """The replay of the game. It shows every civilization: a person leading one waits
        for the end of the game."""
        if self.in_play():
            await self._notice(client, "The replay opens once the game is over.", False)
            return
        await self._send(client, {"type": "replay", **self.replay.payload()})
