"""像素拳斗：阿烈（lie），反应式攻防 + 距离控制。

思路：
  - 对手信息晚 6 帧，起手快的招没法"看见再防"，所以靠距离预判：站在对手
    主要判定范围之外，逼近时才出手。
  - 内嵌四角色招式表，用（对手 6 帧前招式帧 + 6）判断"接下来几帧会不会被打到"，
    决定蹲防 / 站防 / 跳开 / 抢先投。
  - 投抓不到空中、硬直、倒地、无敌状态（attack 可以抓），所以近身时抢先投很赚。
  - 气满 100 时，能收头就超必杀（5 段），对方贴脸乱攻时也用它的无敌帧反打。
  - 自己被硬直时不做无谓输入；连段/追击窗口按距离挑招。
"""
import random

CHAR = "lie"

# 招表: (起手, 判定, reach_lo, reach_hi, kind)
M = {
    "lie": {
        "p": (3, 2, 8, 40, "mid"),
        "h": (7, 3, 10, 54, "mid"),
        "k": (6, 3, 12, 62, "mid"),
        "s": (7, 3, 10, 60, "low"),
        "a": (4, 8, 2, 34, "mid"),
        "x": (6, 15, 4, 50, "mid"),
        "t": (2, 1, 38, 38, "throw"),
    },
    "tie": {
        "p": (4, 2, 8, 42, "mid"),
        "h": (9, 4, 10, 58, "mid"),
        "k": (7, 3, 12, 64, "mid"),
        "s": (8, 3, 10, 60, "low"),
        "a": (5, 6, 2, 32, "mid"),
        "x": (3, 3, 74, 74, "throw"),
        "z": (5, 2, 62, 62, "throw"),
        "t": (2, 1, 40, 40, "throw"),
    },
    "yan": {
        "p": (3, 2, 8, 38, "mid"),
        "h": (6, 3, 10, 48, "mid"),
        "k": (5, 3, 12, 64, "mid"),
        "s": (6, 3, 10, 62, "low"),
        "a": (3, 7, 0, 32, "mid"),
        "x": (5, 18, 4, 48, "mid"),
        "z": (6, 9, 4, 49, "mid"),
        "t": (2, 1, 36, 36, "throw"),
    },
    "rei": {
        "p": (3, 2, 8, 46, "mid"),
        "h": (9, 3, 10, 72, "mid"),
        "k": (7, 3, 12, 80, "mid"),
        "s": (8, 3, 10, 70, "low"),
        "a": (6, 8, 16, 52, "mid"),
        "t": (2, 1, 38, 38, "throw"),
    },
}
MBY = {c: dict(m) for c, m in M.items()}
MBY["lie"]["air"] = (4, 10, 0, 40, "high")
MBY["tie"]["air"] = (5, 9, 0, 40, "high")
MBY["yan"]["air"] = (3, 10, 0, 42, "high")
MBY["rei"]["air"] = (5, 8, 0, 44, "high")

BUSY = ("hitstun", "blockstun", "knock", "wake", "thrown", "throw",
        "ko", "win", "dash", "backdash", "prejump", "land")
GROUND = ("stand", "walk", "crouch")

# 每个角色"要小心的中距离招"上限，用来定安全距离
RANGE = {"lie": 62, "tie": 64, "yan": 64, "rei": 80}


def _threat(op, d):
    """对手（6 帧前）接下来会不会打到我；返回需要的防法。"""
    ost = op["st"]
    oc = op["char"]
    tbl = MBY.get(oc) or {}
    if ost == "air":
        if d < 78 and op["y"] > 4:
            return "high"
        return None
    if ost == "attack":
        mv = op["mv"]
        rec = tbl.get(mv)
        if not rec:
            return None
        s, a, r0, r1, kind = rec
        now = op["mf"] + 6
        if now > s + a + 1:
            return None
        reach = r1
        if oc == "yan" and mv == "z":
            reach = r1 + 5.5 * (a + 1)
        if oc == "tie" and mv in ("z", "x"):
            reach = r1
        if d <= reach + 14:
            if kind == "throw":
                return "throw"
            return kind
    return None


def _incoming(state, me):
    """对手飞行道具是否马上要到。"""
    for p in state.get("projectiles") or []:
        if p.get("mine"):
            continue
        if (me["x"] - p["x"]) * p.get("vx", 0) > 0:
            if abs(me["x"] - p["x"]) < 55:
                return True
        elif abs(me["x"] - p["x"]) < 30:
            return True
    return False


def _attack(d, rnd, meter, ophp, myhp):
    """选一招打。"""
    if d <= 34:
        r = rnd.random()
        if r < 0.42:
            return "t"          # 投（抓不到空中/硬直，但抓 attack）
        if r < 0.72:
            return "p"
        return "h"
    if d <= 46:
        r = rnd.random()
        if r < 0.5:
            return "h"
        if r < 0.72:
            return "p"
        return "k"
    if d <= 58:
        r = rnd.random()
        if r < 0.42:
            return "s"          # 下段击倒
        if r < 0.74:
            return "k"
        return "h"
    if d <= 70:
        return "k" if rnd.random() < 0.5 else "f"
    return "f"


class Bot:
    def __init__(self):
        self.rnd = random.Random(0xB17E)
        self.last = "n"
        self.cool = 0
        self.round = 0


_B = Bot()


def decide(state):
    if state["phase"] == "select":
        return CHAR
    if state["phase"] != "fight" or state.get("freeze", 0) > 0:
        return "n"
    me = state["me"]
    op = state["opp"]
    st = me["st"]
    rnd = _B.rnd
    meter = me["meter"]
    myx = me["x"]

    # 对手当前位置粗估（延迟 6 帧 + 速度外推）
    ovx = op.get("vx") or 0.0
    est = op["x"] + ovx * 6
    d = abs(est - myx)
    tgt_d = abs(op["x"] - myx)
    ost = op["st"]
    omv = op["mv"]
    ophp = op["hp"] / max(1, op["max_hp"])
    myhp = me["hp"] / max(1, me["max_hp"])

    # ---- 空中 ----
    if st == "air":
        if me["mv"] is None and d < 52 and me["y"] > 14:
            return "p"
        return "n"

    # ---- 出招中 ----
    if st == "attack":
        mv = me["mv"]
        if me["contact"] and mv in ("p", "h"):
            # 取消：气够就接超必杀收头 / 接对空技对付跳
            if meter >= 100 and d < 58 and (ost in ("stand", "walk", "crouch", "attack") or ophp < 0.42):
                return "x"
            if meter >= 100 and d < 48 and op["y"] > 20:
                return "x"
        return "n"

    # ---- 不可控 ----
    if st in BUSY:
        if st == "knock" or st == "wake":
            return "n"
        return "n"

    # 以下站在地上，可以出新动作
    th = _threat(op, d)
    inc = _incoming(state, me)
    safe = RANGE.get(op["char"], 62)

    # 超必杀收头
    if meter >= 100:
        if d < 46 and (op["hp"] <= 430 or (th and th != "throw")) and ost != "air":
            return "x"
        if d < 46 and ost in ("stand", "walk", "crouch", "attack") and rnd.random() < 0.22:
            return "x"

    # 对手起跳 → 对空
    if ost == "air":
        if d < 62 and op["y"] > 8:
            return "a"
        if d < 78:
            return "b"      # 站防挡跳攻
        return "f"

    # 对手投 / 指令投 → 跳开或抢先打
    if th == "throw":
        if d < 50:
            if rnd.random() < 0.55:
                return "y"      # 后跳躲投（prejump 抓不到）
            return "t" if d < 30 else "h"
        return "b" if rnd.random() < 0.5 else "f"

    # 对手在出招且会打到我 → 防 / 抢先投
    if th:
        if d < 30 and rnd.random() < 0.30 and meter >= 100:
            return "x"
        if d < 30 and rnd.random() < 0.25:
            return "t"
        return "b" if th == "high" else "g"

    # 对方倒地/硬直 → 压制、追击
    if ost in ("hitstun", "blockstun"):
        if d <= 34:
            return "h" if me["mv"] is None else "p"
        if d <= 58:
            return "h" if d > 44 else "k"
        if d <= 78:
            return "f"
        return "f"

    if ost == "knock":
        return "f" if d > 44 else ("t" if rnd.random() < 0.5 else "s")

    if ost == "wake":
        return "f" if d > 52 else "t"

    # 波来了：距离远就跳过，近就防
    if inc:
        if rnd.random() < 0.35:
            return "j"
        return "g"

    # ---- 常规：控距离 ----
    if d > safe + 26:
        # 远距离：偶尔发波，主要前进
        if meter >= 100 and rnd.random() < 0.25 and state["timer_frames"] > 200:
            return "x"
        if rnd.random() < 0.10 and state["timer_frames"] > 240:
            return "z"
        return "f"
    if d > safe - 6:
        # 临界距离：走动调整，偶尔抢先手
        if rnd.random() < 0.30:
            return _attack(d, rnd, meter, ophp, myhp)
        return "f" if rnd.random() < 0.6 else "b"
    # 打得到的距离
    if state["timer_frames"] < 260 and myhp <= ophp:
        return _attack(d, rnd, meter, ophp, myhp)
    return _attack(d, rnd, meter, ophp, myhp)
