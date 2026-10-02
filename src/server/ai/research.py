"""Choice of the next advance to research.

An advance is worth what it unlocks (better units, buildings, wonders, governments, terrain
work) plus a share of the worth of the advances it leads to. The personality bends the
values: civilized leaders favour science and economy, militaristic ones weapons.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..engine.view import PlayerView


@dataclass
class ResearchChoice:
    tech_id: str
    score: float
    ranking: list[tuple[str, float]]


def choose(view: PlayerView) -> Optional[ResearchChoice]:
    options = view.research_options()
    if not options:
        return None
    rules = view.rules
    get = lambda name: rules.ai.get("research", name)
    personality = view.player.civ.personality
    bend = lambda name: rules.ai.get("personality", name)
    military = 1 + personality.mood * bend("aggressive_attack") \
        - personality.ideology * bend("militarist_attack")
    civil = 1 + personality.ideology * bend("civilized_science") \
        - personality.policy * bend("perfectionist_buildings")
    known = view.player.techs
    enabled_domains = rules.game.enabled_unit_domains

    best_attack = max((u.attack for u in rules.units.values()
                       if u.domain == "land" and (u.requires is None or u.requires in known)),
                      default=0)
    best_defense = max((u.defense for u in rules.units.values()
                        if u.domain == "land" and u.role == "defense"
                        and (u.requires is None or u.requires in known)), default=0)

    best_capacity = max((u.capacity for u in rules.units.values()
                         if u.carries == "land" and (u.requires is None or u.requires in known)),
                        default=0)

    children: dict[str, list[str]] = {t: [] for t in rules.techs}
    for tech in rules.techs.values():
        for pre in tech.prerequisites:
            children[pre].append(tech.id)

    own_wonders = [w for w in rules.wonders if view.has_wonder(w.id)]

    def direct_value(tech_id: str) -> float:
        value = 0.0
        for unit in rules.units.values():
            if unit.requires != tech_id or not unit.enabled or unit.domain not in enabled_domains:
                continue
            if unit.attack > best_attack:
                value += get("unit_attack") * (unit.attack - best_attack) * military
            if unit.role == "defense" and unit.defense > best_defense:
                value += get("unit_defense") * (unit.defense - best_defense)
            if unit.moves > 1:
                value += get("unit_moves") * military
            if unit.can("trade"):
                value += get("building_economy") * civil
            if unit.carries == "land" and unit.capacity > best_capacity:
                value += get("transport")
        for building in rules.buildings.values():
            if building.requires != tech_id or not building.enabled:
                continue
            if building.wonder:
                if not view.wonder_built(building.id):
                    value += get("wonder") * civil
                continue
            value += get("building")
            for effect in building.effects:
                if effect.type == "yield_bonus" and effect.yield_kind == "science":
                    value += get("building_science") * civil
                elif effect.type == "yield_bonus" and effect.yield_kind == "shields":
                    value += get("building_shields")
                elif effect.type == "yield_bonus":
                    value += get("building_economy") * civil
                elif effect.type == "content":
                    value += get("building_happiness")
        for government in rules.governments.values():
            if government.requires == tech_id:
                value += get("government") * (1 + rules.ai.government_preference.get(government.id, 0) / 50)
        movement = rules.game.movement
        if tech_id in movement.road_requires_tech_on.values() or tech_id == movement.railroad_tech:
            value += get("terraform")
        for effect_owner in rules.buildings.values():
            for effect in effect_owner.effects:
                if effect.requires_tech == tech_id and effect_owner.id in _owned(view, effect_owner.id):
                    value += get("building_happiness")
        for wonder in own_wonders:
            if wonder.obsolete_by == tech_id:
                value -= get("obsoletes_wonder_penalty")
        return value

    cache: dict[str, float] = {}

    def value(tech_id: str, depth: int) -> float:
        key = f"{tech_id}:{depth}"
        if key in cache:
            return cache[key]
        total = direct_value(tech_id)
        if depth > 0:
            future = [value(child, depth - 1) for child in children[tech_id] if child not in known]
            if future:
                total += get("lookahead") * max(future)
        cache[key] = total
        return total

    depth = int(get("lookahead_depth"))
    ranking = []
    for tech_id in sorted(options):
        if rules.techs[tech_id].repeatable and len(options) > 1:
            continue
        score = value(tech_id, depth) + view.rng.random() * get("random")
        ranking.append((tech_id, round(score, 1)))
    ranking.sort(key=lambda r: (-r[1], r[0]))
    if not ranking:
        ranking = [(options[0], 0.0)]
    return ResearchChoice(ranking[0][0], ranking[0][1], ranking[:5])


def _owned(view: PlayerView, building_id: str) -> set[str]:
    """Buildings of that kind present in at least one of our cities."""
    return {building_id} if any(building_id in c.buildings for c in view.my_cities()) else set()
