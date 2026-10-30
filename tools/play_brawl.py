"""本地打一场像素拳斗：两个程序 1 对 1，三局两胜，打完打印角色、局分和每局怎么结束的。

    python3 tools/play_brawl.py opus astra
    python3 tools/play_brawl.py my_bot.py baseline --seed 7 --export fight.json

程序名先找 bots/brawl/<名字>.py，找不到就当文件路径。每个程序在单独的子进程里跑，限时和比赛一样；
macOS 上默认再套一层 sandbox-exec，设 ARENA_NO_SANDBOX=1 可关掉。
--export 写出完整回放（每帧快照和事件），网页版和 games/brawl/render.js 都能读。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arena.referee import BotProc, play  # noqa: E402
from games import load_game  # noqa: E402

GAME = "brawl"
NAME = {"lie": "阿烈", "tie": "铁山", "yan": "飞燕", "rei": "雷娜"}
REASON = {"ko": "K.O.", "time": "时间到", "double_ko": "双倒"}


def resolve(name):
    path = ROOT / "bots" / GAME / f"{name}.py"
    if path.is_file():
        return name, path
    path = Path(name).expanduser().resolve()
    if path.is_file():
        return path.stem, path
    raise SystemExit(f"找不到程序：{name}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bots", nargs=2, help="2 个程序：bots/brawl 里的名字或 .py 路径（第一个坐左边）")
    ap.add_argument("--seed", type=int, default=1, help="种子（只影响选角出错时的随机抽签）")
    ap.add_argument("--export", type=Path, help="把回放写成 JSON")
    a = ap.parse_args(argv)
    package = load_game(GAME)
    names, paths = zip(*(resolve(b) for b in a.bots))
    procs = [BotProc(str(p)) for p in paths]
    try:
        rec = play(procs, a.seed, names=list(names), collect_errors=True, game=GAME, config=package.config("duel"))
    finally:
        for p in procs:
            p.kill()
    data = package.export(rec)
    print(f"{names[0]}（{NAME.get(rec['chars'][0], rec['chars'][0])}） {rec['wins'][0]} : {rec['wins'][1]} "
          f"{names[1]}（{NAME.get(rec['chars'][1], rec['chars'][1])}），{rec['turns']} 帧")
    for k, e in enumerate(e for e in data["events"] if e["type"] == "round"):
        who = "、".join(names[i] for i in e.get("win", [])) or "没人"
        print(f"  第 {k + 1} 局：{REASON.get(e['reason'], e['reason'])}，{who} 赢")
    for i, s in enumerate(rec.get("stats", [])):
        if s.get("timeouts") or s.get("errors"):
            print(f"  {names[i]}：超时 {s.get('timeouts', 0)} 次，报错 {s.get('errors', 0)} 次")
    if a.export:
        a.export.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        print(f"回放写到 {a.export}")


if __name__ == "__main__":
    main()
