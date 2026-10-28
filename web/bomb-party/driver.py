"""One simultaneous round per RPC; runs unchanged in CPython and Pyodide."""
import json
import random
import re
import sys
import time
import types
from pathlib import Path

import engine as E

HERE = Path(__file__).resolve().parent
SLOW = 2.5
MAX_STRIKES = 3
_table = None


class DecisionTimeout(BaseException):
    pass


def bounded(call):
    """Interrupt Python loops, including a bot which never returns a decision.

    Pyodide cannot preempt a single long native/C call without COOP/COEP.
    The page also has a Worker watchdog so that case cannot freeze the UI.
    """
    deadline = time.perf_counter() + SLOW
    previous = sys.gettrace()

    def trace(frame, event, arg):
        if time.perf_counter() > deadline:
            raise DecisionTimeout()
        return trace

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
    bounded(lambda: exec(compile(source, module.__file__, "exec"), module.__dict__))
    if not callable(getattr(module, "decide", None)):
        raise ValueError("missing decide(state)")
    return module


class Table:
    def __init__(self, seats, human, seed):
        if len(seats) != 4 or (human is not None and type(human) is not int):
            raise ValueError("four seats required")
        if human is not None and human not in range(4):
            raise ValueError("invalid human seat")
        self.seats, self.human, self.seed = list(seats), human, int(seed)
        self.g = E.Game.new(4, self.seed)
        self.mods, self.rng = {}, {}
        self.strikes, self.errors, self.broken = [0] * 4, [0] * 4, [False] * 4
        self.load_errors, self.rows = {}, []
        for i, slug in enumerate(seats):
            if i == human:
                continue
            try:
                self.mods[i] = load_bot(slug, self.seed * 101 + i)
                # Each seat owns its random stream, even when slugs repeat.
                self.rng[i] = random.getstate()
            except BaseException as exc:
                self.broken[i] = True
                self.load_errors[i] = type(exc).__name__

    def view(self, events=None, **extra):
        return {"frame": self.g.frame(), "over": self.g.over(),
                "place": self.g.placements() if self.g.over() else None,
                "events": events or [], "errors": list(self.errors),
                "broken": list(self.broken), **extra}

    def step(self, human_action="stay"):
        if self.g.over():
            return self.view()
        moves, timings, faults = {}, {}, {}
        for p in self.g.alive():
            i = p.id
            action = "stay"
            if i == self.human:
                action = human_action if type(human_action) is str and human_action in E.ACTIONS else "stay"
            elif not self.broken[i]:
                state, err = self.g.state_for(i), None
                random.setstate(self.rng[i])
                start = time.perf_counter()
                try:
                    choice = bounded(lambda: self.mods[i].decide(state))
                    elapsed = time.perf_counter() - start
                    if elapsed > SLOW:
                        err = "slow"
                    elif type(choice) is not str or choice not in E.ACTIONS:
                        err = "invalid"
                    else:
                        action = choice
                except DecisionTimeout:
                    err = "slow"
                except BaseException as exc:
                    err = type(exc).__name__
                elapsed = time.perf_counter() - start
                if elapsed > SLOW:
                    err, action = "slow", "stay"
                self.rng[i] = random.getstate()
                timings[i] = round(elapsed * 1000, 3)
                if err:
                    faults[i] = err
                    self.errors[i] += 1
                    self.strikes[i] += 1
                    if err == "slow" or self.strikes[i] >= MAX_STRIKES:
                        self.broken[i] = True
                else:
                    self.strikes[i] = 0
            moves[i] = action
        row = "".join(E.LETTER[moves.get(i, "stay")] for i in range(4))
        self.rows.append(row)
        events = self.g.step(moves)
        return self.view(events, moves=row, ms=timings, faults=faults)


def rpc(cmd, args_json="{}"):
    global _table
    args = json.loads(args_json)
    if cmd == "start":
        seed = args.get("seed")
        _table = Table(args["seats"], args.get("human"),
                       int(seed) if seed is not None else random.randrange(1, 2**31))
        return json.dumps(_table.view(seed=_table.seed, load_errors=_table.load_errors))
    if _table is None:
        raise ValueError("start a game first")
    if cmd == "step":
        return json.dumps(_table.step(args.get("action", "stay")))
    if cmd == "view":
        return json.dumps(_table.view())
    raise ValueError(cmd)
