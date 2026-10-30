"""像素拳斗（Pixel Brawl）：两人同时出招的确定性 2D 格斗引擎。

一帧就是一回合，30 帧/秒。两名选手每帧同时交一个动作；对手的信息晚 DELAY 帧送达
（约 0.2 秒），模拟反应时间。第 1 帧是选角：返回四个角色代号之一，非法就按种子抽一个。
三局两胜，每局 45 秒；同样的种子和动作序列必得同样结果，不用墙钟、不用全局随机数。
"""
from __future__ import annotations

import copy
import random

FPS = 30
STAGE_W = 384
STAGE_H = 216
WALL = 26
DELAY = 6
PUSH_W = 22
GRAV = 0.9
INTRO = 36
OUTRO = 80
METER_MAX = 300
GUARD_MAX = 100
START_X = (128, 256)

FIGHT = ("n", "f", "b", "d", "g", "u", "j", "y", "r", "e", "p", "h", "k", "s", "t", "z", "a", "x")
CHAR_KEYS = ("lie", "tie", "yan", "rei")
ACTIONS = FIGHT + CHAR_KEYS
LETTER = {**{a: a for a in FIGHT}, "lie": "L", "tie": "T", "yan": "Y", "rei": "R"}
FROM_LETTER = {v: k for k, v in LETTER.items()}
NAMES = {
    "n": "站立", "f": "前走", "b": "后走/站防", "d": "蹲", "g": "蹲防", "u": "原地跳", "j": "前跳", "y": "后跳",
    "r": "前冲", "e": "后撤步", "p": "轻拳", "h": "重拳", "k": "脚", "s": "扫腿", "t": "投", "z": "必杀技",
    "a": "对空技", "x": "超必杀",
}
DEFAULTS = {"round_seconds": 45, "rounds_to_win": 2, "max_rounds": 5, "chars": None}

# 招式表。s/a/r：起手、判定、收招帧数；reach：从身体中心朝前的横向判定范围；hy：相对脚底的判定高度。
# kind：mid 站防蹲防都能挡，low 只能蹲防，high 只能站防（跳攻）。kd：击倒。inv：无敌帧（含两端，按招式帧计）。
# armor：起手这几帧挨一下不硬直（照样掉血）。throw：抓取距离；cmd：指令投（必杀/超必杀）。
# vx/vy：判定帧里每帧的位移。proj：飞行道具。hits：多段判定所在的判定帧序号。cost：耗气。
# throw_arc：(最高点, 落点相对投者的横向距离，负数是扔到身后)。
_LIE = {
    "p": dict(s=3, a=2, r=6, dmg=30, hs=7, bs=8, reach=(8, 40), hy=(40, 62), kind="mid", push=8, cancel=True),
    "h": dict(s=7, a=3, r=14, dmg=80, hs=18, bs=10, reach=(10, 54), hy=(46, 68), kind="mid", push=9, cancel=True),
    "k": dict(s=6, a=3, r=14, dmg=60, hs=15, bs=9, reach=(12, 62), hy=(18, 40), kind="mid", push=9),
    "s": dict(s=7, a=3, r=18, dmg=55, hs=0, bs=12, reach=(10, 60), hy=(0, 12), kind="low", kd=True, push=7, crouch=True),
    "air": dict(s=4, a=10, r=0, dmg=65, hs=16, bs=12, reach=(0, 40), hy=(-14, 26), kind="high", push=6),
    "t": dict(s=2, a=1, r=20, dmg=120, throw=38, throw_arc=(26, 46)),
    "z": dict(s=12, a=1, r=24, proj=dict(v=5.0, dmg=58, hs=18, bs=14, chip=8, hy=(38, 56), w=12, push=8, look="fire")),
    "a": dict(s=4, a=8, r=26, dmg=110, hs=0, bs=16, reach=(2, 34), hy=(28, 112), kind="mid", kd=True, inv=(1, 6),
              vy=7.0, vx=1.2, push=6),
    "x": dict(s=6, a=15, r=30, dmg=62, hs=10, bs=8, reach=(4, 50), hy=(10, 80), kind="mid", inv=(1, 9), vx=6.0, chip=6,
              hits=(1, 4, 7, 10, 13), kd_last=True, push=3, cost=100),
}
_TIE = {
    "p": dict(s=4, a=2, r=7, dmg=35, hs=7, bs=9, reach=(8, 42), hy=(40, 64), kind="mid", push=8, cancel=True),
    "h": dict(s=9, a=4, r=17, dmg=105, hs=19, bs=14, reach=(10, 58), hy=(46, 70), kind="mid", push=11, cancel=True,
              armor=(1, 8)),
    "k": dict(s=7, a=3, r=14, dmg=70, hs=15, bs=10, reach=(12, 64), hy=(16, 40), kind="mid", push=9),
    "s": dict(s=8, a=3, r=20, dmg=60, hs=0, bs=12, reach=(10, 60), hy=(0, 12), kind="low", kd=True, push=7, crouch=True),
    "air": dict(s=5, a=9, r=0, dmg=80, hs=17, bs=12, reach=(0, 40), hy=(-14, 26), kind="high", push=6),
    "t": dict(s=2, a=1, r=20, dmg=130, throw=40, throw_arc=(30, -44)),
    "z": dict(s=5, a=2, r=30, dmg=215, throw=62, cmd=True, throw_arc=(64, -40)),
    "a": dict(s=5, a=6, r=34, dmg=105, hs=0, bs=16, reach=(2, 32), hy=(40, 116), kind="mid", kd=True, inv=(1, 5),
              vy=3.0, push=6),
    "x": dict(s=3, a=3, r=48, dmg=320, throw=74, cmd=True, inv=(1, 4), cost=100, throw_arc=(90, 20)),
}
_YAN = {
    "p": dict(s=3, a=2, r=5, dmg=26, hs=7, bs=7, reach=(8, 38), hy=(40, 60), kind="mid", push=8, cancel=True),
    "h": dict(s=6, a=3, r=13, dmg=62, hs=16, bs=9, reach=(10, 48), hy=(42, 64), kind="mid", push=8, cancel=True),
    "k": dict(s=5, a=3, r=14, dmg=58, hs=15, bs=10, reach=(12, 64), hy=(30, 62), kind="mid", push=9),
    "s": dict(s=6, a=3, r=15, dmg=50, hs=0, bs=12, reach=(10, 62), hy=(0, 12), kind="low", kd=True, push=7, crouch=True),
    "air": dict(s=3, a=10, r=0, dmg=58, hs=16, bs=12, reach=(0, 42), hy=(-14, 26), kind="high", push=6),
    "t": dict(s=2, a=1, r=20, dmg=110, throw=36, throw_arc=(24, 50)),
    "z": dict(s=6, a=9, r=18, dmg=85, hs=0, bs=12, reach=(4, 44), hy=(30, 70), kind="mid", kd=True, vx=5.5, push=7),
    "a": dict(s=3, a=7, r=24, dmg=95, hs=0, bs=16, reach=(0, 32), hy=(30, 110), kind="mid", kd=True, inv=(1, 5),
              vy=6.0, vx=-0.6, push=6),
    "x": dict(s=5, a=18, r=28, dmg=52, hs=10, bs=8, reach=(4, 48), hy=(20, 72), kind="mid", inv=(1, 8), vx=7.0, chip=6,
              hits=(1, 4, 7, 10, 13, 16), kd_last=True, push=3, cost=100),
}
_REI = {
    "p": dict(s=3, a=2, r=7, dmg=30, hs=7, bs=9, reach=(8, 46), hy=(42, 66), kind="mid", push=8, cancel=True),
    "h": dict(s=9, a=3, r=16, dmg=80, hs=18, bs=12, reach=(10, 72), hy=(46, 70), kind="mid", push=10, cancel=True),
    "k": dict(s=7, a=3, r=15, dmg=62, hs=15, bs=11, reach=(12, 80), hy=(22, 46), kind="mid", push=10),
    "s": dict(s=8, a=3, r=19, dmg=50, hs=0, bs=12, reach=(10, 70), hy=(0, 12), kind="low", kd=True, push=7, crouch=True),
    "air": dict(s=5, a=8, r=0, dmg=60, hs=16, bs=12, reach=(0, 44), hy=(-14, 26), kind="high", push=6),
    "t": dict(s=2, a=1, r=20, dmg=115, throw=38, throw_arc=(26, 46)),
    "z": dict(s=14, a=1, r=22, proj=dict(v=3.6, dmg=64, hs=20, bs=15, chip=10, hy=(36, 58), w=16, push=9, look="bolt")),
    "a": dict(s=6, a=8, r=24, dmg=100, hs=0, bs=16, reach=(16, 52), hy=(40, 130), kind="mid", kd=True, inv=(1, 4),
              push=6),
    "x": dict(s=10, a=1, r=34, cost=100, proj=dict(v=8.0, dmg=230, hs=0, bs=20, chip=40, hy=(10, 80), w=26, push=12,
                                                    kd=True, look="beam")),
}
CHARS = {
    "lie": dict(name="阿烈", style="均衡", hp=980, walk=2.2, back=1.7, dash=(9, 5.0), backdash=(12, 4.0, 5),
                jump_v=11.0, jump_x=3.2, height=72, crouch=46, moves=_LIE),
    "tie": dict(name="铁山", style="投技", hp=1250, walk=1.9, back=1.4, dash=(8, 4.6), backdash=(11, 3.4, 4),
                jump_v=10.2, jump_x=2.6, height=78, crouch=50, moves=_TIE),
    "yan": dict(name="飞燕", style="速度", hp=890, walk=2.7, back=2.1, dash=(8, 6.2), backdash=(11, 4.6, 6),
                jump_v=11.6, jump_x=3.8, height=68, crouch=42, moves=_YAN),
    "rei": dict(name="雷娜", style="远程", hp=990, walk=1.9, back=1.7, dash=(9, 4.4), backdash=(12, 4.2, 5),
                jump_v=10.6, jump_x=3.0, height=74, crouch=46, moves=_REI),
}

DAMAGE_SCALE = 2.0  # 整体伤害倍率：一局 15–20 秒打完，比赛三局两胜 30–60 秒
METER_GAIN = 0.6     # 攒气倍率


def _scale(moves):
    for m in moves.values():
        for box in (m, m.get("proj") or {}):
            for k in ("dmg", "chip"):
                if k in box:
                    box[k] = int(round(box[k] * DAMAGE_SCALE))


for _c in CHARS.values():
    _scale(_c["moves"])

GROUND_OK = ("stand", "walk", "crouch")
NOT_THROWABLE = ("hitstun", "blockstun", "knock", "wake", "thrown", "throw", "ko", "air", "prejump")


def configuration(config=None):
    out = dict(DEFAULTS)
    out.update(config or {})
    for key in ("round_seconds", "rounds_to_win", "max_rounds"):
        if type(out[key]) is not int or out[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if out["chars"] is not None:
        if len(out["chars"]) != 2 or any(c not in CHARS for c in out["chars"]):
            raise ValueError("chars must be two of " + "/".join(CHAR_KEYS))
        out["chars"] = list(out["chars"])
    return out


class Fighter:
    def __init__(self, i, char):
        self.id, self.char, self.c = i, char, CHARS[char]
        self.wins, self.meter = 0, 0.0
        self.stats = dict(dmg=0, hits=0, blocked=0, throws=0, supers=0, specials=0, crushes=0, counters=0, max_combo=0,
                          proj=0, techs=0)
        self.reset(START_X[i])

    def reset(self, x):
        self.x, self.y, self.vx, self.vy = float(x), 0.0, 0.0, 0.0
        self.face = 1 if x < STAGE_W / 2 else -1
        self.st, self.mv, self.mf, self.stun = "stand", None, 0, 0
        self.hp, self.guard, self.combo = self.c["hp"], float(GUARD_MAX), 0
        self.gmode, self.gmode_last, self.jdir, self.air_mv, self.air_mf = None, None, 0, None, 0
        self.contact, self.hitn, self.pushv, self.inv, self.armored = False, 0, 0.0, 0, False
        self.arc = None  # 被投时的轨迹 (起点 x, 落点 x, 最高点)

    def move(self, key=None):
        return self.c["moves"][key or self.mv]

    def snap(self):
        mv = self.mv if self.st in ("attack", "throw") else (self.air_mv if self.st == "air" else None)
        mf = self.mf if self.st != "air" else self.air_mf
        phase = None
        if mv:
            m = self.move(mv)
            phase = "startup" if mf <= m["s"] else ("active" if mf <= m["s"] + m["a"] else "recovery")
        return dict(x=round(self.x, 2), y=round(self.y, 2), vx=round(self.vx, 2), face=self.face, st=self.st, mv=mv,
                    mf=mf, phase=phase, stun=self.stun, hp=self.hp, max_hp=self.c["hp"], meter=int(self.meter),
                    guard=int(self.guard), combo=self.combo, inv=self.inv > 0, char=self.char, gmode=self.gmode,
                    contact=self.contact if self.st == "attack" else False)


class Game:
    def __init__(self, seed=0, config=None):
        self.config = configuration(config)
        self.n, self.seed, self.turn = 2, seed, 0
        self.width, self.height = STAGE_W, STAGE_H
        self.round_frames = self.config["round_seconds"] * FPS
        self.f = None
        self.proj, self.events = [], []
        self.round, self.phase, self.pt, self.timer = 1, "select", 0, self.round_frames
        self.flash = 0
        self.hist, self.phist = [], []
        self.end_reason = None
        if self.config["chars"]:
            self._begin(self.config["chars"], [])

    @classmethod
    def new(cls, n, seed, config=None):
        if n != 2:
            raise ValueError("像素拳斗只有 1 对 1")
        return cls(seed, config)

    # ---------- 选手接口 ----------
    def alive(self):
        return [] if self.over() else [type("Seat", (), {"id": i})() for i in (0, 1)]

    def fallback(self, i):
        return "n"

    def over(self):
        return self.phase == "over"

    def state_for(self, i):
        if self.phase == "select":
            return dict(turn=self.turn + 1, phase="select", you=i, chars=list(CHAR_KEYS), stage_w=STAGE_W, wall=WALL,
                        delay=DELAY, fps=FPS, round_seconds=self.config["round_seconds"],
                        rounds_to_win=self.config["rounds_to_win"])
        me = self.f[i]
        old = self.hist[max(0, len(self.hist) - 1 - DELAY)]
        projs = [self._pub_proj(p, True) for p in self.proj if p["o"] == i]
        oldp = self.phist[max(0, len(self.phist) - 1 - DELAY)]
        projs += [self._pub_proj(p, False) for p in oldp if p["o"] != i]
        return dict(turn=self.turn + 1, phase=self.phase, you=i, round=self.round, timer=-(-self.timer // FPS),
                    timer_frames=self.timer, score=[me.wins, self.f[1 - i].wins], me=me.snap(), opp=old[1 - i],
                    projectiles=projs, stage_w=STAGE_W, wall=WALL, delay=DELAY, fps=FPS,
                    round_seconds=self.config["round_seconds"], rounds_to_win=self.config["rounds_to_win"],
                    freeze=self.flash)

    @staticmethod
    def _pub_proj(p, mine):
        return dict(mine=mine, x=round(p["x"], 1), y=p["y"], vx=p["vx"], w=p["w"], look=p["look"])

    # ---------- 推进一帧 ----------
    def step(self, actions):
        self.turn += 1
        ev = []
        if self.phase == "select":
            picks = []
            rng = random.Random(self.seed * 7 + 3)
            for i in (0, 1):
                a = actions.get(i)
                picks.append(a if a in CHARS else rng.choice(CHAR_KEYS))
            for i in (0, 1):
                ev.append(dict(type="pick", id=i, char=picks[i], drawn=actions.get(i) not in CHARS))
            self._begin(picks, ev)
        elif self.flash:
            self.flash -= 1  # 超必杀定格：画面停，双方都不动
        elif self.phase == "intro":
            self.pt -= 1
            if self.pt <= 0:
                self.phase = "fight"
                ev.append(dict(type="fight", round=self.round))
        elif self.phase == "fight":
            self._fight({i: actions.get(i, "n") if actions.get(i, "n") in FIGHT else "n" for i in (0, 1)}, ev)
        elif self.phase == "end":
            for f in self.f:
                self._advance(f)
            self.pt -= 1
            if self.pt <= 0:
                self._next_round(ev)
        for e in ev:
            e["t"] = self.turn
        self.events += ev
        self._remember()
        return ev

    def _begin(self, chars, ev):
        self.f = [Fighter(0, chars[0]), Fighter(1, chars[1])]  # config["chars"] 只记事先指定的，选角结果看 result()
        self.phase, self.pt = "intro", INTRO
        self.hist, self.phist = [], []
        self._remember()

    def _remember(self):
        if self.f is None:
            return
        self.hist.append([f.snap() for f in self.f])
        self.phist.append([dict(o=p["o"], x=round(p["x"], 1), y=p["y"], vx=p["vx"], w=p["w"], look=p["look"])
                           for p in self.proj])
        if len(self.hist) > DELAY + 2:
            del self.hist[0], self.phist[0]

    def _fight(self, acts, ev):
        A, B = self.f
        for f, o in ((A, B), (B, A)):
            if f.st in GROUND_OK and f.y == 0 and o.st != "thrown":
                f.face = 1 if o.x > f.x else (-1 if o.x < f.x else f.face)
        for f, o in ((A, B), (B, A)):
            self._input(f, o, acts[f.id], ev)
        if self.flash:
            return
        for f in self.f:
            self._advance(f)
        self._push()
        self._projectiles(ev)
        self._collide(ev)
        for f in self.f:
            if f.gmode is None and f.st != "blockstun":
                f.guard = min(GUARD_MAX, f.guard + 0.25)
        self.timer -= 1
        ko = [f for f in self.f if f.hp <= 0]
        if ko or self.timer <= 0:
            self._round_over(ko, ev)

    def _input(self, f, o, a, ev):
        f.gmode = None
        if f.st == "blockstun":
            f.gmode = "low" if a == "g" else ("high" if a == "b" else f.gmode_last)
            return
        if f.st == "air":
            if f.air_mv is None and a in ("p", "h", "k"):
                f.air_mv, f.air_mf = "air", 0
            return
        if f.st == "attack" and f.contact and a in ("z", "a", "x") and f.move().get("cancel"):
            m = f.move()
            if f.mf <= m["s"] + m["a"] + 4 and self._can(f, a):
                self._start(f, a, ev)
            return
        if f.st not in GROUND_OK:
            return
        if a in ("n", "f", "b"):
            f.st = "walk" if a != "n" else "stand"
            f.vx = f.c["walk"] * f.face if a == "f" else (-f.c["back"] * f.face if a == "b" else 0.0)
            if a == "b":
                f.gmode = "high"
        elif a in ("d", "g"):
            f.st, f.vx = "crouch", 0.0
            if a == "g":
                f.gmode = "low"
        elif a in ("u", "j", "y"):
            f.st, f.mf, f.vx = "prejump", 0, 0.0
            f.jdir = {"u": 0, "j": 1, "y": -1}[a]
        elif a == "r":
            f.st, f.mf = "dash", 0
        elif a == "e":
            f.st, f.mf = "backdash", 0
        elif a in ("p", "h", "k", "s", "t", "z", "a", "x"):
            if self._can(f, a):
                self._start(f, a, ev)
            else:
                f.st, f.vx = "stand", 0.0
        f.gmode_last = f.gmode

    def _can(self, f, a):
        m = f.move(a)
        if m.get("cost", 0) > f.meter:
            return False
        if "proj" in m and any(p["o"] == f.id for p in self.proj):
            return False
        return True

    def _start(self, f, a, ev):
        m = f.move(a)
        f.st, f.mv, f.mf, f.vx = "attack", a, 0, 0.0
        f.contact, f.hitn, f.armored = False, 0, False
        if m.get("cost"):
            f.meter -= m["cost"]
            self.flash = 18
            f.stats["supers"] += 1
            ev.append(dict(type="super", id=f.id))
        if a in ("z", "a"):
            f.stats["specials"] += 1
            ev.append(dict(type="special", id=f.id, mv=a))

    def _advance(self, f):
        f.inv = max(0, f.inv - 1)
        if f.st in ("stand", "crouch", "win"):
            f.vx = 0.0
        elif f.st == "walk":
            f.x += f.vx
        elif f.st == "prejump":
            f.mf += 1
            if f.mf >= 3:
                f.st, f.vy, f.vx = "air", f.c["jump_v"], f.jdir * f.c["jump_x"] * f.face
                f.air_mv, f.air_mf = None, 0
        elif f.st == "air":
            f.x += f.vx
            f.y += f.vy
            f.vy -= GRAV
            if f.air_mv:
                f.air_mf += 1
            if f.y <= 0 and f.vy < 0:
                f.y, f.vy, f.st, f.mf, f.air_mv = 0.0, 0.0, "land", 0, None
        elif f.st == "land":
            f.mf += 1
            if f.mf >= 3:
                f.st = "stand"
        elif f.st == "dash":
            n, v = f.c["dash"]
            f.mf += 1
            f.x += v * f.face
            if f.mf >= n:
                f.st = "stand"
        elif f.st == "backdash":
            n, v, inv = f.c["backdash"]
            f.mf += 1
            f.x -= v * f.face
            if f.mf <= inv:
                f.inv = 1
            if f.mf >= n:
                f.st = "stand"
        elif f.st == "attack":
            m = f.move()
            f.mf += 1
            lo, hi = m.get("inv", (0, -1))
            if lo <= f.mf <= hi:
                f.inv = 1
            act = m["s"] < f.mf <= m["s"] + m["a"]
            if act and m.get("vx") and not (f.contact and m.get("stop_on_hit", True) and not m.get("hits")):
                f.x += m["vx"] * f.face
            if m.get("vy"):
                if act:
                    f.y += m["vy"]
                elif f.mf > m["s"] + m["a"]:
                    f.y = max(0.0, f.y - m["vy"] * 1.4)
            if f.mf > m["s"] + m["a"] + m["r"] and f.y == 0:
                f.st, f.mv = ("crouch" if m.get("crouch") else "stand"), None
        elif f.st in ("hitstun", "blockstun"):
            f.stun -= 1
            f.x += f.pushv
            f.pushv *= 0.8
            if f.stun <= 0:
                f.st, f.combo = "stand", 0
        elif f.st == "knock":
            f.inv = 1
            if f.y > 0 or f.vy > 0:
                f.x += f.vx
                f.y += f.vy
                f.vy -= GRAV
                if f.y <= 0:
                    f.y, f.vy, f.vx = 0.0, 0.0, 0.0
            else:
                f.stun -= 1
                if f.stun <= 0:
                    f.st, f.mf, f.combo = ("wake", 0, 0) if f.hp > 0 else ("ko", 0, f.combo)
        elif f.st == "wake":
            f.inv = 1
            f.mf += 1
            if f.mf >= 10:
                f.st = "stand"
        elif f.st == "throw":
            f.mf += 1
            if f.mf >= 22:
                f.st, f.mv = "stand", None
        elif f.st == "thrown":
            f.inv = 1
            f.mf += 1
            x0, x1, top = f.arc
            k = min(1.0, f.mf / 20)
            f.x = x0 + (x1 - x0) * k
            f.y = top * 4 * k * (1 - k)
            if f.mf >= 20:
                f.st, f.stun, f.vx, f.y = "knock", 30, 0.0, 0.0
        f.x = max(WALL, min(STAGE_W - WALL, f.x))

    def _push(self):
        A, B = self.f
        if A.y > 30 or B.y > 30 or "thrown" in (A.st, B.st):
            return
        d = B.x - A.x
        if abs(d) < PUSH_W:
            sgn = 1 if (d > 0 or (d == 0 and A.face == 1)) else -1
            over = (PUSH_W - abs(d)) / 2
            A.x -= sgn * over
            B.x += sgn * over
            for f in (A, B):
                f.x = max(WALL, min(STAGE_W - WALL, f.x))
            if abs(B.x - A.x) < PUSH_W:  # 墙角：把不靠墙的一方推开
                if A.x <= WALL + 0.01 or A.x >= STAGE_W - WALL - 0.01:
                    B.x = A.x + sgn * PUSH_W
                else:
                    A.x = B.x - sgn * PUSH_W

    def _projectiles(self, ev):
        for p in self.proj:
            p["x"] += p["vx"]
        a = [p for p in self.proj if p["o"] == 0]
        b = [p for p in self.proj if p["o"] == 1]
        for p in a:
            for q in b:
                if abs(p["x"] - q["x"]) < (p["w"] + q["w"]) / 2:
                    # 大招光束吃掉普通飞行道具继续走
                    if p["look"] == "beam" and q["look"] != "beam":
                        q["dead"] = True
                    elif q["look"] == "beam" and p["look"] != "beam":
                        p["dead"] = True
                    else:
                        p["dead"] = q["dead"] = True
                    ev.append(dict(type="clash", x=round((p["x"] + q["x"]) / 2, 1)))
        self.proj = [p for p in self.proj if not p.get("dead") and WALL - 20 < p["x"] < STAGE_W - WALL + 20]

    def _hurt(self, f):
        crouching = f.st == "crouch" or (f.st == "attack" and f.move().get("crouch"))
        h = f.c["crouch"] if crouching else f.c["height"]
        if f.st == "air":
            h = 56
        return f.x - 11, f.x + 11, f.y, f.y + h

    def _collide(self, ev):
        hits, throws = [], []
        for f, o in ((self.f[0], self.f[1]), (self.f[1], self.f[0])):
            if f.st == "attack" and "throw" in f.move():
                m = f.move()
                if m["s"] < f.mf <= m["s"] + m["a"] and not f.contact:
                    if abs(f.x - o.x) <= m["throw"] and o.y == 0 and o.st not in NOT_THROWABLE and o.inv == 0:
                        throws.append((f, o, m))
                continue
            m = None
            if f.st == "attack" and "dmg" in f.move():
                m, mf = f.move(), f.mf
            elif f.st == "air" and f.air_mv:
                m, mf = f.move("air"), f.air_mf
            if m and m["s"] < mf <= m["s"] + m["a"]:
                hits_at = m.get("hits")
                k = mf - m["s"]
                ok = (k in hits_at and f.hitn < len(hits_at)) if hits_at else f.hitn == 0
                if ok:
                    x0, x1 = sorted((f.x + f.face * m["reach"][0], f.x + f.face * m["reach"][1]))
                    y0, y1 = f.y + m["hy"][0], f.y + m["hy"][1]
                    hx0, hx1, hy0, hy1 = self._hurt(o)
                    if x0 <= hx1 and hx0 <= x1 and y0 <= hy1 and hy0 <= y1 and o.inv == 0:
                        last = hits_at and f.hitn == len(hits_at) - 1
                        hits.append((f, o, dict(m, kd=m.get("kd") or (m.get("kd_last") and last),
                                                key=f.mv if f.st == "attack" else "air"), "strike"))
                    elif hits_at:
                        f.hitn += 1 if k in hits_at else 0
        for p in self.proj:
            o = self.f[1 - p["o"]]
            hx0, hx1, hy0, hy1 = self._hurt(o)
            py0, py1 = p["hy"]
            if p["x"] - p["w"] / 2 <= hx1 and hx0 <= p["x"] + p["w"] / 2 and py0 <= hy1 and hy0 <= py1 and o.inv == 0:
                p["dead"] = True
                hits.append((self.f[p["o"]], o, dict(p, kind="mid", key="x" if p["look"] == "beam" else "z"), "proj"))
        self.proj = [p for p in self.proj if not p.get("dead")]
        for f in self.f:
            if f.st == "attack" and "proj" in f.move() and f.mf == f.move()["s"] + 1:
                q = f.move()["proj"]
                f.stats["proj"] += 1
                self.proj.append(dict(o=f.id, x=f.x + f.face * 22, y=47, vx=q["v"] * f.face,
                                      **{k: v for k, v in q.items() if k != "v"}))
        struck = set()
        pre = {f.id: (f.st, f.mv, f.mf, f.gmode, f.y) for f in self.f}
        for a, d, m, src in hits:
            self._apply(a, d, m, pre[d.id], ev, src)
            struck.add(d.id)
        if len(throws) == 2:
            for f in self.f:
                f.st, f.mv, f.stun, f.pushv = "blockstun", None, 10, -3.0 * f.face
                f.gmode_last = "high"
                f.stats["techs"] += 1
            ev.append(dict(type="tech"))
        elif throws:
            f, o, m = throws[0]
            if f.id not in struck:
                self._throw(f, o, m, ev)

    def _apply(self, a, d, m, pre, ev, src):
        st, mv, mf, gmode, y = pre
        a.contact = True
        if src == "strike":
            a.hitn += 1
        can_block = y == 0 and st in GROUND_OK + ("blockstun",) and gmode is not None
        ok_height = (m["kind"] == "mid") or (m["kind"] == "low" and gmode == "low") or (m["kind"] == "high" and gmode == "high")
        dmg = m["dmg"]
        hx, hy = round(d.x - a.face * 6, 1), round(d.y + ((m["hy"][0] + m["hy"][1]) / 2 if "hy" in m else 47), 1)
        if can_block and ok_height:
            chip = m.get("chip", 0)
            if chip:
                d.hp = max(1, d.hp - chip)  # 削血不致死
            d.st, d.stun, d.mv = "blockstun", m["bs"], None
            d.gmode_last = gmode
            d.guard -= dmg * 0.45
            self._pushback(a, d, m.get("push", 6) / 4.0, src)
            a.meter = min(METER_MAX, a.meter + METER_GAIN * dmg / 14)
            d.meter = min(METER_MAX, d.meter + METER_GAIN * dmg / 16)
            d.stats["blocked"] += 1
            ev.append(dict(type="block", id=d.id, by=a.id, x=hx, y=hy, mv=m["key"]))
            if d.guard <= 0:
                d.st, d.stun, d.guard = "hitstun", 42, float(GUARD_MAX)
                a.stats["crushes"] += 1
                ev.append(dict(type="crush", id=d.id, by=a.id))
            return
        counter = st == "attack" and mv and mf <= d.move(mv)["s"]
        scale = max(0.7 if m.get("cost") else 0.4, 1 - 0.15 * d.combo)
        dealt = int(round(dmg * scale * (1.25 if counter else 1.0)))
        armor = st == "attack" and mv and "armor" in d.move(mv) and not d.armored \
            and d.move(mv)["armor"][0] <= mf <= d.move(mv)["armor"][1] and not m.get("cost")
        d.hp = max(0, d.hp - dealt)
        a.stats["dmg"] += dealt
        a.stats["hits"] += 1
        a.stats["counters"] += bool(counter)
        a.meter = min(METER_MAX, a.meter + METER_GAIN * dealt / 8)
        d.meter = min(METER_MAX, d.meter + METER_GAIN * dealt / 10)
        if armor and d.hp > 0:
            d.armored = True
            ev.append(dict(type="armor", id=d.id, by=a.id, dmg=dealt, x=hx, y=hy, mv=m["key"]))
            return
        d.combo += 1
        a.stats["max_combo"] = max(a.stats["max_combo"], d.combo)
        d.mv, d.air_mv, d.gmode = None, None, None
        if m.get("kd") or y > 0:
            d.st, d.stun = "knock", 34
            d.vy, d.vx = (6.0 if y == 0 else 2.0), a.face * 2.2
        else:
            d.st, d.stun = "hitstun", max(6, m["hs"] - 2 * (d.combo - 1)) + (4 if counter and m["key"] != "p" else 0)
            self._pushback(a, d, m.get("push", 6) / 4.0, src)
        ev.append(dict(type="hit", id=d.id, by=a.id, dmg=dealt, combo=d.combo, counter=bool(counter), src=src,
                       mv=m["key"], big=dealt >= 80 or bool(m.get("kd")), x=hx, y=hy))
        if d.hp <= 0:
            d.st, d.stun = "knock", 34
            d.vy, d.vx = 6.0, a.face * 2.6

    @staticmethod
    def _pushback(a, d, v, src):
        d.pushv = a.face * v
        # 对方贴墙时把攻方往回推，墙角不能无限压
        if src == "strike" and (d.x <= WALL + 2 or d.x >= STAGE_W - WALL - 2):
            a.x = max(WALL, min(STAGE_W - WALL, a.x - a.face * v * 2.5))

    def _throw(self, f, o, m, ev):
        f.contact = True
        dealt = m["dmg"]
        o.hp = max(0, o.hp - dealt)
        f.stats["dmg"] += dealt
        f.stats["throws"] += 1
        f.meter = min(METER_MAX, f.meter + METER_GAIN * dealt / 8)
        o.meter = min(METER_MAX, o.meter + METER_GAIN * dealt / 10)
        f.st, f.mf = "throw", 0
        o.st, o.mf, o.mv, o.air_mv, o.combo = "thrown", 0, None, None, 0
        top, dist = m.get("throw_arc", (26, 46))
        x0 = f.x + f.face * 18
        x1 = max(WALL, min(STAGE_W - WALL, f.x + f.face * dist))
        o.arc = (x0, x1, float(top))
        o.x, o.vx = x0, 0.0
        ev.append(dict(type="throw", id=o.id, by=f.id, dmg=dealt, cmd=bool(m.get("cmd")), super=bool(m.get("cost")),
                       mv=f.mv))

    def _round_over(self, ko, ev):
        A, B = self.f
        if ko:
            winners = [f for f in self.f if f.hp > 0]
            reason = "ko" if winners else "double_ko"
        else:
            ra, rb = A.hp / A.c["hp"], B.hp / B.c["hp"]
            winners = [A] if ra > rb else ([B] if rb > ra else [])
            reason = "time"
        for w in winners:
            w.wins += 1
        self.end_reason = reason
        ev.append(dict(type="round", reason=reason, win=[w.id for w in winners], round=self.round,
                       hp=[A.hp, B.hp]))
        self.phase, self.pt, self.proj = "end", OUTRO, []
        for f in self.f:
            if f.hp > 0 and f.st in GROUND_OK + ("blockstun", "hitstun", "land", "attack", "dash", "backdash", "wake",
                                                  "prejump"):
                f.st, f.mv = ("win" if f in winners else "stand"), None

    def _next_round(self, ev):
        A, B = self.f
        need = self.config["rounds_to_win"]
        if max(A.wins, B.wins) >= need or self.round >= self.config["max_rounds"]:
            self.phase = "over"
            ev.append(dict(type="match", win=[f.id for f in self.f if f.wins == max(A.wins, B.wins)]))
            return
        self.round += 1
        for f in self.f:
            f.reset(START_X[f.id])
        self.phase, self.pt, self.timer = "intro", INTRO, self.round_frames
        self.proj = []

    # ---------- 结果和画面 ----------
    def placements(self):
        if self.f is None:
            return [1, 1]
        a, b = self.f[0].wins, self.f[1].wins
        return [1, 1] if a == b else ([1, 2] if a > b else [2, 1])

    def result(self):
        place = self.placements()
        ko_by = [0, 0]
        for e in self.events:
            if e["type"] == "round" and e["reason"] == "ko":
                ko_by[e["win"][0]] += 1
        last = next((e["t"] for e in reversed(self.events) if e["type"] == "match"), self.turn)
        death = [None if place[i] == 1 else [last, "ko" if ko_by[1 - i] else "decision", 1 - i] for i in (0, 1)]
        fs = self.f or []
        return {"n": 2, "seed": self.seed, "turns": self.turn, "place": place, "death": death, "kills": ko_by,
                "wins": [f.wins for f in fs], "chars": [f.char for f in fs], "hp": [f.hp for f in fs],
                "rounds": self.round,
                "play": [dict(f.stats, wins=f.wins, char=f.char) for f in fs]}

    def frame(self):
        fs = self.f or []
        return dict(t=self.turn, phase=self.phase, round=self.round, timer=-(-self.timer // FPS), flash=self.flash,
                    f=[f.snap() for f in fs], wins=[f.wins for f in fs],
                    proj=[dict(o=p["o"], x=round(p["x"], 1), y=p["y"], vx=p["vx"], w=p["w"], look=p["look"])
                          for p in self.proj],
                    ev=[e for e in self.events if e["t"] == self.turn],
                    throw=[list(f.arc) if f.st == "thrown" and f.arc else None for f in fs])


def replay(n, seed, rows, config=None):
    g = Game.new(n, seed, config)
    for row in rows:
        g.step({i: FROM_LETTER[c] for i, c in enumerate(row) if c in FROM_LETTER})
    return g


def export_game(g, rows, seats):
    frames = [g.frame()]
    for row in rows:
        g.step({i: FROM_LETTER[c] for i, c in enumerate(row) if c in FROM_LETTER})
        frames.append(g.frame())
    res = g.result()
    return {"game": "brawl", "kind": "brawl", "n": 2, "seed": g.seed, "w": STAGE_W, "h": STAGE_H, "turns": g.turn,
            "config": copy.deepcopy(g.config), "seats": list(seats), "place": res["place"], "death": res["death"],
            "kills": res["kills"], "chars": res["chars"], "wins": res["wins"], "frames": frames,
            "events": copy.deepcopy(g.events)}


def export(record, upto=None):
    rows = record["moves"] if upto is None else record["moves"][:max(0, upto)]
    cfg = dict(record.get("config") or {})
    return export_game(Game.new(2, record["seed"], cfg), rows, record["seats"])


def play(bots, seed=0, config=None, max_frames=30000):
    """进程内对局：bots 是两个 decide(state) 函数。返回 (Game, 动作行)。"""
    g = Game.new(2, seed, config)
    rows = []
    while not g.over() and g.turn < max_frames:
        acts = {}
        for i in (0, 1):
            try:
                a = bots[i](g.state_for(i))
            except Exception:
                a = "n"
            acts[i] = a if a in ACTIONS else "n"
        rows.append("".join(LETTER[acts[i]] for i in (0, 1)))
        g.step(acts)
    return g, rows
