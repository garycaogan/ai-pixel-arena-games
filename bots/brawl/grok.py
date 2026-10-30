"""像素拳斗 — 飞燕。

外推对手 6 帧前的锁定动作，打断火球起手，跳过已经放出的波，
硬直里用最快能打中的高伤招惩罚，贴身混合投与后撤。
"""

import random

CHAR = "yan"
WALL, STAGE, DELAY, GRAV = 26, 384, 6, 0.9

STATS = {
    "lie": dict(walk=2.2, back=1.7, dash=(9, 5.0), bd=(12, 4.0, 5), jv=11.0, jx=3.2, h=72, c=46, hp=980),
    "tie": dict(walk=1.9, back=1.4, dash=(8, 4.6), bd=(11, 3.4, 4), jv=10.2, jx=2.6, h=78, c=50, hp=1250),
    "yan": dict(walk=2.7, back=2.1, dash=(8, 6.2), bd=(11, 4.6, 6), jv=11.6, jx=3.8, h=68, c=42, hp=890),
    "rei": dict(walk=1.9, back=1.7, dash=(9, 4.4), bd=(12, 4.2, 5), jv=10.6, jx=3.0, h=74, c=46, hp=990),
}

def M(s, a, r, reach=(0, 0), hy=(0, 1), kind="mid", dmg=0, grab=0, kd=False,
      cancel=False, vx=0.0, vy=0.0, inv=None, proj=None, hits=None, cost=0):
    return dict(s=s, a=a, r=r, reach=reach, hy=hy, kind=kind, dmg=dmg, grab=grab,
                kd=kd, cancel=cancel, vx=vx, vy=vy, inv=inv, proj=proj, hits=hits, cost=cost)

MOVES = {
    "lie": {
        "p": M(3, 2, 6, (8, 40), (40, 62), dmg=60, cancel=True),
        "h": M(7, 3, 14, (10, 54), (46, 68), dmg=160, cancel=True),
        "k": M(6, 3, 14, (12, 62), (18, 40), dmg=120),
        "s": M(7, 3, 18, (10, 60), (0, 12), "low", 110, kd=True),
        "t": M(2, 1, 20, dmg=240, grab=38),
        "z": M(12, 1, 24, proj=(5.0, 12, 38, 56)),
        "a": M(4, 8, 26, (2, 34), (28, 112), dmg=220, kd=True, vx=1.2, vy=7.0, inv=(1, 6)),
        "x": M(6, 15, 30, (4, 50), (10, 80), dmg=124, kd=True, vx=6.0, inv=(1, 9), hits=(1, 4, 7, 10, 13), cost=100),
        "air": M(4, 10, 0, (0, 40), (-14, 26), "high", 130),
    },
    "tie": {
        "p": M(4, 2, 7, (8, 42), (40, 64), dmg=70, cancel=True),
        "h": M(9, 4, 17, (10, 58), (46, 70), dmg=210, cancel=True),
        "k": M(7, 3, 14, (12, 64), (16, 40), dmg=140),
        "s": M(8, 3, 20, (10, 60), (0, 12), "low", 120, kd=True),
        "t": M(2, 1, 20, dmg=260, grab=40),
        "z": M(5, 2, 30, dmg=430, grab=62),
        "a": M(5, 6, 34, (2, 32), (40, 116), dmg=210, kd=True, vy=3.0, inv=(1, 5)),
        "x": M(3, 3, 48, dmg=640, grab=74, inv=(1, 4), cost=100),
        "air": M(5, 9, 0, (0, 40), (-14, 26), "high", 160),
    },
    "yan": {
        "p": M(3, 2, 5, (8, 38), (40, 60), dmg=52, cancel=True),
        "h": M(6, 3, 13, (10, 48), (42, 64), dmg=124, cancel=True),
        "k": M(5, 3, 14, (12, 64), (30, 62), dmg=116),
        "s": M(6, 3, 15, (10, 62), (0, 12), "low", 100, kd=True),
        "t": M(2, 1, 20, dmg=220, grab=36),
        "z": M(6, 9, 18, (4, 44), (30, 70), dmg=170, kd=True, vx=5.5),
        "a": M(3, 7, 24, (0, 32), (30, 110), dmg=190, kd=True, vx=-0.6, vy=6.0, inv=(1, 5)),
        "x": M(5, 18, 28, (4, 48), (20, 72), dmg=104, kd=True, vx=7.0, inv=(1, 8), hits=(1, 4, 7, 10, 13, 16), cost=100),
        "air": M(3, 10, 0, (0, 42), (-14, 26), "high", 116),
    },
    "rei": {
        "p": M(3, 2, 7, (8, 46), (42, 66), dmg=60, cancel=True),
        "h": M(9, 3, 16, (10, 72), (46, 70), dmg=160, cancel=True),
        "k": M(7, 3, 15, (12, 80), (22, 46), dmg=124),
        "s": M(8, 3, 19, (10, 70), (0, 12), "low", 100, kd=True),
        "t": M(2, 1, 20, dmg=230, grab=38),
        "z": M(14, 1, 22, proj=(3.6, 16, 36, 58)),
        "a": M(6, 8, 24, (16, 52), (40, 130), dmg=200, kd=True, inv=(1, 4)),
        "x": M(10, 1, 34, proj=(8.0, 26, 10, 80), kd=True, cost=100),
        "air": M(5, 8, 0, (0, 44), (-14, 26), "high", 120),
    },
}

_rng = random.Random()
_mem = {"block": 0, "jump": 0, "throw": 0, "n": 1, "pending": None}


def decide(state):
    if state["phase"] == "select":
        return CHAR
    if state["phase"] != "fight" or state.get("freeze", 0):
        return "n"
    me, opp = state["me"], state["opp"]
    _note(opp)
    pred = predict(opp, me)
    projs = live_projs(state.get("projectiles") or [], pred)

    if me["st"] == "attack" and me.get("contact") and _mem.get("pending"):
        c = _cancel(me, pred)
        if c:
            return c
    if me["st"] == "blockstun":
        return "b" if pred["st"] == "air" or pred.get("mv") == "air" else "g"
    if me["st"] == "air":
        return "p" if abs(me["x"] - pred["x"]) < 78 else "n"
    if me["st"] not in ("stand", "walk", "crouch"):
        return "n"
    return ground(me, pred, projs, state)


def _note(opp):
    _mem["n"] += 1
    if opp["st"] in ("air", "prejump"):
        _mem["jump"] += 1
    if opp["st"] == "blockstun" or opp.get("gmode"):
        _mem["block"] += 1
    if opp.get("mv") in ("t",) or (opp.get("char") == "tie" and opp.get("mv") in ("z", "x")):
        _mem["throw"] += 1


# ---------- 外推 ----------

def predict(opp, me):
    sim = {
        "x": float(opp["x"]), "y": float(opp["y"]),
        "vx": float(opp.get("vx") or 0.0), "vy": 0.0,
        "face": opp["face"] or (1 if me["x"] > opp["x"] else -1),
        "st": opp["st"], "mv": opp.get("mv"), "mf": int(opp.get("mf") or 0),
        "stun": int(opp.get("stun") or 0), "char": opp["char"],
        "hp": opp["hp"], "meter": opp.get("meter") or 0,
        "guard": opp.get("guard") if opp.get("guard") is not None else 100,
        "jdir": 0,
    }
    if sim["st"] == "air":
        sim["vy"] = _vy_from_y(sim["char"], sim["y"], sim["vx"])
        # 空中 vx 已经告诉方向
    toward = 1 if me["x"] > sim["x"] else -1
    spawned = []
    for _ in range(DELAY):
        if sim["st"] in ("stand", "walk", "crouch"):
            # 盲区：不知道新动作。位置按“可能冲刺”另算，这里停住。
            sim["st"] = "stand"
            sim["mv"] = None
            break
        _advance(sim, spawned)
        # 若中途回到可行动，后面的帧是盲的
        if sim["st"] in ("stand", "walk", "crouch"):
            break
    # 如果提前 break，后面没模拟完的帧：他们可能已经动了。用冲刺估最近位置。
    return sim | {
        "toward": toward,
        "lock": lock_of(sim),
        "spawned": spawned,
        "x0": float(opp["x"]),
    }


def _vy_from_y(char, y, vx):
    stt = STATS[char]
    if y <= 1:
        return 0.0
    vy, yy = stt["jv"], 0.0
    best, best_vy = 99.0, 0.0
    for _ in range(36):
        vy -= GRAV
        yy += vy
        if abs(yy - y) < best:
            best, best_vy = abs(yy - y), vy
        if yy > y + 8 and vy < 0:
            break
    return best_vy


def _advance(sim, spawned):
    stt = STATS[sim["char"]]
    st = sim["st"]
    if st == "prejump":
        sim["mf"] += 1
        if sim["mf"] >= 3:
            sim["st"] = "air"
            sim["vy"] = stt["jv"]
            sim["vx"] = stt["jx"] * sim["face"] * sim.get("jdir", 0)
            sim["y"] = 0.0
            sim["mf"] = 0
            sim["mv"] = None
        return
    if st == "air":
        sim["x"] += sim["vx"]
        sim["vy"] -= GRAV
        sim["y"] += sim["vy"]
        if sim["y"] <= 0:
            sim.update(y=0.0, vy=0.0, vx=0.0, st="land", mf=0, mv=None)
        return
    if st == "land":
        sim["mf"] += 1
        if sim["mf"] >= 3:
            sim["st"] = "stand"
        return
    if st == "dash":
        dur, spd = stt["dash"]
        sim["x"] += spd * sim["face"]
        sim["mf"] += 1
        if sim["mf"] >= dur:
            sim["st"] = "stand"
        return
    if st == "backdash":
        dur, spd, invn = stt["bd"]
        sim["x"] -= spd * sim["face"]
        sim["mf"] += 1
        if sim["mf"] >= dur:
            sim["st"] = "stand"
        return
    if st in ("hitstun", "blockstun"):
        sim["stun"] -= 1
        if sim["stun"] <= 0:
            sim["st"] = "stand"
            sim["mv"] = None
        return
    if st == "knock":
        sim["stun"] -= 1
        if sim["stun"] <= 0:
            sim.update(st="wake", mf=0, y=0.0)
        return
    if st == "wake":
        sim["mf"] += 1
        if sim["mf"] >= 10:
            sim["st"] = "stand"
            sim["mv"] = None
        return
    if st == "thrown":
        sim["mf"] += 1
        if sim["mf"] >= 20:
            sim.update(st="knock", stun=30, y=0.0, mf=0)
        return
    if st in ("attack", "throw"):
        m = MOVES.get(sim["char"], {}).get(sim.get("mv") or "")
        if not m:
            sim["st"] = "stand"
            return
        sim["mf"] += 1
        mf = sim["mf"]
        active = m["s"] < mf <= m["s"] + m["a"]
        if active and m["vx"]:
            sim["x"] += m["vx"] * sim["face"]
        if active and m["vy"]:
            sim["y"] += m["vy"]
        if m["proj"] and mf == m["s"] + 1:
            v, w, hy0, hy1 = m["proj"]
            spawned.append({"x": sim["x"] + sim["face"] * 22.0, "vx": v * sim["face"], "w": w, "hy": (hy0, hy1)})
        end = 22 if st == "throw" else m["s"] + m["a"] + m["r"]
        if mf > end and sim["y"] <= 0:
            sim["st"] = "crouch" if sim.get("mv") == "s" else "stand"
            sim["mv"] = None
            sim["y"] = 0.0
        return
    sim["st"] = "stand"


def lock_of(sim):
    if sim["st"] in ("stand", "walk", "crouch"):
        return 0
    s = {k: sim[k] for k in ("x", "y", "vx", "vy", "face", "st", "mv", "mf", "stun", "char", "jdir") if k in sim}
    s.setdefault("jdir", 0)
    s.setdefault("vy", 0.0)
    s.setdefault("vx", 0.0)
    for i in range(1, 70):
        _advance(s, [])
        if s["st"] in ("stand", "walk", "crouch"):
            return i
    return 40


def live_projs(raw, pred):
    out = []
    for p in raw:
        if p.get("mine"):
            out.append({"x": p["x"], "vx": p["vx"], "w": p["w"], "hy": hy_of(p), "mine": True})
        else:
            out.append({"x": p["x"] + p["vx"] * DELAY, "vx": p["vx"], "w": p["w"], "hy": hy_of(p), "mine": False})
    for sp in pred.get("spawned") or []:
        out.append({**sp, "mine": False})
    # 对手正在出波，弹丸还没生成：把未来弹道也算上
    m = MOVES.get(pred["char"], {}).get(pred.get("mv") or "")
    if m and m["proj"] and pred["st"] == "attack":
        v, w, hy0, hy1 = m["proj"]
        # 还要几帧才生成
        left = (m["s"] + 1) - pred["mf"]
        if left > 0:
            face = pred["face"]
            out.append({
                "x": pred["x"] + face * 22.0 + v * face * 0,  # 生成点
                "vx": v * face, "w": w, "hy": (hy0, hy1), "mine": False,
                "delay": left,  # 这么多帧后才开始飞
            })
    return out


def hy_of(p):
    look = p.get("look")
    if look == "beam":
        return (10, 80)
    if look == "bolt":
        return (36, 58)
    return (38, 56)


# ---------- 几何 ----------

def dist(me, x):
    return abs(me["x"] - x)


def reach(m):
    if m.get("grab"):
        return m["grab"]
    far = m["reach"][1] + 11
    if m["vx"] > 0:
        far += m["vx"] * max(0, m["a"] - 1)
    return far


def throw_range(pred):
    c = pred["char"]
    if c == "tie":
        return 74 if pred["meter"] >= 100 else 62
    return {"lie": 38, "yan": 36, "rei": 38}[c]


def proj_eta(me, projs, y=0.0, hh=None):
    """对手的波几帧后打中 (x, y) 处的受击框。None=打不中。"""
    if hh is None:
        hh = STATS[me["char"]]["h"]
    best = None
    for p in projs:
        if p.get("mine"):
            continue
        delay = p.get("delay", 0)
        px, vx = p["x"], p["vx"]
        hy0, hy1 = p["hy"]
        if not (y < hy1 and y + hh > hy0):
            continue
        for t in range(delay, delay + 48):
            if t >= delay and abs(px - me["x"]) < p["w"] / 2 + 11:
                best = t if best is None else min(best, t)
                break
            if t >= delay:
                px += vx
            if px < -20 or px > STAGE + 20:
                break
    return best


def boxes_hit(ax, ay, face, m, me):
    near, far = m["reach"]
    x0, x1 = ax + face * near, ax + face * far
    if x1 < x0:
        x0, x1 = x1, x0
    y0, y1 = ay + m["hy"][0], ay + m["hy"][1]
    hh = 56 if me["st"] == "air" else (STATS[me["char"]]["c"] if me["st"] == "crouch" else STATS[me["char"]]["h"])
    return x0 <= me["x"] + 11 and me["x"] - 11 <= x1 and y0 <= me["y"] + hh and me["y"] <= y1


def immediate(me, pred, projs):
    m = MOVES.get(pred["char"], {}).get(pred.get("mv") or "")
    if m and pred["st"] in ("attack", "throw"):
        mf = pred["mf"] + 1
        active = m["s"] < mf <= m["s"] + m["a"]
        if m.get("hits"):
            active = active and (mf - m["s"]) in m["hits"]
        if active:
            ax = pred["x"] + (m["vx"] * pred["face"] if active else 0)
            ay = pred["y"] + (m["vy"] if active else 0)
            if m.get("grab"):
                if me["y"] <= 0 and abs(me["x"] - pred["x"]) <= m["grab"] + 1:
                    return "throw"
            elif boxes_hit(ax, ay, pred["face"], m, me):
                return m["kind"]
    if proj_eta(me, projs) == 0:
        return "proj"
    return None


def jump_clears(me, projs, kind, toward):
    """起跳后，波经过身体时脚底是否高于波。返回 (clears, land_x)。"""
    stt = STATS[me["char"]]
    vx = {"u": 0.0, "j": stt["jx"] * toward, "y": -stt["jx"] * toward}[kind]
    x, y, vy = me["x"], 0.0, 0.0
    # 复制弹丸
    ps = []
    for p in projs:
        if p.get("mine"):
            continue
        ps.append([p["x"], p["vx"], p["w"], p["hy"], p.get("delay", 0)])
    if not ps:
        return False, x
    cleared = True
    overlapped = False
    for t in range(42):
        if t < 3:
            pass
        else:
            if t == 3:
                vy = stt["jv"]
            x += vx
            vy -= GRAV
            y += vy
            if y <= 0 and t > 4:
                return (cleared and overlapped), x
        for p in ps:
            if t >= p[4]:
                p[0] += p[1]
            if t >= p[4] and abs(p[0] - x) < p[2] / 2 + 11:
                overlapped = True
                hy0, hy1 = p[3]
                # 受击框从脚底到脚底+56
                if y < hy1 and y + 56 > hy0:
                    return False, x
    return False, x


# ---------- 决策 ----------

def ground(me, pred, projs, state):
    char = me["char"]
    d = dist(me, pred["x"])
    oc = pred["char"]
    meter = me["meter"]
    timer = state.get("timer_frames", 9999)
    my_r = me["hp"] / max(1, me["max_hp"])
    op_r = pred["hp"] / max(1, STATS[oc]["hp"])
    ahead = my_r > op_r + 0.04
    behind = my_r + 0.06 < op_r

    # 1. 这一帧的打击
    imm = immediate(me, pred, projs)
    if imm == "throw":
        return "e" if _rng.random() < 0.7 else "u"
    if imm in ("low", "mid"):
        return "g"
    if imm == "high":
        return "b"
    if imm == "proj":
        return "g"

    # 2. 飞行道具
    eta = proj_eta(me, projs)
    if eta is not None:
        ans = deal_proj(me, pred, projs, eta, d)
        if ans:
            return ans

    # 3. 对空
    if pred["st"] in ("air", "prejump") or pred["y"] > 6:
        aa = antiair(me, pred, d)
        if aa:
            return aa

    # 4. 他们在出波的起手里，且我够得着：打断
    if pred["st"] == "attack" and MOVES.get(oc, {}).get(pred.get("mv") or "", {}).get("proj"):
        inter = interrupt(me, pred, d)
        if inter:
            return inter

    # 4.8 倒地：走近等起身，卡投或脚，别提前空招
    if pred["st"] in ("knock", "wake") and pred["y"] <= 1:
        inv = (max(0, pred.get("stun") or 0) + 10) if pred["st"] == "knock" else max(0, 10 - pred.get("mf", 0))
        if d > 42:
            return "f"
        if inv > 4:
            return "n"
        if d <= 36:
            return "t" if _rng.random() < 0.55 else "k"
        return "k"

    # 5. 锁定惩罚 / 起身
    if pred["lock"] >= 3 and pred["st"] not in ("air", "prejump"):
        pun = punish(me, pred, projs, d)
        if pun:
            return pun

    # 6. 时间将尽
    if timer < 80 and ahead and d > throw_range(pred) + 10:
        return "g" if d < 140 else "b"
    if timer < 80 and behind:
        if meter >= 100 and d < 130:
            return "x"
        if d > 55:
            return "r"
        return "t" if d < throw_range_self(char) else "k"

    # 6.5 铁山：永远别站在指令投距离里
    if oc == "tie" and pred["y"] <= 0:
        tr = 76 if pred["meter"] >= 100 else 66
        if pred["st"] == "dash":
            return "e"
        if d < tr and pred["lock"] < 5:
            if meter >= 100 and 40 <= d:
                return "x"
            return "e"
        if meter >= 100 and d <= 115 and pred["lock"] < 8 and pred["st"] not in ("knock", "wake", "thrown"):
            if behind or pred["hp"] < 500 or _rng.random() < 0.55:
                return "x"
        if tr + 2 <= d <= 80 and pred["lock"] < 4:
            return "k" if _rng.random() < 0.62 else "z"
        if 82 <= d <= 118 and pred["lock"] < 4 and _rng.random() < 0.4:
            return "z"

    # 6.6 有气就用超必杀。起手 5，对手反应不及；防住也会破防。
    if meter >= 100 and pred["y"] <= 0 and pred["lock"] < 6 and pred["st"] not in ("knock", "wake", "thrown", "air"):
        if 32 <= d <= 108 and (behind or pred["hp"] < me["hp"] + 80 or _rng.random() < 0.42):
            return "x"

    # 7. 贴身
    tr = throw_range(pred)
    if d <= tr + 4 and pred["y"] <= 0 and pred["lock"] < 3:
        return close_mix(me, pred, d)

    # 起身后撤，躲过肉搏
    if _mem.get("prev") in ("wake", "knock") and d < 90:
        _mem["prev"] = me["st"]
        return "e"
    _mem["prev"] = me["st"]

    # 7.5 贴墙：没波就往外冲，有波已经在上面防了
    if _walled(me, pred) and (eta is None or eta > 20):
        if pred["lock"] >= 6 or d > 70:
            return "r"
        if d <= reach(MOVES[char]["k"]) and pred["lock"] < 4:
            return "k"
        return "f"

    # 7.8 对手贴墙：超必杀和投都更难逃
    if pred["y"] <= 0 and (pred["x"] < WALL + 42 or pred["x"] > STAGE - WALL - 42):
        if meter >= 100 and 28 <= d <= 120 and pred["st"] not in ("knock", "wake", "air"):
            return "x"
        if d <= 36 and pred["lock"] < 4:
            return "t" if _rng.random() < 0.6 else "k"

    # 8. 中距离
    return neutral(me, pred, projs, d, meter, ahead, behind)


def _walled(me, pred):
    """后撤会不会贴墙。"""
    if pred["x"] > me["x"]:
        return me["x"] < WALL + 48
    return me["x"] > STAGE - WALL - 48


def deal_proj(me, pred, projs, eta, d):
    toward = 1 if pred["x"] > me["x"] else -1
    # 跳得过就前跳穿过去（对方对空够不着时更安全）
    if eta >= 3:
        ok, land = jump_clears(me, projs, "j", toward)
        if ok:
            # 落地离对手还远，或者对手正在出招收不了对空
            if d > 110 or pred["lock"] >= 6 or pred["st"] in ("attack", "throw", "dash"):
                return "j"
        ok, land = jump_clears(me, projs, "u", toward)
        if ok and eta <= 16:
            return "u"
    if eta <= 4:
        return "g"
    if eta <= 12:
        return "g"
    # 波还远：别迎着走，等跳的时机。贴墙就先防着。
    return "g" if _walled(me, pred) else None


def interrupt(me, pred, d):
    """对手火球还在起手，用够得着的快招打断。"""
    m = MOVES[pred["char"]][pred["mv"]]
    frames_to_spawn = (m["s"] + 1) - pred["mf"]
    char = me["char"]
    # 选起手 < frames_to_spawn 且够得着的最高伤
    best, score = None, -1
    for mv, mm in MOVES[char].items():
        if mv == "air" or mm["proj"] or mm["grab"]:
            continue
        if mm["cost"] > me["meter"]:
            continue
        if mm["s"] >= frames_to_spawn:
            continue
        if d > reach(mm) + 4:
            continue
        sc = mm["dmg"] + (50 if mm["kd"] else 0)
        if mm["hits"]:
            sc = mm["dmg"] * len(mm["hits"]) * 0.7
        if sc > score:
            best, score = mv, sc
    return best


def punish(me, pred, projs, d):
    char = me["char"]
    ready = pred["lock"]  # 这么多帧后他们能动（含倒地起身）
    # 倒地/起身期间无敌，攻击要卡在无敌结束
    inv = 0
    if pred["st"] == "knock":
        inv = max(0, pred["stun"]) + 10
    elif pred["st"] == "wake":
        inv = max(0, 10 - pred["mf"])
    elif pred["st"] == "thrown":
        inv = max(0, 20 - pred["mf"]) + 40
    # 窗口：起手 >= inv（别打在无敌上），起手 <= ready（他们还不能防）
    # ready 通常 >= inv。若 inv==ready（起身最后），startup==ready 仍能打中。
    best, score = None, -1
    for mv, mm in MOVES[char].items():
        if mv == "air":
            continue
        if mm["cost"] > me["meter"]:
            continue
        if mm["proj"] and any(p.get("mine") for p in projs):
            continue
        if mm["grab"] and pred["st"] in ("hitstun", "blockstun", "knock", "wake", "thrown", "air"):
            continue
        if mm["s"] > ready or mm["s"] < inv:
            continue
        if d > reach(mm) + 6:
            continue
        sc = mm["dmg"] + (70 if mm["kd"] else 0) + (30 if mm["cost"] else 0)
        if mm["hits"]:
            sc = mm["dmg"] * len(mm["hits"]) * 0.72 + 40
        if mm["grab"]:
            sc += 20
        if sc > score:
            best, score = mv, sc
    if best:
        if MOVES[char][best]["cancel"]:
            _mem["pending"] = best
        return best
    # 够不着：若锁定长且没有波挡路，冲进去
    eta = proj_eta(me, projs)
    if eta is not None and eta < 18:
        return None
    if ready >= 8 and d > 36:
        return "r" if d > 55 else "f"
    if inv > 4 and d > 40:
        return "f"
    return None


def antiair(me, pred, d):
    char = me["char"]
    if pred["st"] == "prejump" and d < 60:
        return "a"
    if pred["st"] != "air" and pred["y"] <= 6:
        return None
    # 落点
    x, y, vx, vy = pred["x"], pred["y"], pred.get("vx", 0), pred.get("vy", 0)
    for _ in range(30):
        x += vx
        vy -= GRAV
        y += vy
        if y <= 0:
            break
    land = x
    aa = reach(MOVES[char]["a"])
    if d <= aa + 14 and pred["y"] < 115:
        return "a"
    if abs(land - me["x"]) < 36 and d < 80:
        return "a" if d < aa + 10 else "b"
    # 他们在空中但还远：别跳，等或后退
    if d < 120:
        return "b"
    return None


def close_mix(me, pred, d):
    char = me["char"]
    n = max(1, _mem["n"])
    blocky = _mem["block"] / n
    throwy = _mem["throw"] / n
    jumpy = _mem["jump"] / n
    if char == "tie":
        if me["meter"] >= 100 and d <= 74 and _rng.random() < 0.55:
            return "x"
        if d <= 62 and _rng.random() < 0.7:
            return "z"
        return "h" if _rng.random() < 0.4 else "e"
    r = _rng.random()
    # 爱防就投，爱投就后撤，爱跳就对地等（他们落地）
    if r < 0.28 + 0.4 * blocky - 0.15 * jumpy:
        if char == "tie" and me["meter"] >= 100:
            return "x"
        return "z" if char == "tie" and d <= 62 else "t"
    if r < 0.62 + 0.25 * throwy:
        return "e"
    if d <= reach(MOVES[char]["k"]) and _rng.random() < 0.5:
        return "s" if _rng.random() < 0.3 else "k"
    return "g"


def throw_range_self(char):
    return MOVES[char]["t"]["grab"]


def neutral(me, pred, projs, d, meter, ahead, behind):
    char = me["char"]
    oc = pred["char"]
    eta = proj_eta(me, projs)
    moves = MOVES[char]
    tr = throw_range(pred)

    # 有波在飞且会打中：别往前
    if eta is not None and eta < 16:
        return "g"

    # 理想距离
    if oc == "tie":
        ideal = 86 if pred["meter"] >= 100 else 72
    elif oc == "yan":
        ideal = 66
    elif oc in ("lie", "rei"):
        # 站在能打断火球的距离
        ideal = 64
    else:
        ideal = 70

    # 超必杀：有气、距离合适、对手在地上可被打或正在走
    if meter >= 100 and pred["y"] <= 0 and pred["lock"] < 4:
        xreach = reach(moves["x"])
        # 飞燕超必杀会前进，实际更远
        if char == "yan" and 36 <= d <= 120 and (behind or _rng.random() < 0.16):
            return "x"
        if char == "lie" and 30 <= d <= 100 and (behind or _rng.random() < 0.2):
            return "x"
        if char == "rei" and d >= 80 and not any(p.get("mine") for p in projs):
            if _rng.random() < 0.6 or behind:
                return "x"
        if char == "tie" and d <= 76 and _rng.random() < 0.35:
            return "x"

    # 放波
    if moves["z"]["proj"] and not any(p.get("mine") for p in projs):
        if d >= 100 and pred["y"] <= 0 and pred["st"] not in ("air", "prejump"):
            if _rng.random() < 0.8:
                return "z"

    # 飞燕中距离脚
    if char == "yan" and pred["y"] <= 0 and pred["lock"] < 3:
        kr = reach(moves["k"])
        if tr + 6 <= d <= kr - 1:
            # 护卫低就戳破防；否则有节奏地戳
            if pred["guard"] < 60 or _rng.random() < 0.48:
                return "k"
        # 飞燕后撤能躲必杀再反打，不对他空放
        if oc != "yan" and 78 <= d <= 112 and d > tr + 8 and _rng.random() < 0.28:
            return "z"

    if char == "tie":
        if d <= 64:
            return "z" if _rng.random() < 0.55 else "t"
        if d > ideal:
            return "r" if d > ideal + 30 else "f"
        return "f"

    if char == "rei" and tr + 10 <= d <= reach(moves["k"]) - 4 and _rng.random() < 0.4:
        return "k"
    if char == "lie" and tr + 8 <= d <= reach(moves["k"]) - 4 and _rng.random() < 0.36:
        return "k"

    # 走位
    if d > ideal + 18:
        zoner = oc in ("lie", "rei") or MOVES.get(oc, {}).get("z", {}).get("proj")
        spawning = pred["st"] == "attack" and MOVES.get(oc, {}).get(pred.get("mv") or "", {}).get("proj")
        if eta is None and not spawning and d > ideal + 16 and (zoner or _rng.random() < 0.6):
            return "r"
        if eta is None and not spawning:
            return "f"
        return "g"
    if d < ideal - 10:
        if d < tr + 8 and not _walled(me, pred):
            return "e" if _rng.random() < 0.45 else "b"
        return "b"
    # 理想距：蹲防等出招（他们出招我们下帧能看到锁定并惩罚），偶尔自己戳
    r = _rng.random()
    if r < 0.4:
        return "g"
    if r < 0.55:
        return "k" if d <= reach(moves["k"]) else "n"
    if r < 0.7:
        return "b"
    return "n"


def _cancel(me, pred):
    m = MOVES[me["char"]].get(me.get("mv") or "")
    if not m or not m["cancel"]:
        return None
    if me.get("mf", 99) > m["s"] + m["a"] + 4:
        _mem["pending"] = None
        return None
    d = dist(me, pred["x"])
    if me["meter"] >= 100 and d <= reach(MOVES[me["char"]]["x"]) + 30:
        _mem["pending"] = None
        return "x"
    zm = MOVES[me["char"]]["z"]
    if not zm["proj"] and d <= reach(zm) + 10:
        _mem["pending"] = None
        return "z"
    return None
