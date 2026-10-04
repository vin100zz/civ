"""War and peace between civilizations.

Two civilizations that have met are at war until they sign a peace treaty, as in Civ 1.
A treaty forbids attacks and entering the other's cities. Governments with a senate cannot
declare war and always accept peace.
"""
from __future__ import annotations

from typing import Callable, Optional

from .. import effects as fx
from ..model.entities import NO_CONTACT, PEACE, WAR
from ..model.game import Game


def can_declare_war(game: Game, a: int, b: int) -> bool:
    if a == b or game.players[b].is_barbarian or not game.players[b].alive:
        return False
    if game.relation(a, b).state != PEACE:
        return False
    return not game.government(game.players[a]).senate


def declare_war(game: Game, a: int, b: int) -> bool:
    if not can_declare_war(game, a, b):
        return False
    relation = game.relation(a, b)
    relation.state = WAR
    relation.since_turn = game.turn
    relation.pending_from = None
    game.emit("war", f"The {game.players[a].civ.nation} declare war on the "
              f"{game.players[b].civ.nation}.", player=a, other=b)
    return True


def must_accept_peace(game: Game, proposer: int, target: int) -> bool:
    """The target has no choice: its senate, or the proposer's United Nations."""
    if game.government(game.players[target]).senate:
        return True
    return fx.has_player_effect(game, game.players[proposer], "peace_keeper")


def propose_peace(game: Game, proposer: int, target: int,
                  accepts: Callable[[], Optional[bool]]) -> bool:
    """Offers a treaty; `accepts` is asked only if the target is free to refuse.

    An answer of None means the target will answer during its own turn (a person leads it):
    the proposal stays on the table until then, see `answer_peace`.
    """
    if proposer == target or game.players[target].is_barbarian or not game.players[target].alive:
        return False
    relation = game.relation(proposer, target)
    if relation.state != WAR:
        return False
    relation.last_proposal_turn = game.turn
    if not must_accept_peace(game, proposer, target):
        answer = accepts()
        if answer is None:
            relation.pending_from = proposer
        if not answer:
            return False
    _sign(game, proposer, target)
    return True


def _sign(game: Game, proposer: int, target: int) -> None:
    relation = game.relation(proposer, target)
    relation.state = PEACE
    relation.since_turn = game.turn
    relation.pending_from = None
    game.emit("peace", f"The {game.players[proposer].civ.nation} and the "
              f"{game.players[target].civ.nation} sign a peace treaty.",
              player=proposer, other=target)


def pending_proposals(game: Game, player_id: int) -> list[int]:
    """Civilizations waiting for this player's answer to their peace proposal."""
    return [other.id for other in game.civilizations
            if other.id != player_id and game.relation(player_id, other.id).pending_from == other.id]


def answer_peace(game: Game, player_id: int, proposer: int, accept: bool) -> bool:
    """The player answers a proposal left on the table. False if there is none."""
    if proposer not in pending_proposals(game, player_id):
        return False
    relation = game.relation(player_id, proposer)
    relation.pending_from = None
    if accept and relation.state == WAR:
        _sign(game, proposer, player_id)
    return True


def expire_proposals(game: Game, player_id: int) -> None:
    """A proposal left unanswered at the end of the player's turn is refused."""
    for proposer in pending_proposals(game, player_id):
        game.relation(player_id, proposer).pending_from = None


def contacts(game: Game, player_id: int) -> list[int]:
    return [p.id for p in game.civilizations
            if p.id != player_id and game.relation(player_id, p.id).state != NO_CONTACT]
