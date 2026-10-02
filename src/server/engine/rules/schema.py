"""Typed, immutable view of everything in config/.

Each dataclass mirrors one YAML structure. The loader (loader.py) fills them and rejects
unknown keys, wrong types and dangling references, so the rest of the code can trust them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ── Vocabulary ────────────────────────────────────────────────────────────────

DOMAINS = ("land", "sea", "air")
ROLES = ("settler", "defense", "attack", "sea_attack", "air_attack", "transport", "carrier",
         "neutral")
ABILITIES = ("found_city", "terraform", "trade", "ignore_zoc", "ignore_walls",
             "coastal",            # may be lost at sea when it ends its turn away from land
             "attack_air",         # may attack aircraft in flight
             "no_shore_attack",    # cannot attack units on land
             "nuclear")            # destroys everything around its target, and itself
CARGO_KINDS = ("land", "air")
YIELD_KINDS = ("shields", "tax", "luxury", "science")
EFFECT_SCOPES = ("city", "player", "continent")
EFFECT_MODES = ("additive", "compound")
# Effects the rules engine understands (see engine/effects.py and the config files).
EFFECT_TYPES = (
    "capital", "veteran_units", "food_box_keep", "content", "happy", "no_unhappy",
    "yield_bonus", "tile_trade_bonus", "corruption_percent", "defense_multiplier",
    "allow_size_above", "acts_as_building", "free_government", "free_techs",
    "shared_knowledge", "military_unhappiness", "peace_keeper", "unit_moves",
    "no_population_pollution", "pollution_percent", "meltdown_risk", "nuclear_shield",
    "reveal_map", "spaceship_part",
)
SPACESHIP_PARTS = ("structural", "component", "module")
FREE_UNITS = ("none", "city_size")


def key(name: str):
    """Field whose YAML key differs from the attribute name (Python keywords)."""
    return field(default=None, metadata={"key": name})


# ── Terrain ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Yields:
    food: int = 0
    shields: int = 0
    trade: int = 0

    def __add__(self, other: "Yields") -> "Yields":
        return Yields(self.food + other.food, self.shields + other.shields, self.trade + other.trade)


@dataclass(frozen=True)
class SpecialResource:
    id: str
    name: str
    yields: Yields
    sprite: str


@dataclass(frozen=True)
class PatternBonus:
    yields: Yields
    sprite: str


@dataclass(frozen=True)
class TerrainWork:
    """Irrigation or mining: a yield bonus, or a change of terrain."""
    turns: int
    bonus: int = 0
    becomes: Optional[str] = None
    needs_water: bool = False


@dataclass(frozen=True)
class TerrainDef:
    id: str
    name: str
    move_cost: int
    defense: float
    yields: Yields
    sprite: str
    color: str
    domain: str = "land"
    road_trade: bool = False
    special: Optional[SpecialResource] = None
    pattern_bonus: Optional[PatternBonus] = None
    irrigation: Optional[TerrainWork] = None
    mine: Optional[TerrainWork] = None
    is_water_source: bool = False
    base_sprite: Optional[str] = None

    @property
    def is_land(self) -> bool:
        return self.domain == "land"


# ── Units ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class UnitDef:
    id: str
    name: str
    domain: str
    role: str
    attack: int
    defense: int
    moves: int
    cost: int
    sprite: str
    requires: Optional[str] = None
    obsolete_by: Optional[str] = None
    abilities: tuple[str, ...] = ()
    pop_cost: int = 0
    needs_support: bool = True
    sight: int = 1
    fuel: int = 0                     # air units: turns they may end away from a base
    capacity: int = 0                 # units the ship can carry
    carries: Optional[str] = None     # what it carries: land units or aircraft
    requires_wonder: Optional[str] = None
    enabled: bool = True

    def can(self, ability: str) -> bool:
        return ability in self.abilities

    @property
    def is_military(self) -> bool:
        return self.attack > 0


# ── Buildings and wonders ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class Effect:
    type: str
    scope: str = "city"
    amount: int = 0
    percent: float = 0.0
    factor: float = 1.0
    yield_kind: Optional[str] = key("yield")
    mode: str = "additive"
    exclusive_group: Optional[str] = None
    requires_tech: Optional[str] = None
    requires_building: Optional[str] = None
    building: Optional[str] = None
    size: int = 0
    vs: Optional[str] = None
    count: int = 0
    min_civs: int = 0
    domain: Optional[str] = None
    part: Optional[str] = None        # spaceship_part: structural | component | module
    safe_tech: Optional[str] = None   # meltdown_risk: the advance that removes the risk


@dataclass(frozen=True)
class BuildingDef:
    id: str
    name: str
    cost: int
    upkeep: int = 0
    requires: Optional[str] = None
    requires_building: Optional[str] = None
    requires_wonder: Optional[str] = None   # some civilization must have built this wonder
    obsolete_by: Optional[str] = None
    effects: tuple[Effect, ...] = ()
    upkeep_increase_techs: tuple[str, ...] = ()
    description: str = ""
    enabled: bool = True
    wonder: bool = False      # set by the loader: true for entries of wonders.yaml

    def has_effect(self, effect_type: str) -> bool:
        return any(e.type == effect_type for e in self.effects)

    @property
    def spaceship_part(self) -> Optional[str]:
        """The kind of spaceship part this is, if it is one (it then goes to the ship,
        not to the city, and can be built many times)."""
        for effect in self.effects:
            if effect.type == "spaceship_part":
                return effect.part
        return None


# ── Technologies, governments, civilizations ──────────────────────────────────

@dataclass(frozen=True)
class TechDef:
    id: str
    name: str
    era: str
    prerequisites: tuple[str, ...] = ()
    repeatable: bool = False


@dataclass(frozen=True)
class GovernmentDef:
    id: str
    name: str
    max_rate: int
    empire_size_factor: int
    settlers_food: int
    requires: Optional[str] = None
    tile_penalty: bool = False
    trade_bonus: bool = False
    celebration_trade_bonus: bool = False
    corruption_divisor: Optional[int] = None
    corruption_distance: Optional[int] = None
    free_units: str = "none"
    martial_law: int = 0
    military_unhappiness: int = 0
    collects_taxes: bool = True
    does_research: bool = True
    rapture_growth: bool = False
    falls_on_disorder: bool = False
    senate: bool = False


@dataclass(frozen=True)
class Personality:
    mood: int = 0        # -1 friendly      .. 1 aggressive
    policy: int = 0      # -1 perfectionist .. 1 expansionist
    ideology: int = 0    # -1 militaristic  .. 1 civilized


@dataclass(frozen=True)
class CivDef:
    id: str
    name: str
    nation: str
    leader: str
    color: str
    personality: Personality
    city_names: tuple[str, ...]
    playable: bool = True


# ── game.yaml ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MapSettings:
    width: int
    height: int
    wrap_x: bool
    land_mass: int
    temperature: int
    climate: int
    age: int


@dataclass(frozen=True)
class CalendarStep:
    until: Optional[int]
    years: int


@dataclass(frozen=True)
class CalendarSettings:
    start_year: int
    steps: tuple[CalendarStep, ...]
    max_turns: int


@dataclass(frozen=True)
class Rates:
    tax: int
    luxury: int
    science: int


@dataclass(frozen=True)
class PlayerSettings:
    count: int
    start_units: tuple[str, ...]
    start_gold: int
    start_government: str
    start_rates: Rates
    start_min_site_score: int
    start_min_distance: int
    start_min_continent_sites: int


@dataclass(frozen=True)
class DifficultySettings:
    content_base: int
    empire_size_base: int


@dataclass(frozen=True)
class WorkerWeights:
    food_starving: float
    food_low: float
    food: float
    shields_none: float
    shields_low: float
    shields: float
    trade: float


@dataclass(frozen=True)
class CitySettings:
    min_distance: int
    food_per_citizen: int
    food_box_per_size: int
    disorder_shields: bool
    specialist_yield: int
    luxury_per_happy: int
    max_trade_routes: int
    trade_route_min_distance: int
    celebration_min_size: int
    capture_building_loss: float
    no_palace_distance: int
    worker_weights: WorkerWeights


@dataclass(frozen=True)
class BuyUnitFormula:
    quadratic_divisor: int
    linear: int


@dataclass(frozen=True)
class ProductionSettings:
    buy_unit: BuyUnitFormula
    buy_building: int
    buy_wonder: int
    buy_from_scratch_multiplier: int


@dataclass(frozen=True)
class ResearchSettings:
    cost_factor: int
    early_factor_base: int
    doubled_from_year: int
    capture_steals_tech: bool


@dataclass(frozen=True)
class MovementSettings:
    points_per_move: int
    road_cost: int
    railroad_cost: int
    road_turns_factor: int
    railroad_turns_factor: int
    fortress_turns_base: int
    road_trade_bonus: int
    railroad_yield_percent: int
    road_requires_tech_on: dict[str, str]
    railroad_tech: str
    fortress_tech: str
    lost_at_sea_chance: float       # for `coastal` ships ending their turn away from land
    pollution_clean_turns: int


@dataclass(frozen=True)
class CombatSettings:
    fortified_multiplier: float
    fortress_multiplier: float
    veteran_multiplier: float
    veteran_promotion_chance: float
    barbarian_attack_multiplier: float
    barbarian_vs_capital_multiplier: float
    barbarians_spare_last_city: bool
    city_shrinks_on_defeat: bool


@dataclass(frozen=True)
class HutBarbarians:
    open: str
    rough: str


@dataclass(frozen=True)
class HutSettings:
    enabled: bool
    gold: int
    mercenaries: tuple[str, ...]
    barbarian_units: HutBarbarians
    wisdom_until_year: int
    advanced_tribe_min_site_score: int


@dataclass(frozen=True)
class BarbarianTier:
    min_techs: int
    units: tuple[str, ...]
    ship: Optional[str] = None      # what they land from


@dataclass(frozen=True)
class BarbarianSettings:
    enabled: bool
    first_turn: int
    spawn_chance_per_turn: float
    min_distance_from_city: int
    max_distance_from_city: int
    group_size: tuple[int, ...]
    march_radius: int
    min_attack_odds: float
    sea_raid_chance: float          # share of the raids that come from the sea
    units_by_tech_count: tuple[BarbarianTier, ...]


@dataclass(frozen=True)
class GovernmentSettings:
    anarchy_turn_multiple: int


@dataclass(frozen=True)
class PollutionSettings:
    enabled: bool
    tolerance: int                  # pollution index a city absorbs without harm
    population_techs: tuple[str, ...]   # each known one makes citizens pollute more
    roll: int                       # a tile is polluted when index x 2 > random(roll - ...)
    roll_per_tech: int              # ... known advances x this
    warming_per_tile: int           # how fast polluted tiles heat the planet
    warming_recovery: int           # each past warming raises the bar by this
    warming_threshold: int
    warming_coastal: dict[str, str]     # terrain -> what it becomes when the sea rises
    warming_inland: dict[str, str]      # terrain -> what it becomes when the land dries up


@dataclass(frozen=True)
class NuclearSettings:
    fallout_chance: float           # chance for each land tile around the blast to be polluted
    city_loss_percent: int          # population lost by a city in the blast
    meltdown_chance: float          # per turn of civil disorder in a city with a risky plant


@dataclass(frozen=True)
class SpaceshipSettings:
    min_parts: dict[str, int]       # parts needed before the ship can be launched
    max_parts: dict[str, int]
    flight_years: int               # flight time of the smallest ship
    years_per_component: float      # saved by each component beyond the minimum
    years_per_mass: float           # added by each structural or module beyond the minimum
    min_flight_years: int


@dataclass(frozen=True)
class ScoreSettings:
    happy_citizen: int
    content_citizen: int
    wonder: int
    advance: int
    future_tech: int
    polluted_tile: int
    spaceship_arrival: int


@dataclass(frozen=True)
class VictorySettings:
    conquest: bool
    spaceship: bool


@dataclass(frozen=True)
class GameSettings:
    map: MapSettings
    calendar: CalendarSettings
    players: PlayerSettings
    enabled_unit_domains: tuple[str, ...]
    difficulty: DifficultySettings
    city: CitySettings
    production: ProductionSettings
    research: ResearchSettings
    movement: MovementSettings
    combat: CombatSettings
    huts: HutSettings
    barbarians: BarbarianSettings
    government: GovernmentSettings
    pollution: PollutionSettings
    nuclear: NuclearSettings
    spaceship: SpaceshipSettings
    score: ScoreSettings
    victory: VictorySettings


# ── ai.yaml ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AISettings:
    """Weights and thresholds of the AI, grouped by decision area.

    Kept as plain tables so tuning the AI never requires a code change; a missing key
    raises a clear error the first time it is read (see `get`).
    """
    strategy: dict[str, float]
    overseas: dict[str, float]
    production: dict[str, float]
    personality: dict[str, float]
    research: dict[str, float]
    diplomacy: dict[str, float]
    military: dict[str, float]
    settlers: dict[str, float]
    economy: dict[str, float]
    government_preference: dict[str, float]

    def get(self, section: str, name: str) -> float:
        table = getattr(self, section)
        if name not in table:
            raise KeyError(f"ai.yaml: missing '{name}' in section '{section}'")
        return table[name]


# ── Everything ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Rules:
    game: GameSettings
    terrains: dict[str, TerrainDef]
    units: dict[str, UnitDef]
    buildings: dict[str, BuildingDef]      # city improvements and wonders
    techs: dict[str, TechDef]
    governments: dict[str, GovernmentDef]
    civs: dict[str, CivDef]
    ai: AISettings

    @property
    def wonders(self) -> list[BuildingDef]:
        return [b for b in self.buildings.values() if b.wonder]

    @property
    def playable_civs(self) -> list[CivDef]:
        return [c for c in self.civs.values() if c.playable]
