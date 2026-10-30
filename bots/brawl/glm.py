"""像素拳斗 bot — 铁山(tie)：指令投主导 + 打投择。

核心逻辑：反应延迟 6 帧 + 指令投起手 5 帧 → 对手看见时投已判定。
对手站地面且不在攻击/硬直 → 52 距离内 z（430伤害）几乎必中。
有气时 66 距离内超杀投 x（640伤害）。对手跳跃 → 对空 a / armor 重拳；
对手出招 → 防御住以后惩罚（扫腿/重拳）；对手倒地 → 算帧数用肉投压起身；
对手飞行道具 → 蹲防（chip 不致死）推进。避免在对手出招中出投。
"""

GROUND = ("stand", "walk", "crouch")
ATK_SA = {
    "lie": {"p": 5, "h": 10, "k": 9, "s": 10, "a": 12, "x": 21, "z": 13},
    "tie": {"p": 6, "h": 13, "k": 10, "s": 11, "a": 11, "x": 6, "z": 7},
    "yan": {"p": 5, "h": 9, "k": 8, "s": 9, "a": 10, "z": 15, "x": 23},
    "rei": {"p": 5, "h": 12, "k": 10, "s": 11, "a": 14, "x": 11, "z": 15},
}
M = {"lastatk": -99, "aggro": 1.0}


def decide(state):
    ph = state["phase"]
    if ph == "select":
        return "tie"
    if ph != "fight" or state.get("freeze"):
        return "n"
    me, opp = state["me"], state["opp"]
    turn = state["turn"]
    ost = opp["st"]

    if me["st"] == "air":
        if me["mv"] is None:
            dx = abs(opp["x"] - me["x"])
            if dx < 48 and me["y"] > 3:
                return "k"
        return "n"
    if me["st"] == "blockstun":
        return "g"
    if me["st"] not in GROUND:
        return "n"

    d = abs(opp["x"] + 6 * (opp.get("vx") or 0.0) - me["x"])
    meter = me["meter"]
    myhp = me["hp"]
    oground = ost in GROUND
    # 对手真实是否可能正在出招（快照是 6 帧前，出招多为 3-10 帧）
    risk_throw = (turn - M["lastatk"]) < 9

    if ost == "attack" and opp["mv"]:
        M["lastatk"] = turn
        M["aggro"] = min(2.0, M["aggro"] + 0.05)
        sa = ATK_SA.get(opp["char"], {}).get(opp["mv"], 12)
        rem = sa - opp["mf"] - 6
        if rem > 0:
            return "b" if opp["mv"] == "air" else "g"
        # 对手收招：投之（对手收招帧数不短）
        if opp["mv"] == "z" and opp["char"] == "tie":
            return "b"
        if d < 52:
            return "z" if meter >= 100 and d < 66 else "t"
        if d < 58:
            return "t"
        return "f"

    for p in state["projectiles"]:
        if not p["mine"]:
            rx = p["x"] + 6 * p["vx"]
            v = abs(p["vx"])
            ttc = abs(rx - me["x"]) / max(0.5, v)
            if ttc < 9:
                if p["look"] == "beam" and myhp <= 110:
                    return "j"
                return "g"

    if ost == "prejump":
        return "g" if d < 70 else "f"
    if ost == "air":
        oy = opp["y"]
        if d < 44 and 6 < oy < 66:
            return "a"
        if d < 50 and oy <= 30:
            return "h"
        if d < 62:
            return "b"
        return "f"
    if ost == "hitstun":
        if opp["stun"] > 8:
            if d < 50:
                return "h"
            if d < 64:
                return "k"
        return "f"
    if ost == "blockstun":
        if d < 50 and opp["stun"] > 5:
            return "s"
        return "f"
    if ost == "knock":
        est = opp["stun"] - 6 + 10
        if d > 62:
            return "f"
        if 3 <= est <= 5:
            return "z"
        if est > 6:
            return "f"
        return "g"
    if ost == "wake":
        rem = max(0, 10 - opp["mf"] - 6)
        if rem <= 1:
            if meter >= 100 and d < 66:
                return "x"
            if d < 56:
                return "z"
            return "f"
        if d < 56 and rem <= 3:
            return "s"
        return "f" if d > 48 else "g"
    if ost == "thrown":
        return "f"
    if ost == "dash":
        if d < 62:
            return "g"
        return "f"

    if oground:
        aggressive = M["aggro"] > 1.3 or not risk_throw
        if meter >= 100 and d < 66:
            return "x"
        if d < 52 and aggressive:
            return "z"
        if d < 38 and not aggressive:
            return "t"
        # 对手爱出招：蹲防引诱，逼近
        if d < 88 and M["aggro"] > 1.3:
            return "g"
        return "f"
    return "f"
