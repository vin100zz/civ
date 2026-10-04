"""City rules: tile yields, worker placement, trade, happiness, growth.

Source for every formula: OpenCivOne CityWorker.cs (F0_1d12_0045_ProcessCityState and
F0_1d12_6abc_GetCityResourceCount), rewritten as separate, testable steps.
"""
from __future__ import annotations

from typing import Optional

from .. import effects as fx
from ..model.entities import SPECIALISTS, City, CityStats, Unit
from ..model.game import Game
from ..model.worldmap import CITY_OFFSETS, Tile
from ..rules.schema import Effect, Yields


# ── Tile yields ───────────────────────────────────────────────────────────────

def tile_yields(game: Game, city: City, tile: Tile, effects: Optional[list[Effect]] = None) -> Yields:
    """Food, shields and trade a tile gives to the city working it."""
    rules = game.rules
    terrain = rules.terrains[tile.terrain]
    government = game.government(game.players[city.owner])
    movement = rules.game.movement
    base = terrain.special.yields if (tile.special and terrain.special) else terrain.yields
    food, shields, trade = base.food, base.shields, base.trade
    is_center = tile.x == city.x and tile.y == city.y

    if terrain.pattern_bonus is not None and tile.pattern:
        bonus = terrain.pattern_bonus.yields
        food, shields, trade = food + bonus.food, shields + bonus.shields, trade + bonus.trade

    if terrain.is_land:
        irrigation = terrain.irrigation
        # The city tile is farmed and has a road without any settler work.
        if irrigation is not None and irrigation.bonus and (tile.irrigation or is_center):
            food += irrigation.bonus
        if tile.mine and terrain.mine is not None and terrain.mine.bonus:
            shields += terrain.mine.bonus
        if terrain.road_trade and (tile.road or is_center):
            trade += movement.road_trade_bonus
    if is_center and shields < 1:
        shields = 1

    if trade > 0:
        if effects is None:
            effects = fx.city_effects(game, city)
        for effect in effects:
            if effect.type == "tile_trade_bonus":
                trade += effect.amount

    if tile.railroad:
        percent = movement.railroad_yield_percent
        food += food * percent // 100
        shields += shields * percent // 100
        trade += trade * percent // 100

    if government.tile_penalty and not city.celebrating:
        food -= food > 2
        shields -= shields > 2
        trade -= trade > 2

    if trade > 0 and (government.trade_bonus
                      or (city.celebrating and government.celebration_trade_bonus)):
        trade += 1

    if tile.pollution:
        food, shields, trade = (food + 1) // 2, (shields + 1) // 2, (trade + 1) // 2
    return Yields(food, shields, trade)


def workable_tiles(game: Game, city: City) -> list[tuple[tuple[int, int], Tile]]:
    """Tiles of the city area this city may work: free of other cities' workers and of enemies."""
    result = []
    for offset, tile in game.map.city_area(city.x, city.y):
        if tile.city_id is not None:
            continue
        if tile.worked_by is not None and tile.worked_by != city.id:
            continue
        if tile.unit_ids:
            occupant = game.units[tile.unit_ids[0]].owner
            if occupant != city.owner and game.at_war(occupant, city.owner):
                continue
        result.append((offset, tile))
    return result


def is_coastal(game: Game, city: City) -> bool:
    """A city next to the sea can build ships."""
    return any(not game.terrain(tile).is_land for tile in game.map.neighbors(game.tile_of(city)))


# ── Worker placement ──────────────────────────────────────────────────────────

def set_worked(game: Game, city: City, offsets: list[tuple[int, int]]) -> None:
    """Replaces the tiles worked by the city, keeping the map's `worked_by` in sync."""
    for dx, dy in city.worked:
        tile = game.map.tile(city.x + dx, city.y + dy)
        if tile is not None and tile.worked_by == city.id:
            tile.worked_by = None
    city.worked = list(offsets)
    for dx, dy in city.worked:
        tile = game.map.tile(city.x + dx, city.y + dy)
        if tile is not None:
            tile.worked_by = city.id
    center = game.tile_of(city)
    center.worked_by = city.id


def release_tiles(game: Game, city: City) -> None:
    set_worked(game, city, [])
    game.tile_of(city).worked_by = None


def settlers_of(game: Game, city: City) -> int:
    return sum(1 for u in game.units_of_city(city)
               if game.rules.units[u.type].can("found_city"))


def auto_arrange(game: Game, city: City) -> None:
    """Puts every citizen on a tile: the city's own mayor.

    Citizens are placed one by one on the tile worth the most to the city at that moment:
    food counts most while the city does not feed itself, shields while its units eat all
    the production (weights in game.yaml, city.worker_weights). Citizens left without a
    tile become entertainers, and more are taken off the land while the city would riot.

    The original game uses a similar two-step rule (CityWorker.cs, around line 575) that
    leaves large cities without any shield; this one keeps them producing.
    """
    rules = game.rules
    weights = rules.game.city.worker_weights
    government = game.government(game.players[city.owner])
    effects = fx.city_effects(game, city)
    candidates = {offset: tile_yields(game, city, tile, effects)
                  for offset, tile in workable_tiles(game, city)}
    center = tile_yields(game, city, game.tile_of(city), effects)
    food, shields, trade = center.food, center.shields, center.trade
    need = (city.size * rules.game.city.food_per_citizen
            + settlers_of(game, city) * government.settlers_food)
    upkeep = _shield_upkeep(game, city)
    limit = max_size(game, city)
    # A city that can still grow wants a surplus, not just enough to eat.
    wanted_surplus = 0 if limit is not None and city.size >= limit else 1
    chosen: list[tuple[int, int]] = []

    for _ in range(city.size):
        if not candidates:
            break
        food_surplus = food - need
        shield_surplus = shields - upkeep
        food_weight = (weights.food_starving if food_surplus < wanted_surplus
                       else weights.food_low if food_surplus < wanted_surplus + 2
                       else weights.food)
        shield_weight = (weights.shields_none if shield_surplus <= 0
                         else weights.shields_low if shield_surplus < 3 else weights.shields)

        def value(offset: tuple[int, int]) -> tuple[float, int]:
            y = candidates[offset]
            return (y.food * food_weight + y.shields * shield_weight + y.trade * weights.trade,
                    -CITY_OFFSETS.index(offset))

        best = max(candidates, key=value)
        if value(best)[0] <= 0:
            break
        y = candidates.pop(best)
        food, shields, trade = food + y.food, shields + y.shields, trade + y.trade
        chosen.append(best)

    set_worked(game, city, chosen)
    city.specialists = {name: 0 for name in SPECIALISTS}
    city.specialists["entertainer"] = city.size - len(chosen)

    # Calm a rioting city with entertainers.
    while city.worked:
        stats = compute_city(game, city)
        if not stats.disorder:
            break
        worst = min(city.worked, key=lambda o: _tile_worth(game, city, o, effects))
        set_worked(game, city, [o for o in city.worked if o != worst])
        city.specialists["entertainer"] += 1


def toggle_tile(game: Game, city: City, offset: tuple[int, int]) -> bool:
    """The player moves one citizen by hand: off a worked tile (it becomes an entertainer),
    or from the specialists onto a tile the city may work. The mayor takes over again when
    the city grows or shrinks (see `auto_arrange`)."""
    if offset in city.worked:
        set_worked(game, city, [o for o in city.worked if o != offset])
        city.specialists["entertainer"] += 1
    else:
        allowed = {o for o, _ in workable_tiles(game, city)}
        idle = next((kind for kind in SPECIALISTS if city.specialists[kind] > 0), None)
        if offset not in allowed or idle is None:
            return False
        city.specialists[idle] -= 1
        set_worked(game, city, city.worked + [offset])
    city.stats = compute_city(game, city)
    return True


def change_specialist(game: Game, city: City, kind: str) -> bool:
    """Turns one specialist into the next kind: entertainer, taxman, scientist, and round."""
    if kind not in SPECIALISTS or city.specialists[kind] <= 0:
        return False
    if city.size < game.rules.game.city.specialist_min_size:
        return False
    following = SPECIALISTS[(SPECIALISTS.index(kind) + 1) % len(SPECIALISTS)]
    city.specialists[kind] -= 1
    city.specialists[following] += 1
    city.stats = compute_city(game, city)
    return True


def _tile_worth(game: Game, city: City, offset: tuple[int, int], effects: list[Effect]) -> int:
    tile = game.map.tile(city.x + offset[0], city.y + offset[1])
    if tile is None:
        return 0
    y = tile_yields(game, city, tile, effects)
    return 3 * y.food + 2 * y.shields + y.trade


def ensure_valid_assignment(game: Game, city: City) -> None:
    """Re-arranges the workers if the current assignment no longer matches the city."""
    allowed = {offset for offset, _ in workable_tiles(game, city)}
    valid = all(offset in allowed for offset in city.worked)
    if not valid or len(city.worked) + city.specialist_count != city.size:
        auto_arrange(game, city)
    else:
        game.tile_of(city).worked_by = city.id


# ── The city's figures for one turn ───────────────────────────────────────────

def _supported_units(game: Game, city: City) -> list[Unit]:
    return [u for u in game.units_of_city(city) if game.rules.units[u.type].needs_support]


def _shield_upkeep(game: Game, city: City) -> int:
    player = game.players[city.owner]
    if player.is_barbarian:
        return 0
    government = game.government(player)
    free = city.size if government.free_units == "city_size" else 0
    return max(0, len(_supported_units(game, city)) - free)


def capital_distance(game: Game, city: City) -> int:
    player = game.players[city.owner]
    government = game.government(player)
    if fx.is_capital(game, city):
        return 0
    if government.corruption_distance is not None:
        return government.corruption_distance
    capital = game.cities.get(player.capital_id) if player.capital_id is not None else None
    if capital is None or capital.owner != city.owner:
        return game.rules.game.city.no_palace_distance
    return game.map.distance(city.x, city.y, capital.x, capital.y)


def _corruption(game: Game, city: City, trade: int, effects: list[Effect]) -> int:
    government = game.government(game.players[city.owner])
    if government.corruption_divisor is None:
        return 0
    corruption = trade * capital_distance(game, city) * 3 // government.corruption_divisor
    for effect in effects:
        if effect.type == "corruption_percent":
            corruption = int(corruption * effect.percent / 100)
    return min(corruption, trade)


def _apply_yield_bonus(base: int, effects: list[Effect], kind: str) -> int:
    """Additive bonuses are each computed on the base, compound ones are chained after."""
    total = base
    groups_seen: set[str] = set()
    compound: list[Effect] = []
    for effect in effects:
        if effect.type != "yield_bonus" or effect.yield_kind != kind:
            continue
        if effect.exclusive_group is not None:
            if effect.exclusive_group in groups_seen:
                continue
            groups_seen.add(effect.exclusive_group)
        if effect.mode == "compound":
            compound.append(effect)
        else:
            total += int(base * effect.percent / 100)
    for effect in compound:
        total += int(total * effect.percent / 100)
    return total


def _settle_mood(happy: int, unhappy: int, excess: int, size: int, workers: int) -> tuple[int, int, int]:
    """Keeps the mood counters consistent (original: F0_1d12_6dfe).

    `excess` holds unhappiness beyond the city size; it comes back when unhappiness drops.
    A happy citizen and an unhappy one cancel out into two content ones.
    """
    while excess > 0 and unhappy < excess:
        excess -= 1
        unhappy += 1
    happy = max(0, min(happy, size))
    unhappy = max(0, min(unhappy, size))
    while happy + unhappy > max(0, workers):
        if excess > 0:
            excess -= 1
        else:
            happy = max(0, happy - 1)
        unhappy = max(0, unhappy - 1)
    return happy, unhappy, excess


def empire_unhappiness(game: Game, city: City) -> int:
    """Extra unhappy citizens caused by the number of cities of the empire."""
    player = game.players[city.owner]
    government = game.government(player)
    span = government.empire_size_factor * game.difficulty(player).empire_size_base
    count = sum(1 for c in game.cities.values() if c.owner == city.owner)
    return max(0, (city.id % span + count - span) // span)


def compute_city(game: Game, city: City) -> CityStats:
    """All the figures of a city for the current assignment of its citizens. Changes nothing."""
    rules = game.rules
    settings = rules.game.city
    player = game.players[city.owner]
    government = game.government(player)
    effects = fx.city_effects(game, city)
    stats = CityStats()

    # Tiles.
    tiles = [game.tile_of(city)]
    for dx, dy in city.worked:
        tile = game.map.tile(city.x + dx, city.y + dy)
        if tile is not None:
            tiles.append(tile)
    food = shields = trade = 0
    for tile in tiles:
        y = tile_yields(game, city, tile, effects)
        food, shields, trade = food + y.food, shields + y.shields, trade + y.trade

    # Food.
    stats.food = food
    stats.food_eaten = city.size * settings.food_per_citizen \
        + settlers_of(game, city) * government.settlers_food
    stats.food_surplus = food - stats.food_eaten
    stats.food_box = (city.size + 1) * settings.food_box_per_size

    # Shields.
    stats.shields = _apply_yield_bonus(shields, effects, "shields")
    stats.supported_units = len(_supported_units(game, city))
    stats.shield_upkeep = _shield_upkeep(game, city)
    stats.shield_surplus = stats.shields - stats.shield_upkeep

    # Trade: corruption, trade routes, then the split between luxuries, taxes and science.
    corruption = _corruption(game, city, trade, effects)
    stats.base_trade = trade - corruption
    for other_id in city.trade_routes:
        other = game.cities.get(other_id)
        if other is None:
            continue
        divisor = 16 if other.owner == city.owner else 8
        trade += (other.base_trade + trade + 4) // divisor
    corruption = _corruption(game, city, trade, effects)
    net = trade - corruption
    luxury = max(0, min(trade, (player.luxury_rate * net + 50) // 100))
    tax = max(0, min(trade - luxury - corruption, (player.tax_rate * net + 50) // 100))
    science = trade - luxury - tax - corruption
    per_specialist = settings.specialist_yield
    luxury += city.specialists["entertainer"] * per_specialist
    tax += city.specialists["taxman"] * per_specialist
    science += city.specialists["scientist"] * per_specialist
    luxury = _apply_yield_bonus(luxury, effects, "luxury")
    tax = _apply_yield_bonus(tax, effects, "tax")
    science = _apply_yield_bonus(science, effects, "science")
    stats.trade = trade
    stats.corruption = corruption
    stats.luxury = luxury
    stats.tax = tax if government.collects_taxes else 0
    stats.science = science if government.does_research else 0

    # Mood.
    workers = city.size - city.specialist_count
    unhappy = city.size - game.difficulty(player).content_base + empire_unhappiness(game, city)
    if player.is_barbarian:
        unhappy = 0
    excess = max(0, unhappy - city.size)
    unhappy = max(0, min(unhappy, city.size))
    happy = 0
    happy, unhappy, excess = _settle_mood(happy, unhappy, excess, city.size, workers)

    happy = luxury // settings.luxury_per_happy
    happy, unhappy, excess = _settle_mood(happy, unhappy, excess, city.size, workers)

    unhappy -= sum(e.amount for e in effects if e.type == "content")
    happy, unhappy, excess = _settle_mood(happy, unhappy, excess, city.size, workers)

    if government.martial_law > 0:
        garrison = sum(1 for u in game.units_at(game.tile_of(city))
                       if u.owner == city.owner and rules.units[u.type].is_military)
        unhappy -= min(garrison, government.martial_law, max(0, unhappy))
    per_unit = government.military_unhappiness
    if per_unit > 0:
        per_unit += sum(e.amount for e in fx.player_effects(game, player, "military_unhappiness"))
        abroad = sum(1 for u in game.units_of_city(city)
                     if rules.units[u.type].is_military
                     and (rules.units[u.type].domain == "air" or (u.x, u.y) != (city.x, city.y)))
        unhappy += max(0, per_unit) * abroad
    happy, unhappy, excess = _settle_mood(happy, unhappy, excess, city.size, workers)

    happy += sum(e.amount for e in effects if e.type == "happy")
    if fx.has_effect(effects, "no_unhappy"):
        unhappy = 0
        excess = 0
    happy, unhappy, excess = _settle_mood(happy, unhappy, excess, city.size, workers)

    stats.happy = happy
    stats.unhappy = unhappy
    stats.content = max(0, workers - happy - unhappy)
    stats.disorder = unhappy > happy
    stats.celebrating = (unhappy == 0 and city.size >= settings.celebration_min_size
                         and happy >= (city.size + 1) // 2 and government.collects_taxes)

    # Maintenance and pollution.
    stats.building_upkeep = sum(building_upkeep(game, city, b) for b in city.buildings)
    if not player.is_barbarian:
        from . import pollution
        stats.pollution = pollution.pollution_index(game, city, stats.shields, effects)
    return stats


def building_upkeep(game: Game, city: City, building_id: str) -> int:
    definition = game.rules.buildings[building_id]
    player = game.players[city.owner]
    extra = sum(1 for tech in definition.upkeep_increase_techs if tech in player.techs)
    return definition.upkeep + extra


def max_size(game: Game, city: City) -> Optional[int]:
    """Size the city cannot exceed for lack of a building (aqueduct), or None."""
    limits = sorted({e.size for b in game.rules.buildings.values()
                     for e in b.effects if e.type == "allow_size_above"})
    allowed = {e.size for e in fx.city_effects(game, city) if e.type == "allow_size_above"}
    for limit in limits:
        if limit not in allowed:
            return limit
    return None
