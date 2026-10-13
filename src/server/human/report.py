"""What needs the person's attention: a treasury about to run dry, enemies near its cities,
cities in trouble.

Built from the player's view at the start of its turn and after each of its actions.
"""
from __future__ import annotations

from typing import Optional

from ..engine.view import PlayerView

THREAT_RADIUS = 2
TREASURY_WARNING_TURNS = 5      # the treasury is watched when it runs dry within this many turns


def alerts(view: PlayerView) -> list[dict]:
    result: list[dict] = []
    treasury = treasury_alert(view)
    if treasury is not None:
        result.append(treasury)
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


def treasury_alert(view: PlayerView) -> Optional[dict]:
    """The treasury runs dry within a few turns and a building would then be sold: which
    one, and when ("bad" next turn, "warn" later)."""
    player = view.player
    if not view.rules.governments[player.government].collects_taxes:
        return None                         # no upkeep is paid in anarchy
    gold, _, _ = view.budget_with_rates(player.tax_rate, player.luxury_rate, player.science_rate)
    if gold >= 0:
        return None
    turns = player.gold // -gold + 1        # the first turn the treasury falls below zero
    if turns > TREASURY_WARNING_TURNS:
        return None
    sale = view.building_to_sell()
    if sale is None:
        return None                         # nothing left to sell, nothing to lose
    city, building_id = sale
    when = "next turn" if turns == 1 else f"in {turns} turns"
    return {"kind": "treasury", "level": "bad" if turns == 1 else "warn", "turns": turns,
            "gold": gold, "city": city.id, "x": city.x, "y": city.y,
            "building": building_id,
            "text": f"Treasury empty {when}",
            "detail": f"{city.name} would sell its {view.rules.buildings[building_id].name}"}


def balancing_rates(view: PlayerView) -> Optional[dict]:
    """Rates that stop the treasury losing gold, as close to the present ones as can be:
    taxes go up, science gives way first, then luxuries as long as no city riots for it.
    {"rates": [tax, luxury, science], "gold": per turn}, the best the government allows if
    nothing balances the budget; None when it is balanced already or nothing would help."""
    player = view.player
    if not view.rules.governments[player.government].collects_taxes:
        return None
    tax, luxury, science = player.tax_rate, player.luxury_rate, player.science_rate
    gold, _, disorder = view.budget_with_rates(tax, luxury, science)
    if gold >= 0:
        return None
    best = None
    while science > 0 or luxury > 0:
        if science > 0:
            science -= 10
        else:
            luxury -= 10
        tax += 10
        if not view.valid_rates(tax, luxury, science):
            break
        net, _, riots = view.budget_with_rates(tax, luxury, science)
        if riots > disorder:
            break
        if best is None or net > best["gold"]:
            best = {"rates": [tax, luxury, science], "gold": net}
        if net >= 0:
            break
    if best is None or best["gold"] <= gold:
        return None
    return best
