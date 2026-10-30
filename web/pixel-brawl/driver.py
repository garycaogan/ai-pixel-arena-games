"""像素拳斗网页驱动：一次 RPC 推进若干帧，CPython 和 Pyodide 里跑同一份代码。

人类座位每帧送 {"h": -1/0/1, "v": -1/0/1, "press": [...]}：h、v 是按住的绝对方向，
press 是这一帧新按下的键（p h k s t z a x，或 dash+/dash-）。驱动按当前朝向换成引擎动作，
攻击键按住缓冲几帧，等角色能出招的那一帧才送进引擎；送进引擎的动作逐帧记在 rows 里，
和 engine.export() 用同一份 rows 重放能逐帧对上。
"""
import json
import random
import re
import sys
import time
import types
from pathlib import Path

import engine as E

HERE = Path(__file__).resolve().parent
SLOW = 1.0          # 单帧一次 decide 超过这么久（秒）就停用这家程序，本场后续站着不动
MAX_STRIKES = 3     # 连续出错几次停用
BUFFER = 8          # 攻击键缓冲帧数（约 0.27 秒）
MAX_BATCH = 12
BUTTONS = ("p", "h", "k", "s", "t", "z", "a", "x")
_table = None


class DecisionTimeout(BaseException):
    pass


def bounded(call, limit=None):
    """只在函数调用处看表：不追每一行，开销小。

    不调函数的死循环这里打断不了，页面主线程另有看门狗（几秒没回音就重置 Worker）。
    """
    deadline = time.perf_counter() + (SLOW if limit is None else limit)
    previous = sys.gettrace()

    def trace(frame, event, arg):
        if time.perf_counter() > deadline:
            raise DecisionTimeout()
        return None

    sys.settrace(trace)
    try:
        return call()
    finally:
        sys.settrace(previous)


def load_bot(slug, seed):
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9_-]+", slug):
        raise ValueError("invalid bot slug")
    random.seed(seed)
    module = types.ModuleType("bot_" + slug)
    module.__file__ = str(HERE / "bots" / (slug + ".py"))
    source = Path(module.__file__).read_text(encoding="utf-8")
    bounded(lambda: exec(compile(source, module.__file__, "exec"), module.__dict__), 3.0)
    if not callable(getattr(module, "decide", None)):
        raise ValueError("missing decide(state)")
    return module


def accepts(g, f, a):
    """引擎这一帧会不会接下按键 a（照 engine.Game._input 的条件）。"""
    if g.phase != "fight" or g.flash:
        return False
    if a in ("r", "e"):
        return f.st in E.GROUND_OK
    if f.st == "air":
        return f.air_mv is None and a in ("p", "h", "k")
    if f.st == "attack" and f.contact and a in ("z", "a", "x") and f.move().get("cancel"):
        m = f.move()
        return f.mf <= m["s"] + m["a"] + 4 and g._can(f, a)
    if f.st not in E.GROUND_OK:
        return False
    return g._can(f, a)


class Table:
    def __init__(self, seats, human, seed, pick=None):
        if len(seats) != 2 or (human is not None and human not in (0, 1)) or type(human) is bool:
            raise ValueError("two seats required")
        self.seats, self.human, self.seed = list(seats), human, int(seed)
        self.pick = pick if pick in E.CHARS else None
        self.g = E.Game.new(2, self.seed)
        self.mods, self.rng = {}, {}
        self.strikes, self.errors, self.broken = [0, 0], [0, 0], [False, False]
        self.load_errors, self.rows, self.ms = {}, [], [0.0, 0.0]
        self.calls, self.slowest = [0, 0], [0.0, 0.0]
        self.buffer = None  # [按键, 剩余帧]
        for i, slug in enumerate(self.seats):
            if i == human:
                continue
            try:
                self.mods[i] = load_bot(slug, self.seed * 100 + i)
                self.rng[i] = random.getstate()
            except BaseException as exc:
                self.broken[i] = True
                self.load_errors[i] = type(exc).__name__

    # ---------- 人类 ----------
    def human_action(self, inp):
        g, i = self.g, self.human
        inp = inp if isinstance(inp, dict) else {}
        h = inp.get("h") if inp.get("h") in (-1, 0, 1) else 0
        v = inp.get("v") if inp.get("v") in (-1, 0, 1) else 0
        presses = inp.get("press") if isinstance(inp.get("press"), list) else []
        if g.phase == "select":
            return self.pick or "lie"
        if g.phase != "fight":
            self.buffer = None
            return "n"
        f = g.f[i]
        face = f.face or 1
        for key in presses:
            if key in BUTTONS:
                self.buffer = [key, BUFFER]
            elif key in ("dash+", "dash-"):
                ahead = (1 if key == "dash+" else -1) * face > 0
                self.buffer = ["r" if ahead else "e", 4]
        if self.buffer and not g.flash:
            key = self.buffer[0]
            if accepts(g, f, key):
                self.buffer = None
                return key
            self.buffer[1] -= 1
            if self.buffer[1] <= 0:
                self.buffer = None
        rel = h * face
        if v > 0:
            return "j" if rel > 0 else ("y" if rel < 0 else "u")
        if v < 0:
            return "g" if rel < 0 else "d"
        return "f" if rel > 0 else ("b" if rel < 0 else "n")

    # ---------- AI ----------
    def bot_action(self, i, faults):
        if self.broken[i]:
            return "n"
        state, err, action = json.loads(json.dumps(self.g.state_for(i))), None, "n"
        random.setstate(self.rng[i])
        start = time.perf_counter()
        try:
            choice = bounded(lambda: self.mods[i].decide(state))
            if type(choice) is not str or choice not in E.ACTIONS:
                err = "invalid"
            else:
                action = choice
        except DecisionTimeout:
            err = "slow"
        except BaseException as exc:
            err = type(exc).__name__
        elapsed = time.perf_counter() - start
        if elapsed > SLOW:
            err, action = "slow", "n"
        self.rng[i] = random.getstate()
        self.ms[i] += elapsed * 1000
        self.calls[i] += 1
        self.slowest[i] = max(self.slowest[i], elapsed * 1000)
        if err:
            faults[i] = err
            self.errors[i] += 1
            self.strikes[i] += 1
            if err == "slow" or self.strikes[i] >= MAX_STRIKES:
                self.broken[i] = True
        else:
            self.strikes[i] = 0
        return action

    def step_one(self, inp, faults):
        acts = {}
        for i in (0, 1):
            acts[i] = self.human_action(inp) if i == self.human else self.bot_action(i, faults)
        self.rows.append("".join(E.LETTER[acts[i]] for i in (0, 1)))
        self.g.step(acts)
        return self.g.frame()

    def step(self, inputs):
        inputs = inputs if isinstance(inputs, list) else []
        n = max(1, min(MAX_BATCH, len(inputs) or 1))
        frames, faults = [], {}
        for k in range(n):
            if self.g.over():
                break
            frames.append(self.step_one(inputs[k] if k < len(inputs) else {}, faults))
        return self.view(frames, faults=faults)

    def view(self, frames, **extra):
        over = self.g.over()
        out = {"frames": frames, "over": over, "turn": self.g.turn, "errors": list(self.errors),
               "broken": list(self.broken), **extra}
        if over:
            out["result"] = self.g.result()
        return out

    def stats(self):
        return {"calls": list(self.calls), "mean_ms": [round(self.ms[i] / self.calls[i], 3) if self.calls[i] else 0
                                                        for i in (0, 1)],
                "max_ms": [round(x, 3) for x in self.slowest]}


def rpc(cmd, args_json="{}"):
    global _table
    args = json.loads(args_json)
    if cmd == "start":
        seed = args.get("seed")
        _table = Table(args["seats"], args.get("human"),
                       int(seed) if seed is not None else random.randrange(1, 2**31), args.get("pick"))
        return json.dumps({"seed": _table.seed, "frame": _table.g.frame(), "load_errors": _table.load_errors,
                           "broken": _table.broken, "config": _table.g.config})
    if _table is None:
        raise ValueError("start a game first")
    if cmd == "step":
        return json.dumps(_table.step(args.get("inputs")))
    if cmd == "stats":
        return json.dumps(_table.stats())
    raise ValueError(cmd)
