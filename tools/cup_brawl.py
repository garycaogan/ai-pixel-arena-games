"""像素拳斗杯：10 家 AI 1 对 1，场数少到每一场都能在节目里放。

抽签分 A、B 两组各 5 家，组内单循环、每对打一场（一场三局两胜），胜 3 分、平 1 分、负 0 分；
组内排名看积分、相互胜负、赢的局数减输的局数、剩余血量比例之和、抽签。
各组前两名交叉打半决赛（A1–B2、B1–A2），输的两家打一场季军赛，赢的两家打决赛，决赛先赢两场的夺冠。
角色由各家程序在第 1 帧自己选（选错按种子抽），整届不换程序；左右座位按抽签号，小号在左。
淘汰赛打平就换种子重打，最多 3 次，还平就按剩余血量比例之和判。

    .venv/bin/python tools/brawl_cup.py --bots-dir bots/brawl --out results/brawl
"""
from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from games import load_game  # noqa: E402

GAME = "brawl"
AIS = ["opus", "astra", "gemini", "deepseek", "kimi", "doubao", "qwen", "glm", "minimax", "grok"]


def play_one(task):
    from arena.referee import BotProc, play
    gid, seed, seats, paths = task
    bots = [BotProc(paths[name]) for name in seats]
    try:
        t0 = time.monotonic()
        config = load_game(GAME).config("duel")
        rec = play(bots, seed, names=list(seats), collect_errors=True, game=GAME, config=config)
        rec["wall"] = round(time.monotonic() - t0, 3)
        rec["id"] = gid
        return rec
    finally:
        for b in bots:
            b.kill()


def hp_ratio(rec, seat):
    """这一场每局结束时剩余血量比例之和（局末事件里记的血量）。"""
    from games.brawl.engine import CHARS
    total = 0.0
    for e in rec.get("round_ends", []):
        total += e["hp"][seat] / CHARS[rec["chars"][seat]]["hp"]
    return round(total, 4)


def summary(rec, export_path):
    return {"id": rec["id"], "seed": rec["seed"], "seats": rec["seats"], "chars": rec["chars"],
            "wins": rec["wins"], "place": rec["place"], "turns": rec["turns"], "rounds": rec["rounds"],
            "reasons": [e["reason"] for e in rec["round_ends"]], "hp_ratio": [hp_ratio(rec, i) for i in (0, 1)],
            "play": rec.get("play"),
            "timeouts": [s.get("timeouts", 0) for s in rec.get("stats", [])],
            "errors": [s.get("errors", 0) for s in rec.get("stats", [])],
            "invalid": [s.get("invalid", 0) for s in rec.get("stats", [])],
            "wall": rec.get("wall"),
            "export": str(export_path.relative_to(ROOT) if export_path.is_relative_to(ROOT) else export_path)}


def tally(infos, members, lots):
    rows = {m: {"slug": m, "points": 0, "won": 0, "lost": 0, "drawn": 0, "rounds_for": 0, "rounds_against": 0,
                "hp_ratio": 0.0, "matches": [], "beat": []} for m in members}
    for info in infos:
        a, b = info["seats"]
        for i, me in enumerate((a, b)):
            row, other = rows[me], (a, b)[1 - i]
            row["rounds_for"] += info["wins"][i]
            row["rounds_against"] += info["wins"][1 - i]
            row["hp_ratio"] = round(row["hp_ratio"] + info["hp_ratio"][i], 4)
            row["matches"].append(info["id"])
            if info["place"][i] < info["place"][1 - i]:
                row["won"] += 1
                row["points"] += 3
                row["beat"].append(other)
            elif info["place"][i] == info["place"][1 - i]:
                row["drawn"] += 1
                row["points"] += 1
            else:
                row["lost"] += 1

    def key(r):
        tied = [x for x in rows.values() if x["points"] == r["points"]]
        h2h = sum(1 for x in tied if x["slug"] in r["beat"])
        return (-r["points"], -h2h, -(r["rounds_for"] - r["rounds_against"]), -r["hp_ratio"], lots[r["slug"]])
    return sorted(rows.values(), key=key)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bots-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "results/brawl")
    ap.add_argument("--seed", type=int, default=20261030, help="抽签和对局的公开种子")
    ap.add_argument("--players", nargs="+", default=AIS)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    package = load_game(GAME)
    out = a.out if a.out.is_absolute() else ROOT / a.out
    (out / "games").mkdir(parents=True, exist_ok=True)
    bots_dir = a.bots_dir if a.bots_dir.is_absolute() else ROOT / a.bots_dir
    paths = {s: str(bots_dir / f"{s}.py") for s in a.players}
    missing = [s for s, p in paths.items() if not Path(p).is_file()]
    if missing:
        raise SystemExit("缺程序：" + ", ".join(missing))
    if len(a.players) % 2 or len(a.players) < 4:
        raise SystemExit("两组人数要一样多、每组至少 2 家")

    rng = random.Random(a.seed)
    draw = list(a.players)
    rng.shuffle(draw)
    number = {s: i + 1 for i, s in enumerate(draw)}       # 抽签号：小号坐左边
    half = len(draw) // 2
    groups = {"A": sorted(draw[:half], key=number.get), "B": sorted(draw[half:], key=number.get)}
    lots = {s: rng.random() for s in a.players}
    seeds = iter(a.seed * 100 + k for k in itertools.count())

    def run(tasks):
        with mp.Pool(min(a.workers, len(tasks))) as pool:
            recs = pool.map(play_one, tasks)
        result = []
        for rec in recs:
            export = out / "games" / f"{rec['id']}.json"
            data = package.export(rec)
            rec["round_ends"] = [e for e in data["events"] if e["type"] == "round"]
            data.update(id=rec["id"], seats=rec["seats"])
            export.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
            (out / "games" / f"{rec['id']}.rec.json").write_text(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
            info = summary(rec, export)
            result.append(info)
            print(f"{rec['id']}: {rec['seats']} 角色 {rec['chars']} 局分 {rec['wins']} 名次 {rec['place']} "
                  f"{rec['turns']} 帧 超时 {info['timeouts']} 报错 {info['errors']}", flush=True)
        return result

    def seat(x, y):
        return (x, y) if number[x] < number[y] else (y, x)

    tasks = []
    for g, members in groups.items():
        for k, (x, y) in enumerate(itertools.combinations(members, 2)):
            tasks.append((f"{g}{k + 1}", next(seeds), seat(x, y), paths))
    group_games = run(tasks)
    standings = {g: tally([i for i in group_games if i["id"].startswith(g)], m, lots) for g, m in groups.items()}

    def knockout(gid, x, y):
        """淘汰赛一场；打平换种子重打，最多 3 次，还平按剩余血量比例之和。"""
        played = []
        for k in range(4):
            info, = run([(gid if not k else f"{gid}r{k}", next(seeds), seat(x, y), paths)])
            played.append(info)
            if info["place"][0] != info["place"][1]:
                return info["seats"][info["place"].index(1)], played
        last = played[-1]
        return last["seats"][0 if last["hp_ratio"][0] >= last["hp_ratio"][1] else 1], played

    A, B = standings["A"], standings["B"]
    knock = []
    s1, p1 = knockout("S1", A[0]["slug"], B[1]["slug"])
    s2, p2 = knockout("S2", B[0]["slug"], A[1]["slug"])
    knock += p1 + p2
    l1 = next(s for s in (A[0]["slug"], B[1]["slug"]) if s != s1)
    l2 = next(s for s in (B[0]["slug"], A[1]["slug"]) if s != s2)
    third, p3 = knockout("M3", l1, l2)
    knock += p3
    final_wins = {s1: 0, s2: 0}
    k = 0
    while max(final_wins.values()) < 2:
        k += 1
        w, pf = knockout(f"F{k}", s1, s2)
        knock += pf
        final_wins[w] += 1
    champion = max(final_wins, key=final_wins.get)
    runner_up = s2 if champion == s1 else s1
    fourth = l2 if third == l1 else l1

    cup = {"game": GAME, "seed": a.seed, "bots_dir": str(a.bots_dir), "points": {"win": 3, "draw": 1, "loss": 0},
           "draw_numbers": number, "groups": groups, "games": group_games + knock, "standings": standings,
           "semis": [[A[0]["slug"], B[1]["slug"], s1], [B[0]["slug"], A[1]["slug"], s2]],
           "third_place": [l1, l2, third], "final": {"players": [s1, s2], "wins": final_wins},
           "podium": [champion, runner_up, third, fourth], "champion": champion,
           "picks": {s: sorted({i["chars"][i["seats"].index(s)] for i in group_games + knock if s in i["seats"]})
                     for s in a.players}}
    (out / "cup.json").write_text(json.dumps(cup, ensure_ascii=False, indent=1))
    print("分组：", json.dumps(groups, ensure_ascii=False))
    for g in groups:
        print(g, [(r["slug"], r["points"], f"{r['won']}胜{r['drawn']}平{r['lost']}负", r["rounds_for"] - r["rounds_against"]) for r in standings[g]])
    print("半决赛：", cup["semis"], "季军赛：", cup["third_place"], "决赛：", final_wins, "冠军", champion)


if __name__ == "__main__":
    main()
