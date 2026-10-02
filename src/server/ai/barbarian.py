"""The barbarians: no strategy, no knowledge limits, they march on the nearest city.

Barbarians are not a civilization, so unlike AIController this controller reads the game
directly. Those who come by sea sail to the nearest coastal city, land next to it and
send their ship away.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

from ..engine import actions
from ..engine.model.entities import ORDER_FORTIFIED, ORDER_FORTIFY, City, Player, Unit
from ..engine.model.game import Game
from ..engine.model.worldmap import Tile
from ..engine.systems import combat, movement, production


class BarbarianController:
    def __init__(self) -> None:
        self.debug: dict = {}

    def play_turn(self, game: Game, player: Player) -> None:
        for city in game.player_cities(player.id):
            self._manage_city(game, city)
        for unit in sorted(game.player_units(player.id), key=lambda u: u.id):
            if unit.id in game.units:
                self._move(game, player, unit)

    def accepts_peace(self, game: Game, player: Player, proposer: int) -> bool:
        return False

    def _manage_city(self, game: Game, city: City) -> None:
        if city.production is not None and production.can_build(game, city, city.production):
            return
        options = [i for i in production.production_options(game, city) if i.kind == "unit"]
        if options:
            best = max(options, key=lambda i: (game.rules.units[i.id].attack, i.id))
            actions.apply(game, city.owner, actions.SetProduction(city.id, best.kind, best.id))

    def _move(self, game: Game, player: Player, unit: Unit) -> None:
        if game.rules.units[unit.type].domain == "sea":
            self._sail(game, player, unit)
            return
        if unit.aboard is not None:
            return                               # its ship decides when to land
        here = game.tile_of(unit)
        # One unit holds each captured city.
        if here.city_id is not None:
            garrison = [u for u in game.units_at(here) if u.order in (ORDER_FORTIFY, ORDER_FORTIFIED)]
            if not garrison or unit in garrison:
                if unit.order not in (ORDER_FORTIFY, ORDER_FORTIFIED):
                    actions.apply(game, player.id, actions.SetOrder(unit.id, ORDER_FORTIFY))
                return
        while unit.id in game.units and unit.moves_left > 0:
            target = self._adjacent_target(game, unit)
            if target is None:
                target = self._step_toward_city(game, unit)
            if target is None:
                return
            result = actions.apply(game, player.id, actions.MoveUnit(unit.id, target.x, target.y))
            if not result.ok or result.outcome != "moved":
                return

    def _adjacent_target(self, game: Game, unit: Unit) -> Optional[Tile]:
        """An adjacent enemy worth attacking: cities first, then the weakest stack."""
        best = None
        for tile in game.map.neighbors(game.tile_of(unit)):
            if not movement.can_enter(game, unit, tile):
                continue
            owner = game.tile_owner(tile)
            if owner is None or owner == unit.owner:
                continue
            if not tile.unit_ids:
                return tile                      # undefended city
            odds = combat.odds(game, unit, tile)
            chance = odds.win_chance if odds else 0.0
            if tile.city_id is not None:
                chance += 1.0                    # barbarians never give up on a city
            if chance >= game.rules.game.barbarians.min_attack_odds \
                    and (best is None or chance > best[0]):
                best = (chance, tile)
        return best[1] if best else None

    def _step_toward_city(self, game: Game, unit: Unit) -> Optional[Tile]:
        here = game.tile_of(unit)
        cities = [c for c in game.cities.values() if c.owner != unit.owner
                  and game.tile_of(c).continent == here.continent
                  and game.map.steps(unit.x, unit.y, c.x, c.y) <= game.rules.game.barbarians.march_radius]
        if not cities:
            return None
        goal = min(cities, key=lambda c: (game.map.steps(unit.x, unit.y, c.x, c.y), c.id))
        current = game.map.steps(unit.x, unit.y, goal.x, goal.y)
        options = []
        for tile in game.map.neighbors(here):
            if game.tile_owner(tile) not in (None, unit.owner):
                continue
            if not movement.can_enter(game, unit, tile):
                continue
            distance = game.map.steps(tile.x, tile.y, goal.x, goal.y)
            if distance < current:
                options.append((distance, game.terrain(tile).move_cost, tile.index, tile))
        if not options:
            return None
        return min(options)[3]

    # ── Raids from the sea ────────────────────────────────────────────────────

    def _sail(self, game: Game, player: Player, ship: Unit) -> None:
        """Carries the raiders to the shore of the nearest city, then leaves."""
        if not game.cargo_of(ship):
            actions.apply(game, player.id, actions.Disband(ship.id))
            return
        for _ in range(game.rules.units[ship.type].moves + 2):
            if ship.id not in game.units or ship.moves_left <= 0:
                return
            if self._land(game, player, ship):
                return
            step = self._step_to_shore(game, ship)
            if step is None:
                # Nowhere to land: the raid is called off.
                actions.apply(game, player.id, actions.Disband(ship.id))
                return
            result = actions.apply(game, player.id, actions.MoveUnit(ship.id, step.x, step.y))
            if not result.ok or result.outcome != "moved":
                return

    def _beach(self, game: Game, ship: Unit, tile: Tile) -> list[Tile]:
        """Free land next to a sea tile where raiders could go ashore near a city."""
        radius = 2
        result = []
        for land in game.map.neighbors(tile):
            if not game.terrain(land).is_land or land.city_id is not None:
                continue
            if game.tile_owner(land) not in (None, ship.owner):
                continue
            if any(c.owner != ship.owner and game.map.steps(land.x, land.y, c.x, c.y) <= radius
                   for c in game.cities.values()):
                result.append(land)
        return result

    def _land(self, game: Game, player: Player, ship: Unit) -> bool:
        """Puts the raiders ashore if the ship has reached a beach. True when it is done."""
        beach = self._beach(game, ship, game.tile_of(ship))
        if not beach:
            return False

        def nearest_city(tile: Tile) -> int:
            return min(game.map.steps(tile.x, tile.y, c.x, c.y)
                       for c in game.cities.values() if c.owner != ship.owner)

        target = min(beach, key=lambda t: (nearest_city(t), t.index))
        for raider in game.cargo_of(ship):
            actions.apply(game, player.id, actions.MoveUnit(raider.id, target.x, target.y))
        if ship.id in game.units and not game.cargo_of(ship):
            actions.apply(game, player.id, actions.Disband(ship.id))
            return True
        return False

    def _step_to_shore(self, game: Game, ship: Unit) -> Optional[Tile]:
        """First step of the shortest sea route to a beach (breadth-first over open water)."""
        start = game.tile_of(ship)
        first: dict[int, Tile] = {}
        queue: deque[Tile] = deque([start])
        seen = {start.index}
        visited = 0
        while queue and visited < 1500:
            tile = queue.popleft()
            visited += 1
            if tile is not start and self._beach(game, ship, tile):
                return first[tile.index]
            for other in game.map.neighbors(tile):
                if other.index in seen:
                    continue
                seen.add(other.index)
                if game.terrain(other).is_land or other.unit_ids:
                    continue
                first[other.index] = other if tile is start else first[tile.index]
                queue.append(other)
        return None
