"""The turn sequence.

Each player in turn: its cities are processed, then its units move. When everybody has
played, the year advances. Source of the order: OpenCivOne Segment_1238.cs GameTurn.
"""
from __future__ import annotations

from typing import Callable, Protocol

from ..model.entities import Player
from ..model.game import Game
from . import barbarians, calendar, cities, government, movement, pollution, research
from . import spaceship, visibility


class Controller(Protocol):
    """Whoever decides for a player (an AI today, a human later).

    A controller that remembers things from turn to turn may also define `save_state()` and
    `load_state(state)` (plain JSON data) to be part of saved games.
    """

    def play_turn(self, game: Game, player: Player) -> None:
        """Called once per turn, after the player's cities have been processed."""

    def accepts_peace(self, game: Game, player: Player, proposer: int) -> bool:
        """Answer to a peace proposal from another civilization."""


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
    barbarians.maybe_spawn(game)
    pollution.global_warming(game)
    advance_calendar(game)
    update_scores(game)
    check_end(game)
