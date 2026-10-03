"""Headless games: the tool to judge and tune the AI.

    python simulate.py --seeds 1 2 3 --turns 300
    python simulate.py --seed 7 --turns 400 --csv out.csv --every 50
    python simulate.py --seed 7 --turns 300 --save saves/seed7.json
    python simulate.py --load saves/seed7.json --turns 100

Runs complete games without the web server, prints a report per civilization and can
export the per-turn metrics as CSV.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import time
from collections import Counter
from typing import Optional, Sequence

from ..ai.barbarian import BarbarianController
from ..ai.controller import AIController
from ..engine import persistence
from ..engine.model.game import Game
from ..engine.rules.loader import load_rules
from ..engine.rules.schema import MapSettings, Rules
from ..engine.setup import new_game
from ..engine.systems import turn
from .metrics import Metrics


def attach_ai(game: Game) -> None:
    """Gives every player its controller."""
    for player in game.players:
        game.controllers[player.id] = BarbarianController() if player.is_barbarian else AIController()


def create_game(rules: Rules, seed: int, civ_ids: Optional[Sequence[str]] = None,
                player_count: Optional[int] = None,
                map_settings: Optional[MapSettings] = None) -> Game:
    game = new_game(rules, seed, civ_ids=civ_ids, player_count=player_count,
                    map_settings=map_settings)
    attach_ai(game)
    return game


def restore_game(rules: Rules, data: dict) -> Game:
    """A saved game, with its AI players and what they remembered."""
    game = persistence.game_from_data(rules, data)
    attach_ai(game)
    persistence.restore_controllers(game, data)
    return game


def run_game(rules: Rules, seed: int, turns: int, metrics: Optional[Metrics] = None,
             every: int = 0, game: Optional[Game] = None,
             map_settings: Optional[MapSettings] = None) -> Game:
    game = game or create_game(rules, seed, map_settings=map_settings)
    for _ in range(turns):
        if game.finished:
            break
        game.events.clear()
        turn.play_turn(game)
        if metrics is not None:
            metrics.record(game)
        if every and game.turn % every == 0:
            print(report(game, brief=True))
    return game


def report(game: Game, brief: bool = False) -> str:
    year = f"{abs(game.year)} {'BC' if game.year < 0 else 'AD'}"
    lines = [f"Seed {game.seed}, turn {game.turn} ({year})"]
    header = f"  {'civilization':<14}{'cities':>7}{'pop':>5}{'techs':>6}{'units':>6}{'ships':>6}" \
             f"{'air':>5}{'gold':>7}{'score':>6}  government"
    lines.append(header)
    domains = {unit_id: definition.domain for unit_id, definition in game.rules.units.items()}
    for player in game.players:
        cities = game.player_cities(player.id)
        units = game.player_units(player.id)
        if player.is_barbarian and not cities and not units:
            continue
        status = "" if player.alive else f"  (destroyed turn {player.destroyed_turn})"
        if player.spaceship.launched:
            status += f"  (spaceship arrives turn {player.spaceship.arrival_turn})"
        ships = sum(1 for u in units if domains[u.type] == "sea")
        aircraft = sum(1 for u in units if domains[u.type] == "air")
        lines.append(
            f"  {player.civ.name:<14}{len(cities):>7}{sum(c.size for c in cities):>5}"
            f"{player.tech_count:>6}{len(units):>6}{ships:>6}{aircraft:>5}{player.gold:>7}"
            f"{player.score:>6}  {player.government}{status}")
    if not brief:
        wars = [f"{game.players[a].civ.name}-{game.players[b].civ.name}"
                for (a, b), r in sorted(game.relations.items()) if r.state == "war"
                and game.players[a].alive and game.players[b].alive]
        lines.append(f"  wars: {', '.join(wars) or 'none'}")
        polluted = sum(1 for tile in game.map.tiles if tile.pollution)
        lines.append(f"  wonders: {len(game.wonders)}, polluted tiles: {polluted}, "
                     f"global warmings: {game.warming_count}")
        if game.finished and game.winner is not None:
            lines.append(f"  winner: {game.players[game.winner].civ.name} ({game.victory})")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--seeds", type=int, nargs="*", default=None)
    parser.add_argument("--turns", type=int, default=300)
    parser.add_argument("--every", type=int, default=0, help="print a brief report every N turns")
    parser.add_argument("--csv", type=str, default=None, help="write per-turn metrics here")
    parser.add_argument("--events", action="store_true", help="count events by type")
    parser.add_argument("--save", type=str, default=None, help="save the game here at the end")
    parser.add_argument("--load", type=str, default=None, help="continue this saved game")
    parser.add_argument("--shape", type=str, default=None,
                        help="map shape, one of map.shapes in config/game.yaml")
    for name in ("relief", "climate", "temperature"):
        parser.add_argument(f"--{name}", type=int, choices=(0, 1, 2), default=None)
    args = parser.parse_args()

    seeds = args.seeds if args.seeds else [args.seed if args.seed is not None else 1]
    rules = load_rules()
    if args.shape is not None and args.shape not in rules.game.map.shapes:
        parser.error(f"unknown shape '{args.shape}' (known: {', '.join(rules.game.map.shapes)})")
    choices = {name: getattr(args, name) for name in ("shape", "relief", "climate", "temperature")}
    map_settings = dataclasses.replace(
        rules.game.map, **{name: value for name, value in choices.items() if value is not None})
    loaded = restore_game(rules, persistence.read_save(args.load)) if args.load else None
    if loaded is not None:
        seeds = [loaded.seed]
    all_rows: list[dict] = []
    for seed in seeds:
        metrics = Metrics()
        started = time.time()
        first_turn = loaded.turn if loaded is not None else 0
        game = run_game(rules, seed, args.turns, metrics, args.every, game=loaded,
                        map_settings=map_settings)
        elapsed = time.time() - started
        print(report(game))
        print(f"  {elapsed:.1f}s, {1000 * elapsed / max(1, game.turn - first_turn):.0f} ms/turn")
        if args.save:
            persistence.save_game(game, args.save)
            print(f"  saved to {args.save}")
        if args.events:
            counts = Counter(metrics.event_counts)
            print("  events: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        problems = metrics.problems(game)
        for problem in problems:
            print(f"  ! {problem}")
        all_rows.extend(metrics.rows)
    if args.csv and all_rows:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"metrics written to {args.csv}")


if __name__ == "__main__":
    main()
