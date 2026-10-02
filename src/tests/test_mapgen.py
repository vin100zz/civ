"""World generation and starting positions."""
from __future__ import annotations

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
