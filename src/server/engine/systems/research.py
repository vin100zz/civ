"""Science: which advances can be researched, what they cost, what happens on discovery.

Source: OpenCivOne CityWorker.cs (research progress, around L635d) and Segment_1238.cs
(the doubling of costs from 1 AD).
"""
from __future__ import annotations

from typing import Optional

from .. import effects as fx
from ..model.entities import Player
from ..model.game import Game
from ..rules.schema import Rules


def can_research(rules: Rules, player: Player, tech_id: str) -> bool:
    tech = rules.techs[tech_id]
    if tech_id in player.techs and not tech.repeatable:
        return False
    return all(pre in player.techs for pre in tech.prerequisites)


def research_options(game: Game, player: Player) -> list[str]:
    return [tech_id for tech_id in game.rules.techs if can_research(game.rules, player, tech_id)]


def research_cost(game: Game, player: Player) -> int:
    """Science needed for the next advance: grows with the number of advances known."""
    settings = game.rules.game.research
    known = player.tech_count + 1
    factor = max(settings.cost_factor, settings.early_factor_base - known)
    cost = known * factor
    if game.year >= settings.doubled_from_year:
        cost *= 2
    return cost


def add_science(game: Game, player: Player, amount: int) -> None:
    player.research_progress += amount


def check_discovery(game: Game, player: Player) -> Optional[str]:
    """Completes the current research if enough science has been gathered."""
    if player.researching is None:
        return None
    if not can_research(game.rules, player, player.researching):
        player.researching = None
        return None
    if player.research_progress <= research_cost(game, player):
        return None
    tech_id = player.researching
    player.research_progress = 0
    player.researching = None
    give_tech(game, player, tech_id, "discover")
    return tech_id


def give_tech(game: Game, player: Player, tech_id: str, how: str = "discover") -> None:
    """Adds an advance to a player, whatever the way it was obtained."""
    tech = game.rules.techs[tech_id]
    if tech.repeatable and tech_id in player.techs:
        player.future_techs += 1
    else:
        player.techs.add(tech_id)
    if player.researching == tech_id and not tech.repeatable:
        player.researching = None
    verbs = {"discover": "discover", "steal": "steal", "hut": "learn from ancient scrolls",
             "wonder": "acquire", "library": "learn from other civilizations"}
    game.emit("tech", f"The {player.civ.nation} {verbs.get(how, 'acquire')} {tech.name}.",
              player=player.id, tech=tech_id, how=how)


def give_free_tech(game: Game, player: Player, how: str) -> Optional[str]:
    """Gives the advance being researched, or any available one."""
    options = research_options(game, player)
    if not options:
        return None
    tech_id = player.researching if player.researching in options else game.rng.choice(sorted(options))
    give_tech(game, player, tech_id, how)
    return tech_id


def share_knowledge(game: Game, player: Player) -> None:
    """Great Library: advances known by enough other civilizations are received for free."""
    shared = fx.player_effects(game, player, "shared_knowledge")
    if not shared:
        return
    min_civs = min(e.min_civs for e in shared)
    others = [p for p in game.civilizations if p.id != player.id]
    for tech_id in sorted(game.rules.techs):
        if tech_id in player.techs:
            continue
        if sum(1 for p in others if tech_id in p.techs) >= min_civs:
            give_tech(game, player, tech_id, "library")


def steal_tech(game: Game, thief: Player, victim: Player) -> Optional[str]:
    """One advance the victim knows and the thief does not (city capture)."""
    candidates = sorted(victim.techs - thief.techs)
    if not candidates:
        return None
    tech_id = game.rng.choice(candidates)
    give_tech(game, thief, tech_id, "steal")
    return tech_id


def on_calendar_change(game: Game, old_year: int) -> None:
    """Costs double from 1 AD: progress doubles too so nobody loses work in progress."""
    threshold = game.rules.game.research.doubled_from_year
    if old_year < threshold <= game.year:
        for player in game.players:
            player.research_progress *= 2
