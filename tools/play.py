"""本地打一局炸弹派对：4 个程序各坐一个出生角，打完打印名次、击杀和死因。

    python3 tools/play.py opus astra kimi grok
    python3 tools/play.py my_bot.py baseline gemini deepseek --seed 7 --export game.json

程序名先找 bots/bomb_party/<名字>.py，找不到就当文件路径。每个程序在单独的子进程里跑，
每步 50 毫秒 CPU，和比赛一样；macOS 上默认再套一层 sandbox-exec，设 ARENA_NO_SANDBOX=1 可关掉。
--export 写出完整回放（每回合快照和事件），网页版和 art/bomb-party/render-bomber.js 都能读。
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

GAME = "bomb_party"
CAUSE = {"blast": "被炸", "crush": "被墙压"}


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
    ap.add_argument("bots", nargs=4, help="4 个程序：bots/bomb_party 里的名字或 .py 路径")
    ap.add_argument("--seed", type=int, default=1, help="地图种子")
    ap.add_argument("--export", type=Path, help="把回放写成 JSON")
    a = ap.parse_args(argv)
    package = load_game(GAME)
    names, paths = zip(*(resolve(b) for b in a.bots))
    procs = [BotProc(str(p)) for p in paths]
    try:
        rec = play(procs, a.seed, names=list(names), collect_errors=True, game=GAME,
                   config=package.config("melee", n=4))
    finally:
        for p in procs:
            p.kill()
    print(f"种子 {a.seed}，打了 {rec['turns']} 回合")
    for seat in sorted(range(4), key=lambda i: rec["place"][i]):
        death = rec["death"][seat]
        how = "活到最后" if not death else f"第 {death[0]} 回合{CAUSE.get(death[1], death[1])}"
        stats = rec["stats"][seat]
        slow = f"，超时 {stats['timeouts']} 次" if stats.get("timeouts") else ""
        print(f"  第 {rec['place'][seat]} 名  {names[seat]:<12} 击杀 {rec['kills'][seat]}  {how}{slow}")
    if a.export:
        a.export.write_text(json.dumps(package.export(rec), ensure_ascii=False, separators=(",", ":")))
        print(f"回放写到 {a.export}")


if __name__ == "__main__":
    main()
