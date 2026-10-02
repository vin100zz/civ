"""War and peace decisions.

The AI judges other civilizations from what it knows: the cities it has seen and the units
in sight. Aggressive leaders make peace reluctantly and break it readily.
"""
from __future__ import annotations

from ..engine import actions
from ..engine.view import PlayerView
from .knowledge import Knowledge


def their_power(view: PlayerView, other: int) -> float:
    visible = sum(1 for u in view.visible_foreign_units()
                  if u.owner == other and view.rules.units[u.type].is_military)
    return view.known_strength(other) + visible


def my_power(view: PlayerView, know: Knowledge) -> float:
    military = sum(1 for u in know.units if view.rules.units[u.type].is_military)
    return know.own_power() + military * 0.5


def peace_willingness(view: PlayerView, know: Knowledge, other: int) -> float:
    """0..1: how much we want a treaty with this civilization."""
    get = lambda name: view.rules.ai.get("diplomacy", name)
    mood = view.player.civ.personality.mood
    relation = view.relation(other)
    value = get("peace_base") + mood * get("peace_aggressive")
    mine, theirs = my_power(view, know), their_power(view, other)
    if theirs > mine * get("weaker_ratio"):
        value += get("peace_when_weaker")
    elif mine > theirs * get("stronger_ratio") and theirs > 0:
        value += get("peace_when_stronger")
    value += (view.turn - relation.since_turn) * get("peace_war_weariness")
    # Nobody we can reach: war brings nothing.
    if not any(m.owner == other for m in know.foreign_cities):
        value += get("peace_unreachable")
    return max(0.0, min(1.0, value))


def accepts_peace(view: PlayerView, know: Knowledge, proposer: int) -> bool:
    return view.rng.random() < peace_willingness(view, know, proposer)


def review(view: PlayerView, know: Knowledge, memory: dict) -> list[str]:
    """Proposes treaties and declares wars. Returns notes for the observer."""
    get = lambda name: view.rules.ai.get("diplomacy", name)
    mood = view.player.civ.personality.mood
    notes: list[str] = []
    contacts = view.contacts()
    enemies = [p for p in contacts if view.at_war(p.id)]

    for other in contacts:
        relation = view.relation(other.id)
        if view.at_war(other.id):
            if view.turn - relation.last_proposal_turn < get("peace_min_turns"):
                continue
            willingness = peace_willingness(view, know, other.id)
            if view.rng.random() < willingness:
                if view.do(actions.ProposePeace(other.id)):
                    notes.append(f"peace with {view.player_name(other.id)}")
                else:
                    notes.append(f"{view.player_name(other.id)} refuse peace")
        elif view.at_peace(other.id):
            if len(enemies) >= get("war_max_enemies"):
                continue
            if view.turn - relation.since_turn < get("war_min_peace_turns"):
                continue
            if not view.can_declare_war(other.id):
                continue
            # Only neighbours we can reach by land are worth a war.
            reachable = any(m.owner == other.id and know.region_at(m.x, m.y) is not None
                            and know.region_at(m.x, m.y).my_cities for m in know.foreign_cities)
            if not reachable:
                continue
            mine, theirs = my_power(view, know), their_power(view, other.id)
            if mine < theirs * get("war_strength_ratio"):
                continue
            chance = get("war_base") + mood * get("war_aggressive")
            if view.rng.random() < chance:
                if view.do(actions.DeclareWar(other.id)):
                    notes.append(f"war on {view.player_name(other.id)}")
                    enemies.append(other)
    return notes
