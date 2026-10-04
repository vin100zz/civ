"""Turns the game state into JSON for the client.

The client is a pure display: everything it shows comes from here. A point of view (`pov`)
restricts the output to what that civilization sees; without it the observer sees all.
When a person leads that civilization (its controller is passed along), the output goes
further: the other civilizations keep their secrets, and the person's own units, cities
and affairs come with what it needs to give orders.
"""
from __future__ import annotations

from typing import Any, Optional

from ..engine import effects as fx
from ..engine.model.entities import WORK_ORDERS, City, CityMemory, Player, Unit
from ..engine.model.game import Game
from ..engine.rules.schema import Rules
from ..engine.systems import city as city_rules
from ..engine.systems import production, research
from ..engine.view import PlayerView
from ..human import orders, report
from ..human.controller import HumanController

# Tile flags, packed in one integer per tile.
F_SPECIAL, F_PATTERN, F_HUT, F_ROAD, F_RAILROAD, F_IRRIGATION, F_MINE, F_FORTRESS, F_POLLUTION = (
    1, 2, 4, 8, 16, 32, 64, 128, 256)

# Map settings the observer picks for a new game, each from 0 to 2.
MAP_LEVELS = ("relief", "climate")
UNKNOWN_COLOR = "#8A95A5"


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
             "role": u.role, "capacity": u.capacity, "requires": u.requires,
             "pop_cost": u.pop_cost}
            for u in rules.units.values()],
        "buildings": [
            {"id": b.id, "name": b.name, "cost": b.cost, "upkeep": b.upkeep, "wonder": b.wonder,
             "description": b.description, "requires": b.requires}
            for b in rules.buildings.values()],
        "techs": [
            {"id": t.id, "name": t.name, "era": t.era, "prerequisites": list(t.prerequisites)}
            for t in rules.techs.values()],
        "governments": [{"id": g.id, "name": g.name, "requires": g.requires,
                         "max_rate": g.max_rate, "senate": g.senate}
                        for g in rules.governments.values()],
        "civs": [
            {"id": c.id, "name": c.name, "nation": c.nation, "leader": c.leader, "color": c.color,
             "playable": c.playable,
             "personality": {"mood": c.personality.mood, "policy": c.personality.policy,
                             "ideology": c.personality.ideology}}
            for c in rules.civs.values()],
        "levels": [{"id": level_id, "name": level.name}
                   for level_id, level in rules.game.difficulty.levels.items()],
        "defaults": {"players": rules.game.players.count,
                     "max_players": len(rules.playable_civs),
                     "level": rules.game.difficulty.default_level,
                     "map": {"shape": rules.game.map.shape,
                             **{name: getattr(rules.game.map, name) for name in MAP_LEVELS}}},
        "map_shapes": [
            {"id": shape_id, "name": shape.name, "description": shape.description}
            for shape_id, shape in rules.game.map.shapes.items()],
        "spaceship": {"min_parts": dict(rules.game.spaceship.min_parts),
                      "max_parts": dict(rules.game.spaceship.max_parts)},
        "max_turns": rules.game.calendar.max_turns,
        "points_per_move": rules.game.movement.points_per_move,
        "specialist_min_size": rules.game.city.specialist_min_size,
    }


# ── The map ───────────────────────────────────────────────────────────────────

def tile_flags(tile) -> int:
    return (F_SPECIAL * tile.special | F_PATTERN * tile.pattern | F_HUT * tile.hut
            | F_ROAD * tile.road | F_RAILROAD * tile.railroad | F_IRRIGATION * tile.irrigation
            | F_MINE * tile.mine | F_FORTRESS * tile.fortress | F_POLLUTION * tile.pollution)


def map_payload(game: Game, viewer: Optional[Player] = None) -> dict[str, Any]:
    """The world. For a person, the tiles its civilization has not explored are sent as
    plain sea: the client never holds what the player does not know."""
    terrain_index = {tid: i for i, tid in enumerate(game.rules.terrains)}
    tiles = game.map.tiles
    known = viewer.explored if viewer is not None else None
    sea = next(i for i, t in enumerate(game.rules.terrains.values()) if not t.is_land)

    def seen(tile) -> bool:
        return known is None or bool(known[tile.index])

    return {
        "width": game.map.width,
        "height": game.map.height,
        "wrap_x": game.map.wrap_x,
        "terrain": [terrain_index[t.terrain] if seen(t) else sea for t in tiles],
        "flags": [tile_flags(t) if seen(t) else 0 for t in tiles],
        "continent": [t.continent if seen(t) else 0 for t in tiles],
    }


def tile_rows(game: Game, indexes) -> list[list[int]]:
    """[index, terrain, flags] of the given tiles."""
    terrain_index = {tid: i for i, tid in enumerate(game.rules.terrains)}
    rows = []
    for index in sorted(indexes):
        tile = game.map.tiles[index]
        rows.append([index, terrain_index[tile.terrain], tile_flags(tile)])
    return rows


def tile_changes(game: Game) -> list[list[int]]:
    return tile_rows(game, game.changed_tiles)


# ── Players ───────────────────────────────────────────────────────────────────

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


def public_player_payload(game: Game, player: Player, viewer: Player) -> dict[str, Any]:
    """What a person knows of another civilization: nothing before they meet; afterwards its
    name, its government, the cities seen and what the whole world is told (wonders,
    spaceship launches). Treasury, science and armies stay secret (None)."""
    met = player.is_barbarian or game.in_contact(viewer.id, player.id)
    known = [m for m in viewer.known_cities.values() if m.owner == player.id]
    ship = player.spaceship
    payload: dict[str, Any] = {
        "id": player.id, "barbarian": player.is_barbarian, "alive": player.alive, "met": met,
        "civ": player.civ.id if met else None,
        "name": player.civ.name if met else "Unknown",
        "nation": player.civ.nation if met else "Unknown",
        "leader": player.civ.leader if met else "",
        "color": player.civ.color if met else UNKNOWN_COLOR,
        "government": player.government if met else None,
        "cities": len(known), "population": sum(m.size for m in known),
        "gold": None, "rates": None, "techs": None, "researching": None,
        "research_progress": None, "research_cost": None, "units": None, "score": None,
        "income": None, "science": None, "ships": None, "aircraft": None,
        "at_war": [], "at_peace": [],
        "wonders": sum(1 for cid in game.wonders.values()
                       if cid in game.cities and game.cities[cid].owner == player.id),
        "spaceship": {"parts": {}, "launched_turn": ship.launched_turn,
                      "arrival_turn": ship.arrival_turn},
    }
    if met and not player.is_barbarian and player.alive:
        # Wars and treaties between civilizations the viewer has met are public.
        for other in game.civilizations:
            if other.id == player.id or not game.in_contact(player.id, other.id):
                continue
            if other.id != viewer.id and not game.in_contact(viewer.id, other.id):
                continue
            (payload["at_war"] if game.at_war(player.id, other.id)
             else payload["at_peace"]).append(other.id)
    return payload


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


def own_detail(view: PlayerView, game: Game) -> dict[str, Any]:
    """The affairs of the civilization a person leads: what it may decide and choose from."""
    player = view.player
    detail = player_detail(game, player)
    government = game.government(player)
    gold, science, disorder = view.budget_with_rates(
        player.tax_rate, player.luxury_rate, player.science_rate)
    detail.update({
        # What the next turn should bring with the rates as they are now.
        "forecast": {"gold": gold, "science": science, "disorder": disorder},
        "governments": view.available_governments(),
        "max_rate": government.max_rate,
        "senate": government.senate,
        "anarchy_until": player.anarchy_until_turn,
        "tax_income": player.income,
        "expenses": player.expenses,
        "proposals": view.peace_proposals(),
        "can_launch": view.can_launch_spaceship(),
        "flight_years": view.spaceship_flight_years() if view.can_launch_spaceship() else None,
        "level": player.level,
    })
    return detail


# ── Cities ────────────────────────────────────────────────────────────────────

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


def own_city_payload(game: Game, city: City, controller: HumanController) -> dict[str, Any]:
    """A city of the person, with what the turn summary shows: how far its production is,
    and whether it needs a decision."""
    item = city.production
    building = item is not None and production.can_build(game, city, item)
    done = city.last_completed
    return {
        **city_payload(game, city),
        "shields": city.shields,
        "cost": production.item_cost(game, item) if building else None,
        "surplus": city.stats.shield_surplus,
        "food_surplus": city.stats.food_surplus,
        "buy": production.buy_cost(game, city) if production.can_buy(game, city) else None,
        "idle": not building,
        "completed": production.item_name(game, done) if done is not None else None,
        "governed": controller.governed(city.id),
    }


def remembered_city_payload(memory: CityMemory) -> dict[str, Any]:
    """A foreign city as the person last saw it."""
    return {
        "id": memory.city_id, "name": memory.name, "owner": memory.owner,
        "x": memory.x, "y": memory.y, "size": memory.size, "production": None,
        "disorder": False, "celebrating": False, "capital": False, "walls": memory.has_walls,
        "wonders": 0, "seen": memory.seen_turn, "foreign": True,
    }


def city_detail(game: Game, city: City, decision=None,
                controller: Optional[HumanController] = None) -> dict[str, Any]:
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
    if controller is not None:
        detail["manage"] = _city_choices(game, city, controller)
    return detail


def _city_choices(game: Game, city: City, controller: HumanController) -> dict[str, Any]:
    """What the person may decide in its city."""
    view = PlayerView(game, game.players[city.owner])
    item = city.production
    return {
        "options": [{"kind": option.kind, "id": option.id, "cost": view.item_cost(option)}
                    for option in view.production_options(city)],
        "current": [item.kind, item.id] if item is not None else None,
        "can_buy": view.can_buy(city),
        "gold": view.player.gold,
        "sellable": [b for b in sorted(city.buildings) if view.can_sell(city, b)],
        "workable": [list(offset) for offset in sorted(view.workable_offsets(city))],
        "governed": controller.governed(city.id),
    }


# ── Units ─────────────────────────────────────────────────────────────────────

def unit_payload(unit: Unit) -> list:
    """Compact: [id, type, owner, x, y, order, veteran, aboard a ship]."""
    return [unit.id, unit.type, unit.owner, unit.x, unit.y, unit.order, int(unit.veteran),
            int(unit.aboard is not None)]


def own_unit_payload(unit: Unit, controller: HumanController) -> list:
    """A unit of the person: the same, then the movement points it has left and what it
    was left to do by itself ("goto", "explore", "work" or "")."""
    return [*unit_payload(unit), unit.moves_left, controller.task(unit.id)]


def unit_detail(view: PlayerView, controller: HumanController, unit: Unit) -> dict[str, Any]:
    """Everything about one unit of the person, with the orders it can take now."""
    rules = view.rules
    definition = rules.units[unit.type]
    tile = view.tile_of(unit)
    home = view.city(unit.home_city) if unit.home_city is not None else None
    here = view.my_city_at(unit.x, unit.y)
    working = unit.order in WORK_ORDERS
    return {
        "id": unit.id, "type": unit.type, "x": unit.x, "y": unit.y, "order": unit.order,
        "work": unit.work if working else None,
        "work_turns": view.work_turns(unit, unit.order) if working else None,
        "moves_left": unit.moves_left, "full_moves": view.full_moves(unit),
        "veteran": unit.veteran,
        "fuel": unit.fuel if definition.fuel else None,
        "home": home.name if home is not None else None,
        "terrain": rules.terrains[tile.terrain].name,
        "city": here.name if here is not None else None,
        "aboard": unit.aboard,
        "cargo": [own_unit_payload(u, controller) for u in view.cargo_of(unit)]
        if definition.capacity else [],
        "capacity": definition.capacity,
        "task": controller.task(unit.id),
        "destination": controller.destination(unit.id),
        "orders": orders.unit_orders(view, controller, unit),
        "stack": [own_unit_payload(u, controller) for u in view.my_units_at(tile)],
    }


# ── The moving parts ──────────────────────────────────────────────────────────

def state_payload(game: Game, pov: Optional[int] = None,
                  controller: Optional[HumanController] = None) -> dict[str, Any]:
    """The moving parts of the game, sent after every turn (and every action of a person).

    `pov` limits cities and units to what that civilization sees. With the `controller` of
    the person leading it, the other civilizations' secrets are left out as well.
    """
    viewer = game.players[pov] if pov is not None and 0 <= pov < len(game.players) else None
    leading = viewer is not None and controller is not None
    payload: dict[str, Any] = {
        "seed": game.seed, "turn": game.turn, "year": game.year,
        "finished": game.finished, "winner": game.winner, "victory": game.victory,
        "polluted": sum(1 for tile in game.map.tiles if tile.pollution),
        "warming": {"level": game.warming_level, "count": game.warming_count,
                    "threshold": game.rules.game.pollution.warming_threshold},
        "pov": viewer.id if viewer is not None else None,
    }
    cities = list(game.cities.values())
    units = list(game.units.values())
    if viewer is not None:
        visible = viewer.visible
        cities = [c for c in cities if c.owner == viewer.id or c.id in viewer.known_cities]
        units = [u for u in units
                 if u.owner == viewer.id or visible[game.tile_of(u).index]]
        payload["explored"] = "".join(
            "2" if visible[i] else "1" if viewer.explored[i] else "0"
            for i in range(len(game.map.tiles)))

    if not leading:
        payload["players"] = [player_payload(game, p) for p in game.players]
        payload["cities"] = [city_payload(game, c) for c in cities]
        payload["units"] = [unit_payload(u) for u in units]
        return payload

    view = PlayerView(game, viewer)
    payload["players"] = [
        player_payload(game, p) if p.id == viewer.id else public_player_payload(game, p, viewer)
        for p in game.players]
    payload["cities"] = [
        own_city_payload(game, c, controller) if c.owner == viewer.id
        else remembered_city_payload(viewer.known_cities[c.id]) for c in cities]
    payload["units"] = [
        own_unit_payload(u, controller) if u.owner == viewer.id else unit_payload(u)
        for u in units]
    payload["me"] = own_detail(view, game)
    payload["alerts"] = report.alerts(view)
    payload["notes"] = list(controller.notes)
    return payload
