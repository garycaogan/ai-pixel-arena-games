import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "games/brawl"))
sys.path.insert(0, str(HERE))
import engine as E
import driver as D
import build as B

BASE = (ROOT / "games/brawl/baseline.py").read_text()


class DriverTests(unittest.TestCase):
    def setUp(self):
        (HERE / "verification").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=HERE / "verification")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / "bots").mkdir()
        self.bot("baseline", BASE)
        for style in ("rusher", "zoner"):
            src = ROOT / "games/brawl/artifacts/bots" / (style + ".py")
            if src.is_file():
                shutil.copyfile(src, self.home / "bots" / (style + ".py"))
        p = patch.object(D, "HERE", self.home)
        p.start()
        self.addCleanup(p.stop)

    def bot(self, slug, source):
        (self.home / "bots" / (slug + ".py")).write_text(source)

    def play(self, table, script=None):
        frames, k = [table.g.frame()], 0
        while not table.g.over():
            inp = script(k, table) if script else {}
            frames.extend(table.step([inp])["frames"])
            k += 1
        return frames

    def test_ai_vs_ai_matches_engine_replay_every_frame(self):
        seats = ["baseline", "rusher" if (self.home / "bots/rusher.py").exists() else "baseline"]
        for seed in (0, 7, 43):
            with self.subTest(seed=seed):
                table = D.Table(seats, None, seed)
                frames = self.play(table)
                exported = E.export({"moves": table.rows, "seed": seed, "seats": seats})
                self.assertEqual(frames, exported["frames"])
                self.assertEqual(table.g.result()["wins"], exported["wins"])
                self.assertFalse(any(table.broken))
                self.assertEqual(table.step([{}])["frames"], [])

    def test_scripted_human_match_replays_and_uses_pick(self):
        presses = ["p", "h", "k", "s", "t", "z", "a", "x", "dash+", "dash-"]

        def script(k, table):
            return {"h": (1, 1, 0, -1, 1)[k // 20 % 5], "v": (0, 0, -1, 0, 1, 0)[k // 33 % 6],
                    "press": [presses[k // 7 % len(presses)]] if k % 7 == 0 else []}
        for seed in (1, 99):
            table = D.Table(["human", "baseline"], 0, seed, pick="rei")
            frames = self.play(table, script)
            self.assertEqual(table.rows[0][0], "R")
            self.assertEqual(table.g.result()["chars"][0], "rei")
            self.assertEqual(frames, E.export({"moves": table.rows, "seed": seed, "seats": ["human", "baseline"]})["frames"])
            used = set("".join(r[0] for r in table.rows[1:]))
            self.assertTrue({"p", "h", "f", "b", "j", "d"} <= used, used)

    def fight(self, pick="lie"):
        table = D.Table(["human", "baseline"], 0, 5, pick=pick)
        while table.g.phase != "fight":
            table.step([{}])
        return table

    def test_absolute_directions_follow_facing(self):
        table = self.fight()
        f = table.g.f[0]
        self.assertEqual(f.face, 1)
        cases = [({"h": 1}, "f"), ({"h": -1}, "b"), ({"v": -1, "h": -1}, "g"), ({"v": -1}, "d"),
                 ({"v": 1, "h": 1}, "j"), ({"v": 1, "h": -1}, "y"), ({"v": 1}, "u"), ({}, "n")]
        for inp, want in cases:
            self.assertEqual(table.human_action(inp), want, inp)
        f.face = -1
        self.assertEqual(table.human_action({"h": 1}), "b")
        self.assertEqual(table.human_action({"press": ["dash+"]}), "e")
        f.face = 1
        self.assertEqual(table.human_action({"press": ["dash+"]}), "r")
        self.assertEqual(table.human_action({"h": 7, "v": "x", "press": "p"}), "n")

    def test_attack_button_is_buffered_until_it_can_start(self):
        table = self.fight()
        table.step([{"press": ["h"]}])          # 重拳开始
        self.assertEqual(table.rows[-1][0], "h")
        m = table.g.f[0].move("h")
        while table.g.f[0].mf < m["s"] + m["a"] + m["r"] - 4:
            table.step([{}])
        table.step([{"press": ["p"]}])          # 收招最后几帧按轻拳：先缓冲
        self.assertNotEqual(table.rows[-1][0], "p")
        self.assertIsNotNone(table.buffer)
        started = None
        for k in range(D.BUFFER):
            table.step([{}])
            if table.rows[-1][0] == "p":
                started = k
                break
        self.assertIsNotNone(started, "buffered jab never came out")
        self.assertIsNone(table.buffer)
        # 一直出不了招的按键过了缓冲期就丢掉
        table = self.fight()
        table.g.f[0].st, table.g.f[0].stun = "hitstun", 40
        table.step([{"press": ["k"]}])
        for _ in range(D.BUFFER + 2):
            table.step([{}])
        self.assertIsNone(table.buffer)
        self.assertNotIn("k", "".join(r[0] for r in table.rows[-D.BUFFER - 3:]))

    def test_bad_bots_stand_still_then_disable(self):
        self.bot("bad", "def decide(s): return ['p']\n")
        self.bot("raises", "def decide(s): raise SystemExit()\n")
        table = D.Table(["bad", "raises"], None, 2)
        for _ in range(3):
            table.step([{}])
        self.assertEqual(table.broken, [True, True])
        self.assertEqual(table.errors, [3, 3])
        self.assertEqual(table.rows[1:], ["nn", "nn"])

    def test_slow_and_looping_bots_are_cut_off(self):
        self.bot("loop", "def f():\n return 1\ndef decide(s):\n while True: f()\n")
        self.bot("slow", "import time\ndef decide(s):\n time.sleep(.02)\n return 'n'\n")
        start = time.perf_counter()
        with patch.object(D, "SLOW", 0.01):
            table = D.Table(["loop", "slow"], None, 2)
            table.step([{}])
        self.assertLess(time.perf_counter() - start, 1)
        self.assertEqual(table.broken, [True, True])
        self.assertIsNone(sys.gettrace())

    def test_load_errors(self):
        table = D.Table(["missing", "../escape"], None, 2)
        self.assertEqual(table.broken, [True, True])
        self.assertEqual(set(table.load_errors), {0, 1})
        with self.assertRaises(ValueError):
            D.Table(["baseline"], None, 1)
        with self.assertRaises(ValueError):
            D.Table(["baseline", "baseline"], 2, 1)

    def test_same_seed_same_match_with_fresh_modules(self):
        self.bot("rand", "import random\nn=0\ndef decide(s):\n global n\n n+=1\n return random.choice(s['chars']) if s['phase']=='select' else random.choice('fbpkhjn')\n")
        runs = []
        for _ in range(2):
            table = D.Table(["rand", "rand"], None, 77)
            for _ in range(200):
                table.step([{}])
            runs.append(table.rows)
        self.assertEqual(*runs)

    def test_rpc_json_contract(self):
        reply = json.loads(D.rpc("start", json.dumps({"seats": ["human", "baseline"], "human": 0, "seed": 3, "pick": "tie"})))
        self.assertEqual(reply["seed"], 3)
        self.assertEqual(reply["frame"]["phase"], "select")
        reply = json.loads(D.rpc("step", json.dumps({"inputs": [{}] * 5})))
        self.assertEqual(len(reply["frames"]), 5)
        self.assertEqual(reply["frames"][0]["f"][0]["char"], "tie")
        reply = json.loads(D.rpc("step", json.dumps({"inputs": [{}] * 50})))
        self.assertEqual(len(reply["frames"]), D.MAX_BATCH)
        self.assertIn("mean_ms", json.loads(D.rpc("stats")))


class BuildTests(unittest.TestCase):
    def setUp(self):
        (HERE / "verification").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=HERE / "verification")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_build_manifest_and_versions(self):
        source = self.base / "source"
        source.mkdir()
        for name in B.PAGE_FILES:
            shutil.copyfile(HERE / name, source / name)
        with patch.object(B, "HERE", source):
            out = self.base / "dist"
            first = B.build(out, cast_only="baseline")
            manifest = json.loads((out / "manifest.json").read_text())
            for name, digest in manifest["hashes"].items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest, name)
            for name in manifest["files"]:
                self.assertTrue((out / name).is_file())
            self.assertEqual([c["slug"] for c in manifest["cast"]], ["baseline"])
            self.assertEqual(manifest["cast"][0]["name"], "陪练")
            for banned in ("online.js", "ququ.js", "ququ.css", "ququ-config.json"):
                self.assertFalse((out / banned).exists(), banned)
            page = (out / "index.html").read_text()
            for token in ("__VERSION__", "__LINK_"):
                self.assertNotIn(token, page)
            self.assertIn(B.LINKS["video"], page)
            self.assertIn(B.LINKS["source"], page)
            self.assertNotIn("拳皇", page)
            self.assertNotIn("__PYODIDE__", (out / "worker.js").read_text())
            self.assertEqual(first["version"], B.build(out, cast_only="baseline")["version"])
            with (source / "app.js").open("a") as stream:
                stream.write("\n// content hash test\n")
            self.assertNotEqual(first["version"], B.build(out, cast_only="baseline")["version"])

    def test_cast_order_and_names(self):
        self.assertEqual([c["name"] for c in B.CAST],
                         ["GPT", "Claude", "Grok", "MiniMax", "Gemini", "千问", "GLM", "DeepSeek", "豆包", "Kimi", "陪练"])
        self.assertEqual(B.CAST[-1]["slug"], "baseline")
        with self.assertRaisesRegex(ValueError, "没有这些 slug"):
            B.pick_cast("nobody")

    def test_missing_bot_file_is_a_clear_error(self):
        cast = [dict(c, source=self.base / "nope" / (c["slug"] + ".py")) if c["slug"] == "opus" else c for c in B.CAST]
        with patch.object(B, "CAST", cast):
            with self.assertRaisesRegex(FileNotFoundError, r"opus（Claude）"):
                B.build(self.base / "dist", cast_only="opus,baseline")

    def test_missing_runtime_and_bad_outputs(self):
        with self.assertRaisesRegex(FileNotFoundError, "no downloads attempted"):
            B.build(self.base / "dist", HERE / "not-installed", cast_only="baseline")
        for bad in (HERE, ROOT / "games/brawl/out", HERE / "tests"):
            with self.assertRaises(ValueError):
                B.build(bad, cast_only="baseline")
        with self.assertRaises(ValueError):
            B.build(self.base / "dist", base="/abs", cast_only="baseline")


if __name__ == "__main__":
    unittest.main()
