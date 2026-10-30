"""像素拳斗引擎：规则、可重放、导出、选角、接口合同。

    python3 -m unittest games.brawl.tests.test_engine
"""
import json
import unittest
from pathlib import Path

from games import load_game
from games.brawl import demos, engine as E
from games.brawl.baseline import make


def fresh(chars=("lie", "tie"), xs=(170, 205)):
    return demos.setup(chars, xs)


def press(g, a, b, n=1):
    for _ in range(n):
        g.step({0: a, 1: b})


class Contract(unittest.TestCase):
    def test_package_loads(self):
        pkg = load_game("brawl")
        self.assertIs(pkg.engine, E)
        self.assertEqual(len(pkg.rules), 4)
        self.assertEqual(set(pkg.demos()), {"combo", "guard", "throw", "super"})
        self.assertTrue(all(len(E.LETTER[a]) == 1 for a in E.ACTIONS))
        self.assertEqual(len(set(E.LETTER.values())), len(E.ACTIONS))
        self.assertNotIn(".", E.LETTER.values())

    def test_select_and_fallback(self):
        g = E.Game.new(2, 7)
        self.assertEqual(g.state_for(0)["phase"], "select")
        g.step({0: "yan", 1: "nonsense"})
        self.assertEqual(g.f[0].char, "yan")
        self.assertIn(g.f[1].char, E.CHAR_KEYS)
        picks = [e for e in g.events if e["type"] == "pick"]
        self.assertEqual([p["drawn"] for p in picks], [False, True])
        g2 = E.Game.new(2, 7)
        g2.step({0: "yan", 1: "nonsense"})
        self.assertEqual(g2.f[1].char, g.f[1].char)  # 抽签只看种子

    def test_replay_and_export_match(self):
        for seed in range(6):
            g, rows = E.play([make("baseline", None, seed), make("rusher", None, seed + 50)], seed=seed)
            r = E.replay(2, seed, rows)
            self.assertEqual(r.result(), g.result())
            self.assertEqual(r.frame(), g.frame())
            ex = E.export({"seed": seed, "moves": rows, "seats": ["a", "b"], "config": dict(g.config)})
            self.assertEqual(len(ex["frames"]), g.turn + 1)
            self.assertEqual(ex["place"], g.placements())
            json.dumps(ex)
            self.assertTrue(g.over())

    def test_state_is_delayed_and_detached(self):
        g = fresh()
        press(g, "f", "n", 10)
        s = g.state_for(1)
        self.assertLess(s["opp"]["x"], g.f[0].x)  # 对手的位置是 6 帧前的
        self.assertEqual(s["me"]["x"], round(g.f[1].x, 2))
        s["me"]["hp"] = -5
        self.assertGreater(g.f[1].hp, 0)

    def test_result_shape(self):
        g, _ = E.play([make("baseline", "lie", 1), make("baseline", "rei", 2)], seed=3)
        r = g.result()
        for k in ("place", "death", "kills"):
            self.assertEqual(len(r[k]), 2)
        loser = r["place"].index(2) if 2 in r["place"] else None
        if loser is not None:
            self.assertIsNone(r["death"][1 - loser])
            self.assertEqual(r["death"][loser][2], 1 - loser)


class Rules(unittest.TestCase):
    def test_low_needs_crouch_guard(self):
        g = fresh(("yan", "tie"))
        press(g, "s", "b")
        press(g, "n", "b", 12)
        self.assertTrue(any(e["type"] == "hit" and e["mv"] == "s" for e in g.events))
        g = fresh(("yan", "tie"))
        press(g, "s", "g")
        press(g, "n", "g", 12)
        self.assertTrue(any(e["type"] == "block" for e in g.events))
        self.assertFalse(any(e["type"] == "hit" for e in g.events))

    def test_throw_beats_guard_and_tech(self):
        g = fresh(("tie", "lie"), (175, 205))
        press(g, "t", "b")
        press(g, "n", "b", 5)
        self.assertTrue(any(e["type"] == "throw" for e in g.events))
        g = fresh(("lie", "lie"), (175, 205))
        press(g, "t", "t")
        press(g, "n", "n", 3)
        self.assertTrue(any(e["type"] == "tech" for e in g.events))
        self.assertFalse(any(e["type"] == "throw" for e in g.events))

    def test_chip_cannot_kill(self):
        g = fresh(("rei", "lie"), (120, 250))
        g.f[1].hp = 3
        press(g, "z", "b", 1)
        press(g, "n", "b", 120)
        self.assertGreaterEqual(g.f[1].hp, 1)
        self.assertTrue(any(e["type"] == "block" for e in g.events))

    def test_jab_cannot_loop(self):
        # 轻拳打中后不占先手：一直按轻拳也连不上第二下（只能取消接必杀）
        for c in E.CHAR_KEYS:
            g = fresh((c, "tie"), (175, 200))
            press(g, "p", "n", 40)
            combos = [e["combo"] for e in g.events if e["type"] == "hit"]
            self.assertTrue(combos and max(combos) == 1, (c, combos))

    def test_cancel_into_special(self):
        d = demos.build()["combo"]
        hits = [e for e in d["events"] if e["type"] == "hit"]
        self.assertEqual([h["mv"] for h in hits], ["h", "z"])
        self.assertEqual(hits[1]["combo"], 2)

    def test_super_freezes_and_costs(self):
        g = demos.setup(("yan", "lie"), (165, 205), meter=(100, 0))
        press(g, "x", "n")
        self.assertEqual(g.flash, 18)
        self.assertEqual(g.f[0].meter, 0)
        t0 = g.timer
        press(g, "n", "f", 18)
        self.assertEqual(g.timer, t0)
        self.assertEqual(g.f[1].x, 205)  # 定格期间不动
        g2 = fresh()
        press(g2, "x", "n")
        self.assertEqual(g2.flash, 0)  # 没气按了等于站着

    def test_meter_persists_and_round_reset(self):
        g = fresh()
        g.f[0].meter = 150
        g.f[1].hp = 1
        press(g, "p", "n", 10)
        self.assertEqual(g.f[0].wins, 1)
        while g.phase != "intro":
            press(g, "n", "n")
        self.assertEqual(g.f[1].hp, g.f[1].c["hp"])
        self.assertGreaterEqual(g.f[0].meter, 150)
        self.assertEqual((g.f[0].x, g.f[1].x), (128.0, 256.0))

    def test_time_decision_uses_ratio(self):
        g = fresh(("tie", "yan"))
        g.f[0].hp, g.f[1].hp = 600, 500   # 铁山 600/1250 < 飞燕 500/890
        g.timer = 1
        press(g, "n", "n")
        self.assertEqual([f.wins for f in g.f], [0, 1])

    def test_walls(self):
        g = fresh()
        press(g, "b", "n", 200)
        self.assertGreaterEqual(g.f[0].x, E.WALL)


class Docs(unittest.TestCase):
    def test_prompt_in_sync(self):
        from games.brawl import make_prompt
        here = Path(E.__file__).parent
        head = (here / "PROMPT.head.md").read_text(encoding="utf-8")
        self.assertIn(make_prompt.table(), (here / "PROMPT.md").read_text(encoding="utf-8"))
        self.assertIn("{{MOVES}}", head)


if __name__ == "__main__":
    unittest.main()
