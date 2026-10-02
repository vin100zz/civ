"""Governments, revolutions and tax rates."""
from __future__ import annotations

from .. import effects as fx
from ..model.entities import Player
from ..model.game import Game

ANARCHY = "anarchy"


def available_governments(game: Game, player: Player) -> list[str]:
    """Governments the player may adopt (anarchy is never chosen, it is suffered)."""
    free = fx.has_player_effect(game, player, "free_government")
    result = []
    for government in game.rules.governments.values():
        if government.id == ANARCHY:
            continue
        if free or government.requires is None or government.requires in player.techs:
            result.append(government.id)
    return result


def start_revolution(game: Game, player: Player, target: str) -> bool:
    """Overthrows the government. The new one starts after a period of anarchy."""
    if target == player.government or target not in available_governments(game, player):
        return False
    if player.government == ANARCHY and player.pending_government is not None:
        player.pending_government = target
        return True
    if fx.has_player_effect(game, player, "free_government"):
        _install(game, player, target)
        return True
    multiple = game.rules.game.government.anarchy_turn_multiple
    player.government = ANARCHY
    player.pending_government = target
    player.anarchy_until_turn = (game.turn // multiple + 1) * multiple
    clamp_rates(game, player)
    game.emit("government", f"Revolution among the {player.civ.nation}: anarchy.",
              player=player.id, government=ANARCHY)
    return True


def collapse(game: Game, player: Player) -> None:
    """The government falls (civil disorder under Democracy)."""
    if player.government == ANARCHY:
        return
    previous = player.government
    multiple = game.rules.game.government.anarchy_turn_multiple
    player.government = ANARCHY
    player.pending_government = previous
    player.anarchy_until_turn = (game.turn // multiple + 1) * multiple
    clamp_rates(game, player)
    game.emit("government", f"The {player.civ.name} government collapses into anarchy.",
              player=player.id, government=ANARCHY)


def tick(game: Game, player: Player) -> None:
    """Start of turn: ends the anarchy when its time is over."""
    if player.government != ANARCHY or player.anarchy_until_turn is None:
        return
    if game.turn < player.anarchy_until_turn:
        return
    target = player.pending_government
    if target is None or target not in available_governments(game, player):
        target = game.rules.game.players.start_government
    _install(game, player, target)


def _install(game: Game, player: Player, target: str) -> None:
    player.government = target
    player.pending_government = None
    player.anarchy_until_turn = None
    clamp_rates(game, player)
    name = game.rules.governments[target].name
    game.emit("government", f"The {player.civ.nation} adopt {name}.",
              player=player.id, government=target)


def valid_rates(game: Game, player: Player, tax: int, luxury: int, science: int) -> bool:
    limit = game.government(player).max_rate
    rates = (tax, luxury, science)
    return (sum(rates) == 100 and all(r >= 0 and r % 10 == 0 for r in rates)
            and all(r <= limit for r in rates))


def set_rates(game: Game, player: Player, tax: int, luxury: int, science: int) -> bool:
    if not valid_rates(game, player, tax, luxury, science):
        return False
    player.tax_rate, player.luxury_rate, player.science_rate = tax, luxury, science
    return True


def clamp_rates(game: Game, player: Player) -> None:
    """Brings the rates back under the maximum allowed by the government."""
    limit = game.government(player).max_rate
    rates = {"tax": player.tax_rate, "science": player.science_rate, "luxury": player.luxury_rate}
    overflow = 0
    for name in rates:
        if rates[name] > limit:
            overflow += rates[name] - limit
            rates[name] = limit
    for name in ("science", "tax", "luxury"):
        room = limit - rates[name]
        moved = min(room, overflow)
        rates[name] += moved
        overflow -= moved
    player.tax_rate, player.science_rate, player.luxury_rate = (
        rates["tax"], rates["science"], rates["luxury"])
