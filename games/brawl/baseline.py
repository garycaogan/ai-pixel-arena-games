"""像素拳斗陪练：只用标准库，只读公开 state。

这个文件单独就是一份合法交卷。测试里用 make(style, char, seed) 造不同打法的陪练：
- baseline：按角色打自己的距离，看见起手就防，对空、确认连段、抓收招
- rusher：贴脸压制，混投、扫腿、重拳
- zoner：拉开距离，能放波就放，近身就后撤
"""
import random

# 各角色自己想站的距离、重拳/脚的够招距离（和 PROMPT 里的招式表一致）
PLAN = {
    "lie": dict(want=110, h=54, k=62, close=44, proj=True),
    "tie": dict(want=40, h=58, k=64, close=40, proj=False),
    "yan": dict(want=60, h=48, k=64, close=40, proj=False),
    "rei": dict(want=150, h=72, k=80, close=46, proj=True),
}
OPP_REACH = {"p": 46, "h": 72, "k": 80, "s": 70, "t": 40, "z": 60, "a": 52, "x": 80, "air": 44}


def _incoming(s, within):
    me = s["me"]
    for p in s["projectiles"]:
        if not p["mine"] and (p["x"] - me["x"]) * -p["vx"] > 0 and abs(p["x"] - me["x"]) < within:
            return p
    return None


def make(style="baseline", char=None, seed=0):
    rng = random.Random(seed)
    want_char = char
    seen = []  # 最近看到的对方出招（按出招时的帧去重）
    last = {"st": "stand"}

    def decide(s):
        if s["phase"] == "select":
            return want_char or rng.choice(s["chars"])
        if s["phase"] != "fight" or s.get("freeze"):
            return "n"
        me, op = s["me"], s["opp"]
        c = me["char"]
        if op["st"] == "attack" and op["mf"] == 1:
            seen.append((s["turn"], op["mv"]))
        while seen and seen[0][0] < s["turn"] - 90:
            seen.pop(0)
        jabs = sum(1 for _, m in seen if m == "p")
        was, last["st"] = last["st"], me["st"]
        if was in ("hitstun", "blockstun", "wake") and me["st"] in ("stand", "crouch", "walk") \
                and abs(op["x"] - me["x"]) < 60:
            r = rng.random()  # 刚挨完打、贴身：多半先防，偶尔无敌技硬顶或投；刚防住就反打
            if was == "blockstun" and r < 0.5:
                return "p" if r < 0.35 else "t"
            if r < 0.55:
                return "b"
            if r < 0.72:
                return "a"
            if r < 0.82:
                return "t"
        plan = PLAN[c]
        d = abs(op["x"] - me["x"])
        mine = any(p["mine"] for p in s["projectiles"])
        meter = me["meter"]
        want = plan["want"]
        aggr = {"baseline": 0.5, "rusher": 0.85, "zoner": 0.2}[style]
        if style == "rusher":
            want = min(want, 46)
        elif style == "zoner":
            want = max(want, 120)

        # 1. 连段确认：轻/重拳打中了就取消成必杀或超必杀
        if me["st"] == "attack" and me["contact"] and me["mv"] in ("p", "h"):
            if meter >= 100 and rng.random() < 0.6:
                return "x"
            if c in ("lie", "rei", "yan") and rng.random() < 0.7:
                return "z"
            return "n"
        # 2. 飞行道具来了：跳过去、对波或防
        p = _incoming(s, 90)
        if p:
            dd = abs(p["x"] - me["x"])
            if plan["proj"] and not mine and dd > 50 and rng.random() < 0.5:
                return "z"
            if p["look"] == "beam":
                return "j" if dd > 40 and rng.random() < 0.5 else "b"
            if dd < 60:
                if d < 150 and rng.random() < 0.45 * (aggr + 0.5):
                    return "j"
                return "b"
        # 2b. 对方在放飞行道具（看见起手）：远处跳进去或冲过去
        if op["st"] == "attack" and op["mv"] in ("z", "x") and op["char"] in ("lie", "rei") and 70 < d < 170 \
                and rng.random() < 0.25 + 0.35 * aggr:
            return "j"
        # 3. 对空
        if op["st"] == "air" and d < 90 and op["y"] > 8:
            r = rng.random()
            return "a" if r < 0.55 + 0.2 * (style != "rusher") else ("b" if r < 0.85 else "e")
        # 4. 对方起手或判定中、够得着我：防（扫腿蹲防）
        if op["st"] == "attack" and op["phase"] in ("startup", "active") and d < OPP_REACH.get(op["mv"], 60) + 12:
            if op["mv"] in ("t", "z") and op["char"] == "tie" and d < 62:
                return "y" if rng.random() < 0.6 else "e"  # 指令投防不住，跳开
            return "g" if op["mv"] == "s" else "b"
        # 5. 抓收招
        if op["st"] in ("attack", "land") and op["phase"] in ("recovery", None) and op["st"] != "air":
            if meter >= 100 and d < 60 and rng.random() < 0.6:
                return "x"
            if c == "tie" and d < 56:
                return "z"
            if d < plan["h"]:
                return "h"
            if c == "yan" and d < 110:
                return "z"
        # 6. 对方倒地起身：压起身
        if op["st"] in ("knock", "wake"):
            if d > want:
                return "f"
            return "g" if rng.random() < 0.4 else ("t" if d < 36 and c != "tie" else "n")
        # 7. 中立
        if meter >= 200 and c == "rei" and d > 90 and rng.random() < 0.08:
            return "x"
        if plan["proj"] and not mine and d > 90 and rng.random() < (0.10 if style != "rusher" else 0.03) + 0.06 * (c == "rei"):
            return "z"
        if d < plan["close"] + 4:
            r = rng.random()
            if c == "tie":
                return "z" if r < 0.22 * (aggr + 0.4) else "p" if r < 0.42 else "t" if r < 0.55 else "s" if r < 0.65 else "b" if r < 0.85 else "h"
            if style == "zoner" and r < 0.3:
                return "e"
            if jabs >= 3:  # 对方在刷轻拳：无敌对空技硬顶、后撤或防
                return "a" if r < 0.35 else "e" if r < 0.55 else "b" if r < 0.85 else "t"
            return "p" if r < 0.24 else "t" if r < 0.38 else "s" if r < 0.48 else "b" if r < 0.7 else "g" if r < 0.8 else "h" if r < 0.88 else "k"
        if d < plan["k"] - 2:
            r = rng.random()
            if r < 0.1:
                return "k"
            if r < 0.16:
                return "s"
            if c == "yan" and r < 0.22:
                return "z"
        if d > want + 10:
            r = rng.random()
            if r < 0.05 * (aggr + 0.3):
                return "r"
            if r < 0.07 * aggr:
                return "j"
            return "f" if r < 0.85 else "b"
        if d < want - 20:
            r = rng.random()
            return "b" if r < 0.7 else ("e" if r < 0.8 else "n")
        r = rng.random()
        return "b" if r < 0.5 else ("f" if r < 0.8 else "n")

    return decide


_default = make("baseline", None, random.random())  # 裁判加载时按种子初始化 random


def decide(state):
    return _default(state)
