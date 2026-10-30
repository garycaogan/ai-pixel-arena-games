"""像素拳斗 - 铁山指令投压制。

核心思路：
- 对手看到的是 6 帧前的我们，投技起手 2/5 帧，根本无法反应，且投防不住。
- 拉近到 62 以内就 z 指令投（430 伤害），36 以内用 t（2 帧起手，拼赢一切轻拳）。
- 对手出招被看见时：恢复期就投惩罚；起手快命中时用霸体重拳 h 硬吃反打；对方是投技就跳。
- 对手倒地/起身：压到投距，起身瞬间投（起身跳是唯一解，多数程序不会）。
- 气满 100 时，对处于冲刺/落地/收招等不能跳的状态的对手用 x（640 伤害投）。
- 对方跳起用对空 a（无敌帧+击倒）；飞行道具跳过去或挡一下；超时领先就拖。
"""
import random

_rng = random.Random(987654321)

_GROUND = ("stand", "walk", "crouch")

# 对手招式简表: mv -> (起手, 判定, 类型, 最大横向范围)
OPPM = {
    "lie": {"p": (3, 2, "mid", 40), "h": (7, 3, "mid", 54), "k": (6, 3, "mid", 62),
            "s": (7, 3, "low", 60), "t": (2, 1, "throw", 38), "z": (12, 1, "proj", 0),
            "a": (4, 8, "mid", 34), "x": (6, 15, "mid", 50)},
    "tie": {"p": (4, 2, "mid", 42), "h": (9, 4, "mid", 58), "k": (7, 3, "mid", 64),
            "s": (8, 3, "low", 60), "t": (2, 1, "throw", 40), "z": (5, 2, "throw", 62),
            "a": (5, 6, "mid", 32), "x": (3, 3, "throw", 74)},
    "yan": {"p": (3, 2, "mid", 38), "h": (6, 3, "mid", 48), "k": (5, 3, "mid", 64),
            "s": (6, 3, "low", 62), "t": (2, 1, "throw", 36), "z": (6, 9, "mid", 44),
            "a": (3, 7, "mid", 32), "x": (5, 18, "mid", 48)},
    "rei": {"p": (3, 2, "mid", 46), "h": (9, 3, "mid", 72), "k": (7, 3, "mid", 80),
            "s": (8, 3, "low", 70), "t": (2, 1, "throw", 38), "z": (14, 1, "proj", 0),
            "a": (6, 8, "mid", 52), "x": (10, 1, "beam", 0)},
}

G = {"frz": 0, "woke": 0, "last": "n", "nr": 0}


def decide(state):
    if state.get("phase") == "select":
        return "tie"
    if state.get("phase") != "fight":
        return "n"

    me, opp = state["me"], state["opp"]
    st, ost = me["st"], opp["st"]

    frz = state.get("freeze") or 0
    if frz:
        G["frz"] = 1
        return "n"

    W, SW = state["wall"], state["stage_w"]
    # 预测对手当前位置（信息晚 6 帧）
    ox = opp["x"]
    if ost == "dash":
        ox += opp["face"] * 27.0
    elif ost == "backdash":
        ox -= opp["face"] * 20.0
    else:
        ox += 6.0 * opp["vx"]
    ox = max(W, min(SW - W, ox))
    d = abs(ox - me["x"])

    # ---------- 非自由状态 ----------
    if st == "hitstun":
        if opp["char"] == "tie" and d <= 72 and ost not in ("air", "prejump"):
            return "u"  # 铁山贴脸大概率在蹲指令投，硬直一结束就跳
        return "n"
    if st == "blockstun":
        return "b" if (ost == "air" or opp.get("mv") == "air") else "g"
    if st == "wake":
        G["woke"] = 1
        return "n"
    if st == "air":
        if me.get("mv") is None and d < 64 and 0 < me["y"] <= 58:
            return "h"  # 落地前跳攻
        return "n"
    if st not in _GROUND:
        return "n"

    # ---------- 超必杀定格刚结束：应对对手超必杀 ----------
    if G["frz"]:
        G["frz"] = 0
        oc = opp["char"]
        if oc == "tie" and d < 95:
            return "u"   # 起跳帧不吃投
        if oc in ("lie", "yan") and d < 115:
            return "a"   # 对空无敌帧换掉对面超杀第一段
        if oc == "rei":
            return "e"   # 光束躲不掉，赌后撤无敌帧
    G["frz"] = 0

    # ---------- 计时领先就拖 ----------
    if state["timer_frames"] < 270 and opp["char"] != "tie":
        if me["hp"] / me["max_hp"] > opp["hp"] / opp["max_hp"] + 0.12:
            if ost == "air" and d < 70:
                return "a"
            if d < 70:
                return "g"
            if d < 160:
                return "b"
            return "n"

    # ---------- 对手在投我们：同帧拆投 ----------
    if ost == "throw" and d <= 40:
        return "t"

    # ---------- 对手在空中 ----------
    if ost == "air":
        if d < 68 and 0 < opp["y"] <= 58:
            return "a"   # 对空
        if d < 55:
            return "b"   # 站防跳攻
        if d > 140:
            return "r"
        return "f"
    if ost == "prejump":
        if d < 34:
            return "a"
        return "b" if d < 70 else "f"

    # ---------- 对方飞行道具 ----------
    for p in state["projectiles"]:
        if p["mine"]:
            continue
        px = p["x"] + 6.0 * p["vx"]
        pd = px - me["x"]
        if pd * p["vx"] < 0:  # 朝我们飞
            ad = abs(pd)
            if ad < 48:
                return "g"
            if ad < 130 and d > 60:
                return "j"   # 前跳越过，顺便压进
    # 对手正在搓飞行道具（起手可见）：跳过去压
    if ost == "attack" and opp["mv"] in ("z", "x"):
        info = OPPM.get(opp["char"], {}).get(opp["mv"])
        if info and info[2] in ("proj", "beam") and d > 80 and d < 220:
            return "j"

    # ---------- 对手倒地 ----------
    if ost == "knock":
        if d > 130:
            return "r"
        if d > 38:
            return "f"
        return "n"
    # ---------- 对手起身：起身瞬间投 ----------
    if ost == "wake":
        if opp["mf"] + 6 >= 7:
            if d <= 58 and _rng.random() < 0.55:
                return "u"   # 起身跳：抓起身无敌结束瞬间
        if d > 38:
            return "f"
        return "n"
    # ---------- 对手硬直（不能投，贴近等起身） ----------
    if ost == "hitstun":
        rem = opp["stun"] - 6
        if rem <= 0:
            if d <= 58 and _rng.random() < 0.45:
                return "u"   # 落地时刻在硬直结束前后，空跳攻击接落地投
            if d > 34:
                return "f"
        else:
            if d > 36:
                return "f"
        return "n"

    # ---------- 对手出招中 ----------
    if ost == "attack" and opp.get("inv"):
        return "g" if d < 60 else ("b" if d < 100 else "n")
    if ost == "attack":
        info = OPPM.get(opp["char"], {}).get(opp["mv"])
        if info:
            s, a, kind, reach = info
            real_mf = opp["mf"] + 6
            act_mf = real_mf - s
            rec = real_mf > s + a
            if kind == "throw":
                if rec:  # 投空了，惩罚
                    if me["meter"] >= 100 and d <= 68:
                        return "x"
                    if d <= 34:
                        return "t"
                    if d <= 56:
                        return "z"
                    return "r" if d > 140 else "f"
                if opp["mf"] + 6 <= 3 and d <= reach:
                    return "t"  # 同帧对投拆投
                if d <= reach + 12:
                    return "u"  # 起跳帧躲投
                return "f" if d < 120 else "r"
            if kind in ("proj", "beam"):
                return "f" if d < 130 else "r"
            # 打击技
            if rec:  # 收招惩罚
                if me["meter"] >= 100 and d <= 68:
                    return "x"
                if d <= 34:
                    return "t"
                if d <= 56:
                    return "z"
                return "r" if d > 140 else "f"
            if opp["mv"] == "a" and act_mf >= 2:
                return "g" if d < 70 else ("b" if d < 100 else "f")  # 对空判定中别送
            if opp["mv"] == "x":  # 打击系超杀进行中
                if d < 100:
                    return "a"
                return "e"
            tta = s - real_mf + 1  # 还有几帧到判定
            if tta <= 2 and d <= reach + 14:
                if d <= 52:
                    return "h"  # 霸体硬吃反打
                return "g"
            if d <= 34 and tta >= 3:
                return "t"
            if d <= 56 and tta >= 6:
                return "z"
            if d <= reach + 14:
                return "g"
            return "r" if d > 140 else "f"
        return "f" if d < 130 else "r"

    # ---------- 对手后撤步（无敌） ----------
    if ost == "backdash":
        return "f" if d < 150 else "r"

    # ---------- 我们刚起身：防压起身 ----------
    if G["woke"] and d < 75:
        G["woke"] = 0
        return "u" if _rng.random() < 0.55 else "g"
    G["woke"] = 0

    # ---------- 对手处于不能跳的状态：超必投 ----------
    if me["meter"] >= 100 and d <= 70 and ost in ("dash", "land"):
        return "x"

    # 连投三次没命中就换拳脚节奏
    if ost in ("stand", "walk", "crouch"):
        if G["last"] in ("t", "z") and ost in ("stand", "walk", "crouch"):
            if opp["char"] != "tie":
                G["nr"] += 1
        else:
            G["nr"] = 0
        if G["nr"] >= 3 and d <= 60:
            G["nr"] = 0
            return "s" if _rng.random() < 0.5 else "h"

    # ---------- 中立项：投或逼近 ----------
    if ost in ("stand", "walk", "crouch", "dash", "land"):
        r0 = _rng.random()
        if d <= 34:
            if r0 < 0.55:
                G["last"] = "t"
                return "t"
            if r0 < 0.75:
                G["last"] = "s"
                return "s"
            if r0 < 0.92:
                G["last"] = "h"
                return "h"
            G["last"] = "e"
            return "e"
        if d <= 56:
            if r0 < 0.48:
                G["last"] = "z"
                return "z"
            if r0 < 0.68:
                G["last"] = "h"
                return "h"
            if r0 < 0.85:
                G["last"] = "s"
                return "s"
            if r0 < 0.95:
                G["last"] = "f"
                return "f"
            G["last"] = "e"
            return "e"
        if d <= 95:
            return "f" if r0 < 0.8 else "r"
        return "r"

    return "f"
