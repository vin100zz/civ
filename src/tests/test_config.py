"""The configuration loads, and a broken one is refused with a useful message."""
from __future__ import annotations

import shutil

import pytest

from server.engine.rules.loader import (DEFAULT_CONFIG_DIR, ConfigError, load_rules,
                                        load_rulesets, ruleset_ids)

CIV1_DIR = "rulesets/civ1"


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
    _replace(config_copy / CIV1_DIR / "units.yaml", "  attack: 0\n", "  attack: 0\n  atack: 3\n")
    with pytest.raises(ConfigError, match="unknown key.*atack"):
        load_rules(config_copy)


def test_unknown_reference_is_refused(config_copy):
    _replace(config_copy / CIV1_DIR / "units.yaml", "requires: bronze_working", "requires: bronze_age")
    with pytest.raises(ConfigError, match=r"units.yaml\[phalanx\].requires: unknown technology 'bronze_age'"):
        load_rules(config_copy)


def test_wrong_type_is_refused(config_copy):
    _replace(config_copy / "game.yaml", "  width: 80", "  width: wide")
    with pytest.raises(ConfigError, match="game.yaml.map.width: expected an integer"):
        load_rules(config_copy)


def test_missing_sprite_is_refused(config_copy):
    _replace(config_copy / CIV1_DIR / "units.yaml", "sprite: militia", "sprite: no_such_file")
    with pytest.raises(ConfigError, match="no_such_file.png not found"):
        load_rules(config_copy)


def test_tech_cycle_is_refused(config_copy):
    _replace(config_copy / CIV1_DIR / "technologies.yaml",
             "- id: alphabet\n  name: Alphabet\n  era: ancient\n  prerequisites: []",
             "- id: alphabet\n  name: Alphabet\n  era: ancient\n  prerequisites: [writing]")
    with pytest.raises(ConfigError, match="cycle in prerequisites"):
        load_rules(config_copy)


def test_all_errors_reported_together(config_copy):
    _replace(config_copy / CIV1_DIR / "units.yaml", "requires: bronze_working", "requires: bronze_age")
    _replace(config_copy / CIV1_DIR / "buildings.yaml", "requires: pottery", "requires: potery")
    with pytest.raises(ConfigError) as error:
        load_rules(config_copy)
    assert "bronze_age" in str(error.value) and "potery" in str(error.value)


def test_every_ruleset_loads():
    rulesets = load_rulesets()
    assert list(rulesets)[0] == "civ1" and "golden_ages" in rulesets
    for ruleset_id, rules in rulesets.items():
        assert rules.ruleset.id == ruleset_id and rules.ruleset.name
    assert "titan" in rulesets["golden_ages"].units and "titan" not in rulesets["civ1"].units


def test_a_ruleset_brings_its_own_files(config_copy):
    own = config_copy / "rulesets" / "mini"
    own.mkdir()
    (own / "ruleset.yaml").write_text("name: Mini\n", encoding="utf-8")
    for name in ("technologies.yaml", "units.yaml", "buildings.yaml", "wonders.yaml"):
        (own / name).write_bytes((config_copy / CIV1_DIR / name).read_bytes())
    _replace(own / "units.yaml", "  name: Phalanx\n", "  name: Hoplites\n")
    # game.yaml is merged: only the keys that change.
    (own / "game.yaml").write_text("players:\n  start_gold: 30\n", encoding="utf-8")
    ids = ruleset_ids(config_copy)
    assert ids[0] == "civ1" and "mini" in ids
    mini = load_rules(config_copy, ruleset="mini")
    assert mini.ruleset.name == "Mini" and mini.units["phalanx"].name == "Hoplites"
    assert mini.game.players.start_gold == 30 and mini.game.players.count == 7
    assert load_rules(config_copy).units["phalanx"].name == "Phalanx"

    # Its errors say which rules they are in.
    _replace(own / "units.yaml", "requires: bronze_working", "requires: bronze_age")
    with pytest.raises(ConfigError, match="(?s)Rules 'mini'.*bronze_age"):
        load_rules(config_copy, ruleset="mini")
    with pytest.raises(ConfigError, match="no set of rules 'maxi'"):
        load_rules(config_copy, ruleset="maxi")
