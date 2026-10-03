"""World generation and starting positions."""
from __future__ import annotations

import dataclasses

import pytest

from server.engine.mapgen.generator import generate_world
from server.engine.mapgen.sites import site_score
from server.engine.setup import new_game


def _signature(world):
    return [(t.terrain, t.special, t.hut) for t in world.tiles]


def test_same_seed_same_world(rules):
    assert _signature(generate_world(rules, 7)) == _signature(generate_world(rules, 7))
    assert _signature(generate_world(rules, 7)) != _signature(generate_world(rules, 8))


def test_world_looks_like_a_world(rules):
    for seed in (1, 2, 3):
        world = generate_world(rules, seed)
        assert world.width == 80 and world.height == 50
        land = sum(1 for t in world.tiles if rules.terrains[t.terrain].is_land)
        assert 0.15 < land / len(world.tiles) < 0.5
        # Polar caps.
        assert all(world.tile(x, 0).terrain in ("arctic", "tundra") for x in range(world.width))
        # Several terrains are present.
        assert len({t.terrain for t in world.tiles}) >= 9


def test_continents_are_consistent(rules):
    world = generate_world(rules, 3)
    for tile in world.tiles:
        is_land = rules.terrains[tile.terrain].is_land
        assert (tile.continent > 0) == is_land
        for other in world.neighbors(tile):
            if rules.terrains[other.terrain].is_land == is_land:
                assert other.continent == tile.continent
    sizes = [size for cid, size in sorted(world.continent_sizes.items()) if cid > 0]
    assert sizes == sorted(sizes, reverse=True)


def test_specials_and_huts(rules):
    world = generate_world(rules, 5)
    specials = [t for t in world.tiles if t.special]
    assert specials
    assert all(rules.terrains[t.terrain].special is not None for t in specials)
    assert all(rules.terrains[t.terrain].is_land for t in world.tiles if t.hut)


def test_site_score_range(rules):
    world = generate_world(rules, 5)
    for tile in world.tiles:
        score = site_score(rules, world, tile)
        if tile.terrain in ("river", "grassland", "plains") and 2 <= tile.y < world.height - 2:
            assert 8 <= score <= 15
        else:
            assert score == 0


def test_unknown_tiles_lower_the_score(rules):
    world = generate_world(rules, 5)
    tile = max(world.tiles, key=lambda t: site_score(rules, world, t))
    full = site_score(rules, world, tile)
    blind = site_score(rules, world, tile, known=lambda t: t is tile)
    assert blind <= full


def test_new_game_starts(rules):
    game = new_game(rules, 11)
    civilizations = game.civilizations
    assert len(civilizations) == rules.game.players.count
    assert game.players[0].is_barbarian
    positions = []
    for player in civilizations:
        units = game.player_units(player.id)
        assert [u.type for u in units] == list(rules.game.players.start_units)
        tile = game.tile_of(units[0])
        assert rules.terrains[tile.terrain].is_land
        assert player.explored[tile.index]
        positions.append((tile.x, tile.y))
    assert len(set(positions)) == len(positions)


def test_new_game_is_reproducible(rules):
    a, b = new_game(rules, 21), new_game(rules, 21)
    assert [p.civ.id for p in a.players] == [p.civ.id for p in b.players]
    assert [(u.x, u.y) for u in a.units.values()] == [(u.x, u.y) for u in b.units.values()]


# ── Map shapes, relief and climate ────────────────────────────────────────────

def _settings(rules, **changes):
    return dataclasses.replace(rules.game.map, **changes)


def _land_masses(world, min_size=8):
    """Sizes of the land masses, largest first, without the two polar caps."""
    caps = {world.tile(0, 0).continent, world.tile(0, world.height - 1).continent}
    return sorted((size for cid, size in world.continent_sizes.items()
                   if cid > 0 and cid not in caps and size >= min_size), reverse=True)


def _share(world, *terrains):
    land = [t for t in world.tiles if t.terrain != "ocean" and 1 < t.y < world.height - 2]
    return sum(1 for t in land if t.terrain in terrains) / len(land)


def test_default_settings_give_the_same_world(rules):
    assert _signature(generate_world(rules, 7, _settings(rules))) == _signature(generate_world(rules, 7))


@pytest.mark.parametrize("shape", ["small_islands", "medium_islands", "large_islands",
                                   "two_continents", "continents_islands", "pangaea",
                                   "pangaea_lakes", "world_belt", "inner_sea"])
def test_every_shape_gives_a_playable_world(rules, shape):
    settings = _settings(rules, shape=shape)
    assert _signature(generate_world(rules, 4, settings)) == _signature(generate_world(rules, 4, settings))
    for seed in (1, 2, 3):
        world = generate_world(rules, seed, settings)
        land = sum(1 for t in world.tiles if rules.terrains[t.terrain].is_land)
        assert 0.15 < land / len(world.tiles) < 0.5
        assert len({t.terrain for t in world.tiles}) >= 9
        game = new_game(rules, seed, map_settings=settings)
        assert all(p.alive for p in game.civilizations)
        assert all(game.player_units(p.id) for p in game.civilizations)


def test_shapes_have_the_land_masses_they_promise(rules):
    for seed in (1, 2, 3):
        def masses(shape):
            return _land_masses(generate_world(rules, seed, _settings(rules, shape=shape)))

        assert len(masses("small_islands")) >= 14 and masses("small_islands")[0] < 150
        assert 7 <= len(masses("medium_islands")) <= 14
        assert 4 <= len(masses("large_islands")) <= 8
        two = masses("two_continents")
        assert two[1] > 300 and sum(two[2:]) < 100
        for shape in ("pangaea", "pangaea_lakes", "inner_sea"):
            one = masses(shape)
            assert one[0] > 800 and sum(one[1:]) < 120


def test_world_belt_goes_around_the_world(rules):
    for seed in range(1, 7):
        world = generate_world(rules, seed, _settings(rules, shape="world_belt"))
        belt = max(_land_masses(world))
        columns = {t.x for t in world.tiles if t.continent > 0
                   and world.continent_sizes[t.continent] == belt}
        assert len(columns) == world.width


def test_large_masses_are_not_all_plains(rules):
    for shape in ("pangaea", "two_continents", "world_belt"):
        for climate, least in ((1, 1.0), (2, 1.8)):
            worlds = [generate_world(rules, seed, _settings(rules, shape=shape, climate=climate))
                      for seed in (1, 2, 3, 4)]
            grassland = sum(_share(world, "grassland") for world in worlds)
            assert grassland > least * sum(_share(world, "plains") for world in worlds)


def test_lakes_and_inner_sea(rules):
    for seed in (1, 2, 3):
        plain = generate_world(rules, seed, _settings(rules, shape="pangaea"))
        lakes = generate_world(rules, seed, _settings(rules, shape="pangaea_lakes"))
        count = lambda world: sum(1 for cid in world.continent_sizes if cid < 0)
        assert count(lakes) >= count(plain) + 5
    # The inner sea is a large body of water, closed on most worlds (a strait may open it).
    rings = [generate_world(rules, seed, _settings(rules, shape="inner_sea")) for seed in range(1, 7)]
    assert any(ring.continent_sizes.get(-2, 0) > 100 for ring in rings)


def test_relief_and_climate_change_the_terrain(rules):
    for shape in ("continents", "pangaea", "medium_islands"):
        def average(terrains, **changes):
            worlds = [generate_world(rules, seed, _settings(rules, shape=shape, **changes))
                      for seed in (1, 2, 3, 4)]
            return sum(_share(world, *terrains) for world in worlds) / len(worlds)

        heights = [average(("hills", "mountains"), relief=level) for level in (0, 1, 2)]
        assert heights[0] + 0.03 < heights[1] < heights[2] - 0.05
        wet = ("grassland", "jungle", "swamp", "river")
        humidity = [average(wet, climate=level) for level in (0, 1, 2)]
        assert humidity[0] + 0.03 < humidity[1] < humidity[2] - 0.03
