"""The configuration loads, and a broken one is refused with a useful message."""
from __future__ import annotations

import shutil

import pytest

from server.engine.rules.loader import DEFAULT_CONFIG_DIR, ConfigError, load_rules


def test_rules_load(rules):
    assert len(rules.terrains) == 12
    assert len(rules.units) == 28
    assert len(rules.governments) == 6
    assert len(rules.playable_civs) == 14
    assert len(rules.wonders) == 21
    assert rules.units["settlers"].can("found_city")
    assert rules.buildings["pyramids"].wonder and not rules.buildings["temple"].wonder


def test_every_tech_reachable(rules):
    """No advance depends on something that can never be researched."""
    known: set[str] = set()
    progress = True
    while progress:
        progress = False
        for tech in rules.techs.values():
            if tech.id not in known and all(p in known for p in tech.prerequisites):
                known.add(tech.id)
                progress = True
    assert known == set(rules.techs)


@pytest.fixture
def config_copy(tmp_path):
    target = tmp_path / "config"
    shutil.copytree(DEFAULT_CONFIG_DIR, target)
    return target


def _replace(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_unknown_key_is_refused(config_copy):
    _replace(config_copy / "units.yaml", "  attack: 0\n", "  attack: 0\n  atack: 3\n")
    with pytest.raises(ConfigError, match="unknown key.*atack"):
        load_rules(config_copy)


def test_unknown_reference_is_refused(config_copy):
    _replace(config_copy / "units.yaml", "requires: bronze_working", "requires: bronze_age")
    with pytest.raises(ConfigError, match=r"units.yaml\[phalanx\].requires: unknown technology 'bronze_age'"):
        load_rules(config_copy)


def test_wrong_type_is_refused(config_copy):
    _replace(config_copy / "game.yaml", "  width: 80", "  width: wide")
    with pytest.raises(ConfigError, match="game.yaml.map.width: expected an integer"):
        load_rules(config_copy)


def test_missing_sprite_is_refused(config_copy):
    _replace(config_copy / "units.yaml", "sprite: militia", "sprite: no_such_file")
    with pytest.raises(ConfigError, match="no_such_file.png not found"):
        load_rules(config_copy)


def test_tech_cycle_is_refused(config_copy):
    _replace(config_copy / "technologies.yaml",
             "- id: alphabet\n  name: Alphabet\n  era: ancient\n  prerequisites: []",
             "- id: alphabet\n  name: Alphabet\n  era: ancient\n  prerequisites: [writing]")
    with pytest.raises(ConfigError, match="cycle in prerequisites"):
        load_rules(config_copy)


def test_all_errors_reported_together(config_copy):
    _replace(config_copy / "units.yaml", "requires: bronze_working", "requires: bronze_age")
    _replace(config_copy / "buildings.yaml", "requires: pottery", "requires: potery")
    with pytest.raises(ConfigError) as error:
        load_rules(config_copy)
    assert "bronze_age" in str(error.value) and "potery" in str(error.value)
