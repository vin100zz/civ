"""Turns the game state into JSON for the client.

The client is a pure display: everything it shows comes from here. A point of view (`pov`)
restricts the output to what that civilization knows; without it the observer sees all.
"""
from __future__ import annotations

from typing import Any, Optional

from ..engine import effects as fx
from ..engine.model.entities import City, Player, Unit
from ..engine.model.game import Game
from ..engine.rules.schema import Rules
from ..engine.systems import city as city_rules
from ..engine.systems import production, research

# Tile flags, packed in one integer per tile.
F_SPECIAL, F_PATTERN, F_HUT, F_ROAD, F_RAILROAD, F_IRRIGATION, F_MINE, F_FORTRESS, F_POLLUTION = (
    1, 2, 4, 8, 16, 32, 64, 128, 256)


def rules_payload(rules: Rules) -> dict[str, Any]:
    """Static data the client needs to draw and label things."""
    return {
        "terrains": [
            {"id": t.id, "name": t.name, "sprite": t.sprite, "base_sprite": t.base_sprite,
             "color": t.color, "land": t.is_land, "move_cost": t.move_cost,
             "defense": t.defense, "yields": [t.yields.food, t.yields.shields, t.yields.trade],
             "special": ({"name": t.special.name, "sprite": t.special.sprite,
                          "yields": [t.special.yields.food, t.special.yields.shields,
                                     t.special.yields.trade]} if t.special else None),
             "pattern_sprite": t.pattern_bonus.sprite if t.pattern_bonus else None}
            for t in rules.terrains.values()],
        "units": [
            {"id": u.id, "name": u.name, "sprite": u.sprite, "attack": u.attack,
             "defense": u.defense, "moves": u.moves, "cost": u.cost, "domain": u.domain,
             "role": u.role, "capacity": u.capacity}
            for u in rules.units.values()],
        "buildings": [
            {"id": b.id, "name": b.name, "cost": b.cost, "upkeep": b.upkeep, "wonder": b.wonder,
             "description": b.description}
            for b in rules.buildings.values()],
        "techs": [
            {"id": t.id, "name": t.name, "era": t.era, "prerequisites": list(t.prerequisites)}
            for t in rules.techs.values()],
        "governments": [{"id": g.id, "name": g.name} for g in rules.governments.values()],
        "civs": [
            {"id": c.id, "name": c.name, "nation": c.nation, "leader": c.leader, "color": c.color,
             "playable": c.playable,
             "personality": {"mood": c.personality.mood, "policy": c.personality.policy,
                             "ideology": c.personality.ideology}}
            for c in rules.civs.values()],
        "defaults": {"players": rules.game.players.count,
                     "max_players": len(rules.playable_civs)},
        "spaceship": {"min_parts": dict(rules.game.spaceship.min_parts),
                      "max_parts": dict(rules.game.spaceship.max_parts)},
        "max_turns": rules.game.calendar.max_turns,
    }


def tile_flags(tile) -> int:
    return (F_SPECIAL * tile.special | F_PATTERN * tile.pattern | F_HUT * tile.hut
            | F_ROAD * tile.road | F_RAILROAD * tile.railroad | F_IRRIGATION * tile.irrigation
            | F_MINE * tile.mine | F_FORTRESS * tile.fortress | F_POLLUTION * tile.pollution)


def map_payload(game: Game) -> dict[str, Any]:
    terrain_index = {tid: i for i, tid in enumerate(game.rules.terrains)}
    return {
        "width": game.map.width,
        "height": game.map.height,
        "wrap_x": game.map.wrap_x,
        "terrain": [terrain_index[t.terrain] for t in game.map.tiles],
        "flags": [tile_flags(t) for t in game.map.tiles],
        "continent": [t.continent for t in game.map.tiles],
    }


def tile_changes(game: Game) -> list[list[int]]:
    terrain_index = {tid: i for i, tid in enumerate(game.rules.terrains)}
    changes = []
    for index in sorted(game.changed_tiles):
        tile = game.map.tiles[index]
        changes.append([index, terrain_index[tile.terrain], tile_flags(tile)])
    return changes


def player_payload(game: Game, player: Player) -> dict[str, Any]:
    cities = game.player_cities(player.id)
    units = game.player_units(player.id)
    others = [p for p in game.civilizations if p.id != player.id] if player.alive else []
    at_war = [p.id for p in others
              if game.in_contact(player.id, p.id) and game.at_war(player.id, p.id)]
    at_peace = [p.id for p in others if game.at_peace(player.id, p.id)]
    return {
        "id": player.id, "civ": player.civ.id, "name": player.civ.name,
        "nation": player.civ.nation, "leader": player.civ.leader, "color": player.civ.color,
        "barbarian": player.is_barbarian, "alive": player.alive,
        "gold": player.gold, "government": player.government,
        "rates": [player.tax_rate, player.luxury_rate, player.science_rate],
        "techs": player.tech_count,
        "researching": player.researching,
        "research_progress": player.research_progress,
        "research_cost": research.research_cost(game, player) if not player.is_barbarian else 0,
        "cities": len(cities), "population": sum(c.size for c in cities),
        "units": len(units), "score": player.score,
        "income": player.income - player.expenses, "science": player.science_income,
        "at_war": at_war, "at_peace": at_peace,
        "wonders": sum(1 for cid in game.wonders.values()
                       if cid in game.cities and game.cities[cid].owner == player.id),
        "ships": sum(1 for u in units if game.rules.units[u.type].domain == "sea"),
        "aircraft": sum(1 for u in units if game.rules.units[u.type].domain == "air"),
        "spaceship": {"parts": dict(player.spaceship.parts),
                      "launched_turn": player.spaceship.launched_turn,
                      "arrival_turn": player.spaceship.arrival_turn},
    }


def city_payload(game: Game, city: City) -> dict[str, Any]:
    item = city.production
    return {
        "id": city.id, "name": city.name, "owner": city.owner, "x": city.x, "y": city.y,
        "size": city.size,
        "production": production.item_name(game, item) if item else None,
        "disorder": city.disorder, "celebrating": city.celebrating,
        "capital": fx.is_capital(game, city),
        "walls": "city_walls" in fx.effective_buildings(game, city),
        "wonders": sum(1 for b in city.buildings if game.rules.buildings[b].wonder),
    }


def unit_payload(unit: Unit) -> list:
    """Compact: [id, type, owner, x, y, order, veteran, aboard a ship]."""
    return [unit.id, unit.type, unit.owner, unit.x, unit.y, unit.order, int(unit.veteran),
            int(unit.aboard is not None)]


def state_payload(game: Game, pov: Optional[int] = None) -> dict[str, Any]:
    """The moving parts of the game, sent after every turn."""
    viewer = game.players[pov] if pov is not None and 0 <= pov < len(game.players) else None
    cities = list(game.cities.values())
    units = list(game.units.values())
    payload: dict[str, Any] = {
        "seed": game.seed, "turn": game.turn, "year": game.year,
        "finished": game.finished, "winner": game.winner, "victory": game.victory,
        "polluted": sum(1 for tile in game.map.tiles if tile.pollution),
        "warming": {"level": game.warming_level, "count": game.warming_count,
                    "threshold": game.rules.game.pollution.warming_threshold},
        "players": [player_payload(game, p) for p in game.players],
    }
    if viewer is not None:
        visible = viewer.visible
        cities = [c for c in cities if c.owner == viewer.id or c.id in viewer.known_cities]
        units = [u for u in units
                 if u.owner == viewer.id or visible[game.tile_of(u).index]]
        payload["explored"] = "".join(
            "2" if visible[i] else "1" if viewer.explored[i] else "0"
            for i in range(len(game.map.tiles)))
    payload["pov"] = viewer.id if viewer is not None else None
    payload["cities"] = [city_payload(game, c) for c in cities]
    payload["units"] = [unit_payload(u) for u in units]
    return payload


def city_detail(game: Game, city: City, decision=None) -> dict[str, Any]:
    stats = city_rules.compute_city(game, city)
    effects = fx.city_effects(game, city)
    tiles = []
    for (dx, dy), tile in [((0, 0), game.tile_of(city))] + game.map.city_area(city.x, city.y):
        y = city_rules.tile_yields(game, city, tile, effects)
        tiles.append({"dx": dx, "dy": dy, "x": tile.x, "y": tile.y,
                      "yields": [y.food, y.shields, y.trade],
                      "worked": (dx, dy) == (0, 0) or (dx, dy) in city.worked})
    item = city.production
    detail: dict[str, Any] = {
        **city_payload(game, city),
        "food": city.food, "food_box": stats.food_box, "shields": city.shields,
        "production_cost": production.item_cost(game, item) if item else None,
        "buy_cost": production.buy_cost(game, city),
        "stats": {
            "food": stats.food, "food_surplus": stats.food_surplus,
            "shields": stats.shields, "shield_upkeep": stats.shield_upkeep,
            "shield_surplus": stats.shield_surplus,
            "trade": stats.trade, "corruption": stats.corruption,
            "luxury": stats.luxury, "tax": stats.tax, "science": stats.science,
            "happy": stats.happy, "content": stats.content, "unhappy": stats.unhappy,
            "building_upkeep": stats.building_upkeep, "pollution": stats.pollution,
        },
        "specialists": dict(city.specialists),
        "buildings": sorted(city.buildings, key=lambda b: game.rules.buildings[b].name),
        "tiles": tiles,
        "units_here": [unit_payload(u) for u in game.units_at(game.tile_of(city))],
        "units_supported": [unit_payload(u) for u in game.units_of_city(city)],
        "trade_routes": [game.cities[c].name for c in city.trade_routes if c in game.cities],
        "founded_turn": city.founded_turn,
    }
    if decision is not None:
        detail["decision"] = {
            "turn": decision.turn,
            "bought": decision.bought,
            "candidates": [
                {"name": production.item_name(game, c.item), "kind": c.item.kind,
                 "score": c.score, "reason": c.reason, "turns": c.turns}
                for c in decision.candidates],
        }
    return detail


def player_detail(game: Game, player: Player, controller=None) -> dict[str, Any]:
    detail = player_payload(game, player)
    detail["tech_list"] = sorted(player.techs)
    detail["future_techs"] = player.future_techs
    detail["research_options"] = (research.research_options(game, player)
                                  if not player.is_barbarian else [])
    detail["personality"] = {"mood": player.civ.personality.mood,
                             "policy": player.civ.personality.policy,
                             "ideology": player.civ.personality.ideology}
    detail["relations"] = [
        {"player": other.id, "state": game.relation(player.id, other.id).state,
         "since": game.relation(player.id, other.id).since_turn}
        for other in game.players
        if other.id != player.id and not other.is_barbarian and other.alive]
    if controller is not None:
        detail["ai"] = getattr(controller, "debug", {})
    return detail
