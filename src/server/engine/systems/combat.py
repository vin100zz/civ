"""Combat between units.

Source: OpenCivOne Segment_29f3.cs F0_29f3_000e. One roll decides the fight: each side
draws a number below its strength and the attacker must draw strictly more.
Strengths are integers on the original scale (attack x 8).
Who may attack what (ships, aircraft, units aboard): CheckPlayerTurn.cs around line 1400.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .. import effects as fx
from ..model.entities import City, Unit
from ..model.game import Game
from ..model.worldmap import Tile
from . import cities
from . import city as city_rules

SCALE = 8


@dataclass(frozen=True)
class Odds:
    attack: int
    defense: int

    @property
    def win_chance(self) -> float:
        """Probability that the attacker wins a single roll."""
        a, d = self.attack, self.defense
        if a <= 0:
            return 0.0
        if d <= 0:
            return 1.0
        # P(x > y) for x uniform in [0, a), y uniform in [0, d)
        wins = sum(min(x, d) for x in range(a))
        return wins / (a * d)


def defenders(game: Game, tile: Tile, attacker: Optional[Unit] = None) -> list[Unit]:
    """Units of a tile that can be fought by this attacker.

    Passengers of a ship at sea do not fight, and aircraft in flight can only be engaged
    by units able to attack them (fighters).
    """
    units = game.units_at(tile)
    if not game.terrain(tile).is_land:
        units = [u for u in units if u.aboard is None]
    if tile.city_id is None and attacker is not None \
            and not game.rules.units[attacker.type].can("attack_air"):
        units = [u for u in units if game.rules.units[u.type].domain != "air"]
    return units


def best_defender(game: Game, tile: Tile, attacker: Optional[Unit] = None) -> Optional[Unit]:
    """The unit that defends a tile: the one with the highest defense strength there."""
    units = defenders(game, tile, attacker)
    if not units:
        return None
    return max(units, key=lambda u: (defense_strength(game, u, tile, attacker), -u.id))


def why_cannot_attack(game: Game, attacker: Unit, tile: Tile) -> Optional[str]:
    """None if the unit may attack the enemy units on the tile, else the reason."""
    definition = game.rules.units[attacker.type]
    if definition.attack <= 0:
        return "unit cannot attack"
    on_land = game.terrain(tile).is_land
    if definition.domain == "land":
        if not on_land:
            return "land units cannot attack ships"
        if not game.terrain(game.tile_of(attacker)).is_land:
            return "units cannot attack from a ship"
    if definition.domain == "sea" and on_land and definition.can("no_shore_attack"):
        return "unit cannot attack land"
    if not defenders(game, tile, attacker):
        return "unit cannot attack aircraft"
    return None


def defense_strength(game: Game, defender: Unit, tile: Tile, attacker: Optional[Unit]) -> int:
    settings = game.rules.game.combat
    definition = game.rules.units[defender.type]
    if definition.domain != "land":
        strength = definition.defense * SCALE
    else:
        multiplier = game.terrain(tile).defense
        if tile.fortress:
            multiplier *= settings.fortress_multiplier
        elif defender.fortified:
            multiplier *= settings.fortified_multiplier
        walls = city_wall_factor(game, tile, attacker)
        if walls is not None:
            multiplier = game.terrain(tile).defense * walls
        strength = int(definition.defense * SCALE * multiplier)
    if defender.veteran:
        strength = int(strength * settings.veteran_multiplier)
    return strength


def city_wall_factor(game: Game, tile: Tile, attacker: Optional[Unit]) -> Optional[float]:
    """Defense factor of the walls of the city on the tile against this attacker, if any."""
    if tile.city_id is None:
        return None
    city = game.cities[tile.city_id]
    if attacker is not None:
        attacking = game.rules.units[attacker.type]
        if attacking.can("ignore_walls"):
            return None
        attacker_domain = attacking.domain
    else:
        attacker_domain = "land"
    for effect in fx.city_effects(game, city):
        if effect.type == "defense_multiplier" and effect.vs in (None, attacker_domain):
            return effect.factor
    return None


def attack_strength(game: Game, attacker: Unit, tile: Tile) -> int:
    settings = game.rules.game.combat
    movement = game.rules.game.movement
    definition = game.rules.units[attacker.type]
    strength = definition.attack * SCALE
    owner = game.players[attacker.owner]
    if owner.is_barbarian:
        strength = int(strength * settings.barbarian_attack_multiplier)
        if tile.city_id is not None:
            city = game.cities[tile.city_id]
            if settings.barbarians_spare_last_city and len(game.player_cities(city.owner)) <= 1:
                strength = 0
            elif fx.is_capital(game, city):
                strength = int(strength * settings.barbarian_vs_capital_multiplier)
    if attacker.veteran:
        strength = int(strength * settings.veteran_multiplier)
    if attacker.moves_left < movement.points_per_move:
        strength = attacker.moves_left * strength // movement.points_per_move
    return strength


def odds(game: Game, attacker: Unit, tile: Tile, defender: Optional[Unit] = None) -> Optional[Odds]:
    if defender is None:
        defender = best_defender(game, tile, attacker)
    if defender is None:
        return None
    return Odds(attack_strength(game, attacker, tile),
                defense_strength(game, defender, tile, attacker))


def explain(game: Game, attacker: Unit, tile: Tile) -> Optional[dict]:
    """The odds of an attack and what makes them, for a player weighing it: strengths in
    unit points, chance to win, and the multipliers at work on each side."""
    defender = best_defender(game, tile, attacker)
    if defender is None:
        return None
    settings = game.rules.game.combat
    strengths = odds(game, attacker, tile, defender)
    attacking = game.rules.units[attacker.type]
    defending = game.rules.units[defender.type]
    terrain = game.terrain(tile)

    attack_factors = []
    if attacker.veteran:
        attack_factors.append(f"veteran x{settings.veteran_multiplier:g}")
    if attacker.moves_left < game.rules.game.movement.points_per_move:
        attack_factors.append("tired")
    defense_factors = []
    if defending.domain == "land":
        walls = city_wall_factor(game, tile, attacker)
        if terrain.defense != 1:
            defense_factors.append(f"{terrain.name.lower()} x{terrain.defense:g}")
        if walls is not None:
            defense_factors.append(f"city walls x{walls:g}")
        elif tile.fortress:
            defense_factors.append(f"fortress x{settings.fortress_multiplier:g}")
        elif defender.fortified:
            defense_factors.append(f"fortified x{settings.fortified_multiplier:g}")
    if defender.veteran:
        defense_factors.append(f"veteran x{settings.veteran_multiplier:g}")
    return {
        "attacker": attacking.name, "attack_base": attacking.attack,
        "attack": round(strengths.attack / SCALE, 1), "attack_factors": attack_factors,
        "defender": defending.name, "defender_owner": defender.owner,
        "defense_base": defending.defense,
        "defense": round(strengths.defense / SCALE, 1), "defense_factors": defense_factors,
        "win": round(strengths.win_chance, 3), "stack": len(defenders(game, tile, attacker)),
    }


def attack(game: Game, attacker: Unit, tile: Tile) -> bool:
    """Resolves an attack on a tile. Returns True if the attacker wins."""
    settings = game.rules.game.combat
    movement = game.rules.game.movement
    defender = best_defender(game, tile, attacker)
    assert defender is not None
    strengths = odds(game, attacker, tile, defender)
    a, d = strengths.attack, strengths.defense

    def roll() -> bool:
        if a <= 0:
            return False
        if d <= 0:
            return True
        return game.rng.randrange(a) > game.rng.randrange(d)

    won = roll()
    if won and game.players[attacker.owner].is_barbarian and tile.city_id is not None:
        won = roll()                    # barbarians must break into a city twice

    attacker_def = game.rules.units[attacker.type]
    defender_def = game.rules.units[defender.type]
    attacker_owner = game.players[attacker.owner]
    defender_owner = game.players[defender.owner]
    winner, loser = (attacker_owner, defender_owner) if won else (defender_owner, attacker_owner)
    game.emit(
        "combat",
        f"{attacker_owner.civ.name} {attacker_def.name} attacks {defender_owner.civ.name} "
        f"{defender_def.name}: {winner.civ.name} victory.",
        player=attacker.owner, other=defender.owner, x=tile.x, y=tile.y,
        attacker=attacker.type, defender=defender.type, attacker_won=won,
        attack=a, defense=d, winner=winner.id, loser=loser.id)

    if won:
        _defender_lost(game, attacker, defender, tile)
        attacker.moves_left = max(0, attacker.moves_left - movement.points_per_move)
        if not attacker.veteran and game.rng.random() < settings.veteran_promotion_chance:
            attacker.veteran = True
    else:
        game.remove_unit(attacker)
        if not defender.veteran and game.rng.random() < settings.veteran_promotion_chance:
            defender.veteran = True
    cities.check_elimination(game, loser)
    return won


def _defender_lost(game: Game, attacker: Unit, defender: Unit, tile: Tile) -> None:
    """The whole stack dies with its defender, except in a city or a fortress."""
    settings = game.rules.game.combat
    city: Optional[City] = game.cities.get(tile.city_id) if tile.city_id is not None else None
    if city is None and not tile.fortress:
        for unit in list(game.units_at(tile)):
            game.remove_unit(unit)
        return
    game.remove_unit(defender)
    if city is not None and settings.city_shrinks_on_defeat and city.size > 1 \
            and city_wall_factor(game, tile, None) is None:
        city.size -= 1
        city_rules.auto_arrange(game, city)
