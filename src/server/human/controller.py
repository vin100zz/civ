"""A civilization led by a person.

The engine stops at this player's turn and waits for the person's actions (turn.advance).
The controller looks after what the person delegated: units on their way somewhere,
explorers and workers left to themselves, cities given to a governor. It borrows the AI's
own tools for that and, like the AI, only sees the game through a PlayerView.
"""
from __future__ import annotations

from typing import Optional

from ..ai import missions, pathfinding, strategic
from ..ai.city_governor import Governor
from ..ai.knowledge import Knowledge
from ..ai.unit_ai import explorer, settler
from ..ai.unit_ai.common import Context
from ..engine import actions
from ..engine.model.entities import ORDER_NONE, ORDER_SENTRY, City, Player, Unit
from ..engine.model.game import Game
from ..engine.model.worldmap import Tile
from ..engine.view import PlayerView

GOTO = "goto"
EXPLORE = "explore"
WORK = "work"
AUTOMATIONS = (EXPLORE, WORK)

# How a journey went this turn
ARRIVED = "arrived"
MOVING = "moving"
BLOCKED = "blocked"
DEAD = "dead"


class HumanController:
    interactive = True                  # turn.advance waits for the person's actions

    def __init__(self) -> None:
        # Plain data, saved with the game. Unit ids are text: JSON keys.
        self.memory: dict = {"goto": {}, "auto": {}, "governed": []}
        self.work_missions: dict[int, tuple] = {}     # worker id -> its job of last turn
        self.notes: list[dict] = []     # what the delegated units and cities did this turn

    # ── Controller interface (engine/systems/turn.py) ─────────────────────────

    def begin_turn(self, game: Game, player: Player) -> None:
        """Start of the person's turn: everything it delegated is carried out first."""
        view = PlayerView(game, player)
        self.notes = []
        self._forget_the_gone(view)
        self._wake_sentries(view)
        if self.memory["auto"] or self.memory["governed"]:
            know = Knowledge(view)
            self._govern_cities(view, know)
            self._run_automated(view, know)
        self._continue_journeys(view)

    def play_turn(self, game: Game, player: Player) -> None:
        """A turn played without the person (headless runs): only delegated work is done."""
        self.begin_turn(game, player)

    def accepts_peace(self, game: Game, player: Player, proposer: int) -> Optional[bool]:
        return None                     # the person answers during its own turn

    # ── Saved games (engine/persistence.py) ───────────────────────────────────

    def save_state(self) -> dict:
        return {"memory": self.memory,
                "work": [[unit_id, list(key)] for unit_id, key in self.work_missions.items()]}

    def load_state(self, state: dict) -> None:
        memory = state.get("memory", {})
        self.memory = {"goto": dict(memory.get("goto", {})), "auto": dict(memory.get("auto", {})),
                       "governed": list(memory.get("governed", []))}
        self.work_missions = {unit_id: tuple(key) for unit_id, key in state.get("work", [])}

    # ── What the person delegates ─────────────────────────────────────────────

    def send(self, view: PlayerView, unit: Unit, goal: Tile) -> str:
        """Go-to: the unit sets off at once and keeps going on the following turns."""
        self.release(unit.id)
        status = travel(view, unit, goal)
        if status == MOVING:
            self.memory["goto"][str(unit.id)] = [goal.x, goal.y]
        return status

    def automate(self, view: PlayerView, unit: Unit, mode: str) -> bool:
        """Leaves a unit to itself: `explore` for any land or sea unit, `work` for settlers."""
        definition = view.rules.units[unit.type]
        if mode == EXPLORE and definition.domain == "air":
            return False
        if mode == WORK and not definition.can("terraform"):
            return False
        if mode not in AUTOMATIONS:
            return False
        self.release(unit.id)
        self.memory["auto"][str(unit.id)] = mode
        self._run_automated(view, Knowledge(view), only=unit.id)
        return True

    def release(self, unit_id: int) -> None:
        """The person takes the unit back in hand."""
        self.memory["goto"].pop(str(unit_id), None)
        self.memory["auto"].pop(str(unit_id), None)
        self.work_missions.pop(unit_id, None)

    def govern(self, view: PlayerView, city: City, on: bool) -> None:
        """Gives a city to a governor (it decides at once if the city builds nothing useful),
        or takes it back."""
        governed = set(self.memory["governed"])
        (governed.add if on else governed.discard)(city.id)
        self.memory["governed"] = sorted(governed)
        if on:
            self._govern_cities(view, Knowledge(view), only=city.id)

    def task(self, unit_id: int) -> str:
        """"goto", "explore", "work", or "" for a unit waiting for the person's orders."""
        if str(unit_id) in self.memory["goto"]:
            return GOTO
        return self.memory["auto"].get(str(unit_id), "")

    def destination(self, unit_id: int) -> Optional[list[int]]:
        return self.memory["goto"].get(str(unit_id))

    def governed(self, city_id: int) -> bool:
        return city_id in self.memory["governed"]

    # ── Start of turn ─────────────────────────────────────────────────────────

    def _note(self, text: str, x: int, y: int, **data) -> None:
        self.notes.append({"text": text, "x": x, "y": y, **data})

    def _forget_the_gone(self, view: PlayerView) -> None:
        alive = {str(unit.id) for unit in view.my_units()}
        for table in ("goto", "auto"):
            self.memory[table] = {k: v for k, v in self.memory[table].items() if k in alive}
        mine = {city.id for city in view.my_cities()}
        self.memory["governed"] = [cid for cid in self.memory["governed"] if cid in mine]

    def _wake_sentries(self, view: PlayerView) -> None:
        """A sentry wakes up when an enemy comes next to it."""
        for unit in view.my_units():
            if unit.order != ORDER_SENTRY or unit.aboard is not None:
                continue
            if any(view.enemy_units_at(tile) for tile in view.map.neighbors(view.tile_of(unit))):
                view.do(actions.SetOrder(unit.id, ORDER_NONE))
                self._note(f"{view.rules.units[unit.type].name} on sentry duty wakes up: "
                           f"enemy in sight.", unit.x, unit.y, unit=unit.id)

    def _continue_journeys(self, view: PlayerView) -> None:
        for key, (x, y) in sorted(self.memory["goto"].items(), key=lambda item: int(item[0])):
            unit = view.unit(int(key))
            if unit is None:
                continue
            name = view.rules.units[unit.type].name
            status = travel(view, unit, view.map.tile(x, y))
            if status == MOVING:
                continue
            del self.memory["goto"][key]
            if status == BLOCKED:
                self._note(f"{name} cannot go on: the way is blocked.", unit.x, unit.y,
                           unit=unit.id)

    def _govern_cities(self, view: PlayerView, know: Knowledge,
                       only: Optional[int] = None) -> None:
        """Governed cities choose what to build the way an AI city would."""
        cities = [city for city in know.cities
                  if self.governed(city.id) and only in (None, city.id)]
        if not cities:
            return
        plan = strategic.make_plan(view, know, {}, {})
        # A governor serves its city: it does not fit out expeditions across the sea.
        plan.ferries_wanted, plan.sea_explorers_wanted = {}, {}
        governor = Governor(view, know, plan)
        for city in cities:
            if not governor.needs_decision(city):
                continue
            before = city.production
            governor.decide(city)
            if city.production is not None and city.production != before:
                self._note(f"The governor of {city.name} starts building "
                           f"{view.item_name(city.production)}.", city.x, city.y, city=city.id)

    def _run_automated(self, view: PlayerView, know: Knowledge,
                       only: Optional[int] = None) -> None:
        ctx = Context(view, know, None, {})
        workers = []
        for key, mode in sorted(self.memory["auto"].items(), key=lambda item: int(item[0])):
            unit = view.unit(int(key))
            if unit is None or (only is not None and unit.id != only):
                continue
            if mode == WORK:
                workers.append(unit)
            elif not explorer.has_frontier(ctx, unit):
                del self.memory["auto"][key]
                self._note(f"{view.rules.units[unit.type].name} has nothing left to explore.",
                           unit.x, unit.y, unit=unit.id)
            elif unit.moves_left > 0:
                explorer.act(ctx, unit, None)
        if workers:
            self._work(ctx, workers)

    def _work(self, ctx: Context, workers: list[Unit]) -> None:
        """Automated settlers share the terrain work an AI would do around the cities."""
        view, know = ctx.view, ctx.know
        plan = strategic.Plan()
        strategic.improve_missions(view, know, plan)
        ids = {unit.id for unit in workers}
        others = frozenset(unit.id for unit in know.units if unit.id not in ids)
        assignment = missions.assign(view, know, plan.missions, self.work_missions, others)
        for unit in workers:
            mission = assignment.get(unit.id)
            if mission is not None and view.unit(unit.id) is not None:
                settler.act(ctx, unit, mission)
        kept = {unit_id: key for unit_id, key in self.work_missions.items() if unit_id not in ids}
        self.work_missions = {**kept, **{unit_id: m.key for unit_id, m in assignment.items()}}


def travel(view: PlayerView, unit: Unit, goal: Tile) -> str:
    """Moves a unit along the route it knows as far as its movement allows. A unit on its way
    never starts a fight: it stops in front of foreign units and cities."""
    path = pathfinding.find_path(view, unit, goal)
    if path is None:
        return BLOCKED
    for step in path:
        if unit.moves_left <= 0:
            return MOVING
        if view.foreign_units_at(step) or view.foreign_city_at(step) is not None:
            return BLOCKED
        result = view.do(actions.MoveUnit(unit.id, step.x, step.y))
        if view.unit(unit.id) is None:
            return DEAD
        if not result.ok:
            return BLOCKED
        if result.outcome != "moved":
            return MOVING                   # stalled on rough ground: it goes on next turn
    return ARRIVED
