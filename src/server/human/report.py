"""What needs the person's attention: enemies near its cities, cities in trouble.

Built from the player's view at the start of its turn and after each of its actions.
"""
from __future__ import annotations

from ..engine.view import PlayerView

THREAT_RADIUS = 2


def alerts(view: PlayerView) -> list[dict]:
    result: list[dict] = []
    world = view.map
    enemies = [u for u in view.visible_enemy_units() if view.rules.units[u.type].attack > 0]
    for city in view.my_cities():
        near = [u for u in enemies if world.steps(city.x, city.y, u.x, u.y) <= THREAT_RADIUS]
        if near:
            closest = min(near, key=lambda u: (world.steps(city.x, city.y, u.x, u.y), u.id))
            distance = world.steps(city.x, city.y, closest.x, closest.y)
            owners = {u.owner for u in near}
            kinds = {u.type for u in near}
            who = view.civ_name(closest.owner) if len(owners) == 1 else "Enemy"
            what = view.rules.units[closest.type].name if len(kinds) == 1 else "units"
            count = f"{len(near)} " if len(near) > 1 or len(kinds) > 1 else ""
            place = "next to" if distance <= 1 else "near"
            result.append({"kind": "threat", "city": city.id, "x": closest.x, "y": closest.y,
                           "text": f"{count}{who} {what} {place} {city.name}"})
        if city.disorder:
            result.append({"kind": "disorder", "city": city.id, "x": city.x, "y": city.y,
                           "text": f"Civil disorder in {city.name}"})
        elif city.stats.food_surplus < 0:
            result.append({"kind": "famine", "city": city.id, "x": city.x, "y": city.y,
                           "text": f"{city.name} is starving"})
    return result
