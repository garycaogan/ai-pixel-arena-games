import hashlib
import importlib.util
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
sys.path.insert(0, str(ROOT / "games/bomb_party"))
sys.path.insert(0, str(HERE))
import engine as E
import driver as D
import build as B

CAST = ["baseline", "aggressive", "farmer", "kicker"]   # 驱动测试坐包里的四个测试陪练，和网页名单（B.CAST）无关


class DriverTests(unittest.TestCase):
    def setUp(self):
        (HERE / "verification").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=HERE / "verification")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        shutil.copytree(ROOT / "bots/bomb_party", self.home / "bots")
        self.patch = patch.object(D, "HERE", self.home)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def bot(self, slug, source):
        (self.home / "bots" / (slug + ".py")).write_text(source)

    def test_scripted_complete_games_match_engine_replay_every_frame(self):
        for human in (0, None):
            for seed in (0, 7, 43, 101):
                with self.subTest(human=human, seed=seed):
                    table = D.Table(CAST, human, seed)
                    frames, events = [table.g.frame()], []
                    while not table.g.over():
                        action = ("right", "down", "bomb", "left", "up", "stay", "bomb")[table.g.turn % 7]
                        reply = table.step(action)
                        frames.append(reply["frame"])
                        events.extend(reply["events"])
                    exported = E.export_game(E.Game.new(4, seed), table.rows, CAST)
                    self.assertEqual(frames, exported["frames"])
                    self.assertEqual(events, exported["events"])
                    self.assertEqual(table.g.result()["place"], exported["place"])
                    self.assertEqual(table.g.result()["death"], exported["death"])
                    self.assertEqual(table.g.result()["kills"], exported["kills"])
                    turn = table.g.turn
                    table.step("bomb")
                    self.assertEqual(table.g.turn, turn)
                    self.assertFalse(any(table.broken))

    def test_bad_actions_and_exceptions_stay_then_disable(self):
        self.bot("bad", "def decide(s): return ['up']\n")
        self.bot("raises", "def decide(s): raise SystemExit()\n")
        self.bot("good", "def decide(s): return 'stay'\n")
        table = D.Table(["bad", "raises", "good", "good"], None, 2)
        for _ in range(3):
            self.assertEqual(table.step()["moves"], "SSSS")
        self.assertEqual(table.broken, [True, True, False, False])
        table.step()
        self.assertEqual(table.errors, [3, 3, 0, 0])

    def test_success_clears_strikes_and_state_cannot_mutate_engine(self):
        self.bot("intermittent", "n=0\ndef decide(s):\n global n\n n+=1\n s['grid'][1]='@'*13\n return 'stay' if n%3==0 else None\n")
        table = D.Table(["intermittent"] * 4, None, 2)
        for _ in range(8):
            table.step()
        self.assertFalse(any(table.broken))
        self.assertEqual(table.strikes, [2] * 4)
        self.assertEqual(table.g.frame()["grid"], E.Game.new(4, 2).frame()["grid"])

    def test_python_infinite_loop_is_interrupted_and_immediately_disabled(self):
        self.bot("loop", "def decide(s):\n while True: pass\n")
        table = D.Table(["loop"] * 4, 0, 2)
        start = time.perf_counter()
        with patch.object(D, "SLOW", 0.01):
            reply = table.step()
        self.assertLess(time.perf_counter() - start, 1)
        self.assertEqual(reply["moves"], "SSSS")
        self.assertEqual(table.broken, [False, True, True, True])
        self.assertIsNone(sys.gettrace())

    def test_slow_return_load_errors_and_invalid_human(self):
        self.bot("slow", "import time\ndef decide(s):\n time.sleep(.015)\n return 'bomb'\n")
        table = D.Table(["baseline", "slow", "missing", "../escape"], 0, 2)
        with patch.object(D, "SLOW", 0.003):
            reply = table.step({"invalid": True})
        self.assertEqual(reply["moves"], "SSSS")
        self.assertEqual(table.broken, [False, True, True, True])
        self.assertEqual(set(table.load_errors), {2, 3})

    def test_same_slug_seats_have_fresh_module_and_rng_per_game(self):
        self.bot("random", "import random\nn=0\ndef decide(s):\n global n\n n+=1\n return random.choice(['left','right','up','down','stay']) if n>1 else 'stay'\n")
        records = []
        for _ in range(2):
            table = D.Table(["random"] * 4, None, 77)
            for _ in range(20):
                table.step()
            self.assertEqual(table.rows[0], "SSSS")
            records.append(table.rows)
        self.assertEqual(*records)

    def test_rpc_json_contract(self):
        reply = json.loads(D.rpc("start", json.dumps({"seats": CAST, "human": 0, "seed": 0})))
        self.assertEqual(reply["seed"], 0)
        self.assertEqual(reply["frame"]["turn"], 0)
        reply = json.loads(D.rpc("step", '{"action":"bomb"}'))
        self.assertEqual(reply["moves"][0], "B")
        self.assertEqual(reply["frame"]["turn"], 1)


class BuildTests(unittest.TestCase):
    def test_complete_reproducible_build_and_content_versions(self):
        (HERE / "verification").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=HERE / "verification") as folder:
            base = Path(folder)
            source = base / "source"
            source.mkdir()
            shutil.copytree(HERE / "assets", source / "assets")
            for name in ("index.html", "style.css", "app.js", "input.js", "audio.js", "worker.js", "driver.py"):
                shutil.copyfile(HERE / name, source / name)
            with patch.object(B, "HERE", source):
                out = base / "dist"
                first = B.build(out)
                manifest = json.loads((out / "manifest.json").read_text())
                for name, digest in manifest["hashes"].items():
                    self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest, name)
                for name in manifest["files"]:
                    self.assertTrue((out / name).is_file())
                self.assertEqual([c["name"] for c in manifest["cast"]], [c["name"] for c in B.CAST])
                self.assertEqual(manifest["cast"][0]["slug"], "opus")      # 杯赛冠军排第一，默认对手
                self.assertEqual(manifest["cast"][-1]["slug"], "baseline")
                self.assertLess((out / "stage.jpg").stat().st_size, (B.ART / "stage-1080.png").stat().st_size)
                for name in ("index.html", "worker.js"):
                    self.assertNotIn("__VERSION__", (out / name).read_text())
                    self.assertNotIn("__PYODIDE__", (out / name).read_text())
                self.assertEqual(first["version"], B.build(out)["version"])
                with (source / "app.js").open("a") as stream:
                    stream.write("\n// content hash test\n")
                second = B.build(out)
                self.assertNotEqual(first["version"], second["version"])
                with patch.object(B, "CAST", [dict(c, name=c["name"] + "测试") for c in B.CAST]):
                    self.assertNotEqual(second["version"], B.build(out)["version"])
                with patch.object(B, "LINKS", {"video": "#different", "source": "#source"}):
                    self.assertNotEqual(second["version"], B.build(out)["version"])

    def test_missing_local_runtime_fails_without_download(self):
        with self.assertRaisesRegex(FileNotFoundError, "no downloads attempted"):
            B.build(HERE / "verification/no-build", HERE / "not-installed")


if __name__ == "__main__":
    unittest.main()
