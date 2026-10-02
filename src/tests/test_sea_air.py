"""Ships, transport, naval combat and aircraft (milestone M6)."""
from __future__ import annotations

from server.ai.barbarian import BarbarianController
from server.ai.controller import AIController
from server.engine import actions
from server.engine.model.entities import Item
from server.engine.systems import barbarians, combat, movement, production, turn

from .conftest import add_city, make_game
from .test_units import RiggedRandom, start

# A strait: land on both sides of three columns of sea.
STRAIT = {(x, y): "ocean" for x in (6, 7, 8) for y in range(12)}


def sea_game(rules, **options):
    return make_game(rules, patches=STRAIT, **options)


# ── Building ships ────────────────────────────────────────────────────────────

def test_ships_need_a_coastal_city(rules):
    game = sea_game(rules)
    port = add_city(game, 1, 5, 5)
    inland = add_city(game, 1, 2, 5)
    game.players[1].techs.add("map_making")
    assert production.can_build(game, port, Item("unit", "trireme"))
    assert not production.can_build(game, inland, Item("unit", "trireme"))


# ── Transport ─────────────────────────────────────────────────────────────────

def test_land_units_board_travel_and_land(rules):
    game = sea_game(rules)
    ship = game.add_unit("sail", 1, 6, 5)
    legion = game.add_unit("legion", 1, 5, 5)
    start(game, 1)
    assert actions.apply(game, 1, actions.MoveUnit(legion.id, 6, 5)).outcome == "moved"
    assert legion.aboard == ship.id and game.cargo_of(ship) == [legion]

    assert actions.apply(game, 1, actions.MoveUnit(ship.id, 7, 5)).ok
    assert actions.apply(game, 1, actions.MoveUnit(ship.id, 8, 5)).ok
    assert legion.pos == ship.pos == (8, 5)                # the passenger travels with the ship

    start(game, 1)
    assert actions.apply(game, 1, actions.MoveUnit(legion.id, 9, 5)).outcome == "moved"
    assert legion.aboard is None and legion.pos == (9, 5)
    assert game.cargo_of(ship) == []


def test_a_ship_carries_no_more_than_its_capacity(rules):
    game = sea_game(rules)
    game.add_unit("trireme", 1, 6, 5)                      # capacity 2
    units = [game.add_unit("militia", 1, 5, 4 + i) for i in range(3)]
    start(game, 1)
    results = [actions.apply(game, 1, actions.MoveUnit(u.id, 6, 5)) for u in units]
    assert [r.ok for r in results] == [True, True, False]
    assert results[2].reason == "land units cannot enter the sea"


def test_boarding_in_port_and_landing_in_port(rules):
    game = sea_game(rules)
    add_city(game, 1, 5, 5)
    add_city(game, 1, 9, 5)
    ship = game.add_unit("sail", 1, 5, 5)
    settlers = game.add_unit("settlers", 1, 5, 5)
    start(game, 1)
    assert actions.apply(game, 1, actions.Board(settlers.id, ship.id))
    assert settlers.aboard == ship.id
    for x in (6, 7, 8):
        assert actions.apply(game, 1, actions.MoveUnit(ship.id, x, 5)).ok
    start(game, 1)
    assert actions.apply(game, 1, actions.MoveUnit(ship.id, 9, 5)).ok
    assert settlers.pos == (9, 5) and settlers.aboard is None      # put ashore in the port


def test_passengers_go_down_with_their_ship(rules):
    game = sea_game(rules)
    ship = game.add_unit("sail", 1, 7, 5)
    legion = game.add_unit("legion", 1, 7, 5)
    legion.aboard = ship.id
    enemy = game.add_unit("ironclad", 2, 7, 6)
    start(game, 2)
    game.rng = RiggedRandom([20, 0])
    assert movement.move_unit(game, enemy, game.map.tile(7, 5)) == movement.ATTACK_WON
    assert ship.id not in game.units and legion.id not in game.units


def test_no_attack_from_a_ship_and_none_on_a_ship_from_land(rules):
    game = sea_game(rules)
    ship = game.add_unit("sail", 1, 8, 5)
    legion = game.add_unit("legion", 1, 8, 5)
    legion.aboard = ship.id
    game.add_unit("militia", 2, 9, 5)
    shore_guard = game.add_unit("legion", 2, 9, 6)
    start(game, 1)
    assert movement.why_cannot_enter(game, legion, game.map.tile(9, 5)) == \
        "units cannot attack from a ship"
    assert movement.why_cannot_enter(game, legion, game.map.tile(9, 4)) is None   # free beach
    start(game, 2)
    assert movement.why_cannot_enter(game, shore_guard, game.map.tile(8, 5)) == \
        "land units cannot attack ships"


def test_passengers_do_not_defend_their_ship(rules):
    game = sea_game(rules)
    ship = game.add_unit("sail", 1, 7, 5)
    armor = game.add_unit("armor", 1, 7, 5)
    armor.aboard = ship.id
    attacker = game.add_unit("ironclad", 2, 7, 6)
    assert combat.best_defender(game, game.map.tile(7, 5), attacker) is ship


# ── Naval combat ──────────────────────────────────────────────────────────────

def test_ships_shell_the_coast_but_submarines_do_not(rules):
    game = sea_game(rules)
    game.add_unit("phalanx", 2, 9, 5)
    cruiser = game.add_unit("cruiser", 1, 8, 5)
    submarine = game.add_unit("submarine", 1, 8, 6)
    start(game, 1)
    target = game.map.tile(9, 5)
    assert movement.why_cannot_enter(game, cruiser, target) is None
    assert movement.why_cannot_enter(game, submarine, target) == "unit cannot attack land"
    assert movement.why_cannot_enter(game, cruiser, game.map.tile(9, 4)) == "ships cannot enter land"


def test_ships_do_not_capture_cities(rules):
    game = sea_game(rules)
    add_city(game, 2, 9, 5)
    cruiser = game.add_unit("cruiser", 1, 8, 5)
    start(game, 1)
    assert movement.why_cannot_enter(game, cruiser, game.map.tile(9, 5)) == \
        "unit cannot capture a city"


def test_city_walls_do_not_stop_ships(rules):
    game = sea_game(rules)
    city = add_city(game, 2, 9, 5)
    city.buildings.add("city_walls")
    defender = game.add_unit("phalanx", 2, 9, 5)
    tile = game.map.tile(9, 5)
    from_land = combat.defense_strength(game, defender, tile, game.add_unit("legion", 1, 10, 5))
    from_sea = combat.defense_strength(game, defender, tile, game.add_unit("cruiser", 1, 8, 5))
    assert from_land == 3 * from_sea


def test_trireme_may_be_lost_away_from_land(rules):
    ocean = {(x, y): "ocean" for x in range(4, 16) for y in range(12)}
    game = make_game(rules, patches=ocean)
    coastal = game.add_unit("trireme", 1, 4, 5)            # next to the land at x = 3
    far = game.add_unit("trireme", 1, 9, 5)
    passenger = game.add_unit("militia", 1, 9, 5)
    passenger.aboard = far.id
    safe = game.add_unit("sail", 1, 10, 8)
    game.rng = RiggedRandom([], chance=0.1)                # below lost_at_sea_chance
    movement.end_turn(game, game.players[1])
    assert coastal.id in game.units and safe.id in game.units
    assert far.id not in game.units and passenger.id not in game.units
    assert [e["type"] for e in game.events] == ["unit_lost"]


def test_sea_wonders_do_not_add_up(rules):
    game = sea_game(rules)
    city = add_city(game, 1, 5, 5)
    ship = game.add_unit("sail", 1, 6, 5)
    base = movement.full_moves(game, ship)
    for wonder in ("lighthouse", "magellans_expedition"):
        city.buildings.add(wonder)
        game.wonders[wonder] = city.id
    assert movement.full_moves(game, ship) == base + rules.game.movement.points_per_move


# ── Aircraft ──────────────────────────────────────────────────────────────────

def test_fighter_must_land_the_same_turn_but_a_bomber_has_two(rules):
    game = make_game(rules)
    add_city(game, 1, 5, 5)
    fighter = game.add_unit("fighter", 1, 8, 5)
    bomber = game.add_unit("bomber", 1, 8, 6)
    parked = game.add_unit("fighter", 1, 5, 5)
    player = game.players[1]
    movement.end_turn(game, player)
    assert fighter.id not in game.units                    # out of fuel
    assert bomber.id in game.units and bomber.fuel == 1
    assert parked.id in game.units and parked.fuel == rules.units["fighter"].fuel
    movement.end_turn(game, player)
    assert bomber.id not in game.units


def test_landing_ends_the_flight_and_refuels(rules):
    game = make_game(rules)
    add_city(game, 1, 5, 5)
    bomber = game.add_unit("bomber", 1, 6, 5)
    bomber.fuel = 1
    start(game, 1)
    assert actions.apply(game, 1, actions.MoveUnit(bomber.id, 5, 5)).outcome == "moved"
    assert bomber.moves_left == 0
    movement.end_turn(game, game.players[1])
    assert bomber.fuel == rules.units["bomber"].fuel


def test_aircraft_fly_over_the_sea_and_land_on_carriers(rules):
    game = sea_game(rules)
    carrier = game.add_unit("carrier", 1, 7, 5)
    fighter = game.add_unit("fighter", 1, 5, 5)
    start(game, 1)
    assert actions.apply(game, 1, actions.MoveUnit(fighter.id, 6, 5)).ok
    assert actions.apply(game, 1, actions.MoveUnit(fighter.id, 7, 5)).ok
    assert fighter.aboard == carrier.id and fighter.moves_left == 0
    movement.end_turn(game, game.players[1])
    assert fighter.id in game.units                        # refuelled on the carrier
    start(game, 1)
    assert actions.apply(game, 1, actions.MoveUnit(carrier.id, 7, 6)).ok
    assert fighter.pos == (7, 6)


def test_only_fighters_attack_aircraft_in_flight(rules):
    game = make_game(rules)
    game.add_unit("bomber", 2, 6, 5)
    legion = game.add_unit("legion", 1, 5, 5)
    fighter = game.add_unit("fighter", 1, 5, 6)
    start(game, 1)
    target = game.map.tile(6, 5)
    assert movement.why_cannot_enter(game, legion, target) == "unit cannot attack aircraft"
    assert movement.why_cannot_enter(game, fighter, target) is None


def test_aircraft_do_not_open_huts(rules):
    game = make_game(rules)
    game.map.tile(6, 5).hut = True
    fighter = game.add_unit("fighter", 1, 5, 5)
    start(game, 1)
    assert actions.apply(game, 1, actions.MoveUnit(fighter.id, 6, 5)).ok
    assert game.map.tile(6, 5).hut and not game.events


# ── Barbarians from the sea ───────────────────────────────────────────────────

def test_barbarians_land_from_the_sea(rules):
    ocean = {(x, y): "ocean" for x in range(6, 20) for y in range(12)}
    game = make_game(rules, width=24, patches=ocean)
    city = add_city(game, 1, 5, 5)
    game.players[1].visible = bytearray(len(game.map.tiles))     # nobody watches the sea
    tier = production.barbarian_tier(game)
    assert barbarians._sea_raid(game, city, tier, 3)
    ship = next(u for u in game.units.values() if rules.units[u.type].domain == "sea")
    raiders = game.cargo_of(ship)
    assert len(raiders) == 3 and all(r.owner == 0 for r in raiders)

    controller = BarbarianController()
    barbarian_player = game.players[0]
    for _ in range(8):
        turn.begin_player_turn(game, barbarian_player)
        controller.play_turn(game, barbarian_player)
        turn.end_player_turn(game, barbarian_player)
        if ship.id not in game.units:
            break
    assert ship.id not in game.units                       # the ship leaves once they are ashore
    ashore = [u for u in game.units.values() if u.owner == 0]
    assert ashore and all(game.terrain(game.tile_of(u)).is_land for u in ashore)


# ── The AI at sea ─────────────────────────────────────────────────────────────

def play_alone(game, player_id, turns, done):
    """Plays the turns of one AI player until `done()`; returns the number of turns played."""
    controller = game.controllers[player_id]
    player = game.players[player_id]
    for played in range(turns):
        if done():
            return played
        turn.begin_player_turn(game, player)
        controller.play_turn(game, player)
        turn.end_player_turn(game, player)
        game.turn += 1
    return turns


def test_ai_settles_across_the_sea(rules):
    """A civilization alone on a small island finds the land next door and settles it."""
    width, height = 24, 12
    patches = {(x, y): "ocean" for x in range(width) for y in range(height)}
    patches.update({(x, y): "grassland" for x in (3, 4, 5) for y in (4, 5, 6)})        # home
    patches.update({(x, y): "grassland" for x in range(9, 15) for y in range(3, 9)})   # next door
    game = make_game(rules, width=width, height=height, patches=patches)
    city = add_city(game, 1, 5, 5, size=4)
    game.add_unit("phalanx", 1, 5, 5)
    player = game.players[1]
    player.techs.update({"bronze_working", "alphabet", "map_making", "navigation"})
    player.gold = 5000
    game.controllers[1] = AIController()

    def colony_founded():
        return any(c.x >= 9 for c in game.player_cities(1))

    played = play_alone(game, 1, 150, colony_founded)
    assert colony_founded(), "no colony after 150 turns"
    assert played < 150
    assert city.id in game.cities
    # Nobody is left drifting at sea.
    for unit in game.player_units(1):
        if rules.units[unit.type].domain == "land":
            assert game.terrain(game.tile_of(unit)).is_land or unit.aboard is not None


def test_ai_invades_across_the_sea(rules):
    """At war with a neighbour it can only reach by sea, the AI ships an army and takes a city."""
    width, height = 24, 12
    patches = {(x, y): "ocean" for x in range(width) for y in range(height)}
    patches.update({(x, y): "grassland" for x in (3, 4, 5) for y in (4, 5, 6)})        # home
    patches.update({(x, y): "grassland" for x in range(9, 15) for y in range(3, 9)})   # the enemy
    game = make_game(rules, width=width, height=height, patches=patches)
    add_city(game, 1, 5, 5, size=5)
    game.add_unit("phalanx", 1, 5, 5)
    enemy_city = add_city(game, 2, 9, 5, size=3)
    player = game.players[1]
    player.techs.update({"bronze_working", "alphabet", "map_making", "navigation",
                         "iron_working"})
    player.gold = 8000
    game.controllers[1] = AIController()

    def city_taken():
        return enemy_city.id in game.cities and game.cities[enemy_city.id].owner == 1

    played = play_alone(game, 1, 200, city_taken)
    assert city_taken(), "the enemy city still stands after 200 turns"
    assert played < 200


def test_ai_aircraft_strike_and_come_back(rules):
    game = make_game(rules)
    add_city(game, 1, 5, 5)
    game.add_unit("riflemen", 1, 5, 5)
    fighter = game.add_unit("fighter", 1, 5, 5)
    enemy = game.add_unit("settlers", 2, 7, 5)
    add_city(game, 2, 12, 5)
    game.controllers[1] = AIController()
    play_alone(game, 1, 1, lambda: False)
    assert enemy.id not in game.units or fighter.id not in game.units     # it attacked
    if fighter.id in game.units:
        assert game.city_at(fighter.x, fighter.y) is not None             # and came back
