"""The space race: building a spaceship, launching it, reaching Alpha Centauri.

The original spaceship code (OpenCivOne Overlay_18) is not readable, so this is a simplified
model with the same ingredients: three kinds of parts, a flight time that depends on what
was built, and a ship that is lost if its owner loses the capital. Figures: game.yaml.
"""
from __future__ import annotations

import math
from typing import Optional

from ..model.entities import Player
from ..model.game import Game
from ..rules.schema import SPACESHIP_PARTS
from . import calendar


def parts(player: Player, part: str) -> int:
    return player.spaceship.parts.get(part, 0)


def can_add_part(game: Game, player: Player, part: str) -> bool:
    ship = player.spaceship
    return not ship.launched and parts(player, part) < game.rules.game.spaceship.max_parts[part]


def add_part(game: Game, player: Player, part: str) -> None:
    player.spaceship.parts[part] = parts(player, part) + 1


def can_launch(game: Game, player: Player) -> bool:
    settings = game.rules.game.spaceship
    if player.spaceship.launched or player.capital_id is None:
        return False
    return all(parts(player, part) >= settings.min_parts[part] for part in SPACESHIP_PARTS)


def flight_years(game: Game, player: Player, built: Optional[dict[str, int]] = None) -> int:
    """Flight time: more engines make the ship faster, more mass makes it slower. `built`
    (part kind -> number) stands for the ship's own parts when given."""
    settings = game.rules.game.spaceship
    if built is None:
        built = player.spaceship.parts
    extra = {part: max(0, built.get(part, 0) - settings.min_parts[part])
             for part in SPACESHIP_PARTS}
    years = settings.flight_years - settings.years_per_component * extra["component"] \
        + settings.years_per_mass * (extra["structural"] + extra["module"])
    return max(settings.min_flight_years, math.ceil(years))


def landing(game: Game, years: int, launch_turn: int) -> tuple[int, int]:
    """Turn and year at which a ship leaving on `launch_turn` (now or later) lands after
    `years` of flight."""
    rules = game.rules
    launch_year = calendar.year_after(rules, game.year, launch_turn - game.turn)
    flight = calendar.turns_until(rules, launch_year, launch_year + years)
    return launch_turn + flight, calendar.year_after(rules, launch_year, flight)


def earliest_landing(game: Game) -> tuple[int, int]:
    """Turn and year at which the fastest ship there can be would land, leaving now: a ship
    in flight that lands before that cannot be caught any more."""
    return landing(game, game.rules.game.spaceship.min_flight_years, game.turn)


def projection(game: Game, player: Player,
               coming: list[tuple[str, Optional[int]]]) -> Optional[dict[str, int]]:
    """When the ship could leave and land: now if it can be launched, otherwise once the parts
    it lacks are done, among those in production (`coming`: part kind, turns left or None if
    it never gets done). The parts done by then fly too. None once it has left, without a
    capital, or when parts are missing that nobody builds."""
    settings = game.rules.game.spaceship
    if player.spaceship.launched or player.capital_id is None:
        return None
    built = {part: parts(player, part) for part in SPACESHIP_PARTS}
    done = sorted((turns, part) for part, turns in coming if turns is not None)
    wait = 0
    for part in SPACESHIP_PARTS:
        missing = settings.min_parts[part] - built[part]
        if missing <= 0:
            continue
        soonest = [turns for turns, kind in done if kind == part][:missing]
        if len(soonest) < missing:
            return None
        wait = max(wait, soonest[-1])
    if wait:
        for turns, part in done:
            if turns <= wait:
                built[part] = min(settings.max_parts[part], built[part] + 1)
    years = flight_years(game, player, built)
    arrival_turn, arrival_year = landing(game, years, game.turn + wait)
    return {"launch_turn": game.turn + wait,
            "launch_year": calendar.year_after(game.rules, game.year, wait),
            "arrival_turn": arrival_turn, "arrival_year": arrival_year, "flight_years": years}


def launch(game: Game, player: Player) -> bool:
    if not can_launch(game, player):
        return False
    ship = player.spaceship
    years = flight_years(game, player)
    ship.launched_turn = game.turn
    ship.arrival_turn = game.turn + calendar.turns_until(game.rules, game.year, game.year + years)
    game.emit("spaceship_launched",
              f"The {player.civ.nation} launch their spaceship: arrival in {years} years.",
              player=player.id, arrival_turn=ship.arrival_turn)
    return True


def lose(game: Game, player: Player) -> None:
    """The capital has fallen: the spaceship, on the ground or in flight, is lost."""
    ship = player.spaceship
    if not ship.launched and not any(ship.parts.values()):
        return
    ship.parts = {}
    ship.launched_turn = None
    ship.arrival_turn = None
    game.emit("spaceship_lost", f"The spaceship of the {player.civ.nation} is lost with "
              f"their capital.", player=player.id)


def arrived(game: Game) -> list[Player]:
    """Civilizations whose spaceship has reached Alpha Centauri, first to arrive first."""
    landed = [p for p in game.civilizations
              if p.spaceship.arrival_turn is not None and p.spaceship.arrival_turn <= game.turn]
    return sorted(landed, key=lambda p: (p.spaceship.arrival_turn, p.spaceship.launched_turn, p.id))
