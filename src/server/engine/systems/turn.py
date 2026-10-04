"""The turn sequence.

Each player in turn: its cities are processed, then its units move. When everybody has
played, the year advances. Source of the order: OpenCivOne Segment_1238.cs GameTurn.
"""
from __future__ import annotations

from typing import Callable, Optional, Protocol

from ..model.entities import Player
from ..model.game import Game
from . import barbarians, calendar, cities, diplomacy, government, movement, pollution
from . import research, spaceship, visibility


class Controller(Protocol):
    """Whoever decides for a player: an AI, or a person.

    An AI plays its whole turn in `play_turn`. A controller with `interactive = True` stands
    for a person: `advance` stops when its turn begins, calls `begin_turn` and waits for the
    person's actions (engine/actions.py).

    A controller that remembers things from turn to turn may also define `save_state()` and
    `load_state(state)` (plain JSON data) to be part of saved games.
    """

    def play_turn(self, game: Game, player: Player) -> None:
        """Called once per turn, after the player's cities have been processed."""

    def accepts_peace(self, game: Game, player: Player, proposer: int) -> Optional[bool]:
        """Answer to a peace proposal from another civilization; None to answer later,
        during the player's own turn."""


def begin_player_turn(game: Game, player: Player) -> None:
    game.current_player = player.id
    player.income = player.expenses = player.science_income = 0
    government.tick(game, player)
    visibility.refresh(game, player)
    if not player.is_barbarian:
        research.share_knowledge(game, player)
    for city in sorted(game.player_cities(player.id), key=lambda c: c.id):
        if city.id in game.cities and city.owner == player.id:
            cities.process_city(game, city)
    if not player.is_barbarian:
        research.check_discovery(game, player)
    movement.start_turn(game, player)


def end_player_turn(game: Game, player: Player) -> None:
    if player.alive:
        movement.end_turn(game, player)
    diplomacy.expire_proposals(game, player.id)
    game.current_player = None


def advance_calendar(game: Game) -> None:
    old_year = game.year
    game.year = calendar.next_year(game.rules, old_year)
    research.on_calendar_change(game, old_year)
    game.turn += 1


def update_scores(game: Game) -> None:
    """Citizens, wonders, advances and pollution, weighted by game.yaml (score)."""
    weights = game.rules.game.score
    for player in game.players:
        if player.is_barbarian:
            continue
        score = 0
        polluted: set[int] = set()
        for city in game.player_cities(player.id):
            score += city.stats.happy * weights.happy_citizen \
                + (city.size - city.stats.happy - city.stats.unhappy) * weights.content_citizen
            polluted.update(tile.index for _, tile in game.map.city_area(city.x, city.y)
                            if tile.pollution)
        score += weights.wonder * sum(
            1 for city_id in game.wonders.values()
            if city_id in game.cities and game.cities[city_id].owner == player.id)
        score += weights.advance * len(player.techs) + weights.future_tech * player.future_techs
        score += weights.polluted_tile * len(polluted)
        ship = player.spaceship
        if ship.arrival_turn is not None and ship.arrival_turn <= game.turn:
            score += weights.spaceship_arrival
        player.score = max(0, score)


def check_end(game: Game) -> None:
    """Conquest, a spaceship reaching Alpha Centauri, or the end of the calendar."""
    victory = game.rules.game.victory
    alive = game.civilizations
    landed = spaceship.arrived(game) if victory.spaceship else []
    if not alive:
        game.finished = True
    elif len(alive) == 1 and victory.conquest:
        game.finished, game.winner, game.victory = True, alive[0].id, "conquest"
    elif landed:
        game.finished, game.winner, game.victory = True, landed[0].id, "spaceship"
    elif game.turn >= game.rules.game.calendar.max_turns:
        best = max(alive, key=lambda p: (p.score, -p.id))
        game.finished, game.winner, game.victory = True, best.id, "score"
    if game.finished and game.winner is not None:
        winner = game.players[game.winner]
        how = {"conquest": "conquer the world",
               "spaceship": "reach Alpha Centauri",
               "score": "have the greatest civilization"}[game.victory]
        game.emit("game_over", f"The {winner.civ.nation} {how} and win the game.",
                  player=winner.id, victory=game.victory)


def play_turn(game: Game, after_player: Callable[[Player], None] | None = None) -> None:
    """Plays one full turn: every living player, then the calendar."""
    if game.finished:
        return
    for player in list(game.players):
        if not player.alive:
            continue
        begin_player_turn(game, player)
        controller = game.controllers.get(player.id)
        if controller is not None and player.alive:
            controller.play_turn(game, player)
        end_player_turn(game, player)
        if after_player is not None:
            after_player(player)
    end_round(game)


def end_round(game: Game) -> None:
    """Everybody has played: barbarians may appear, the planet warms, the year advances."""
    barbarians.maybe_spawn(game)
    pollution.global_warming(game)
    advance_calendar(game)
    update_scores(game)
    check_end(game)
    game.round_position = 0


# ── With a person at the table ────────────────────────────────────────────────

def is_interactive(game: Game, player: Player) -> bool:
    """True if a person gives this player's orders, during its turn."""
    return bool(getattr(game.controllers.get(player.id), "interactive", False))


def advance(game: Game) -> Optional[Player]:
    """Plays the game until a person has to give orders.

    Returns that player, whose turn has begun (cities processed, units ready): the caller
    applies the person's actions, then calls `advance` again, which ends that turn and goes
    on with the other players. The same sequence as `play_turn`, cut where a person plays.

    Returns None when the game is over, or at the end of a round once nobody plays in person
    any more (the last person's civilization was destroyed).
    """
    if game.current_player is not None:               # the person has finished
        end_player_turn(game, game.players[game.current_player])
    while not game.finished:
        player = _next_in_round(game)
        if player is None:
            end_round(game)
            if not any(is_interactive(game, p) for p in game.players if p.alive):
                return None
            continue
        begin_player_turn(game, player)
        controller = game.controllers.get(player.id)
        if player.alive and is_interactive(game, player):
            controller.begin_turn(game, player)
            return player
        if controller is not None and player.alive:
            controller.play_turn(game, player)
        end_player_turn(game, player)
    return None


def _next_in_round(game: Game) -> Optional[Player]:
    while game.round_position < len(game.players):
        player = game.players[game.round_position]
        game.round_position += 1
        if player.alive:
            return player
    return None
