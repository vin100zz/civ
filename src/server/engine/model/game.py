"""The complete state of one game."""
from __future__ import annotations

import random
from typing import Callable, Iterable, Optional

from ..rules.schema import BuildingDef, GovernmentDef, Rules, TerrainDef, UnitDef
from .entities import NO_CONTACT, PEACE, WAR, City, Player, Relation, Unit
from .worldmap import Tile, WorldMap


class Game:
    def __init__(self, rules: Rules, seed: int, world: WorldMap) -> None:
        self.rules = rules
        self.seed = seed
        self.rng = random.Random(seed)
        self.map = world
        self.players: list[Player] = []
        self.cities: dict[int, City] = {}
        self.units: dict[int, Unit] = {}
        self.wonders: dict[str, int] = {}             # wonder id -> city id
        self.relations: dict[tuple[int, int], Relation] = {}
        self.turn = 0
        self.year = rules.game.calendar.start_year
        self.current_player: Optional[int] = None     # whose turn is being played
        self.round_position = 0                       # next player of the round (turn.advance)
        self.events: list[dict] = []                  # events of the current turn
        self.finished = False
        self.winner: Optional[int] = None
        self.victory: Optional[str] = None            # conquest | spaceship | score
        self.warming_level = 0                        # see systems/pollution.py
        self.warming_count = 0                        # global warmings so far
        self.changed_tiles: set[int] = set()          # tile indexes modified since last sync
        self.controllers: dict = {}                   # player id -> Controller (systems/turn.py)
        # Whoever shows the game is told of every step: watcher(unit, origin, target, outcome).
        self.watcher: Optional[Callable[[Unit, Tile, Tile, str], None]] = None
        self._next_unit_id = 1
        self._next_city_id = 1
        self._home_index: Optional[dict[int, list[Unit]]] = None   # city id -> supported units

    # ── Lookups ───────────────────────────────────────────────────────────────

    def terrain(self, tile: Tile) -> TerrainDef:
        return self.rules.terrains[tile.terrain]

    def unit_def(self, unit: Unit) -> UnitDef:
        return self.rules.units[unit.type]

    def government(self, player: Player) -> GovernmentDef:
        return self.rules.governments[player.government]

    def building(self, building_id: str) -> BuildingDef:
        return self.rules.buildings[building_id]

    def difficulty(self, player: Player):
        """The difficulty figures of a player: those of the level it chose (a person),
        else the base ones every AI plays with."""
        settings = self.rules.game.difficulty
        return settings.levels.get(player.level, settings)

    def tile_of(self, entity) -> Tile:
        tile = self.map.tile(entity.x, entity.y)
        assert tile is not None
        return tile

    def city_at(self, x: int, y: int) -> Optional[City]:
        tile = self.map.tile(x, y)
        if tile is None or tile.city_id is None:
            return None
        return self.cities.get(tile.city_id)

    def units_at(self, tile: Tile) -> list[Unit]:
        return [self.units[uid] for uid in tile.unit_ids]

    def cargo_of(self, ship: Unit) -> list[Unit]:
        """Units carried by the ship."""
        return [u for u in self.units_at(self.tile_of(ship)) if u.aboard == ship.id]

    def tile_owner(self, tile: Tile) -> Optional[int]:
        """Owner of the units or city standing on the tile, if any."""
        if tile.city_id is not None:
            return self.cities[tile.city_id].owner
        if tile.unit_ids:
            return self.units[tile.unit_ids[0]].owner
        return None

    def player_cities(self, player_id: int) -> list[City]:
        return [c for c in self.cities.values() if c.owner == player_id]

    def player_units(self, player_id: int) -> list[Unit]:
        return [u for u in self.units.values() if u.owner == player_id]

    def units_of_city(self, city: City) -> list[Unit]:
        """Units whose home is the city (the city pays for them)."""
        if self._home_index is None:
            index: dict[int, list[Unit]] = {}
            for unit in self.units.values():
                if unit.home_city is not None:
                    index.setdefault(unit.home_city, []).append(unit)
            self._home_index = index
        return self._home_index.get(city.id, [])

    def set_home(self, unit: Unit, city_id: Optional[int]) -> None:
        unit.home_city = city_id
        self._home_index = None

    @property
    def civilizations(self) -> list[Player]:
        """Living players, barbarians excluded."""
        return [p for p in self.players if p.alive and not p.is_barbarian]

    @property
    def barbarians(self) -> Optional[Player]:
        for player in self.players:
            if player.is_barbarian:
                return player
        return None

    # ── Diplomacy state ───────────────────────────────────────────────────────

    def relation(self, a: int, b: int) -> Relation:
        key = (a, b) if a < b else (b, a)
        relation = self.relations.get(key)
        if relation is None:
            relation = Relation()
            self.relations[key] = relation
        return relation

    def at_war(self, a: int, b: int) -> bool:
        """True if units of a and b may fight. Barbarians fight everybody."""
        if a == b:
            return False
        if self.players[a].is_barbarian or self.players[b].is_barbarian:
            return True
        return self.relation(a, b).state == WAR

    def at_peace(self, a: int, b: int) -> bool:
        return a != b and not self.at_war(a, b) and self.relation(a, b).state == PEACE

    def in_contact(self, a: int, b: int) -> bool:
        return a != b and self.relation(a, b).state != NO_CONTACT

    # ── Entity bookkeeping ────────────────────────────────────────────────────

    def add_unit(self, type_id: str, owner: int, x: int, y: int, *, veteran: bool = False,
                 home_city: Optional[int] = None) -> Unit:
        unit = Unit(id=self._next_unit_id, type=type_id, owner=owner, x=x, y=y,
                    veteran=veteran, home_city=home_city, created_turn=self.turn)
        self._next_unit_id += 1
        unit.moves_left = self.rules.units[type_id].moves * self.rules.game.movement.points_per_move
        unit.fuel = self.rules.units[type_id].fuel
        self.units[unit.id] = unit
        self.tile_of(unit).unit_ids.append(unit.id)
        self._home_index = None
        return unit

    def remove_unit(self, unit: Unit) -> None:
        if unit.id not in self.units:
            return
        tile = self.tile_of(unit)
        if unit.id in tile.unit_ids:
            tile.unit_ids.remove(unit.id)
        del self.units[unit.id]
        self._home_index = None
        # What the unit carried goes down with it, unless it was in port.
        for other in self.units_at(tile):
            if other.aboard == unit.id:
                other.aboard = None
                if not self.terrain(tile).is_land:
                    self.remove_unit(other)

    def place_unit(self, unit: Unit, x: int, y: int) -> None:
        old = self.tile_of(unit)
        if unit.id in old.unit_ids:
            old.unit_ids.remove(unit.id)
        new = self.map.tile(x, y)
        assert new is not None
        unit.x, unit.y = new.x, new.y
        new.unit_ids.append(unit.id)

    def new_city_id(self) -> int:
        city_id = self._next_city_id
        self._next_city_id += 1
        return city_id

    def mark_tile(self, tile: Tile) -> None:
        self.changed_tiles.add(tile.index)

    # ── Events ────────────────────────────────────────────────────────────────

    def emit(self, type_: str, text: str, *, player: Optional[int] = None,
             x: Optional[int] = None, y: Optional[int] = None, **data) -> None:
        event = {"type": type_, "turn": self.turn, "year": self.year, "text": text}
        if player is not None:
            event["player"] = player
        if x is not None:
            event["x"], event["y"] = x, y
        event.update(data)
        self.events.append(event)

    def report_step(self, unit: Unit, origin: Tile, target: Tile, outcome: str) -> None:
        """A unit has just moved, attacked or captured from one tile into the next (the
        outcome is one of systems/movement.py). The unit may have died doing so."""
        if self.watcher is not None:
            self.watcher(unit, origin, target, outcome)

    def living(self, players: Iterable[Player]) -> list[Player]:
        return [p for p in players if p.alive]


__all__ = ["Game", "NO_CONTACT", "WAR", "PEACE"]
