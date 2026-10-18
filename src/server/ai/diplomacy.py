"""War and peace decisions.

The AI judges other civilizations from what it knows: the cities it has seen and the units
in sight. Aggressive leaders make peace reluctantly and break it readily. A civilization
that broke its treaties is trusted less for a while, and one much stronger than all the
others finds them closing ranks against it.

A war is prepared before it is declared: the AI picks a weaker neighbour, builds up its
attack force and gathers it on the border (strategic.py), then strikes. It does not sign
peace while the war it started is young or goes its way, in cities taken and lost.
"""
from __future__ import annotations

import math
from typing import Optional

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


def attack_force_wanted(view: PlayerView, know: Knowledge, war: bool) -> int:
    """Attack units the empire keeps: so many per city, more in war time or while preparing
    a war, bent by the personality."""
    rules = view.rules
    personality = view.player.civ.personality
    bend = lambda name: rules.ai.get("personality", name)
    per_city = rules.ai.get("strategy", "attackers_per_city" if war else "attackers_peace")
    per_city *= 1.0 + personality.mood * bend("aggressive_attack") \
        - personality.ideology * bend("militarist_attack")
    return math.ceil(len(know.cities) * max(0.0, per_city))


def attack_force(view: PlayerView, know: Knowledge) -> int:
    """Attack units on land, ready to march."""
    return sum(1 for u in know.units_with_role("attack")
               if u.aboard is None and view.rules.units[u.type].domain == "land")


def reachable(view: PlayerView, know: Knowledge, other: int) -> bool:
    """A civilization with a city we know on land where we have cities: we can march on it."""
    for memory in know.foreign_cities:
        if memory.owner != other:
            continue
        region = know.region_at(memory.x, memory.y)
        if region is not None and region.my_cities:
            return True
    return False


def momentum(view: PlayerView, memory: Optional[dict], other: int) -> int:
    """How the war with a civilization goes: the cities we took from it lately, less those it
    took from us (AIController._note_conquests and _note_losses)."""
    if not memory:
        return 0
    window = view.rules.ai.get("diplomacy", "momentum_memory")
    gained = sum(1 for _, turn, owner in memory.get("conquests", [])
                 if owner == other and view.turn - turn <= window)
    owners = {m.city_id: m.owner for m in view.known_foreign_cities()}
    lost = sum(1 for city_id, turn in memory.get("lost_cities", [])
               if owners.get(city_id) == other and view.turn - turn <= window)
    return gained - lost


def pursues_war(view: PlayerView, other: int, memory: Optional[dict] = None) -> bool:
    """A war we declared ourselves is fought for a while, unless it turns against us."""
    relation = view.relation(other)
    if view.turn - relation.since_turn >= view.rules.ai.get("diplomacy", "war_min_turns"):
        return False
    declared = any(victim == other and turn == relation.since_turn
                   for victim, turn, _ in view.player.broken_treaties)
    return declared and momentum(view, memory, other) >= 0


def distrust(view: PlayerView, other: int) -> float:
    """How little we trust a civilization, from the treaties it broke that we heard of:
    1 for each one broken with us, less for one broken with another civilization, double
    when the treaty was hardly signed. A broken treaty fades out over `distrust_memory`."""
    get = lambda name: view.rules.ai.get("diplomacy", name)
    memory = get("distrust_memory")
    total = 0.0
    for victim, turn, age in view.treaties_broken_by(other):
        fade = 1.0 - (view.turn - turn) / memory
        if fade <= 0:
            continue
        weight = 1.0 if victim == view.player.id else get("distrust_rumour")
        if age < get("distrust_perfidy_turns"):
            weight *= 2.0
        total += weight * fade
    return total


def dominant(view: PlayerView, know: Knowledge) -> Optional[int]:
    """A civilization we have met that is far stronger than any other, ourselves included."""
    powers = {p.id: their_power(view, p.id) for p in view.contacts()}
    if not powers:
        return None
    leader = max(powers, key=lambda pid: (powers[pid], -pid))
    rivals = [power for pid, power in powers.items() if pid != leader]
    runner_up = max([my_power(view, know), *rivals])
    if powers[leader] >= view.rules.ai.get("diplomacy", "dominance_ratio") * max(1.0, runner_up):
        return leader
    return None


def peace_willingness(view: PlayerView, know: Knowledge, other: int,
                      leader: Optional[int] = None, memory: Optional[dict] = None) -> float:
    """0..1: how much we want a treaty with this civilization. `leader`: the dominant
    civilization, if any (see `dominant`); `memory`: the controller's, which knows the
    cities taken and lost."""
    get = lambda name: view.rules.ai.get("diplomacy", name)
    mood = view.player.civ.personality.mood
    relation = view.relation(other)
    if pursues_war(view, other, memory):
        return 0.0
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
    value -= distrust(view, other) * get("distrust_peace")
    value -= momentum(view, memory, other) * get("peace_momentum")
    if leader == other:
        value -= get("coalition_peace")
    elif leader is not None and leader in view.wars_of(other):
        value += get("coalition_peace")          # a common enemy
    return max(0.0, min(1.0, value))


def accepts_peace(view: PlayerView, know: Knowledge, proposer: int,
                  memory: Optional[dict] = None) -> bool:
    willingness = peace_willingness(view, know, proposer, dominant(view, know), memory)
    return view.rng.random() < willingness


def review(view: PlayerView, know: Knowledge, memory: dict) -> list[str]:
    """Proposes treaties, prepares and declares wars. Returns notes for the observer."""
    get = lambda name: view.rules.ai.get("diplomacy", name)
    notes: list[str] = []
    contacts = view.contacts()
    leader = dominant(view, know)
    if leader is not None:
        notes.append(f"{view.player_name(leader)} dominate")

    for other in contacts:
        relation = view.relation(other.id)
        if view.at_war(other.id):
            if view.turn - relation.last_proposal_turn < get("peace_min_turns"):
                continue
            willingness = peace_willingness(view, know, other.id, leader, memory)
            if view.rng.random() < willingness:
                if view.do(actions.ProposePeace(other.id)):
                    notes.append(f"peace with {view.player_name(other.id)}")
                else:
                    notes.append(f"{view.player_name(other.id)} refuse peace")
        elif "war_plan" not in memory:
            chance = war_chance(view, know, other.id, leader)
            if chance is not None and view.rng.random() < chance:
                memory["war_plan"] = [other.id, view.turn]
    _follow_war_plan(view, know, memory, leader, notes)
    return notes


def war_chance(view: PlayerView, know: Knowledge, other: int,
               leader: Optional[int] = None) -> Optional[float]:
    """The chance per turn that we set out to war on a civilization we are at peace with, or
    None if a war on it is out of the question: we already fight enough neighbours, the
    treaty is recent, our senate forbids it, we cannot march on it, it is too strong."""
    get = lambda name: view.rules.ai.get("diplomacy", name)
    if not view.at_peace(other) or not view.can_declare_war(other):
        return None
    if view.turn - view.relation(other).since_turn < get("war_min_peace_turns"):
        return None
    fronts = [p.id for p in view.contacts() if view.at_war(p.id) and reachable(view, know, p.id)]
    if len(fronts) >= get("war_max_enemies"):
        return None
    if not reachable(view, know, other):
        return None
    mine, theirs = my_power(view, know), their_power(view, other)
    chance = get("war_base") + view.player.civ.personality.mood * get("war_aggressive") \
        + distrust(view, other) * get("distrust_war")
    # A war makes the citizens of a Republic or a Democracy unhappy.
    chance -= get("war_weariness") * view.rules.governments[view.player.government].military_unhappiness
    if other == leader:
        # Against the dominant civilization, its other enemies count on our side.
        allies = sum(their_power(view, e) for e in view.wars_of(other))
        if mine + allies < theirs * get("coalition_strength_ratio"):
            return None
        chance += get("coalition_war")
    elif mine < theirs * get("war_strength_ratio"):
        return None
    # No land left to settle: the empire grows by the sword or not at all.
    if not any(region.sites for region in know.regions.values() if region.my_cities):
        chance += get("war_land_hunger")
    return chance


def _follow_war_plan(view: PlayerView, know: Knowledge, memory: dict,
                     leader: Optional[int], notes: list[str]) -> None:
    """The war being prepared (memory["war_plan"] = [civilization, turn chosen]) is declared
    once the attack force is ready, given up if it no longer makes sense or the force cannot
    be raised in time."""
    if "war_plan" not in memory:
        return
    get = lambda name: view.rules.ai.get("diplomacy", name)
    target, since = memory["war_plan"]
    name = view.player_name(target)
    if war_chance(view, know, target, leader) is None:
        del memory["war_plan"]
        notes.append(f"war on {name} called off")
        return
    have = attack_force(view, know)
    minimum = int(view.rules.ai.get("strategy", "siege_group_size"))
    wanted = max(minimum, math.ceil(attack_force_wanted(view, know, True) * get("war_ready_share")))
    late = view.turn - since >= get("war_prepare_turns")
    if have >= wanted or (late and have >= minimum):
        del memory["war_plan"]
        if view.do(actions.DeclareWar(target)):
            notes.append(f"war on {name}")
    elif late:
        del memory["war_plan"]
        notes.append(f"war on {name} called off: no army")
    else:
        notes.append(f"preparing war on {name}: {have}/{wanted} attackers")
