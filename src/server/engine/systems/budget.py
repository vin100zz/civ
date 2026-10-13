"""The treasury: what a building is worth to its city, and which one goes when the upkeep
cannot be paid.

Civ 1 sells the building whose upkeep falls due when the treasury runs dry, whatever it is,
and pays its price back (CityWorker.cs, around line 3850). Here the treasury sells the
building the empire misses least: the one whose worth to its city, less its upkeep, is
lowest. The price paid back is the same.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

from ..model.entities import City, Player
from ..model.game import Game
from . import city as city_rules, pollution


def building_worth(game: Game, city: City, building_id: str) -> float:
    """What the city would lose each turn without this building, in gold: its share of the
    city's figures and of its citizens' mood, and what the figures do not show (walls with
    an enemy within reach, the room to grow, veterans, cleaner air)."""
    rules = game.rules
    weights = rules.game.city.sale_weights
    player = game.players[city.owner]
    with_it = city_rules.compute_city(game, city)
    without = city_rules.compute_city(
        game, dataclasses.replace(city, buildings=city.buildings - {building_id}))

    worth = weights.food * (with_it.food_surplus - without.food_surplus) \
        + weights.shields * (with_it.shield_surplus - without.shield_surplus) \
        + weights.trade * (with_it.tax + with_it.science - without.tax - without.science) \
        + weights.citizen * ((without.unhappy - without.happy) - (with_it.unhappy - with_it.happy))
    if without.disorder and not with_it.disorder:
        worth += weights.disorder
    worth += weights.pollution * (pollution.pollution_risk(game, player, without.pollution)
                                  - pollution.pollution_risk(game, player, with_it.pollution))

    for effect in rules.buildings[building_id].effects:
        if effect.requires_tech is not None and effect.requires_tech not in player.techs:
            continue
        if effect.type in ("defense_multiplier", "nuclear_shield"):
            if enemy_within_reach(game, city):
                worth += weights.defense
        elif effect.type == "allow_size_above":
            # Worth all the more as the city nears the size it lets it grow past.
            nearness = 1.0 - (effect.size - city.size) / (weights.growth_lead + 1)
            worth += weights.growth * max(0.0, min(1.0, nearness))
        elif effect.type == "food_box_keep":
            limit = city_rules.max_size(game, city)
            if limit is None or city.size < limit:
                worth += weights.food * max(0, with_it.food_surplus) * effect.percent / 100
        elif effect.type == "veteran_units":
            item = city.production
            if item is not None and item.kind == "unit" and rules.units[item.id].is_military:
                worth += weights.veterans
    return worth


def enemy_within_reach(game: Game, city: City) -> bool:
    """An enemy city the owner knows of, or an enemy unit able to fight that it sees, is
    within `danger_radius` steps of the city."""
    player = game.players[city.owner]
    radius = game.rules.game.city.sale_weights.danger_radius
    world = game.map
    for memory in player.known_cities.values():
        if game.at_war(player.id, memory.owner) \
                and world.steps(city.x, city.y, memory.x, memory.y) <= radius:
            return True
    for unit in game.units.values():
        if unit.owner == player.id or not game.at_war(player.id, unit.owner):
            continue
        if game.rules.units[unit.type].attack <= 0:
            continue
        if player.visible[game.tile_of(unit).index] \
                and world.steps(city.x, city.y, unit.x, unit.y) <= radius:
            return True
    return False


def building_to_sell(game: Game, player: Player) -> Optional[tuple[City, str]]:
    """The building the treasury sells when it cannot pay the upkeep: the one whose worth,
    less its upkeep, is lowest. Wonders, the palace and buildings without upkeep are kept."""
    order = {building_id: i for i, building_id in enumerate(game.rules.buildings)}
    best = None
    for city in sorted(game.player_cities(player.id), key=lambda c: c.id):
        for building_id in city.buildings:
            definition = game.rules.buildings[building_id]
            if definition.wonder or definition.has_effect("capital"):
                continue
            upkeep = city_rules.building_upkeep(game, city, building_id)
            if upkeep <= 0:
                continue
            net = building_worth(game, city, building_id) - upkeep
            key = (net, -upkeep, city.id, order[building_id])
            if best is None or key < best[0]:
                best = (key, city, building_id)
    return None if best is None else (best[1], best[2])
