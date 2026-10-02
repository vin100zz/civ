"""Per-turn figures of a game, and checks that reveal a stuck AI."""
from __future__ import annotations

from collections import Counter

from ..engine.model.game import Game


class Metrics:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.event_counts: Counter = Counter()
        self._last_growth: dict[int, int] = {}       # player id -> last turn it progressed
        self._last_value: dict[int, tuple] = {}
        self._idle_turns: dict[int, int] = {}        # city id -> turns in a row without production

    def record(self, game: Game) -> None:
        for event in game.events:
            self.event_counts[event["type"]] += 1
        # A city may be idle for one turn (its wonder was just completed elsewhere).
        self._idle_turns = {city.id: self._idle_turns.get(city.id, 0) + 1
                            for city in game.cities.values() if city.production is None}
        for player in game.players:
            if player.is_barbarian:
                continue
            cities = game.player_cities(player.id)
            units = game.player_units(player.id)
            row = {
                "seed": game.seed, "turn": game.turn, "year": game.year,
                "player": player.id, "civ": player.civ.id, "alive": int(player.alive),
                "cities": len(cities), "population": sum(c.size for c in cities),
                "techs": player.tech_count, "units": len(units),
                "military": sum(1 for u in units if game.rules.units[u.type].is_military),
                "settlers": sum(1 for u in units if game.rules.units[u.type].can("found_city")),
                "ships": sum(1 for u in units if game.rules.units[u.type].domain == "sea"),
                "aircraft": sum(1 for u in units if game.rules.units[u.type].domain == "air"),
                "pollution": sum(c.stats.pollution for c in cities),
                "gold": player.gold, "income": player.income - player.expenses,
                "science": player.science_income, "score": player.score,
                "government": player.government,
                "disorder": sum(1 for c in cities if c.disorder),
                "buildings": sum(len(c.buildings) for c in cities),
                "explored": sum(player.explored),
            }
            self.rows.append(row)
            value = (row["cities"], row["population"], row["techs"])
            if value != self._last_value.get(player.id):
                self._last_value[player.id] = value
                self._last_growth[player.id] = game.turn

    def problems(self, game: Game) -> list[str]:
        """Signs that something is wrong with the AI or the rules."""
        found = []
        for player in game.civilizations:
            cities = game.player_cities(player.id)
            idle = game.turn - self._last_growth.get(player.id, 0)
            if idle > 40:
                found.append(f"{player.civ.name}: no growth in cities, population or science "
                             f"for {idle} turns")
            for city in cities:
                if self._idle_turns.get(city.id, 0) > 1:
                    found.append(f"{player.civ.name}: {city.name} builds nothing")
            disorder = sum(1 for c in cities if c.disorder)
            if cities and disorder * 2 > len(cities):
                found.append(f"{player.civ.name}: {disorder}/{len(cities)} cities in disorder")
            if player.gold == 0 and player.income - player.expenses < 0 and cities:
                found.append(f"{player.civ.name}: bankrupt")
        return found
