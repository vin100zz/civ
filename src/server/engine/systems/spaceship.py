"""The space race: building a spaceship, launching it, reaching Alpha Centauri.

The original spaceship code (OpenCivOne Overlay_18) is not readable, so this is a simplified
model with the same ingredients: three kinds of parts, a flight time that depends on what
was built, and a ship that is lost if its owner loses the capital. Figures: game.yaml.
"""
from __future__ import annotations

import math

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


def flight_years(game: Game, player: Player) -> int:
    """Flight time: more engines make the ship faster, more mass makes it slower."""
    settings = game.rules.game.spaceship
    extra = {part: max(0, parts(player, part) - settings.min_parts[part])
             for part in SPACESHIP_PARTS}
    years = settings.flight_years - settings.years_per_component * extra["component"] \
        + settings.years_per_mass * (extra["structural"] + extra["module"])
    return max(settings.min_flight_years, math.ceil(years))


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
