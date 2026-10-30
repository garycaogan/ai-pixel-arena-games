"""选手程序的外壳：在沙箱里的独立进程中运行，一行 JSON 进、一行 JSON 出。

协议：
  {"cmd": "load", "path": ..., "seed": ...}   每局开始时发一次，重新加载选手代码（全局变量清零）
  {"cmd": "turn", "state": {...}}             每回合一次
回复：{"ok": true, "move": ..., "cpu": 秒} 或 {"ok": false, "err": ...}
选手代码 print 的东西会被转到标准错误，不会弄乱协议。
"""
import json
import os
import random
import sys
import time
import traceback
import types

proto = os.fdopen(os.dup(1), "w", buffering=1)
sys.stdout = sys.stderr
mod = None


def reply(obj):
    proto.write(json.dumps(obj) + "\n")
    proto.flush()


class _SeededRandom(random.Random):
    """程序自己 new 的 random.Random() 不带种子时，也从这一局的种子派生，同一种子能原样复现（像素拳斗 Grok 10/30）。"""
    _base = 0
    _count = 0

    def __init__(self, x=None):
        if x is None:
            _SeededRandom._count += 1
            x = (_SeededRandom._base, _SeededRandom._count)
            x = hash(x) & 0xFFFFFFFF
        super().__init__(x)


def load(path, seed):
    global mod
    random.seed(seed)
    _SeededRandom._base, _SeededRandom._count = seed, 0
    random.Random = _SeededRandom
    src = open(path, encoding="utf-8").read()
    m = types.ModuleType("bot")
    m.__file__ = path
    t0 = time.process_time()
    exec(compile(src, "bot.py", "exec"), m.__dict__)
    if not callable(m.__dict__.get("decide")):
        raise RuntimeError("bot.py 里没有找到 decide(state) 函数")
    mod = m
    return time.process_time() - t0


for line in sys.stdin:
    msg = json.loads(line)
    try:
        if msg["cmd"] == "load":
            mod = None
            cpu = load(msg["path"], msg["seed"])
            reply({"ok": True, "cpu": cpu})
        else:
            t0 = time.process_time()
            mv = mod.decide(msg["state"])
            reply({"ok": True, "move": mv if isinstance(mv, str) else repr(mv)[:40], "cpu": time.process_time() - t0})
    except BaseException as e:  # noqa: BLE001 选手代码的任何异常都要报回去
        tb = traceback.format_exc(limit=8)
        reply({"ok": False, "err": f"{type(e).__name__}: {e}"[:300], "tb": tb[-2500:]})
