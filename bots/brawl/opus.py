"""铁山（投技）：贴身打指令投，轻拳打中/被防后取消成必杀投或超必杀投（硬直结束那一帧对手没机会输入，必中）。
对手状态晚 6 帧，用确定性推演补回来：出招、硬直、倒地、空中都能推到现在。"""
import random

GROUND = ("stand", "walk", "crouch")
NOTHROW = ("hitstun", "blockstun", "knock", "wake", "thrown", "throw", "ko", "air", "prejump")
GRAV = 0.9
WALL = 26
W = 384

# 各角色招式：s, a, r, reach_hi, kind, vx, inv(lo,hi)
MV = {
    "lie": {"p": (3, 2, 6, 40, "mid", 0, None), "h": (7, 3, 14, 54, "mid", 0, None), "k": (6, 3, 14, 62, "mid", 0, None),
            "s": (7, 3, 18, 60, "low", 0, None), "air": (4, 10, 0, 40, "high", 0, None), "t": (2, 1, 20, 38, "throw", 0, None),
            "z": (12, 1, 24, 0, "proj", 0, None), "a": (4, 8, 26, 34, "mid", 1.2, (1, 6)),
            "x": (6, 15, 30, 50, "mid", 6.0, (1, 9))},
    "tie": {"p": (4, 2, 7, 42, "mid", 0, None), "h": (9, 4, 17, 58, "mid", 0, None), "k": (7, 3, 14, 64, "mid", 0, None),
            "s": (8, 3, 20, 60, "low", 0, None), "air": (5, 9, 0, 40, "high", 0, None), "t": (2, 1, 20, 40, "throw", 0, None),
            "z": (5, 2, 30, 62, "throw", 0, None), "a": (5, 6, 34, 32, "mid", 0, (1, 5)),
            "x": (3, 3, 48, 74, "throw", 0, (1, 4))},
    "yan": {"p": (3, 2, 5, 38, "mid", 0, None), "h": (6, 3, 13, 48, "mid", 0, None), "k": (5, 3, 14, 64, "mid", 0, None),
            "s": (6, 3, 15, 62, "low", 0, None), "air": (3, 10, 0, 42, "high", 0, None), "t": (2, 1, 20, 36, "throw", 0, None),
            "z": (6, 9, 18, 44, "mid", 5.5, None), "a": (3, 7, 24, 32, "mid", -0.6, (1, 5)),
            "x": (5, 18, 28, 48, "mid", 7.0, (1, 8))},
    "rei": {"p": (3, 2, 7, 46, "mid", 0, None), "h": (9, 3, 16, 72, "mid", 0, None), "k": (7, 3, 15, 80, "mid", 0, None),
            "s": (8, 3, 19, 70, "low", 0, None), "air": (5, 8, 0, 44, "high", 0, None), "t": (2, 1, 20, 38, "throw", 0, None),
            "z": (14, 1, 22, 0, "proj", 0, None), "a": (6, 8, 24, 52, "mid", 0, (1, 4)),
            "x": (10, 1, 34, 0, "proj", 0, None)},
}
JUMP = {"lie": (11.0, 3.2), "tie": (10.2, 2.6), "yan": (11.6, 3.8), "rei": (10.6, 3.0)}
DASH = {"lie": (9, 5.0), "tie": (8, 4.6), "yan": (8, 6.2), "rei": (9, 4.4)}
BDASH = {"lie": (12, 4.0, 5), "tie": (11, 3.4, 4), "yan": (11, 4.6, 6), "rei": (12, 4.2, 5)}

G = {"prev_opp": None, "prev_meter": 0, "contact_turn": None, "cancel_plan": None, "last_turn": 0}


def clampx(x):
    return max(WALL, min(W - WALL, x))


def adv(o, oppx):
    """不带输入推进一帧（只对不可控状态准确；可控状态假设保持走动）。返回新 dict。"""
    o = dict(o)
    st = o["st"]
    face = o["face"]
    o["inv"] = False
    if st == "walk":
        o["x"] = clampx(o["x"] + o["vx"])
    elif st == "prejump":
        o["mf"] += 1
        if o["mf"] >= 3:
            jv, jx = JUMP[o["char"]]
            o["st"], o["vy"], o["vx"] = "air", jv, o.get("jdir", 0) * jx * face
            o["air_mv"] = None
    elif st == "air":
        o["x"] = clampx(o["x"] + o["vx"])
        o["y"] += o["vy"]
        o["vy"] -= GRAV
        if o.get("mv") == "air":
            o["mf"] += 1
        if o["y"] <= 0 and o["vy"] < 0:
            o["y"], o["vy"], o["st"], o["mf"], o["mv"] = 0.0, 0.0, "land", 0, None
    elif st == "land":
        o["mf"] += 1
        if o["mf"] >= 3:
            o["st"] = "stand"
    elif st == "dash":
        n, v = DASH[o["char"]]
        o["mf"] += 1
        o["x"] = clampx(o["x"] + v * face)
        if o["mf"] >= n:
            o["st"] = "stand"
    elif st == "backdash":
        n, v, iv = BDASH[o["char"]]
        o["mf"] += 1
        o["x"] = clampx(o["x"] - v * face)
        if o["mf"] <= iv:
            o["inv"] = True
        if o["mf"] >= n:
            o["st"] = "stand"
    elif st == "attack":
        m = MV[o["char"]].get(o["mv"])
        if m is None:
            o["st"] = "stand"
            return o
        s, a, r, reach, kind, vx, inv = m
        o["mf"] += 1
        if inv and inv[0] <= o["mf"] <= inv[1]:
            o["inv"] = True
        if vx and s < o["mf"] <= s + a:
            o["x"] = clampx(o["x"] + vx * face)
        if o["mf"] > s + a + r:
            o["st"], o["mv"] = ("crouch" if o["mv"] == "s" else "stand"), None
    elif st in ("hitstun", "blockstun"):
        o["stun"] -= 1
        if o["stun"] <= 0:
            o["st"] = "stand"
    elif st == "knock":
        o["inv"] = True
        if o["y"] > 0 or o.get("vy", 0) > 0:
            o["y"] += o.get("vy", 0)
            o["vy"] = o.get("vy", 0) - GRAV
            o["x"] = clampx(o["x"] + o["vx"])
            if o["y"] <= 0:
                o["y"], o["vy"], o["vx"] = 0.0, 0.0, 0.0
        else:
            o["stun"] -= 1
            if o["stun"] <= 0:
                o["st"], o["mf"] = "wake", 0
    elif st == "wake":
        o["inv"] = True
        o["mf"] += 1
        if o["mf"] >= 10:
            o["st"] = "stand"
    elif st == "throw":
        o["mf"] += 1
        if o["mf"] >= 22:
            o["st"], o["mv"] = "stand", None
    elif st == "thrown":
        o["inv"] = True
        o["mf"] += 1
        if o["mf"] >= 20:
            o["st"], o["stun"], o["vx"], o["y"] = "knock", 30, 0.0, 0.0
    return o


def throwable(o):
    return o["y"] == 0 and o["st"] not in NOTHROW and not o["inv"]


def decide(state):
    if state["phase"] == "select":
        return "tie"
    fz = G.setdefault("fz", set())
    if state.get("freeze", 0) > 0:
        t = state["turn"]
        if t - 1 not in fz:
            fz.add(t - 1)
        fz.add(t)
    if state["phase"] != "fight" or state.get("freeze", 0) > 0:
        G["prev_opp"] = None
        G["cancel_plan"] = None
        if state.get("freeze", 0) > 0:
            return "u"  # 定格中输入无效
        return "n"
    try:
        return think(state)
    except Exception:
        return "b"


def think(state):
    me, op = state["me"], state["opp"]
    turn = state["turn"]
    meter = me["meter"]
    dmeter = meter - G["prev_meter"]
    G["prev_meter"] = meter

    # 对手当前竖直速度从相邻两帧估出
    o = dict(op)
    po = G["prev_opp"]
    G["prev_opp"] = op
    if po is not None and po["st"] == "wake" and op["st"] != "wake":
        G["wake_n"] = G.get("wake_n", 0) + 1
        if op["st"] in ("attack", "backdash", "prejump") and op["mv"] not in ("p", "t", "s", "k", "h"):
            G["wake_rev"] = G.get("wake_rev", 0) + 1
    if op["st"] in ("air", "knock") and po is not None and po["st"] == op["st"]:
        o["vy"] = (op["y"] - po["y"]) - GRAV
    elif op["st"] == "knock":
        o["vy"] = 0.0 if op["y"] <= 0 else -1.0
    else:
        o["vy"] = 11.0 if op["st"] == "air" and op["y"] < 12 else 0.0
    if op["st"] == "air":
        o["mf"] = op["mf"] if op["mv"] == "air" else 0
    # S[i]：第 turn-7+i 帧结算后的对手状态
    S = [o]
    for i in range(22):
        S.append(adv(S[-1], me["x"]))
    # 定格的那几帧对手没动：把推演往后挪
    nfz = sum(1 for t in range(turn - 6, turn) if t in G["fz"])
    if nfz:
        S = [o] * nfz + S

    my = me["x"]
    face = me["face"]
    def dist(i):
        return abs(S[i]["x"] - my)

    if me["st"] == "attack" and me["mv"] == "x" and me["phase"] == "recovery" and G.get("rawx_turn"):
        G["rev_fail"] = G.get("rev_fail", 0) + 1
        G["rawx_turn"] = None
    if me["st"] == "throw":
        G["rawx_turn"] = None
    prev_st = G.get("my_prev_st")
    G["my_prev_st"] = me["st"]
    # ---- 取消：轻拳打中/被防后转投 ----
    if me["st"] == "attack" and me["mv"] in ("p", "h"):
        if me["contact"]:
            if G["contact_turn"] is None:
                G["contact_turn"] = turn - 1
                hit = dmeter >= 5 or (meter >= 299 and op.get("gmode") is None)
                G["cancel_plan"] = hit
            k = turn - G["contact_turn"]
            hit = G["cancel_plan"]
            if me["mv"] == "p":
                if meter >= 100 and k == 4:
                    return "x"
                if meter < 100:
                    if hit and k == 1:
                        return "z"
                    if not hit and k == 4:
                        return "z"
            return "n"
        return "n"
    G["contact_turn"] = None

    if me["st"] == "blockstun":
        return guard_mode(S, me)
    if me["st"] == "air":
        s7 = S[7]
        if me["mv"] is None and (s7["x"] - my) * face > -4 and abs(s7["x"] - my) < 50 and me["y"] < 64 \
                and s7["y"] < 30:
            return "k"
        return "n"
    if me["st"] not in GROUND:
        return "n"

    # ---- 对手超必杀（定格后才看得到） ----
    cur = S[7]
    # ---- 飞行道具 ----
    proj_danger = 99
    plist = [(p["x"] + p["vx"] * 7, p["vx"], p["w"]) for p in state["projectiles"] if not p["mine"]]
    # 对手正在放波：预测出波
    for i in range(1, len(S)):
        s = S[i]
        if s["st"] == "attack" and s["mv"] in ("z", "x") and MV[s["char"]][s["mv"]][4] == "proj":
            ms = MV[s["char"]][s["mv"]][0]
            if s["mf"] == ms + 1:
                v = {"lie": 5.0, "rei": 3.6}[s["char"]] if s["mv"] == "z" else 8.0
                w = 26 if s["mv"] == "x" else (12 if s["char"] == "lie" else 16)
                plist.append((s["x"] + s["face"] * 22 - s["face"] * v * (i - 7), v * s["face"], w))
                break
    G["plist"] = plist
    beam = False
    for px0, pvx, pw in plist:
        for j in range(0, 40):
            px = px0 + pvx * j
            if abs(px - my) <= pw / 2 + 12:
                proj_danger = min(proj_danger, j)
                if pw == 26 and j <= 4:
                    beam = True
                break
    # 对手打击威胁：第 turn+j 帧对手在判定帧且够得着
    threat_j, threat_kind = 99, None
    for j in range(0, 12):
        s = S[7 + j]
        if s["st"] == "attack" and s["mv"] in MV[s["char"]]:
            ms, ma, mr, reach, kind, vx, inv = MV[s["char"]][s["mv"]]
            if kind in ("mid", "low") and ms < s["mf"] <= ms + ma and abs(s["x"] - my) <= reach + 12 + abs(vx) * 2:
                threat_j, threat_kind = j, kind
                break
            if kind == "throw" and ms < s["mf"] <= ms + ma and abs(s["x"] - my) <= reach + 4:
                threat_j, threat_kind = j, "throw"
                break
        elif s["st"] == "air":
            ss = MV[s["char"]]["air"]
            if abs(s["x"] - my) <= 54 and s["y"] < 60:
                threat_j, threat_kind = j, "high"
                break

    # 超必杀投（对手铁山）定格结束：起跳躲
    if threat_kind == "throw" and threat_j <= 6:
        s = S[7]
        if s["st"] == "attack" and s["mv"] == "x":
            return "u"

    # ---- 惩罚 / 抓破绽 ----
    # 超必杀投：判定在 turn+3..turn+5（S[10..12]）
    if meter >= 100 and proj_danger >= 7:
        for i in (10, 11, 12):
            if throwable(S[i]) and dist(i) <= 70 and S[i]["st"] in ("attack", "throw", "land", "stand", "crouch", "walk"):
                # 只在对手无法靠输入躲开时用：出招中/落地/刚从硬直恢复
                prev = S[i - 1]
                locked = S[i]["st"] in ("attack", "land", "throw") or prev["st"] in ("hitstun", "blockstun")
                if locked and all(S[q]["st"] in ("attack", "land", "throw", "hitstun", "blockstun", "air", "knock", "wake", "thrown")
                                  for q in range(7, i)):
                    return "x"
    # 指令投：判定在 turn+5, turn+6（S[12], S[13]）
    for i in (12, 13):
        if throwable(S[i]) and dist(i) <= (61 if S[i]["st"] in ("attack", "land", "throw") else 57):
            prev = S[i - 1]
            locked = S[i]["st"] in ("attack", "land", "throw") or prev["st"] in ("hitstun", "blockstun")
            if locked and threat_j >= 5 and proj_danger >= 6:
                return "z"
    # 冲刺罚：对手长招落空，冲过去再投（冲 8 帧 + 投判定 6/7 帧）
    if not plist and len(S) > 21 and S[7]["st"] == "attack" and S[7]["mv"] in MV[S[7]["char"]] \
            and S[7]["mf"] > sum(MV[S[7]["char"]][S[7]["mv"]][:2]):
        land = my + face * 36.8
        if all(S[q]["st"] == "attack" for q in range(7, 21)) and abs(S[20]["x"] - land) <= 56 \
                and abs(S[7]["x"] - my) > 58 and threat_j > 8:
            return "r"
    # 普通投：判定在 turn+2（S[9]）
    if throwable(S[9]) and dist(9) <= 36 and S[9]["st"] in ("attack", "land") and threat_j >= 2:
        return "t"

    # 自己起身第一帧：超必杀投反击（无敌 1-4 帧，对手压起身时正好在出招/站着）
    if prev_st == "wake" and meter >= 100 and G.get("rev_fail", 0) < 1 and dist(10) <= 70 \
            and throwable(S[10]) and proj_danger >= 7:
        G["rawx_turn"] = turn
        return "x"
    # ---- 防守 ----
    if beam:
        return "g"
    if G.get("wake_block", 0) > turn:
        return "b"
    if proj_danger <= 3 and me["guard"] > max([(58 if pw == 16 else 53) for _, _, pw in plist] or [0]) + 1:
        return "g"
    if threat_j <= 4:
        if threat_kind == "high":
            s = S[7]
            if s["st"] == "air" and abs(s["x"] - my) <= 40 and s["y"] > 25:
                return "a"
            return "b"
        if threat_kind == "low":
            return "g"
        if threat_kind == "throw":
            return "u"
        return "b"

    # 对空：对手在空中逼近
    s7 = S[7]
    if s7["st"] in ("air", "prejump"):
        for j in range(5, 11):
            s = S[7 + j] if 7 + j < len(S) else S[-1]
            dx = (s["x"] - my) * face
            if s["st"] == "air" and -6 <= dx <= 40 and s["y"] + 56 >= 40 + 3 * (j - 4) and s["y"] <= 116:
                return "a"
        # 落地点在投距离内：等落地投
        return "b" if dist(7) < 60 else "f"

    # 倒地起身：压起身轻拳
    if s7["st"] in ("knock", "wake", "thrown"):
        jf = None
        for j in range(0, 14):
            if S[6 + j]["st"] in GROUND:
                jf = j
                break
        d = dist(7)
        if jf is not None and jf in (4, 5) and d <= 46:
            prev = (G.get("wake_rev", 0) + 0.3) / (G.get("wake_n", 0) + 1.5)
            if random.random() < prev:
                G["wake_block"] = turn + 8
                return "b"
            return "p"

        if d > 40:
            return "f"
        return "n"

    # ---- 中立 ----
    d = abs(cur["x"] - my)
    # 预计对手在判定帧的位置（可能后退）
    if proj_danger <= 26:
        # 试着跳过
        low_guard = me["guard"] <= max([(58 if pw == 16 else 53) for _, _, pw in plist] or [0]) + 1
        if proj_danger >= 3 and jump_clears(state, me) and (low_guard or abs(me["x"] + face * 2.6 * 26 - S[20]["x"]) > 62):
            return "j"
        if low_guard:
            return "f"
        return "g" if proj_danger <= 4 else "f"
    if s7["st"] in ("hitstun", "blockstun"):
        return "f" if d > 40 else "n"
    if s7["st"] == "attack" and s7["mv"] in ("z", "x") and MV[s7["char"]][s7["mv"]][4] == "proj":
        # 放波中：冲过去
        ms, ma, mr = MV[s7["char"]][s7["mv"]][:3]
        left = ms + ma + mr - s7["mf"]
        if not plist and d < 50:
            return "z"
        return "f"
    # 快到时间且血量比例领先：别送
    tf = state.get("timer_frames", 9999)
    if tf < 150 and me["hp"] / me["max_hp"] > cur["hp"] / cur["max_hp"] + 0.03:
        if d < 66 and cur["st"] in GROUND and random.random() < 0.5:
            return "z"
        return "b" if d < 140 else "n"
    r = random.random()
    toward = (cur["x"] - my) * cur["vx"] < 0 if cur["st"] == "walk" else False
    away = (cur["x"] - my) * cur["vx"] > 0 if cur["st"] == "walk" else False
    d12 = d - 2 if toward else (d + 4 if away else d)
    if cur["char"] == "tie" and 46 <= d <= 64 and r < 0.15:
        return "e"
    if d <= 36 and r < 0.4:
        return "t"
    if d <= 50:
        if r < 0.55:
            return "p"
        if d <= 34 and r < 0.75:
            return "t"
        if d12 <= 60:
            return "z"
        return "p"
    if d12 <= 60:
        return "z" if r < 0.6 else "f"
    band = POKE[cur["char"]] + 4
    if d <= band:
        # 对手长腿的范围：蹲防等它出招落空/被防再抓，或者冲进去
        mode, until = G.get("band", (None, 0))
        if turn >= until or mode is None:
            q = random.random()
            mode = "r" if q < 0.25 else ("g" if q < 0.5 else "f")
            G["band"] = (mode, turn + (1 if mode == "r" else random.randint(8, 20)))
        if mode == "r" and d - 37 <= 56 and not plist:
            G["band"] = (None, 0)
            return "r"
        return "g" if mode == "g" else "f"
    if d > 130 and r < 0.3 and not plist:
        return "r"
    return "f"


POKE = {"lie": 74, "tie": 76, "yan": 76, "rei": 92}


def guard_mode(S, me):
    for j in range(0, 8):
        s = S[7 + j]
        if s["st"] == "attack" and s["mv"] == "s":
            return "g"
        if s["st"] == "air":
            return "b"
    return "b"


def jump_clears(state, me):
    """前跳能否越过所有对方飞行道具。"""
    jv, jx = JUMP["tie"]
    x, y, vy = me["x"], 0.0, jv
    traj = []
    for f in range(3):
        traj.append((x, 0.0))
    while True:
        x = clampx(x + jx * me["face"])
        y += vy
        vy -= GRAV
        if y <= 0:
            break
        traj.append((x, y))
    for px0, pvx, pw in G.get("plist", []):
        hy = (10, 80) if pw == 26 else (36, 58)
        for j, (tx, ty) in enumerate(traj):
            px = px0 + pvx * j
            if abs(px - tx) <= pw / 2 + 11:
                h = 56 if ty > 0 else 78
                if hy[0] <= ty + h and ty <= hy[1]:
                    return False
    return True
