import copy
import json
import random
import unittest

from games import load_game
from games.bomb_party import baseline, demos
from games.bomb_party.engine import ACTIONS, Bomb, FROM_LETTER, Game, LETTER, Player, export, orbit, replay, spiral


def setup(points=((1, 1), (7, 7)), **config):
    g = Game.new(len(points), 7, {"size": 9, "max_turns": 120, "crush_start": 1000, "crush_rotation": 0, **config})
    g.grid = [["."] * 9 for _ in range(9)]
    g._spiral = spiral(9)  # This fixture's opening terrain is entirely floor.
    g._hidden = {}
    g.players = [Player(i, *point) for i, point in enumerate(points)]
    return g


def add_bomb(g, x=4, y=4, fuse=20, radius=2, owner=1, direction=None):
    b = Bomb(g.next_bomb, owner, x, y, fuse, radius, direction)
    g.bombs.append(b)
    g.next_bomb += 1
    return b


class MapTests(unittest.TestCase):
    def test_deterministic_and_rotational_hidden_contents(self):
        for seed in range(40):
            g = Game.new(4, seed)
            self.assertEqual(g.frame(), Game.new(4, seed).frame())
            self.assertEqual(g._hidden, Game.new(4, seed)._hidden)
            for y in range(13):
                for x in range(13):
                    for a, b in orbit(x, y, 13):
                        self.assertEqual(g.grid[y][x], g.grid[b][a])
                        self.assertEqual(g._hidden.get((x, y)), g._hidden.get((a, b)))
            self.assertTrue(all(g.grid[y][x] == "#" for x, y in g._hidden))

    def test_item_density_and_kinds_over_seeds(self):
        from collections import Counter
        bricks, kinds = 0, Counter()
        for seed in range(500):
            g = Game.new(4, seed)
            bricks += sum(r.count("#") for r in g.grid)
            kinds.update(g._hidden.values())
        ratio = sum(kinds.values()) / bricks
        self.assertTrue(.30 <= ratio <= .40, ratio)
        for kind, expected in (("fire", .4), ("bomb", .4), ("kick", .2)):
            self.assertLess(abs(kinds[kind] / sum(kinds.values()) - expected), .04)

    def test_corners_and_duel_diagonal(self):
        g = Game.new(4, 1)
        self.assertEqual([(p.x, p.y) for p in g.players], [(1, 1), (11, 1), (11, 11), (1, 11)])
        self.assertEqual([(p.x, p.y) for p in Game.new(2, 1).players], [(1, 1), (11, 11)])
        for p in g.players:
            self.assertEqual((p.radius, p.bomb_limit, p.can_kick), (2, 1, False))
            self.assertEqual(g.grid[p.y][p.x], ".")

    def test_optional_ten_player_map(self):
        g = Game.new(10, 4, {"size": 25})
        self.assertEqual(len({(p.x, p.y) for p in g.players}), 10)
        self.assertTrue(all(g.grid[p.y][p.x] == "." for p in g.players))
        self.assertEqual(g.width, 25)

    def test_invalid_configuration_and_detached_config(self):
        for cfg in ({"size": 12}, {"size": 3}, {"bomb_fuse": 0}, {"crush_start": 0},
                    {"max_bombs": 0}, {"brick_density": -1}, {"item_density": 2},
                    {"blast_radius": 9}, {"bomb_limit": 7}, {"size": True}, {"crush_rotation": 4},
                    {"crush_skip_initial_steel": 1}):
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                Game.new(4, 0, cfg)
        cfg = {"seats": ["a", "b"]}
        g = Game.new(2, 0, cfg)
        cfg["seats"][0] = "changed"
        self.assertEqual(g.config["seats"][0], "a")

    def test_pressure_rotation_is_seeded_balanced_and_frozen_in_config(self):
        for seed in range(4):
            g = Game.new(4, seed)
            self.assertEqual(g.config["crush_rotation"], seed)
            self.assertEqual((g.upcoming_crush()[0]["x"], g.upcoming_crush()[0]["y"]),
                             [(1, 1), (11, 1), (11, 11), (1, 11)][seed])
            self.assertEqual(g._spiral, Game.new(4, 100, g.config)._spiral)


class MovementTests(unittest.TestCase):
    def test_edges_steel_brick_and_missing_invalid_actions(self):
        g = setup(((0, 0), (7, 7)))
        g.step({0: "up", 1: "invalid"})
        self.assertEqual((g.players[0].x, g.players[0].y), (0, 0))
        for wall in ("@", "#"):
            g.grid[0][1] = wall
            g.step({0: "right"})
            self.assertEqual(g.players[0].x, 0)
        g.step({})
        self.assertEqual((g.players[1].x, g.players[1].y), (7, 7))
        self.assertEqual(g.fallback(0), "stay")

    def test_contest_swap_following(self):
        g = setup(((2, 3), (4, 3)))
        g.step({0: "right", 1: "left"})
        self.assertEqual([p.x for p in g.players], [2, 4])
        g.players[1].x = 3
        g.step({0: "right", 1: "left"})
        self.assertEqual([p.x for p in g.players], [2, 3])
        g.step({0: "right", 1: "right"})
        self.assertEqual([p.x for p in g.players], [2, 4])

    def test_plant_capacity_leave_and_no_reentry(self):
        g = setup(((2, 2), (7, 7)))
        g.step({0: "bomb"})
        self.assertEqual(g.bombs[0].fuse, 3)
        g.step({0: "down"})
        g.step({0: "up"})
        self.assertEqual((g.players[0].x, g.players[0].y), (2, 3))
        self.assertEqual(len(g.bombs), 1)
        g.step({0: "bomb"})
        self.assertEqual(g.players[0].bombs, 1)
        self.assertFalse(g.bombs)
        self.assertEqual(g.turn, 4)

    def test_multiple_bombs_and_radius_frozen_at_plant(self):
        g = setup()
        p = g.players[0]
        p.bomb_limit = 2
        g.step({0: "bomb"})
        p.radius = 7
        g.step({0: "right"})
        g.step({0: "bomb"})
        self.assertEqual([b.radius for b in g.bombs], [2, 7])
        self.assertEqual(p.bombs, 2)

    def test_no_bomb_stacking(self):
        g = setup()
        g.players[0].bomb_limit = 6
        g.step({0: "bomb"})
        g.step({0: "bomb"})
        self.assertEqual(len(g.bombs), 1)


class ItemTests(unittest.TestCase):
    def test_hidden_not_in_state_or_frame_until_revealed(self):
        g = setup()
        g.grid[4][4] = "#"
        g._hidden[4, 4] = "kick"
        self.assertEqual(g.state_for(0)["items"], [])
        self.assertNotIn("hidden", json.dumps(g.frame()))
        add_bomb(g, 2, 4, fuse=1)
        g.step({})
        self.assertEqual(g.items, {(4, 4): "kick"})
        self.assertEqual(g.state_for(0)["items"], [{"x": 4, "y": 4, "kind": "kick"}])
        self.assertIn("reveal", [e["type"] for e in g.events])
        self.assertEqual(g._hidden, {})

    def test_new_loot_survives_same_phase_multiple_rays(self):
        g = setup()
        g.grid[4][4] = "#"
        g._hidden[4, 4] = "fire"
        add_bomb(g, 2, 4, fuse=1)
        add_bomb(g, 6, 4, fuse=1)
        g.step({})
        self.assertEqual(g.items[4, 4], "fire")
        self.assertEqual(sum(e["type"] == "reveal" for e in g.events), 1)

    def test_walk_pickup_all_types_and_caps(self):
        for kind in ("fire", "bomb", "kick"):
            with self.subTest(kind=kind):
                g = setup(((2, 3), (7, 7)))
                g.items[3, 3] = kind
                g.step({0: "right"})
                p = g.players[0]
                self.assertEqual(p.pickups, 1)
                self.assertFalse(g.items)
                self.assertEqual((p.radius, p.bomb_limit, p.can_kick),
                                 {"fire": (3, 1, False), "bomb": (2, 2, False), "kick": (2, 1, True)}[kind])
                g.items[p.x, p.y] = kind
                p.radius, p.bomb_limit = 8, 6
                g.step({})
                self.assertEqual((p.radius, p.bomb_limit), (8, 6))
                self.assertEqual(p.pickups, 2)

    def test_exposed_loot_burns_without_blocking_ray(self):
        g = setup(((7, 1), (6, 4)))
        g.items[4, 4] = "bomb"
        add_bomb(g, 2, 4, fuse=1, radius=5, owner=0)
        g.step({})
        self.assertFalse(g.items)
        self.assertFalse(g.players[1].alive)
        self.assertTrue(any(e["type"] == "item_destroy" for e in g.events))

    def test_pickup_precedes_blast_and_consumes_even_at_cap(self):
        g = setup(((3, 4), (7, 7)))
        g.items[4, 4] = "kick"
        add_bomb(g, 6, 4, fuse=1, owner=1)
        g.step({0: "right"})
        self.assertTrue(g.players[0].can_kick)
        self.assertFalse(g.players[0].alive)
        self.assertEqual(g.players[0].pickups, 1)

    def test_pickup_on_start_cell_applies_to_same_turn_plant(self):
        g = setup()
        g.items[1, 1] = "fire"
        g.step({0: "bomb"})
        self.assertEqual(g.bombs[0].radius, 3)
        g = setup()
        add_bomb(g, 5, 5, owner=0)
        g.items[1, 1] = "bomb"
        self.assertFalse(g.state_for(0)["players"][0]["can_bomb"])
        g.step({0: "bomb"})
        self.assertEqual(len(g.bombs), 2)


class KickTests(unittest.TestCase):
    def kick_setup(self):
        g = setup(((3, 4), (7, 7)))
        g.players[0].can_kick = True
        b = add_bomb(g)
        return g, b

    def test_without_upgrade_blocked(self):
        g, b = self.kick_setup()
        g.players[0].can_kick = False
        g.step({0: "right"})
        self.assertEqual(g.players[0].x, 3)
        self.assertEqual((b.x, b.y, b.direction), (4, 4, None))

    def test_new_kick_upgrade_only_applies_next_turn(self):
        g, b = self.kick_setup()
        g.players[0].can_kick = False
        g.items[3, 4] = "kick"
        g.step({0: "right"})
        self.assertEqual(b.x, 4)
        self.assertTrue(g.players[0].can_kick)
        g.step({0: "right"})
        self.assertEqual(b.x, 5)

    def test_kick_stays_and_immediate_then_one_step_per_turn(self):
        g, b = self.kick_setup()
        g.step({0: "right"})
        self.assertEqual((g.players[0].x, b.x, b.fuse, b.direction), (3, 5, 19, "right"))
        g.step({})
        self.assertEqual(b.x, 6)
        self.assertTrue(g.frame()["bombs"][0]["sliding"])
        self.assertIn("kick", [e["type"] for e in g.events])

    def test_each_direction(self):
        for action, point, result in (("right", (3, 4), (5, 4)), ("left", (5, 4), (3, 4)),
                                      ("up", (4, 5), (4, 3)), ("down", (4, 3), (4, 5))):
            with self.subTest(action=action):
                g = setup((point, (7, 7)))
                g.players[0].can_kick = True
                b = add_bomb(g)
                g.step({0: action})
                self.assertEqual((b.x, b.y), result)

    def test_stops_at_steel_brick_item_person_bomb_and_boundary(self):
        for obstacle in ("@", "#", "item", "person", "bomb", "edge"):
            with self.subTest(obstacle=obstacle):
                g, b = self.kick_setup()
                if obstacle in ("@", "#"):
                    g.grid[4][5] = obstacle
                elif obstacle == "item":
                    g.items[5, 4] = "fire"
                elif obstacle == "person":
                    g.players[1].x, g.players[1].y = 5, 4
                elif obstacle == "bomb":
                    add_bomb(g, 5, 4)
                else:
                    b.x = 8
                    g.players[0].x = 7
                before = b.x
                g.step({0: "right"})
                self.assertEqual(b.x, before)
                self.assertIsNone(b.direction)
                # Stopped bombs do not resume after removing the obstacle.
                g.grid[4][5] = "."
                g.items.clear()
                g.players[1].x, g.players[1].y = 7, 7
                g.step({})
                self.assertEqual(b.x, before)

    def test_two_kickers_cancel_and_stop_previous_slide(self):
        g, b = self.kick_setup()
        g.players[1].x, g.players[1].y = 5, 4
        g.players[1].can_kick = True
        b.direction = "up"
        g.step({0: "right", 1: "left"})
        self.assertEqual((b.x, b.y, b.direction), (4, 4, None))
        self.assertTrue(next(e for e in g.events if e["type"] == "kick")["cancelled"])

    def test_person_entering_slide_route_wins_cell(self):
        g, b = self.kick_setup()
        g.players[1].x, g.players[1].y = 5, 3
        g.step({0: "right", 1: "down"})
        self.assertEqual((b.x, b.y, b.direction), (4, 4, None))
        self.assertEqual((g.players[1].x, g.players[1].y), (5, 4))

    def test_contested_player_moves_leave_route_open(self):
        g = setup(((3, 4), (5, 3), (5, 5)))
        g.players[0].can_kick = True
        b = add_bomb(g)
        g.step({0: "right", 1: "down", 2: "up"})
        self.assertEqual(b.x, 5)
        self.assertEqual([p.y for p in g.players[1:]], [3, 5])

    def test_newly_planted_bomb_stops_slide(self):
        g = setup(((5, 4), (7, 7)))
        b = add_bomb(g, 4, 4, direction="right")
        g.step({0: "bomb", 1: "up"})
        self.assertEqual((b.x, b.direction), (4, None))
        self.assertEqual(len(g.bombs), 2)

    def test_person_leaving_route_allows_slide(self):
        g, b = self.kick_setup()
        g.players[1].x, g.players[1].y = 5, 4
        g.step({0: "right", 1: "up"})
        self.assertEqual(b.x, 5)

    def test_two_slides_same_target_cancel(self):
        g = setup()
        b = add_bomb(g, 3, 4, direction="right")
        c = add_bomb(g, 5, 4, direction="left")
        g.step({})
        self.assertEqual((b.x, c.x), (3, 5))
        self.assertIsNone(b.direction)
        self.assertIsNone(c.direction)

    def test_bombs_cannot_swap_or_follow(self):
        for direction in ("left", "right"):
            g = setup()
            b = add_bomb(g, 3, 4, direction="right")
            c = add_bomb(g, 4, 4, direction=direction)
            g.step({})
            self.assertEqual(b.x, 3)
            self.assertIsNone(b.direction)
            self.assertEqual(c.x, 4 if direction == "left" else 5)

    def test_redirect_sliding_bomb(self):
        g = setup(((4, 3), (7, 7)))
        g.players[0].can_kick = True
        b = add_bomb(g, direction="right")
        g.step({0: "down"})
        self.assertEqual((b.x, b.y, b.direction), (4, 5, "down"))

    def test_slide_before_detonation_and_chain(self):
        g, b = self.kick_setup()
        b.fuse, b.radius = 1, 1
        add_bomb(g, 6, 4, fuse=20)
        g.step({0: "right"})
        self.assertEqual(g.bombs, [])
        self.assertEqual([e["at"] for e in g.events if e["type"] == "explode"], [[5, 4], [6, 4]])

    def test_pickup_removes_slide_obstacle_but_player_still_blocks(self):
        g, b = self.kick_setup()
        g.items[5, 4] = "bomb"
        g.players[1].x, g.players[1].y = 5, 3
        g.step({0: "right", 1: "down"})
        self.assertFalse(g.items)
        self.assertEqual((b.x, b.direction), (4, None))


class ExplosionTests(unittest.TestCase):
    def test_fuse_exact_and_no_persistent_flames(self):
        g = setup()
        g.step({0: "bomb"})
        for expected in (2, 1):
            g.step({})
            self.assertEqual(g.bombs[0].fuse, expected)
        g.step({})
        self.assertFalse(g.bombs)
        self.assertFalse(g.players[0].alive)
        self.assertEqual(g.players[0].death_turn, 4)
        g.step({})
        self.assertFalse(g.flames)

    def test_walking_into_previous_turn_fire_is_safe(self):
        g = setup(((4, 4), (7, 7)))
        add_bomb(g, 3, 3, fuse=1)
        g.step({})
        self.assertIn([4, 3], g.flames)
        g.step({0: "up"})
        self.assertTrue(g.players[0].alive)
        self.assertEqual((g.players[0].x, g.players[0].y), (4, 3))

    def test_brick_and_steel_block_rays(self):
        g = setup()
        g.grid[4][4], g.grid[2][2] = "#", "@"
        add_bomb(g, 2, 4, fuse=1, radius=5)
        g.step({})
        self.assertEqual(g.grid[4][4], ".")
        self.assertEqual(g.grid[2][2], "@")
        self.assertIn([4, 4], g.flames)
        self.assertNotIn([5, 4], g.flames)
        self.assertNotIn([2, 2], g.flames)

    def test_snapshot_bricks_and_stop_at_chained_bomb(self):
        g = setup()
        g.grid[4][4] = "#"
        add_bomb(g, 2, 4, fuse=1, radius=6)
        add_bomb(g, 6, 4, fuse=1, radius=6)
        g.step({})
        explosions = [e for e in g.events if e["type"] == "explode"]
        self.assertNotIn([5, 4], explosions[0]["cells"])
        self.assertNotIn([3, 4], explosions[1]["cells"])
        self.assertEqual(sum(p.bricks for p in g.players), 1)
        g = setup()
        add_bomb(g, 2, 4, fuse=1, radius=6)
        add_bomb(g, 4, 4, fuse=9, radius=1)
        g.step({})
        explosions = [e for e in g.events if e["type"] == "explode"]
        self.assertEqual(len(explosions), 2)
        self.assertNotIn([5, 4], explosions[0]["cells"])

    def test_new_bomb_can_chain_and_owner_stays_original(self):
        g = setup(((4, 4), (7, 7)))
        add_bomb(g, 2, 4, fuse=1, owner=1)
        g.step({0: "bomb"})
        self.assertFalse(g.bombs)
        self.assertEqual(g.players[0].killer, 1)
        self.assertEqual(g.players[1].kills, 1)

    def test_smallest_id_credit_and_dead_owner_gets_kills(self):
        g = setup(((2, 4), (4, 4), (4, 5)))
        add_bomb(g, 2, 4, fuse=1, radius=5, owner=0)
        add_bomb(g, 4, 6, fuse=1, radius=5, owner=2)
        g.step({})
        self.assertFalse(g.players[0].alive)
        self.assertIsNone(g.players[0].killer)
        self.assertEqual(g.players[1].killer, 0)
        self.assertEqual(g.players[0].kills, 1)


class CrushAndRankingTests(unittest.TestCase):
    def test_actual_opening_path_skips_steel_and_preserves_rotated_spiral(self):
        for n, size in ((2, 13), (4, 13), (10, 25)):
            for rotation in range(4):
                with self.subTest(n=n, rotation=rotation):
                    g = Game.new(n, 29, {"size": size, "crush_rotation": rotation})
                    expected = spiral(size)
                    for _ in range(rotation):
                        expected = [(size - 1 - y, x) for x, y in expected]
                    expected = [q for q in expected if g.grid[q[1]][q[0]] != "@"]
                    self.assertEqual(g._spiral, expected)
                    self.assertEqual(set(expected), {(x, y) for y in range(size) for x in range(size)
                                                     if g.grid[y][x] in ".#"})
                    self.assertEqual(len(expected), len(set(expected)))
                    if size == 13:
                        self.assertEqual(len(expected), 96)

    def test_first_wall_is_immediate_then_every_turn_and_preview_matches(self):
        g = Game.new(4, 0, {"crush_start": 2})
        original = copy.deepcopy(g.grid)
        path = list(g._spiral)
        self.assertEqual(g.upcoming_crush(), [{"x": x, "y": y, "turn": 2 + i}
                                             for i, (x, y) in enumerate(path[:5])])
        g.step({})
        self.assertEqual(g.crushed, [])
        for index, q in enumerate(path):
            preview = g.upcoming_crush()
            self.assertEqual((preview[0]["x"], preview[0]["y"]), q)
            self.assertEqual(preview[0]["turn"], g.turn + 1)
            self.assertNotEqual(original[q[1]][q[0]], "@")
            events = g.step({})
            self.assertEqual([tuple(e["at"]) for e in events if e["type"] == "crush"], [q])
            self.assertEqual(len(g.crushed), index + 1)
            self.assertEqual(g.grid[q[1]][q[0]], "@")
        self.assertEqual(g.upcoming_crush(), [])
        self.assertTrue(all(tile == "@" for row in g.grid for tile in row))
        for _ in range(3):
            self.assertFalse(any(e["type"] == "crush" for e in g.step({})))
        self.assertEqual(g.crushed, path)

    def test_path_is_frozen_when_a_scheduled_brick_is_broken(self):
        g = Game.new(4, 0, {"crush_start": 1000, "brick_density": 1})
        q, source = next((q, (q[0] + dx, q[1] + dy)) for q in g._spiral
                         for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0))
                         if g.grid[q[1]][q[0]] == "#" and g._floor((q[0] + dx, q[1] + dy)))
        index = g._spiral.index(q)
        before = list(g._spiral)
        add_bomb(g, *source, fuse=1, radius=1)
        g.step({})
        self.assertEqual(g.grid[q[1]][q[0]], ".")
        self.assertEqual(g._spiral, before)
        g.turn = 1000 + index - 1
        self.assertEqual(g.upcoming_crush()[0], {"x": q[0], "y": q[1], "turn": g.turn + 1})
        g.step({})
        self.assertEqual(g.crushed[-1], q)
        self.assertEqual(g.grid[q[1]][q[0]], "@")

    def test_spiral_complete_unique_order_and_preview_timing(self):
        cells = spiral(9)
        self.assertEqual(len(cells), 81)
        self.assertEqual(len(set(cells)), 81)
        self.assertEqual(cells[:10], [(x, 0) for x in range(9)] + [(8, 1)])
        self.assertEqual(cells[-1], (4, 4))
        g = setup(crush_start=2)
        self.assertEqual(g.upcoming_crush()[0], {"x": 0, "y": 0, "turn": 2})
        g.step({})
        self.assertFalse(g.crushed)
        g.step({})
        self.assertEqual(g.crushed, [(0, 0)])
        self.assertEqual(g.upcoming_crush()[0], {"x": 1, "y": 0, "turn": 3})
        self.assertEqual(len(g.upcoming_crush()), 5)

    def test_crush_person_bomb_item_and_hidden_no_kills(self):
        g = setup(((0, 0), (7, 7)), crush_start=1)
        add_bomb(g, 0, 0)
        g.items[0, 0] = "fire"
        g._hidden[0, 0] = "bomb"
        g.step({})
        self.assertEqual(g.players[0].death_cause, "crush")
        self.assertIsNone(g.players[0].killer)
        self.assertEqual(g.players[1].kills, 0)
        self.assertEqual(g.bombs, [])
        self.assertEqual(g.items, {})
        self.assertEqual(g._hidden, {})
        self.assertEqual(g.grid[0][0], "@")
        self.assertIn("crush", [e["type"] for e in g.events])
        self.assertFalse(g.flames)

    def test_blast_precedes_crush_and_move_can_dodge(self):
        g = setup(((0, 0), (7, 7)), crush_start=1)
        add_bomb(g, 1, 0, fuse=1)
        g.step({})
        self.assertEqual(g.players[0].death_cause, "blast")
        g = setup(((0, 0), (7, 7)), crush_start=1)
        g.step({0: "down"})
        self.assertTrue(g.players[0].alive)

    def test_crush_changes_future_rays_and_preview_exhausts(self):
        g = setup(crush_start=1)
        g.step({})
        add_bomb(g, 0, 2, fuse=1, radius=3)
        g.step({})
        self.assertNotIn([0, 0], g.flames)
        for _ in range(80):
            g.step({})
        self.assertEqual(len(g.crushed), 81)
        self.assertEqual(g.upcoming_crush(), [])

    def test_lifetime_kills_and_competition_ties(self):
        g = setup(((1, 1), (7, 7), (3, 3), (5, 5)))
        for p in g.players:
            p.alive, p.death_turn = False, 6
        g.players[0].kills = 2
        self.assertEqual(g.placements(), [1, 2, 2, 2])
        g.players[2].death_turn = 7
        self.assertEqual(g.placements(), [2, 3, 1, 3])
        g.players[1].alive = True
        self.assertEqual(g.placements(), [3, 1, 2, 4])
        g.players[3].alive = True
        self.assertEqual(g.placements(), [4, 1, 3, 1])

    def test_end_conditions_and_limit_tie(self):
        g = setup(max_turns=1)
        g.step({})
        self.assertTrue(g.over())
        self.assertEqual(g.placements(), [1, 1])
        g.players[0].kills = 1
        self.assertEqual(g.placements(), [1, 2])
        g = setup()
        g.players[0].alive = False
        self.assertTrue(g.over())
        g.players[1].alive = False
        self.assertTrue(g.over())


class ContractTests(unittest.TestCase):
    def test_legacy_merged_config_keeps_old_replay_path(self):
        g = Game.new(4, 0, {"crush_start": 1, "crush_skip_initial_steel": False})
        config = dict(g.config)
        config.pop("crush_skip_initial_steel")
        rows = ["SSSS"] * 6
        for _ in rows:
            g.step({})
        old = replay(4, 0, rows, config)
        self.assertEqual(old.frame(), g.frame())
        self.assertEqual(old.events, g.events)
        record = {"n": 4, "seed": 0, "moves": rows, "config": config, "seats": list("abcd")}
        self.assertEqual(export(record)["frames"][-1], g.frame())

    def test_partial_config_replay_uses_current_path(self):
        config = {"crush_start": 1}
        g = Game.new(4, 0, config)
        g.step({})
        self.assertEqual(replay(4, 0, ["SSSS"], config).frame(), g.frame())

    def test_state_and_frame_detached_json_and_fields(self):
        g = Game.new(4, 9)
        state = g.state_for(2)
        before = g.frame()
        state["grid"][0] = "broken"
        state["players"][0]["radius"] = 999
        state["next_crush"][0]["x"] = 999
        self.assertEqual(g.frame(), before)
        json.dumps(before)
        for key in ("items", "bombs", "flames", "crushed", "next_crush", "grid", "players"):
            self.assertIn(key, before)
        self.assertEqual(g.state_for(0)["turn"], 1)
        self.assertEqual(before["turn"], 0)
        frame = g.frame()
        g.step({0: "bomb"})
        self.assertFalse(frame["bombs"])
        for key in ("radius", "bomb_limit", "can_kick", "kills", "alive", "death_turn", "death_cause"):
            self.assertIn(key, frame["players"][0])

    def test_replay_all_frames_events_result_and_partial_export(self):
        rng = random.Random(33)
        for n, cfg in ((2, {}), (4, {}), (10, {"size": 25})):
            g = Game.new(n, 99, cfg)
            rows, frames = [], [g.frame()]
            for _ in range(100):
                actions = {p.id: rng.choice(ACTIONS) for p in g.alive()}
                rows.append("".join(LETTER.get(actions.get(i), ".") for i in range(n)))
                g.step(actions)
                frames.append(g.frame())
            record = {"n": n, "seed": 99, "config": g.config, "moves": rows, "seats": [str(i) for i in range(n)]}
            data = export(record)
            self.assertEqual(data["frames"], frames)
            self.assertEqual(data["events"], g.events)
            self.assertEqual(replay(n, 99, rows, g.config).result(), g.result())
            self.assertEqual(data["death"], g.result()["death"])
            self.assertEqual(export(record, 7)["frames"], frames[:8])
            self.assertEqual(export(record, 0)["frames"], frames[:1])

    def test_package_formats_and_demos(self):
        package = load_game("bomb_party")
        self.assertEqual(package.formats["melee"]["seats_per_game"], 4)
        self.assertEqual(package.config("duel")["size"], 13)
        self.assertEqual(package.config("melee")["size"], 13)
        self.assertLessEqual(len(package.rules), 4)
        all_demos = demos.build()
        self.assertEqual(len(all_demos), 4)
        for demo in all_demos.values():
            self.assertEqual(len(demo["frames"]), demo["turns"] + 1)
            self.assertTrue(demo["events"])
        types = {event["type"] for demo in all_demos.values() for event in demo["events"]}
        self.assertTrue({"bomb", "explode", "brick", "reveal", "pickup", "kick", "die", "crush"} <= types)

    def test_baseline_seeks_visible_loot(self):
        g = setup(((2, 3), (7, 7)))
        g.items[3, 3] = "kick"
        self.assertEqual(baseline.decide(g.state_for(0)), "right")

    def test_baseline_avoids_immediate_wall(self):
        g = setup(((0, 0), (7, 7)), crush_start=1)
        action = baseline.decide(g.state_for(0))
        self.assertIn(action, ("right", "down"))
        g.step({0: action})
        self.assertTrue(g.players[0].alive)

    def test_baseline_forecasts_sliding_chain(self):
        g = setup(((5, 3), (7, 7)))
        add_bomb(g, 3, 4, fuse=1, direction="right")
        add_bomb(g, 5, 4, fuse=5, radius=3)
        state = g.state_for(0)
        forecast = baseline._forecast(state)
        self.assertIn((5, 3), forecast[0][0])
        g.step({0: baseline.decide(state)})
        self.assertTrue(g.players[0].alive)

    def test_baseline_does_not_plan_through_newly_destroyed_brick(self):
        g = setup(((3, 4), (7, 7)))
        g.grid[4][4] = "#"
        add_bomb(g, 5, 4, fuse=1)
        forecast = baseline._forecast(g.state_for(0))
        self.assertEqual(forecast[0][3][4][4], "#")
        self.assertEqual(forecast[1][3][4][4], ".")

    def test_baseline_leaves_blast_lane_early_despite_visible_loot(self):
        g = setup(((3, 3), (7, 7)))
        add_bomb(g, 2, 3, fuse=3, radius=3, owner=0)
        g.items[5, 3] = "bomb"
        self.assertIn(baseline.decide(g.state_for(0)), ("up", "down"))

    def test_identical_baselines_choose_rotationally_equal_actions(self):
        rotate = {"up": "right", "right": "down", "down": "left", "left": "up", "bomb": "bomb", "stay": "stay"}
        for seed in range(12):
            g = Game.new(4, seed)
            for _ in range(30):
                if g.over():
                    break
                actions = {p.id: baseline.decide(g.state_for(p.id)) for p in g.alive()}
                expected = actions[0]
                for i in range(4):
                    self.assertEqual(actions[i], expected, (seed, g.turn, actions))
                    expected = rotate[expected]
                g.step(actions)

    def test_baseline_solitary_escape_does_not_use_occupied_enemy_cells(self):
        for seed in range(40):
            with self.subTest(seed=seed):
                g = Game.new(4, seed)
                while not g.over() and g.players[0].alive:
                    g.step({0: baseline.decide(g.state_for(0))})
                self.assertNotEqual(g.players[0].death_cause, "blast")


if __name__ == "__main__":
    unittest.main()
