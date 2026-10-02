"""The AI player: one controller per civilization.

Each turn: look at the world (Knowledge), decide what the empire wants (Plan), then let the
governors pick production and the units carry out their missions. The controller only talks
to the game through a PlayerView, so it knows nothing a human player would not know.
"""
from __future__ import annotations

from typing import Optional

from ..engine import actions
from ..engine.model.entities import Player
from ..engine.model.game import Game
from ..engine.view import PlayerView
from . import diplomacy, economy, research, strategic
from .city_governor import Decision, Governor
from .knowledge import Knowledge
from .missions import Mission
from .unit_ai import aircraft, attacker, caravan, defender, explorer, settler, ship
from .unit_ai.common import Context

# Order in which unit roles act: fighters clear the way before civilians move, and ships
# sail last, once their passengers are aboard.
ROLE_ORDER = {"air_attack": 0, "sea_attack": 1, "attack": 2, "defense": 3, "settler": 4,
              "neutral": 5, "transport": 6, "carrier": 6}
BEHAVIOURS = {"settler": settler.act, "defense": defender.act, "attack": attacker.act,
              "neutral": caravan.act, "air_attack": aircraft.act, "sea_attack": ship.act,
              "transport": ship.act, "carrier": ship.act}


class AIController:
    def __init__(self) -> None:
        self.memory: dict = {}                       # persists across turns (plain data)
        self.unit_missions: dict[int, tuple] = {}    # unit id -> mission key of last turn
        self.decisions: dict[int, Decision] = {}     # city id -> last production decision
        self.debug: dict = {}                        # shown to the observer

    # ── Controller interface (engine/systems/turn.py) ─────────────────────────

    def play_turn(self, game: Game, player: Player) -> None:
        view = PlayerView(game, player)
        know = Knowledge(view)

        notes = diplomacy.review(view, know, self.memory)
        plan = strategic.make_plan(view, know, self.unit_missions, self.memory)
        plan.notes.extend(notes)

        choice = None
        if player.researching is None:
            choice = research.choose(view)
            if choice is not None:
                view.do(actions.SetResearch(choice.tech_id))
                self.memory["research_ranking"] = [list(entry) for entry in choice.ranking]

        period = int(view.rules.ai.get("economy", "rates_review_period"))
        if view.turn % period == player.id % period or player.gold <= 0:
            economy.review_rates(view, know)
        new_government = economy.review_government(view, know, plan, self.memory)
        if new_government is not None:
            plan.notes.append(f"revolution: {new_government}")

        governor = Governor(view, know, plan)
        for city in know.cities:
            if governor.needs_decision(city):
                self._decide(governor, city)
            # Gold is not spent on what a city builds only to keep busy.
            busy_work = city.id in self.memory.get("busy_work", [])
            if governor.maybe_buy(city, emergency_only=busy_work) and city.id in self.decisions:
                self.decisions[city.id].bought = True
        if governor.should_launch_spaceship():
            if view.do(actions.LaunchSpaceship()):
                plan.notes.append("spaceship launched")

        self._trim_army(view, know, plan)
        self._move_units(view, know, plan)
        # Cities founded or captured this turn start building at once.
        for city in view.my_cities():
            if city.production is None:
                self._decide(governor, city)
        self._remember(view, know, plan)

    def _decide(self, governor: Governor, city) -> None:
        decision = governor.decide(city)
        self.decisions[city.id] = decision
        # Remembered (and saved with the game): cities building something just to keep busy.
        busy = set(self.memory.get("busy_work", []))
        busy.discard(city.id)
        if decision.chosen is not None and decision.chosen.score < governor.w("buy_min_score"):
            busy.add(city.id)
        self.memory["busy_work"] = sorted(busy)

    def accepts_peace(self, game: Game, player: Player, proposer: int) -> bool:
        view = PlayerView(game, player)
        return diplomacy.accepts_peace(view, Knowledge(view), proposer)

    # ── Saved games (engine/persistence.py) ───────────────────────────────────

    def save_state(self) -> dict:
        return {"memory": self.memory,
                "unit_missions": [[unit_id, list(key)] for unit_id, key in self.unit_missions.items()]}

    def load_state(self, state: dict) -> None:
        self.memory = dict(state.get("memory", {}))
        self.unit_missions = {unit_id: tuple(key) for unit_id, key in state.get("unit_missions", [])}

    # ── Units ─────────────────────────────────────────────────────────────────

    def _move_units(self, view: PlayerView, know: Knowledge, plan: strategic.Plan) -> None:
        ctx = Context(view, know, plan, self.memory)
        rules = view.rules
        units = sorted(know.units, key=lambda u: (ROLE_ORDER.get(rules.units[u.type].role, 9), u.id))
        for unit in units:
            if view.unit(unit.id) is None or unit.moves_left <= 0:
                continue
            role = rules.units[unit.type].role
            if unit.aboard is not None and rules.units[unit.type].domain == "land":
                continue                         # passengers: their ship puts them ashore
            mission: Optional[Mission] = plan.assignment.get(unit.id)
            if mission is not None and mission.kind == "explore":
                explorer.act(ctx, unit, mission)
                continue
            behaviour = BEHAVIOURS.get(role)
            if behaviour is not None:
                behaviour(ctx, unit, mission)

    def _trim_army(self, view: PlayerView, know: Knowledge, plan: strategic.Plan) -> None:
        """Disbands the units nobody needs any more when their city pays for them:
        garrison leftovers, obsolete units without a mission, transport ships in excess."""
        rules = view.rules
        techs = view.player.techs
        surplus_attackers = plan.attackers_surplus
        spare_transports = sum(1 for u in know.units if rules.units[u.type].role == "transport"
                               and u.id not in plan.assignment and u.id not in plan.reserved) - 1
        for city in know.cities:
            upkeep = city.stats.shield_upkeep
            if upkeep <= 0:
                continue
            idle = []
            for unit in view.units_of_city(city):
                definition = rules.units[unit.type]
                if unit.id in plan.assignment or not definition.needs_support:
                    continue
                if unit.id in plan.reserved or unit.aboard is not None:
                    continue
                obsolete = definition.obsolete_by is not None and definition.obsolete_by in techs
                if definition.role == "defense" or (obsolete and definition.is_military):
                    idle.append(unit)
                elif definition.role == "attack" and surplus_attackers > 0:
                    surplus_attackers -= 1
                    idle.append(unit)
                elif definition.role == "transport" and spare_transports > 0:
                    spare_transports -= 1
                    idle.append(unit)
            idle.sort(key=lambda u: (rules.units[u.type].attack + rules.units[u.type].defense, u.id))
            for unit in idle[:upkeep]:
                view.do(actions.Disband(unit.id))
                plan.notes.append(f"disbanded {rules.units[unit.type].name} of {city.name}")

    # ── Observer information ──────────────────────────────────────────────────

    def _remember(self, view: PlayerView, know: Knowledge, plan: strategic.Plan) -> None:
        self.unit_missions = {uid: m.key for uid, m in plan.assignment.items()
                              if view.unit(uid) is not None}
        alive_cities = {c.id for c in view.my_cities()}
        self.decisions = {cid: d for cid, d in self.decisions.items() if cid in alive_cities}
        self.memory["busy_work"] = [cid for cid in self.memory.get("busy_work", [])
                                    if cid in alive_cities]
        self.debug = {
            "turn": view.turn,
            "needs": {
                "settlers": plan.settlers_wanted, "workers": plan.workers_wanted,
                "attackers": plan.attackers_wanted, "explorers": plan.explorers_wanted,
                "defenders": sum(plan.defenders_missing.values()),
                "ships": len(plan.ferries_wanted) + len(plan.sea_explorers_wanted)
                + plan.warships_wanted,
                "aircraft": plan.aircraft_wanted + plan.nuclear_wanted,
            },
            "expeditions": [dict(e) for e in self.memory.get("expeditions", [])],
            "spaceship": view.spaceship_parts(),
            "at_war_with": [view.player_name(e) for e in plan.enemies],
            "targets": [m.name for m in plan.war_targets],
            "notes": plan.notes,
            "missions": [
                {"kind": m.kind, "x": m.x, "y": m.y, "priority": round(m.priority, 1),
                 "units": len(m.assigned), "capacity": m.capacity, "note": m.note}
                for m in sorted(plan.missions, key=lambda m: -m.priority)[:25]
            ],
            "research": self.memory.get("research_ranking", []),
        }
