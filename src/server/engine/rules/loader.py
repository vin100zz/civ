"""Loads config/*.yaml into the dataclasses of schema.py and validates them.

Any problem (unknown key, wrong type, reference to something that does not exist) raises
ConfigError with the file and the path of the faulty value, so a bad config never starts a game.
"""
from __future__ import annotations

import dataclasses
import re
import types
import typing
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from . import schema
from .schema import Rules

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_RESOURCES_DIR = PROJECT_ROOT / "resources"


class ConfigError(Exception):
    """The configuration is invalid."""


# ── Generic YAML → dataclass conversion ───────────────────────────────────────

def _convert(tp: Any, value: Any, where: str) -> Any:
    origin = typing.get_origin(tp)

    if origin in (Union, types.UnionType):
        args = typing.get_args(tp)
        if value is None:
            if type(None) in args:
                return None
            raise ConfigError(f"{where}: a value is required")
        inner = [a for a in args if a is not type(None)]
        return _convert(inner[0], value, where)

    if dataclasses.is_dataclass(tp):
        return _build(tp, value, where)

    if origin is tuple:
        item_type = typing.get_args(tp)[0]
        if not isinstance(value, list):
            raise ConfigError(f"{where}: expected a list, got {value!r}")
        return tuple(_convert(item_type, v, f"{where}[{i}]") for i, v in enumerate(value))

    if origin is dict:
        _, value_type = typing.get_args(tp)
        if not isinstance(value, dict):
            raise ConfigError(f"{where}: expected a mapping, got {value!r}")
        return {str(k): _convert(value_type, v, f"{where}.{k}") for k, v in value.items()}

    if tp is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{where}: expected true or false, got {value!r}")
        return value
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where}: expected an integer, got {value!r}")
        return value
    if tp is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{where}: expected a number, got {value!r}")
        return float(value)
    if tp is str:
        if not isinstance(value, str):
            raise ConfigError(f"{where}: expected text, got {value!r}")
        return value
    raise ConfigError(f"{where}: unsupported type {tp!r}")


def _build(cls: type, data: Any, where: str) -> Any:
    fields = dataclasses.fields(cls)
    hints = typing.get_type_hints(cls)

    if isinstance(data, list):                      # positional form, e.g. yields: [2, 1, 0]
        if len(data) > len(fields):
            raise ConfigError(f"{where}: too many values for {cls.__name__}")
        data = {f.name: v for f, v in zip(fields, data)}
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: expected a mapping for {cls.__name__}, got {data!r}")

    yaml_keys = {f.metadata.get("key", f.name): f for f in fields}
    unknown = set(data) - set(yaml_keys)
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {sorted(unknown)} "
                          f"(allowed: {sorted(yaml_keys)})")

    kwargs = {}
    for yaml_key, f in yaml_keys.items():
        if yaml_key in data:
            kwargs[f.name] = _convert(hints[f.name], data[yaml_key], f"{where}.{yaml_key}")
        elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            raise ConfigError(f"{where}: missing required key '{yaml_key}'")
    return cls(**kwargs)


def _read(config_dir: Path, name: str) -> Any:
    path = config_dir / name
    if not path.exists():
        raise ConfigError(f"{path}: file not found")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{name}: invalid YAML: {exc}") from exc


def _load_list(config_dir: Path, name: str, cls: type) -> dict[str, Any]:
    raw = _read(config_dir, name)
    if not isinstance(raw, list):
        raise ConfigError(f"{name}: expected a list of entries")
    result: dict[str, Any] = {}
    for i, entry in enumerate(raw):
        label = entry.get("id", i) if isinstance(entry, dict) else i
        item = _build(cls, entry, f"{name}[{label}]")
        if item.id in result:
            raise ConfigError(f"{name}: duplicate id '{item.id}'")
        result[item.id] = item
    return result


# ── Public entry point ────────────────────────────────────────────────────────

def load_rules(config_dir: Optional[Path] = None, resources_dir: Optional[Path] = None,
               check_sprites: bool = True) -> Rules:
    config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    resources_dir = Path(resources_dir) if resources_dir else DEFAULT_RESOURCES_DIR

    buildings = _load_list(config_dir, "buildings.yaml", schema.BuildingDef)
    wonders = _load_list(config_dir, "wonders.yaml", schema.BuildingDef)
    for wonder_id, wonder in wonders.items():
        if wonder_id in buildings:
            raise ConfigError(f"wonders.yaml: id '{wonder_id}' already used in buildings.yaml")
        buildings[wonder_id] = dataclasses.replace(wonder, wonder=True)

    rules = Rules(
        game=_build(schema.GameSettings, _read(config_dir, "game.yaml"), "game.yaml"),
        terrains=_load_list(config_dir, "terrains.yaml", schema.TerrainDef),
        units=_load_list(config_dir, "units.yaml", schema.UnitDef),
        buildings=buildings,
        techs=_load_list(config_dir, "technologies.yaml", schema.TechDef),
        governments=_load_list(config_dir, "governments.yaml", schema.GovernmentDef),
        civs=_load_list(config_dir, "civilizations.yaml", schema.CivDef),
        ai=_build(schema.AISettings, _read(config_dir, "ai.yaml"), "ai.yaml"),
    )
    _validate(rules, resources_dir if check_sprites else None)
    return rules


# ── Cross-reference validation ────────────────────────────────────────────────

class _Checker:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def ref(self, value: Optional[str], table: dict, where: str, what: str) -> None:
        if value is not None and value not in table:
            self.error(f"{where}: unknown {what} '{value}'")

    def one_of(self, value: Any, allowed: tuple, where: str) -> None:
        if value not in allowed:
            self.error(f"{where}: '{value}' is not one of {list(allowed)}")


def _validate(rules: Rules, resources_dir: Optional[Path]) -> None:
    c = _Checker()
    techs, units, buildings, terrains = rules.techs, rules.units, rules.buildings, rules.terrains

    # Technologies: prerequisites exist, no cycle.
    for tech in techs.values():
        if len(tech.prerequisites) > 2:
            c.error(f"technologies.yaml[{tech.id}]: more than 2 prerequisites")
        for pre in tech.prerequisites:
            c.ref(pre, techs, f"technologies.yaml[{tech.id}].prerequisites", "technology")
    state: dict[str, int] = {}

    def visit(tech_id: str, trail: tuple[str, ...]) -> None:
        if state.get(tech_id) == 2 or tech_id not in techs:
            return
        if state.get(tech_id) == 1:
            c.error(f"technologies.yaml: cycle in prerequisites: {' -> '.join(trail + (tech_id,))}")
            return
        state[tech_id] = 1
        for pre in techs[tech_id].prerequisites:
            visit(pre, trail + (tech_id,))
        state[tech_id] = 2

    for tech_id in techs:
        visit(tech_id, ())

    # Terrains.
    for t in terrains.values():
        where = f"terrains.yaml[{t.id}]"
        c.one_of(t.domain, ("land", "sea"), f"{where}.domain")
        if t.move_cost < 1:
            c.error(f"{where}.move_cost: must be at least 1")
        for work_name in ("irrigation", "mine"):
            work = getattr(t, work_name)
            if work is None:
                continue
            c.ref(work.becomes, terrains, f"{where}.{work_name}.becomes", "terrain")
            if (work.becomes is None) == (work.bonus == 0):
                c.error(f"{where}.{work_name}: give exactly one of 'bonus' or 'becomes'")
            if work.turns < 1:
                c.error(f"{where}.{work_name}.turns: must be at least 1")
        if not _is_color(t.color):
            c.error(f"{where}.color: '{t.color}' is not a #rrggbb color")

    # Units.
    for u in units.values():
        where = f"units.yaml[{u.id}]"
        c.one_of(u.domain, schema.DOMAINS, f"{where}.domain")
        c.one_of(u.role, schema.ROLES, f"{where}.role")
        c.ref(u.requires, techs, f"{where}.requires", "technology")
        c.ref(u.obsolete_by, techs, f"{where}.obsolete_by", "technology")
        c.ref(u.requires_wonder, buildings, f"{where}.requires_wonder", "wonder")
        for ability in u.abilities:
            c.one_of(ability, schema.ABILITIES, f"{where}.abilities")
        if u.moves < 1 or u.cost < 1:
            c.error(f"{where}: moves and cost must be at least 1")
        if u.capacity > 0 or u.carries is not None:
            c.one_of(u.carries, schema.CARGO_KINDS, f"{where}.carries")
            if u.capacity < 1 or u.domain != "sea":
                c.error(f"{where}: only ships with a capacity can carry units")
        if u.domain == "air" and u.fuel < 1:
            c.error(f"{where}.fuel: air units need at least 1")

    # Buildings and wonders.
    for b in buildings.values():
        where = f"{'wonders' if b.wonder else 'buildings'}.yaml[{b.id}]"
        c.ref(b.requires, techs, f"{where}.requires", "technology")
        c.ref(b.obsolete_by, techs, f"{where}.obsolete_by", "technology")
        c.ref(b.requires_building, buildings, f"{where}.requires_building", "building")
        c.ref(b.requires_wonder, buildings, f"{where}.requires_wonder", "wonder")
        for tech_id in b.upkeep_increase_techs:
            c.ref(tech_id, techs, f"{where}.upkeep_increase_techs", "technology")
        for i, e in enumerate(b.effects):
            ewhere = f"{where}.effects[{i}]"
            c.one_of(e.type, schema.EFFECT_TYPES, f"{ewhere}.type")
            c.one_of(e.scope, schema.EFFECT_SCOPES, f"{ewhere}.scope")
            c.one_of(e.mode, schema.EFFECT_MODES, f"{ewhere}.mode")
            c.ref(e.requires_tech, techs, f"{ewhere}.requires_tech", "technology")
            c.ref(e.requires_building, buildings, f"{ewhere}.requires_building", "building")
            c.ref(e.building, buildings, f"{ewhere}.building", "building")
            if e.type == "yield_bonus":
                c.one_of(e.yield_kind, schema.YIELD_KINDS, f"{ewhere}.yield")
            if e.type == "acts_as_building" and e.building is None:
                c.error(f"{ewhere}: 'building' is required")
            if e.domain is not None:
                c.one_of(e.domain, schema.DOMAINS, f"{ewhere}.domain")
            if e.vs is not None:
                c.one_of(e.vs, schema.DOMAINS, f"{ewhere}.vs")
            if e.type == "spaceship_part":
                c.one_of(e.part, schema.SPACESHIP_PARTS, f"{ewhere}.part")
            c.ref(e.safe_tech, techs, f"{ewhere}.safe_tech", "technology")

    # Governments.
    for g in rules.governments.values():
        where = f"governments.yaml[{g.id}]"
        c.ref(g.requires, techs, f"{where}.requires", "technology")
        c.one_of(g.free_units, schema.FREE_UNITS, f"{where}.free_units")
        if not 0 < g.max_rate <= 100 or g.max_rate % 10:
            c.error(f"{where}.max_rate: must be a multiple of 10 between 10 and 100")
    if "anarchy" not in rules.governments:
        c.error("governments.yaml: an 'anarchy' government is required (revolutions)")

    # Civilizations.
    for civ in rules.civs.values():
        where = f"civilizations.yaml[{civ.id}]"
        if not _is_color(civ.color):
            c.error(f"{where}.color: '{civ.color}' is not a #rrggbb color")
        if not civ.city_names:
            c.error(f"{where}.city_names: at least one name is required")
        for trait in ("mood", "policy", "ideology"):
            c.one_of(getattr(civ.personality, trait), (-1, 0, 1), f"{where}.personality.{trait}")
    if "barbarians" not in rules.civs:
        c.error("civilizations.yaml: a 'barbarians' entry is required")

    # game.yaml.
    g = rules.game
    if g.players.count > len(rules.playable_civs):
        c.error(f"game.yaml.players.count: {g.players.count} players but only "
                f"{len(rules.playable_civs)} playable civilizations")
    for unit_id in g.players.start_units:
        c.ref(unit_id, units, "game.yaml.players.start_units", "unit")
    c.ref(g.players.start_government, rules.governments, "game.yaml.players.start_government",
          "government")
    r = g.players.start_rates
    if r.tax + r.luxury + r.science != 100 or any(v % 10 for v in (r.tax, r.luxury, r.science)):
        c.error("game.yaml.players.start_rates: must be multiples of 10 that add up to 100")
    for domain in g.enabled_unit_domains:
        c.one_of(domain, schema.DOMAINS, "game.yaml.enabled_unit_domains")
    c.ref(g.difficulty.default_level, g.difficulty.levels, "game.yaml.difficulty.default_level",
          "difficulty level")
    c.ref(g.map.shape, g.map.shapes, "game.yaml.map.shape", "map shape")
    for name in ("temperature", "climate", "relief"):
        c.one_of(getattr(g.map, name), (0, 1, 2), f"game.yaml.map.{name}")
    for shape_id, shape in g.map.shapes.items():
        where = f"game.yaml.map.shapes.{shape_id}"
        if not 0 <= shape.lakes < 1:
            c.error(f"{where}.lakes: expected a share between 0 and 1")
        for masses in shape.masses:
            if masses.belt and masses.hollow:
                c.error(f"{where}.masses: a belt cannot be hollow")
            if masses.count < 1 or not 0 < masses.land < 1 or not 0 <= masses.hollow < 1:
                c.error(f"{where}.masses: expected count >= 1, and land and hollow between "
                        f"0 and 1")
    steps = g.calendar.steps
    if not steps or steps[-1].until is not None:
        c.error("game.yaml.calendar.steps: the last step must have 'until: null'")
    for terrain_id, tech_id in g.movement.road_requires_tech_on.items():
        c.ref(terrain_id, terrains, "game.yaml.movement.road_requires_tech_on", "terrain")
        c.ref(tech_id, techs, "game.yaml.movement.road_requires_tech_on", "technology")
    c.ref(g.movement.railroad_tech, techs, "game.yaml.movement.railroad_tech", "technology")
    c.ref(g.movement.fortress_tech, techs, "game.yaml.movement.fortress_tech", "technology")
    for unit_id in g.huts.mercenaries:
        c.ref(unit_id, units, "game.yaml.huts.mercenaries", "unit")
    c.ref(g.huts.barbarian_units.open, units, "game.yaml.huts.barbarian_units.open", "unit")
    c.ref(g.huts.barbarian_units.rough, units, "game.yaml.huts.barbarian_units.rough", "unit")
    if len(g.barbarians.group_size) != 2 or g.barbarians.group_size[0] > g.barbarians.group_size[1]:
        c.error("game.yaml.barbarians.group_size: expected [min, max]")
    for tier in g.barbarians.units_by_tech_count:
        for unit_id in tier.units:
            c.ref(unit_id, units, "game.yaml.barbarians.units_by_tech_count", "unit")
        c.ref(tier.ship, units, "game.yaml.barbarians.units_by_tech_count.ship", "unit")
        if tier.ship in units and units[tier.ship].carries != "land":
            c.error(f"game.yaml.barbarians.units_by_tech_count: '{tier.ship}' cannot carry "
                    f"land units")
    for tech_id in g.pollution.population_techs:
        c.ref(tech_id, techs, "game.yaml.pollution.population_techs", "technology")
    for table_name in ("warming_coastal", "warming_inland"):
        for before, after in getattr(g.pollution, table_name).items():
            c.ref(before, terrains, f"game.yaml.pollution.{table_name}", "terrain")
            c.ref(after, terrains, f"game.yaml.pollution.{table_name}", "terrain")
    for table_name in ("min_parts", "max_parts"):
        table = getattr(g.spaceship, table_name)
        if set(table) != set(schema.SPACESHIP_PARTS):
            c.error(f"game.yaml.spaceship.{table_name}: expected exactly the keys "
                    f"{list(schema.SPACESHIP_PARTS)}")
    for needed in ("ocean", "grassland", "plains", "hills", "mountains", "forest", "river",
                   "desert", "tundra", "arctic", "swamp", "jungle"):
        if needed not in terrains:
            c.error(f"terrains.yaml: terrain '{needed}' is required by the map generator")

    # ai.yaml.
    for gov_id in rules.ai.government_preference:
        c.ref(gov_id, rules.governments, "ai.yaml.government_preference", "government")

    # Sprites.
    if resources_dir is not None:
        def sprite(folder: str, name: Optional[str], where: str) -> None:
            if name is not None and not (resources_dir / folder / f"{name}.png").exists():
                c.error(f"{where}: sprite resources/{folder}/{name}.png not found")

        for t in terrains.values():
            sprite("terrain", t.sprite, f"terrains.yaml[{t.id}].sprite")
            sprite("terrain", t.base_sprite, f"terrains.yaml[{t.id}].base_sprite")
            if t.special:
                sprite("terrain", t.special.sprite, f"terrains.yaml[{t.id}].special.sprite")
            if t.pattern_bonus:
                sprite("terrain", t.pattern_bonus.sprite, f"terrains.yaml[{t.id}].pattern_bonus.sprite")
        for u in units.values():
            sprite("unit", u.sprite, f"units.yaml[{u.id}].sprite")

    if c.errors:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(c.errors))


def _is_color(value: str) -> bool:
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value))
