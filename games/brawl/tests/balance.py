"""陪练互打看平衡：四个角色两两对打（不含同角色），三种打法交叉，左右换边。

    python3 -m games.brawl.tests.balance --games 4 --out games/brawl/artifacts/balance.json
"""
import argparse
import itertools
import json
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

from games.brawl import engine
from games.brawl.baseline import make

STYLES = ("baseline", "rusher", "zoner")


def one(job):
    ca, cb, sa, sb, seed = job
    g, rows = engine.play([make(sa, ca, seed * 2 + 1), make(sb, cb, seed * 2 + 2)], seed=seed)
    r = g.result()
    rounds = [e for e in g.events if e["type"] == "round"]
    fights = [e["t"] for e in g.events if e["type"] == "fight"]
    lens = [(rd["t"] - ft) / engine.FPS for ft, rd in zip(fights, rounds)]
    moves = [Counter(), Counter()]
    for e in g.events:
        if e["type"] == "hit":
            moves[e["by"]][e["mv"]] += e["dmg"]
        elif e["type"] == "throw":
            moves[e["by"]][e["mv"]] += e["dmg"]
    return dict(chars=[ca, cb], styles=[sa, sb], place=r["place"], wins=r["wins"], frames=g.turn,
                fight_sec=sum(lens), round_lens=lens, reasons=[x["reason"] for x in rounds], moves=[dict(m) for m in moves],
                play=r["play"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=4, help="每组（角色对×打法对×边）的种子数")
    ap.add_argument("--out")
    ap.add_argument("--mirror", action="store_true", help="同一打法互打（不交叉打法）")
    a = ap.parse_args()
    jobs = []
    seed = 1
    for ca, cb in itertools.permutations(engine.CHAR_KEYS, 2):
        pairs = [(s, s) for s in STYLES] if a.mirror else list(itertools.product(STYLES, repeat=2))
        for sa, sb in pairs:
            for _ in range(a.games):
                jobs.append((ca, cb, sa, sb, seed))
                seed += 1
    with Pool() as pool:
        res = pool.map(one, jobs, chunksize=4)
    score = defaultdict(float)
    n = Counter()
    pair = defaultdict(float)
    pn = Counter()
    style_score = defaultdict(float)
    dmg_by_move = defaultdict(Counter)
    for r in res:
        for i in (0, 1):
            pts = 1.0 if r["place"][i] == 1 and r["place"][1 - i] == 2 else (0.5 if r["place"][0] == r["place"][1] else 0.0)
            score[r["chars"][i]] += pts
            n[r["chars"][i]] += 1
            pair[r["chars"][i], r["chars"][1 - i]] += pts
            pn[r["chars"][i], r["chars"][1 - i]] += 1
            style_score[r["chars"][i], r["styles"][i]] += pts
            for k, v in r["moves"][i].items():
                dmg_by_move[r["chars"][i]][k] += v
    secs = sorted(r["fight_sec"] for r in res)
    rl = sorted(x for r in res for x in r["round_lens"])
    reasons = Counter(x for r in res for x in r["reasons"])
    out = dict(
        games=len(res),
        char_winrate={c: round(score[c] / n[c], 3) for c in engine.CHAR_KEYS},
        matchups={f"{a}>{b}": round(pair[a, b] / pn[a, b], 3) for a, b in itertools.permutations(engine.CHAR_KEYS, 2)},
        char_style={f"{c}/{s}": round(style_score[c, s] / max(1, sum(1 for r in res for i in (0, 1) if r["chars"][i] == c and r["styles"][i] == s)), 3)
                    for c in engine.CHAR_KEYS for s in STYLES},
        match_fight_sec=dict(mean=round(sum(secs) / len(secs), 1), p10=secs[len(secs) // 10], p50=secs[len(secs) // 2],
                             p90=secs[len(secs) * 9 // 10]),
        round_sec=dict(mean=round(sum(rl) / len(rl), 1), p50=rl[len(rl) // 2]),
        reasons=dict(reasons),
        dmg_share={c: {k: round(v / max(1, sum(m.values())), 3) for k, v in m.most_common()} for c, m in dmg_by_move.items()},
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
