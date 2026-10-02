"""Tax rates and form of government."""
from __future__ import annotations

from typing import Optional

from ..engine import actions
from ..engine.view import PlayerView
from .knowledge import Knowledge
from .strategic import Plan


def review_rates(view: PlayerView, know: Knowledge) -> Optional[tuple[int, int, int]]:
    """Picks the rates giving the most science while the treasury stays afloat.

    Luxuries are raised only when cities riot despite their entertainers.
    """
    if not know.cities:
        return None
    rules = view.rules
    get = lambda name: rules.ai.get("economy", name)
    player = view.player
    limit = rules.governments[player.government].max_rate
    reserve = get("gold_reserve")
    best = None
    for luxury in range(0, int(get("luxury_when_disorder")) + 1, 10):
        for tax in range(0, limit + 1, 10):
            science = 100 - luxury - tax
            if not view.valid_rates(tax, luxury, science):
                continue
            income, science_total, disorder = view.budget_with_rates(tax, luxury, science)
            # A rich treasury can run a deficit for a while.
            floor = get("min_income") if player.gold < reserve \
                else -player.gold * get("deficit_per_gold")
            affordable = income >= floor
            if affordable:
                value = (1, -disorder, science_total + 0.5 * income, -luxury)
            else:
                value = (0, income, -disorder, -luxury)      # as little deficit as possible
            if best is None or value > best[0]:
                best = (value, (tax, luxury, science))
    if best is None:
        return None
    rates = best[1]
    if rates != (player.tax_rate, player.luxury_rate, player.science_rate):
        view.do(actions.SetRates(*rates))
    return rates


def review_government(view: PlayerView, know: Knowledge, plan: Plan, memory: dict) -> Optional[str]:
    """Starts a revolution when a clearly better government is available."""
    rules = view.rules
    player = view.player
    if player.government == "anarchy" or not know.cities:
        return None
    get = lambda name: rules.ai.get("economy", name)
    if view.turn - memory.get("last_revolution", -1000) < get("revolution_cooldown"):
        return None
    personality = player.civ.personality
    preference = rules.ai.government_preference

    def appeal(government_id: str) -> float:
        government = rules.governments[government_id]
        value = preference.get(government_id, 0.0)
        if government.senate:
            # A senate forbids declaring war: warmongers do not like it.
            value -= get("senate_aggressive_penalty") * max(0, personality.mood)
            if plan.at_war and plan.war_targets:
                value -= get("senate_war_penalty")
        if government.military_unhappiness and plan.at_war:
            value -= get("war_weariness_penalty") * government.military_unhappiness
        if government.martial_law and plan.at_war:
            value += get("martial_law_bonus")
        return value

    options = view.available_governments()
    if not options:
        return None
    best = max(options, key=lambda g: (appeal(g), g))
    if best != player.government \
            and appeal(best) >= appeal(player.government) + get("revolution_min_gain"):
        if view.do(actions.Revolution(best)):
            memory["last_revolution"] = view.turn
            return best
    return None
