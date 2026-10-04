"""The orders a person sends from the browser, turned into engine actions.

A message looks like {"cmd": "action", "action": "move", "unit": 12, "x": 4, "y": 7}.
Each entry below names the engine action and the fields it takes from the message, with
their type; a message that does not fit gives no action at all.
"""
from __future__ import annotations

from typing import Any, Optional

from ..engine import actions

# order name -> (action, ((message key, action field, type), ...))
ORDERS: dict[str, tuple[type, tuple[tuple[str, str, type], ...]]] = {
    "move": (actions.MoveUnit, (("unit", "unit_id", int), ("x", "x", int), ("y", "y", int))),
    "board": (actions.Board, (("unit", "unit_id", int), ("ship", "ship_id", int))),
    "disembark": (actions.Disembark, (("unit", "unit_id", int),)),
    "found_city": (actions.FoundCity, (("unit", "unit_id", int),)),
    "join_city": (actions.JoinCity, (("unit", "unit_id", int),)),
    "order": (actions.SetOrder, (("unit", "unit_id", int), ("order", "order", str))),
    "disband": (actions.Disband, (("unit", "unit_id", int),)),
    "home": (actions.Rehome, (("unit", "unit_id", int),)),
    "help_wonder": (actions.HelpBuildWonder, (("unit", "unit_id", int),)),
    "trade_route": (actions.EstablishTradeRoute, (("unit", "unit_id", int),)),
    "production": (actions.SetProduction,
                   (("city", "city_id", int), ("kind", "kind", str), ("id", "id", str))),
    "buy": (actions.Buy, (("city", "city_id", int),)),
    "arrange": (actions.ArrangeWorkers, (("city", "city_id", int),)),
    "tile": (actions.ToggleTile, (("city", "city_id", int), ("dx", "dx", int), ("dy", "dy", int))),
    "specialist": (actions.ChangeSpecialist, (("city", "city_id", int), ("kind", "kind", str))),
    "sell": (actions.SellBuilding, (("city", "city_id", int), ("building", "building", str))),
    "research": (actions.SetResearch, (("tech", "tech_id", str),)),
    "rates": (actions.SetRates,
              (("tax", "tax", int), ("luxury", "luxury", int), ("science", "science", int))),
    "revolution": (actions.Revolution, (("government", "government", str),)),
    "war": (actions.DeclareWar, (("player", "target", int),)),
    "peace": (actions.ProposePeace, (("player", "target", int),)),
    "answer_peace": (actions.AnswerPeace, (("player", "other", int), ("accept", "accept", bool))),
    "launch": (actions.LaunchSpaceship, ()),
}


def parse(message: dict[str, Any]) -> Optional[actions.Action]:
    """The engine action a message asks for, or None if it is not a well-formed order."""
    entry = ORDERS.get(message.get("action"))
    if entry is None:
        return None
    action, fields = entry
    values = {}
    for key, name, kind in fields:
        value = message.get(key)
        if type(value) is not kind:             # a bool is not an int here
            return None
        values[name] = value
    return action(**values)
