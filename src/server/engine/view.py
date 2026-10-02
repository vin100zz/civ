"""What one player knows of the game, and its only way to act on it.

The AI receives a PlayerView, never the Game itself: the view answers from the player's own
cities and units, the tiles it has explored and the foreign units and cities it can see or
remembers. That is what keeps the AI honest.
"""
from __future__ import annotations

from typing import Optional

from . import actions
from . import effects as fx
from .mapgen.sites import site_score
from .model.entities import City, CityMemory, CityStats, Item, Player, Unit
from .model.game import Game
from .model.worldmap import Tile, WorldMap
from .rules.schema import Effect, Rules, Yields
from .systems import city as city_rules, combat, diplomacy, government, movement
from .systems import production, research, spaceship, trade


class PlayerView:
    def __init__(self, game: Game, player: Player) -> None:
        self._game = game
        self.player = player

    # ── General ───────────────────────────────────────────────────────────────

    @property
    def rules(self) -> Rules:
        return self._game.rules

    @property
    def map(self) -> WorldMap:
        """The map's geometry. Use `explored`/`visible` before trusting a tile's content."""
        return self._game.map

    @property
    def turn(self) -> int:
        return self._game.turn

    @property
    def year(self) -> int:
        return self._game.year

    @property
    def rng(self):
        return self._game.rng

    def do(self, action: actions.Action) -> actions.Result:
        return actions.apply(self._game, self.player.id, action)

    # ── Knowledge of the map ──────────────────────────────────────────────────

    def explored(self, tile: Tile) -> bool:
        return bool(self.player.explored[tile.index])

    def visible(self, tile: Tile) -> bool:
        return bool(self.player.visible[tile.index])

    def is_land(self, tile: Tile) -> bool:
        return self.rules.terrains[tile.terrain].is_land

    def site_score(self, tile: Tile) -> int:
        """City site quality, judged only from the tiles the player has explored."""
        if not self.explored(tile):
            return 0
        return site_score(self.rules, self._game.map, tile, known=self.explored)

    def can_found_city(self, tile: Tile) -> bool:
        """Founding rules, checked against the cities the player knows about."""
        if not self.is_land(tile):
            return False
        minimum = self.rules.game.city.min_distance
        for x, y in self.known_city_positions():
            if self._game.map.steps(tile.x, tile.y, x, y) < minimum:
                return False
        return True

    # ── Own cities and units ──────────────────────────────────────────────────

    def my_cities(self) -> list[City]:
        return sorted(self._game.player_cities(self.player.id), key=lambda c: c.id)

    def my_units(self) -> list[Unit]:
        return sorted(self._game.player_units(self.player.id), key=lambda u: u.id)

    def unit(self, unit_id: int) -> Optional[Unit]:
        unit = self._game.units.get(unit_id)
        return unit if unit is not None and unit.owner == self.player.id else None

    def city(self, city_id: int) -> Optional[City]:
        city = self._game.cities.get(city_id)
        return city if city is not None and city.owner == self.player.id else None

    def my_city_at(self, x: int, y: int) -> Optional[City]:
        city = self._game.city_at(x, y)
        return city if city is not None and city.owner == self.player.id else None

    def my_units_at(self, tile: Tile) -> list[Unit]:
        return [u for u in self._game.units_at(tile) if u.owner == self.player.id]

    def units_of_city(self, city: City) -> list[Unit]:
        return list(self._game.units_of_city(city))

    def city_stats(self, city: City) -> CityStats:
        return city_rules.compute_city(self._game, city)

    def city_tile_yields(self, city: City, tile: Tile) -> Yields:
        return city_rules.tile_yields(self._game, city, tile)

    def city_max_size(self, city: City) -> Optional[int]:
        return city_rules.max_size(self._game, city)

    def is_coastal(self, city: City) -> bool:
        return city_rules.is_coastal(self._game, city)

    def city_effects(self, city: City) -> list[Effect]:
        """Effects of buildings and wonders that currently apply to the city."""
        return fx.city_effects(self._game, city)

    def production_options(self, city: City) -> list[Item]:
        return production.production_options(self._game, city)

    def item_cost(self, item: Item) -> int:
        return production.item_cost(self._game, item)

    def buy_cost(self, city: City) -> Optional[int]:
        return production.buy_cost(self._game, city)

    def can_buy(self, city: City) -> bool:
        return production.can_buy(self._game, city)

    def capital(self) -> Optional[City]:
        if self.player.capital_id is None:
            return None
        return self.city(self.player.capital_id)

    def wonder_built(self, wonder_id: str) -> bool:
        """Wonders completed anywhere are public knowledge (announced to the world)."""
        return wonder_id in self._game.wonders

    def has_wonder(self, wonder_id: str) -> bool:
        city_id = self._game.wonders.get(wonder_id)
        return city_id is not None and self.city(city_id) is not None

    # ── Spaceship ─────────────────────────────────────────────────────────────

    def spaceship_parts(self) -> dict[str, int]:
        return {part: spaceship.parts(self.player, part) for part in
                self.rules.game.spaceship.min_parts}

    def can_launch_spaceship(self) -> bool:
        return spaceship.can_launch(self._game, self.player)

    def spaceship_flight_years(self) -> int:
        return spaceship.flight_years(self._game, self.player)

    def rival_spaceships(self) -> list[tuple[int, int]]:
        """(player id, arrival turn) of the spaceships other civilizations have launched:
        a launch is announced to the whole world."""
        return [(p.id, p.spaceship.arrival_turn) for p in self._game.civilizations
                if p.id != self.player.id and p.spaceship.launched]

    # ── Movement and combat ───────────────────────────────────────────────────

    def tile_of(self, entity) -> Tile:
        return self._game.tile_of(entity)

    def can_enter(self, unit: Unit, tile: Tile) -> bool:
        return movement.can_enter(self._game, unit, tile)

    def move_cost(self, unit: Unit, origin: Tile, target: Tile) -> int:
        return movement.move_cost(self._game, unit, origin, target)

    def full_moves(self, unit: Unit) -> int:
        return movement.full_moves(self._game, unit)

    def work_turns(self, unit: Unit, order: str) -> Optional[int]:
        return movement.work_turns(self._game, unit, order)

    def work_turns_at(self, tile: Tile, order: str) -> Optional[int]:
        return movement.work_turns_at(self._game, self.player, tile, order)

    def has_water_source(self, tile: Tile) -> bool:
        return movement.has_water_source(self._game, tile)

    def cargo_of(self, ship: Unit) -> list[Unit]:
        return self._game.cargo_of(ship)

    def room_left(self, ship: Unit) -> int:
        return movement.room_left(self._game, ship)

    def attack_odds(self, unit: Unit, tile: Tile) -> Optional[combat.Odds]:
        """Odds against the defender of a tile, or None if no enemy unit is seen there
        (or none this unit could fight)."""
        if not self.visible(tile) or not self.enemy_units_at(tile):
            return None
        return combat.odds(self._game, unit, tile)

    def can_attack(self, unit: Unit, tile: Tile) -> bool:
        """Could this kind of unit fight the enemy seen on the tile (from anywhere)?"""
        if not self.visible(tile) or not self.enemy_units_at(tile):
            return False
        return combat.why_cannot_attack(self._game, unit, tile) is None

    def trade_route_target(self, unit: Unit) -> Optional[City]:
        return trade.route_target(self._game, unit)

    # ── Foreign units and cities ──────────────────────────────────────────────

    def foreign_units_at(self, tile: Tile) -> list[Unit]:
        """Units of other players on a tile the player currently sees."""
        if not self.visible(tile):
            return []
        return [u for u in self._game.units_at(tile) if u.owner != self.player.id]

    def enemy_units_at(self, tile: Tile) -> list[Unit]:
        return [u for u in self.foreign_units_at(tile) if self.at_war(u.owner)]

    def visible_foreign_units(self) -> list[Unit]:
        result = []
        for unit in self._game.units.values():
            if unit.owner != self.player.id and self.player.visible[self._game.tile_of(unit).index]:
                result.append(unit)
        return sorted(result, key=lambda u: u.id)

    def visible_enemy_units(self) -> list[Unit]:
        return [u for u in self.visible_foreign_units() if self.at_war(u.owner)]

    def foreign_city_at(self, tile: Tile) -> Optional[CityMemory]:
        if tile.city_id is None:
            return None
        return self.player.known_cities.get(tile.city_id)

    def known_foreign_cities(self) -> list[CityMemory]:
        return sorted(self.player.known_cities.values(), key=lambda m: m.city_id)

    def known_city_positions(self) -> list[tuple[int, int]]:
        positions = [(c.x, c.y) for c in self.my_cities()]
        positions += [(m.x, m.y) for m in self.player.known_cities.values()]
        return positions

    def city_defenders_seen(self, memory: CityMemory) -> Optional[int]:
        """Number of units seen in a foreign city, or None if it is out of sight."""
        tile = self._game.map.tile(memory.x, memory.y)
        if not self.visible(tile):
            return None
        return len(self._game.units_at(tile))

    # ── Other players ─────────────────────────────────────────────────────────

    def contacts(self) -> list[Player]:
        """Living civilizations the player has met."""
        return [self._game.players[i] for i in diplomacy.contacts(self._game, self.player.id)]

    def at_war(self, other: int) -> bool:
        return self._game.at_war(self.player.id, other)

    def at_peace(self, other: int) -> bool:
        return self._game.at_peace(self.player.id, other)

    def relation(self, other: int):
        return self._game.relation(self.player.id, other)

    def is_barbarian(self, other: int) -> bool:
        return self._game.players[other].is_barbarian

    def player_name(self, other: int) -> str:
        return self._game.players[other].civ.nation

    def can_declare_war(self, other: int) -> bool:
        return diplomacy.can_declare_war(self._game, self.player.id, other)

    def known_strength(self, other: int) -> int:
        """Rough power of another civilization from what is known: size of its known cities."""
        return sum(m.size for m in self.player.known_cities.values() if m.owner == other)

    # ── Science and government ────────────────────────────────────────────────

    def research_options(self) -> list[str]:
        return research.research_options(self._game, self.player)

    def research_cost(self) -> int:
        return research.research_cost(self._game, self.player)

    def available_governments(self) -> list[str]:
        return government.available_governments(self._game, self.player)

    def valid_rates(self, tax: int, luxury: int, science: int) -> bool:
        return government.valid_rates(self._game, self.player, tax, luxury, science)

    def budget_with_rates(self, tax: int, luxury: int, science: int) -> tuple[int, int, int]:
        """(net gold per turn, science per turn, cities in disorder) the rates would give."""
        player = self.player
        saved = (player.tax_rate, player.luxury_rate, player.science_rate)
        player.tax_rate, player.luxury_rate, player.science_rate = tax, luxury, science
        try:
            income = science_total = disorder = 0
            for city in self.my_cities():
                stats = city_rules.compute_city(self._game, city)
                if stats.disorder:
                    disorder += 1
                else:
                    income += stats.tax
                income -= stats.building_upkeep
                science_total += stats.science
            return income, science_total, disorder
        finally:
            player.tax_rate, player.luxury_rate, player.science_rate = saved
