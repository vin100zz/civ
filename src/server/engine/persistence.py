"""Saved games: the whole state of a game as plain JSON data, and back.

Everything that decides the future of a game is saved, including the state of the random
generator: a loaded game continues exactly as the original would have. What can be derived
(which tile holds which city, the figures of each city) is rebuilt on load.

The players' controllers (the AI, or what a person delegated) keep their own memory; they
save and restore it through `save_state()` / `load_state()` and the result travels in the
same file, with the list of the players led by a person (`humans`).
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from .model.entities import (City, CityMemory, Item, Player, Relation, Spaceship, Unit)
from .model.game import Game
from .model.worldmap import WorldMap
from .rules.schema import Rules
from .systems import city as city_rules

VERSION = 1
TILE_FLAGS = ("special", "pattern", "hut", "road", "railroad", "irrigation", "mine", "fortress",
              "pollution")


class SaveError(Exception):
    """The file is not a saved game this version can read."""


# ── Saving ────────────────────────────────────────────────────────────────────

def game_to_data(game: Game) -> dict[str, Any]:
    terrain_ids = list(game.rules.terrains)
    terrain_index = {terrain_id: i for i, terrain_id in enumerate(terrain_ids)}
    world = game.map
    version, internal, gauss = game.rng.getstate()
    return {
        "version": VERSION,
        "seed": game.seed, "turn": game.turn, "year": game.year,
        "finished": game.finished, "winner": game.winner, "victory": game.victory,
        "warming_level": game.warming_level, "warming_count": game.warming_count,
        "next_unit_id": game._next_unit_id, "next_city_id": game._next_city_id,
        "rng": [version, list(internal), gauss],
        "map": {
            "width": world.width, "height": world.height, "wrap_x": world.wrap_x,
            "terrains": terrain_ids,
            "terrain": [terrain_index[t.terrain] for t in world.tiles],
            "flags": [sum(1 << bit for bit, name in enumerate(TILE_FLAGS) if getattr(t, name))
                      for t in world.tiles],
            "continent": [t.continent for t in world.tiles],
            "continent_sizes": [[k, v] for k, v in world.continent_sizes.items()],
            "units": [[t.index, list(t.unit_ids)] for t in world.tiles if t.unit_ids],
        },
        "players": [_player_to_data(p) for p in game.players],
        "cities": [_city_to_data(c) for c in game.cities.values()],
        "units": [dataclasses.asdict(u) for u in game.units.values()],
        "wonders": [[wonder_id, city_id] for wonder_id, city_id in game.wonders.items()],
        "relations": [[a, b, r.state, r.since_turn, r.last_proposal_turn, r.pending_from]
                      for (a, b), r in game.relations.items()],
        # A game led by a person is saved in the middle of that person's turn.
        "current_player": game.current_player,
        "round_position": game.round_position,
        "humans": [player_id for player_id, controller in game.controllers.items()
                   if getattr(controller, "interactive", False)],
        "controllers": {
            str(player_id): controller.save_state()
            for player_id, controller in game.controllers.items()
            if hasattr(controller, "save_state")},
    }


def _player_to_data(player: Player) -> dict[str, Any]:
    data = {f.name: getattr(player, f.name) for f in dataclasses.fields(player)
            if f.name not in ("civ", "techs", "explored", "visible", "known_cities", "spaceship")}
    data["civ"] = player.civ.id
    data["techs"] = sorted(player.techs)
    data["explored"] = player.explored.hex()
    data["visible"] = player.visible.hex()
    data["known_cities"] = [dataclasses.asdict(m) for m in player.known_cities.values()]
    data["spaceship"] = dataclasses.asdict(player.spaceship)
    return data


def _city_to_data(city: City) -> dict[str, Any]:
    data = {f.name: getattr(city, f.name) for f in dataclasses.fields(city)
            if f.name not in ("production", "buildings", "worked", "stats", "last_completed")}
    data["production"] = _item_to_data(city.production)
    data["last_completed"] = _item_to_data(city.last_completed)
    data["buildings"] = sorted(city.buildings)
    data["worked"] = [list(offset) for offset in city.worked]
    return data


def _item_to_data(item) -> Any:
    return [item.kind, item.id] if item is not None else None


def save_game(game: Game, path: Path, extra: dict[str, Any] | None = None) -> None:
    """Writes the game to a file. `extra` is stored as is (the observer's charts and log)."""
    data = game_to_data(game)
    if extra:
        data["extra"] = extra
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))


# ── Loading ───────────────────────────────────────────────────────────────────

def game_from_data(rules: Rules, data: dict[str, Any]) -> Game:
    """Rebuilds a game. Controllers are not attached: see `restore_controllers`."""
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise SaveError(f"unsupported save version: {data.get('version') if isinstance(data, dict) else data!r}")
    try:
        return _build_game(rules, data)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SaveError(f"the saved game does not match the current rules: {exc!r}") from exc


def _build_game(rules: Rules, data: dict[str, Any]) -> Game:
    saved_map = data["map"]
    terrain_ids = saved_map["terrains"]
    for terrain_id in terrain_ids:
        if terrain_id not in rules.terrains:
            raise ValueError(f"unknown terrain '{terrain_id}'")
    world = WorldMap(saved_map["width"], saved_map["height"], saved_map["wrap_x"], terrain_ids[0])
    for tile, terrain, flags, continent in zip(world.tiles, saved_map["terrain"],
                                               saved_map["flags"], saved_map["continent"]):
        tile.terrain = terrain_ids[terrain]
        tile.continent = continent
        for bit, name in enumerate(TILE_FLAGS):
            setattr(tile, name, bool(flags >> bit & 1))
    world.continent_sizes = {k: v for k, v in saved_map["continent_sizes"]}

    game = Game(rules, data["seed"], world)
    game.turn, game.year = data["turn"], data["year"]
    game.finished, game.winner, game.victory = data["finished"], data["winner"], data["victory"]
    game.warming_level, game.warming_count = data["warming_level"], data["warming_count"]
    game._next_unit_id, game._next_city_id = data["next_unit_id"], data["next_city_id"]
    version, internal, gauss = data["rng"]
    game.rng.setstate((version, tuple(internal), gauss))

    for saved in data["players"]:
        game.players.append(_player_from_data(rules, saved))
    for saved in data["cities"]:
        city = _city_from_data(saved)
        game.cities[city.id] = city
        world.tile(city.x, city.y).city_id = city.id
    for saved in data["units"]:
        unit = Unit(**saved)
        if unit.type not in rules.units:
            raise ValueError(f"unknown unit '{unit.type}'")
        game.units[unit.id] = unit
    for index, unit_ids in saved_map["units"]:
        world.tiles[index].unit_ids = list(unit_ids)
    game.wonders = {wonder_id: city_id for wonder_id, city_id in data["wonders"]}
    for a, b, state, since, proposal, *pending in data["relations"]:
        game.relations[(a, b)] = Relation(state, since, proposal, pending[0] if pending else None)
    game.current_player = data.get("current_player")
    game.round_position = data.get("round_position", 0)

    # Derived state.
    for city in game.cities.values():
        for dx, dy in city.worked:
            world.tile(city.x + dx, city.y + dy).worked_by = city.id
        world.tile(city.x, city.y).worked_by = city.id
    for city in game.cities.values():
        city.stats = city_rules.compute_city(game, city)
    return game


def _player_from_data(rules: Rules, saved: dict[str, Any]) -> Player:
    saved = dict(saved)
    player = Player(id=saved.pop("id"), civ=rules.civs[saved.pop("civ")])
    player.techs = set(saved.pop("techs"))
    unknown = player.techs - set(rules.techs)
    if unknown:
        raise ValueError(f"unknown advances {sorted(unknown)}")
    player.explored = bytearray.fromhex(saved.pop("explored"))
    player.visible = bytearray.fromhex(saved.pop("visible"))
    player.known_cities = {m["city_id"]: CityMemory(**m) for m in saved.pop("known_cities")}
    player.spaceship = Spaceship(**saved.pop("spaceship"))
    for name, value in saved.items():
        setattr(player, name, value)
    return player


def _city_from_data(saved: dict[str, Any]) -> City:
    saved = dict(saved)
    production = saved.pop("production")
    completed = saved.pop("last_completed")
    city = City(**{**saved, "buildings": set(saved["buildings"]),
                   "worked": [tuple(offset) for offset in saved["worked"]]})
    city.production = Item(*production) if production else None
    city.last_completed = Item(*completed) if completed else None
    return city


def restore_controllers(game: Game, data: dict[str, Any]) -> None:
    """Gives the controllers attached to the game the memory they had when it was saved."""
    for player_id, state in data.get("controllers", {}).items():
        controller = game.controllers.get(int(player_id))
        if controller is not None and hasattr(controller, "load_state"):
            controller.load_state(state)


def read_save(path: Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveError(f"cannot read {path}: {exc}") from exc
