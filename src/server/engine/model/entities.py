"""Game entities: units, cities, players. Plain data; the rules live in engine/systems."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..rules.schema import CivDef

# Unit orders
ORDER_NONE = "none"
ORDER_FORTIFY = "fortify"        # digging in; becomes "fortified" at the start of the next turn
ORDER_FORTIFIED = "fortified"
ORDER_SENTRY = "sentry"
WORK_ORDERS = ("road", "railroad", "irrigate", "mine", "fortress", "clean")

SPECIALISTS = ("entertainer", "taxman", "scientist")

# Diplomatic states between two civilizations
NO_CONTACT = "no_contact"
WAR = "war"
PEACE = "peace"


@dataclass(frozen=True)
class Item:
    """Something a city can build."""
    kind: str      # "unit" | "building"
    id: str


@dataclass
class Unit:
    id: int
    type: str
    owner: int
    x: int
    y: int
    moves_left: int = 0                 # in thirds of a move (movement.points_per_move)
    veteran: bool = False
    home_city: Optional[int] = None
    order: str = ORDER_NONE
    work: int = 0                       # turns already spent on the current work order
    created_turn: int = 0
    aboard: Optional[int] = None        # id of the ship carrying the unit
    fuel: int = 0                       # air units: turns left before they must land

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def fortified(self) -> bool:
        return self.order == ORDER_FORTIFIED


@dataclass
class CityStats:
    """Everything computed for a city in one turn (see systems/city.py)."""
    food: int = 0
    shields: int = 0
    trade: int = 0
    food_eaten: int = 0
    food_surplus: int = 0
    shield_upkeep: int = 0
    shield_surplus: int = 0
    corruption: int = 0
    base_trade: int = 0                 # trade after corruption, before trade routes
    luxury: int = 0
    tax: int = 0
    science: int = 0
    happy: int = 0
    content: int = 0
    unhappy: int = 0
    disorder: bool = False
    celebrating: bool = False
    building_upkeep: int = 0
    supported_units: int = 0
    food_box: int = 0
    pollution: int = 0                  # pollution index (see systems/pollution.py)


@dataclass
class City:
    id: int
    name: str
    owner: int
    x: int
    y: int
    size: int = 1
    food: int = 0
    shields: int = 0
    production: Optional[Item] = None
    buildings: set[str] = field(default_factory=set)
    worked: list[tuple[int, int]] = field(default_factory=list)   # offsets, city tile excluded
    specialists: dict[str, int] = field(default_factory=lambda: {s: 0 for s in SPECIALISTS})
    disorder: bool = False
    celebrating: bool = False
    trade_routes: list[int] = field(default_factory=list)
    founded_turn: int = 0
    founder: int = 0
    base_trade: int = 0                 # copy of stats.base_trade from the last turn
    stats: CityStats = field(default_factory=CityStats)
    bought_this_turn: bool = False
    last_completed: Optional[Item] = None   # what the city finished on its last turn

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def specialist_count(self) -> int:
        return sum(self.specialists.values())


@dataclass
class CityMemory:
    """What a player remembers of a foreign city (last time it was seen)."""
    city_id: int
    name: str
    owner: int
    x: int
    y: int
    size: int
    seen_turn: int
    has_walls: bool = False


@dataclass
class Relation:
    """Diplomatic state between two civilizations."""
    state: str = NO_CONTACT
    since_turn: int = 0
    last_proposal_turn: int = -99


@dataclass
class Spaceship:
    """The spaceship a civilization builds for Alpha Centauri."""
    parts: dict[str, int] = field(default_factory=dict)     # part kind -> number built
    launched_turn: Optional[int] = None
    arrival_turn: Optional[int] = None

    @property
    def launched(self) -> bool:
        return self.launched_turn is not None


@dataclass
class Player:
    id: int
    civ: CivDef
    is_barbarian: bool = False
    alive: bool = True
    gold: int = 0
    tax_rate: int = 50
    luxury_rate: int = 0
    science_rate: int = 50
    government: str = "despotism"
    pending_government: Optional[str] = None      # chosen at the end of the anarchy
    anarchy_until_turn: Optional[int] = None
    techs: set[str] = field(default_factory=set)
    future_techs: int = 0
    researching: Optional[str] = None
    research_progress: int = 0
    explored: bytearray = field(default_factory=bytearray)
    visible: bytearray = field(default_factory=bytearray)
    known_cities: dict[int, CityMemory] = field(default_factory=dict)
    capital_id: Optional[int] = None
    next_city_name: int = 0
    score: int = 0
    destroyed_turn: Optional[int] = None
    spaceship: Spaceship = field(default_factory=Spaceship)
    # last turn totals, for display and for the AI
    income: int = 0
    expenses: int = 0
    science_income: int = 0

    @property
    def name(self) -> str:
        return self.civ.name

    @property
    def tech_count(self) -> int:
        return len(self.techs) + self.future_techs
