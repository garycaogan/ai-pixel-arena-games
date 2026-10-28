"""裁判：开沙箱进程跑选手程序，逐回合收方向、按规则结算、记下每一步。

时限（CPU 时间，由外壳在选手进程里量）：加载代码 1 秒，第 1 回合 1 秒，之后每回合 50 毫秒。
超时、报错、返回值不对：使用游戏包的 fallback。连续 3 次，或者进程卡死被杀，本局剩下的回合都用 fallback。
"""
from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path

from games import load_game

ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "runner.py"
PY = sys.executable
SANDBOX = """(version 1)
(allow default)
(deny network*)
(deny process-fork)
(deny file-write*)
(allow file-write* (literal "/dev/null"))
"""
LOAD_LIMIT = 1.0
FIRST_LIMIT = 1.0
TURN_LIMIT = 0.050
WALL_LIMIT = 3.0          # 墙钟兜底：一次回复超过 3 秒就杀进程
MAX_STRIKES = 3


class BotProc:
    """一个选手的常驻进程。每局开始发 load，重新执行选手代码。"""

    def __init__(self, path: str, stderr=subprocess.DEVNULL):
        self.path = str(Path(path).resolve())
        self.stderr = stderr
        self.p = None

    def start(self):
        cmd = [PY, "-I", "-B", str(RUNNER)]
        if sys.platform == "darwin" and not os.environ.get("ARENA_NO_SANDBOX"):
            cmd = ["sandbox-exec", "-p", SANDBOX] + cmd
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                                  text=True, bufsize=1)

    def alive(self):
        return self.p is not None and self.p.poll() is None

    def kill(self):
        if self.p is not None:
            try:
                self.p.kill()
                self.p.wait(timeout=2)
            except Exception:
                pass
        self.p = None

    def send(self, obj):
        self.p.stdin.write(json.dumps(obj, separators=(",", ":")) + "\n")
        self.p.stdin.flush()

    def recv(self, timeout):
        sel = selectors.DefaultSelector()
        sel.register(self.p.stdout, selectors.EVENT_READ)
        try:
            if not sel.select(timeout):
                return None
            line = self.p.stdout.readline()
            return json.loads(line) if line else None
        finally:
            sel.close()


def _gather(procs: dict[int, BotProc], timeout: float) -> dict[int, dict | None]:
    """所有选手同时算：先把输入发完，再统一收回复。"""
    out: dict[int, dict | None] = {}
    sel = selectors.DefaultSelector()
    for sid, bp in procs.items():
        sel.register(bp.p.stdout, selectors.EVENT_READ, sid)
    deadline = time.monotonic() + timeout
    while len(out) < len(procs):
        left = deadline - time.monotonic()
        if left <= 0:
            break
        for key, _ in sel.select(left):
            sid = key.data
            line = procs[sid].p.stdout.readline()
            try:
                out[sid] = json.loads(line) if line else None
            except json.JSONDecodeError:
                out[sid] = None
            sel.unregister(key.fileobj)
    sel.close()
    for sid in procs:
        out.setdefault(sid, None)
    return out


def play(bots: list[BotProc], seed: int, names: list[str] | None = None, collect_errors: bool = False,
         game: str = "snake", config: dict | None = None) -> dict:
    """打一局。bots[i] 坐 i 号位。返回这局的完整记录（含逐回合走法，可用 snake.replay 重放）。"""
    n = len(bots)
    package = load_game(game)
    engine = package.engine
    seats = names or [Path(b.path).stem for b in bots]
    cfg = dict(config or {})
    cfg.setdefault("seats", seats)
    g = engine.Game.new(n, seed, cfg)
    strikes = [0] * n
    broken = [False] * n
    stats = [{"timeouts": 0, "errors": 0, "invalid": 0, "killed": 0, "max_cpu": 0.0, "cpu": 0.0, "turns": 0} for _ in range(n)]
    errors: list[dict] = []

    def fail(i, kind, detail=None, state=None):
        stats[i][kind] += 1
        strikes[i] += 1
        if collect_errors and len(errors) < 40:
            errors.append({"seat": i, "turn": g.turn + 1, "kind": kind, "detail": detail, "state": state})
        if strikes[i] >= MAX_STRIKES:
            broken[i] = True

    # 加载
    for i, b in enumerate(bots):
        if not b.alive():
            b.start()
        try:
            b.send({"cmd": "load", "path": b.path, "seed": seed * 101 + i})
        except (BrokenPipeError, OSError):
            b.kill()
    loaded = _gather({i: b for i, b in enumerate(bots) if b.alive()}, WALL_LIMIT + LOAD_LIMIT)
    for i, b in enumerate(bots):
        r = loaded.get(i)
        if r is None:
            fail(i, "killed", "加载代码时没有回应（超时或进程退出）")
            broken[i] = True
            b.kill()
        elif not r.get("ok"):
            fail(i, "errors", r.get("tb") or r.get("err"))
            broken[i] = True
        elif r.get("cpu", 0) > LOAD_LIMIT:
            fail(i, "timeouts", f"加载代码用了 {r['cpu']*1000:.0f} 毫秒 CPU，上限 {LOAD_LIMIT*1000:.0f}")

    rows: list[str] = []
    while not g.over():
        alive = [s for s in g.alive()]
        limit = FIRST_LIMIT if g.turn == 0 else TURN_LIMIT
        asking = {}
        states = {}
        for s in alive:
            i = s.id
            if broken[i] or not bots[i].alive():
                continue
            st = g.state_for(i)
            states[i] = st
            try:
                bots[i].send({"cmd": "turn", "state": st})
                asking[i] = bots[i]
            except (BrokenPipeError, OSError):
                broken[i] = True
                bots[i].kill()
        answers = _gather(asking, WALL_LIMIT + limit)
        moves = {}
        for s in alive:
            i = s.id
            cur = g.fallback(i)
            if i not in asking:
                moves[i] = cur
                continue
            r = answers.get(i)
            stats[i]["turns"] += 1
            if r is None:
                fail(i, "killed", f"超过 {WALL_LIMIT:.0f} 秒没有回应，进程被结束", states[i] if collect_errors else None)
                broken[i] = True
                bots[i].kill()
                moves[i] = cur
                continue
            if not r.get("ok"):
                fail(i, "errors", r.get("tb") or r.get("err"), states[i] if collect_errors else None)
                moves[i] = cur
                continue
            cpu = float(r.get("cpu") or 0)
            stats[i]["cpu"] += cpu
            stats[i]["max_cpu"] = max(stats[i]["max_cpu"], cpu)
            mv = r.get("move")
            if cpu > limit:
                fail(i, "timeouts", f"这一回合用了 {cpu*1000:.1f} 毫秒 CPU，上限 {limit*1000:.0f}",
                     states[i] if collect_errors else None)
                moves[i] = cur
            elif mv not in engine.ACTIONS:
                fail(i, "invalid", f"返回值是 {mv!r}，只能是 {'/'.join(engine.ACTIONS)}", states[i] if collect_errors else None)
                moves[i] = cur
            else:
                strikes[i] = 0
                moves[i] = mv
        rows.append("".join(engine.LETTER[moves[i]] if i in moves else "." for i in range(n)))
        g.step(moves)

    rec = {
        "n": n, "seed": seed, "turns": g.turn, "seats": seats,
        **g.result(),
        "stats": [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in st.items()} for st in stats],
        "moves": rows,
    }
    if game != "snake":
        rec["game"] = game
    if config or game != "snake":
        rec["config"] = dict(getattr(g, "config", cfg))
    if collect_errors:
        rec["errors"] = errors
    return rec
