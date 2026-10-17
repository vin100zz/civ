"""What the replay at the end of a game shows, noted turn by turn while it is played.

The replay draws the whole world at each turn of the game: where the cities stood, who held
them and how big they were, where the battles were fought, and the great events. The session
notes it whenever it notes the figures of the History (one row per turn) and keeps it in the
saves. It shows every civilization: a person leading one only gets it once nothing is hidden
any more (the game is over, or its civilization destroyed).

The cities are noted as changes, a few entries per turn for the whole world:

    ["found", turn, city id, owner, x, y, name, size]
    ["owner", turn, city id, owner]
    ["size", turn, city id, size]
    ["gone", turn, city id]

`turn` is that of the History row they belong to: the world as it stands when that turn
begins. The events keep their own turn, the one they happened in.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from ..engine.model.game import Game

# The events the replay tells of, in its chronicle and on the map. Combats are kept apart,
# as battles: where, who won, who lost.
HEADLINES = ("city_founded", "city_captured", "city_destroyed", "civ_destroyed", "wonder",
             "government", "war", "peace", "contact", "spaceship_launched", "spaceship_lost",
             "nuclear", "global_warming", "game_over")
EVENT_FIELDS = ("type", "turn", "year", "text", "player", "other", "x", "y")


class Replay:
    def __init__(self, since: int = 0) -> None:
        self.since = since                      # the first turn noted in full
        self.cities: list[list[Any]] = []
        self.events: list[dict[str, Any]] = []
        self.battles: list[list[int]] = []      # [turn, x, y, winner, loser]
        self._noted: dict[int, tuple[int, int]] = {}    # city id -> (owner, size) last noted

    def note_cities(self, game: Game) -> None:
        """Notes what changed in the cities since the last turn, as `game.turn` begins."""
        turn = game.turn
        for city in game.cities.values():
            noted = self._noted.get(city.id)
            if noted is None:
                self.cities.append(["found", turn, city.id, city.owner, city.x, city.y,
                                    city.name, city.size])
            else:
                if noted[0] != city.owner:
                    self.cities.append(["owner", turn, city.id, city.owner])
                if noted[1] != city.size:
                    self.cities.append(["size", turn, city.id, city.size])
            self._noted[city.id] = (city.owner, city.size)
        for city_id in [c for c in self._noted if c not in game.cities]:
            self.cities.append(["gone", turn, city_id])
            del self._noted[city_id]

    def note_events(self, events: Iterable[dict]) -> None:
        """Keeps the great events and the battles among events just read."""
        for event in events:
            if event["type"] == "combat":
                self.battles.append([event["turn"], event["x"], event["y"], event["winner"],
                                     event["loser"]])
            elif event["type"] in HEADLINES:
                self.events.append({key: event[key] for key in EVENT_FIELDS if key in event})

    def payload(self) -> dict[str, Any]:
        """What the browsers get, and what the saves keep."""
        return {"since": self.since, "cities": self.cities, "events": self.events,
                "battles": self.battles}

    @classmethod
    def restore(cls, data: Optional[dict], game: Game, log: Iterable[dict]) -> "Replay":
        """The replay of a saved game. A game saved before replays were noted gets what can
        be told of it: its cities as they are now, each from the turn it was founded, and
        the events its chronicle still holds. It is noted in full from now on."""
        if data:
            replay = cls(data["since"])
            replay.cities, replay.events, replay.battles = (
                data["cities"], data["events"], data["battles"])
            for change in replay.cities:
                kind, city_id = change[0], change[2]
                if kind == "found":
                    replay._noted[city_id] = (change[3], change[7])
                elif kind == "owner":
                    replay._noted[city_id] = (change[3], replay._noted[city_id][1])
                elif kind == "size":
                    replay._noted[city_id] = (replay._noted[city_id][0], change[3])
                else:
                    del replay._noted[city_id]
            return replay
        replay = cls(game.turn)
        for city in sorted(game.cities.values(), key=lambda c: (c.founded_turn, c.id)):
            replay.cities.append(["found", city.founded_turn + 1, city.id, city.owner, city.x,
                                  city.y, city.name, city.size])
            replay._noted[city.id] = (city.owner, city.size)
        replay.note_events(log)
        return replay


__all__ = ["Replay", "HEADLINES"]
