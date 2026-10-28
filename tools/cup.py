"""炸弹派对杯：小组赛加决赛，局数少到每局都能在节目里放。

10 家 AI 加 2 个陪练抽签分成 3 个 4 人小组；每组打 4 局，四个出生角每人各站一次，
三个小组用同样的 4 张图。名次积分 3/2/1/0（并列同分），同分看击杀、再看存活回合。
每组最好的 AI 出线（陪练不出线），再加三个小组第二里最好的一家，4 家打决赛，
决赛换 4 张新图、同样轮换出生角；冠军同分同击杀就加赛，加赛里名次最好的赢。

    .venv/bin/python tools/bomber_cup.py --bots-dir bots/bomb_party --out results/bomb_party
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from games import load_game  # noqa: E402

GAME = "bomb_party"
AIS = ["opus", "astra", "gemini", "deepseek", "kimi", "doubao", "qwen", "glm", "minimax", "grok"]
SPARRING = "baseline"
POINTS = {1: 3, 2: 2, 3: 1, 4: 0}
GROUPS = "ABC"


def play_one(task):
    from arena.referee import BotProc, play
    gid, seed, seats, paths = task
    bots = [BotProc(paths[name]) for name in seats]
    try:
        t0 = time.monotonic()
        config = load_game(GAME).config("melee", n=4)
        rec = play(bots, seed, names=list(seats), collect_errors=True, game=GAME, config=config)
        rec["wall"] = round(time.monotonic() - t0, 3)
        rec["id"] = gid
        return rec
    finally:
        for b in bots:
            b.kill()


def rotation(members, k):
    """第 k 局：座位 s（出生角 s）坐 members[(s + k) % 4]，四局下来每人每个角各一次。"""
    return [members[(s + k) % 4] for s in range(4)]


def tally(records, members):
    rows = {m: {"slug": m, "points": 0, "kills": 0, "survival": 0, "places": [], "games": []} for m in members}
    for rec in records:
        for seat, name in enumerate(rec["seats"]):
            row = rows[name]
            place = rec["place"][seat]
            death = rec["death"][seat]
            row["points"] += POINTS[place]
            row["kills"] += rec["kills"][seat]
            row["survival"] += death[0] if death else rec["turns"]
            row["places"].append(place)
            row["games"].append(rec["id"])
    return rows


def ranked(rows, lots):
    return sorted(rows.values(), key=lambda r: (-r["points"], -r["kills"], -r["survival"], lots[r["slug"]]))


def summary(rec, export_path):
    seats = rec["seats"]
    return {"id": rec["id"], "seed": rec["seed"], "seats": seats, "turns": rec["turns"],
            "place": rec["place"], "death": rec["death"], "kills": rec["kills"],
            "bombs": rec.get("bombs"), "bricks": rec.get("bricks"), "pickups": rec.get("pickups"),
            "timeouts": [s.get("timeouts", 0) for s in rec.get("stats", [])],
            "errors": [s.get("errors", 0) for s in rec.get("stats", [])],
            "crush_rotation": (rec.get("config") or {}).get("crush_rotation"),
            "wall": rec.get("wall"), "export": str(export_path.relative_to(ROOT) if export_path.is_relative_to(ROOT) else export_path)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bots-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "results/bomb_party")
    ap.add_argument("--seed", type=int, default=20261028, help="抽签和地图的公开种子")
    ap.add_argument("--players", nargs="+", default=AIS)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    package = load_game(GAME)
    out = a.out if a.out.is_absolute() else ROOT / a.out
    (out / "games").mkdir(parents=True, exist_ok=True)
    paths = {s: str((a.bots_dir if a.bots_dir.is_absolute() else ROOT / a.bots_dir) / f"{s}.py") for s in a.players}
    paths[SPARRING] = str(package.path / "baseline.py")
    missing = [s for s, p in paths.items() if not Path(p).is_file()]
    if missing:
        raise SystemExit("缺程序：" + ", ".join(missing))
    if len(a.players) + 2 != 12:
        raise SystemExit("赛制按 10 家 AI 加 2 个陪练排；家数不同要先改赛制")

    rng = random.Random(a.seed)
    draw = list(a.players)
    rng.shuffle(draw)
    sparring_groups = sorted(rng.sample(range(3), 2))
    groups, it = {}, iter(draw)
    for gi, name in enumerate(GROUPS):
        members = [next(it) for _ in range(3 if gi in sparring_groups else 4)]
        if gi in sparring_groups:
            members.insert(rng.randrange(4), SPARRING)
        groups[name] = members
    lots = {s: rng.random() for s in a.players + [SPARRING]}
    group_seeds = [a.seed * 10 + k for k in range(4)]        # 三个小组同样的 4 张图
    final_seeds = [a.seed * 10 + 4 + k for k in range(4)]

    def run(tasks):
        with mp.Pool(min(a.workers, len(tasks))) as pool:
            recs = pool.map(play_one, tasks)
        result = []
        for rec in recs:
            export = out / "games" / f"{rec['id']}.json"
            data = package.export(rec)
            data.update(id=rec["id"], seats=rec["seats"], place=rec["place"], death=rec["death"], kills=rec["kills"])
            export.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
            (out / "games" / f"{rec['id']}.rec.json").write_text(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
            result.append((rec, summary(rec, export)))
            print(f"{rec['id']}: 座位 {rec['seats']} 名次 {rec['place']} 击杀 {rec['kills']} {rec['turns']} 回合 "
                  f"超时 {[s.get('timeouts', 0) for s in rec.get('stats', [])]}", flush=True)
        return result

    tasks = [(f"{g}{k + 1}", group_seeds[k], rotation(groups[g], k), paths) for g in GROUPS for k in range(4)]
    group_games = run(tasks)
    standings, seconds = {}, []
    for g in GROUPS:
        recs = [rec for rec, _ in group_games if rec["id"].startswith(g)]
        order = ranked(tally(recs, groups[g]), lots)
        standings[g] = order
        ais = [r for r in order if r["slug"] != SPARRING]
        seconds.append(ais[1])
    winners = [next(r for r in standings[g] if r["slug"] != SPARRING) for g in GROUPS]
    best_second = sorted(seconds, key=lambda r: (-r["points"], -r["kills"], -r["survival"], lots[r["slug"]]))[0]
    finalists = [r["slug"] for r in winners] + [best_second["slug"]]

    final_games = run([(f"F{k + 1}", final_seeds[k], rotation(finalists, k), paths) for k in range(4)])
    final = ranked(tally([rec for rec, _ in final_games], finalists), lots)
    tiebreaks = []
    top = [r["slug"] for r in final if (r["points"], r["kills"]) == (final[0]["points"], final[0]["kills"])]
    champion = top[0] if len(top) == 1 else None
    extra = 0
    while champion is None and extra < 3:
        extra += 1
        seats = rotation(finalists, extra - 1)
        (rec, info), = run([(f"T{extra}", a.seed * 10 + 7 + extra, seats, paths)])
        tiebreaks.append(info)
        best = min(rec["place"][rec["seats"].index(s)] for s in top)
        leaders = [s for s in top if rec["place"][rec["seats"].index(s)] == best]
        champion = leaders[0] if len(leaders) == 1 else None
        top = leaders
    if champion is None:
        champion = top[0]   # 三次加赛还分不出：按决赛存活回合和抽签（final 已按此排序）

    cup = {"game": GAME, "seed": a.seed, "bots_dir": str(a.bots_dir), "points": POINTS,
           "groups": groups, "group_seeds": group_seeds, "final_seeds": final_seeds,
           "games": [info for _, info in group_games + final_games] + tiebreaks,
           "standings": standings, "group_winners": [r["slug"] for r in winners],
           "best_second": best_second["slug"], "seconds": [r["slug"] for r in seconds],
           "finalists": finalists, "final": final, "tiebreaks": [t["id"] for t in tiebreaks],
           "champion": champion}
    (out / "cup.json").write_text(json.dumps(cup, ensure_ascii=False, indent=1))
    print("小组：", json.dumps(groups, ensure_ascii=False))
    for g in GROUPS:
        print(g, [(r["slug"], r["points"], r["kills"], r["places"]) for r in standings[g]])
    print("决赛：", [(r["slug"], r["points"], r["kills"], r["places"]) for r in final], "冠军", champion)


if __name__ == "__main__":
    main()
