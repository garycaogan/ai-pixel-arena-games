"""一招鲜检查：每个角色只会一招（够得着就按，够不着就往前走），对四个角色的标准陪练各打若干局。

    python3 -m games.brawl.tests.spam --games 12 --out games/brawl/artifacts/spam.json
"""
import argparse
import json
import random
from multiprocessing import Pool
from pathlib import Path

from games.brawl import engine
from games.brawl.baseline import make

REACH = {"p": 40, "h": 54, "k": 62, "s": 60, "t": 36, "z": 999, "a": 34, "x": 70, "j": 140, "g": 0, "b": 0, "r": 999}
LABEL = {"p": "刷轻拳", "h": "刷重拳", "k": "刷脚", "s": "刷扫腿", "t": "刷投", "z": "刷必杀", "a": "刷对空",
         "x": "刷超必杀", "j": "一直跳", "g": "一直蹲防", "b": "一直站防", "r": "一直冲"}


def spam(key, char, seed):
    rng = random.Random(seed)

    def decide(s):
        if s["phase"] == "select":
            return char
        if s["phase"] != "fight":
            return "n"
        if key in "gb":
            return key
        d = abs(s["opp"]["x"] - s["me"]["x"])
        return key if d <= REACH[key] else ("f" if rng.random() < 0.9 else "n")
    return decide


def one(job):
    key, ca, cb, seed = job
    side = seed % 2
    bots = [spam(key, ca, seed), make("baseline", cb, seed + 7)]
    if side:
        bots.reverse()
    g, _ = engine.play(bots, seed=seed)
    p = g.placements()
    me = side
    return key, ca, 1.0 if p[me] < p[1 - me] else (0.5 if p[0] == p[1] else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=12)
    ap.add_argument("--out")
    a = ap.parse_args()
    jobs = [(k, ca, cb, s) for k in LABEL for ca in engine.CHAR_KEYS for cb in engine.CHAR_KEYS for s in range(a.games)]
    with Pool() as pool:
        res = pool.map(one, jobs, chunksize=8)
    agg = {}
    for k, c, v in res:
        agg.setdefault(f"{c}/{LABEL[k]}", []).append(v)
    out = {k: round(sum(v) / len(v), 3) for k, v in agg.items()}
    worst = sorted(out.items(), key=lambda kv: -kv[1])[:8]
    print("最好的一招鲜：", worst)
    if a.out:
        Path(a.out).write_text(json.dumps(dict(by=out, worst=worst), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
