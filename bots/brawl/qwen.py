"""像素拳斗 bot：延迟补偿 + 帧数据驱动的反应式格斗 AI。"""
import random

GRAV = 0.9
DELAY = 6
WALL = 26.0
STAGE_W = 384.0
PICK = "tie"
CHARS = {
  'lie': dict(hp=980, walk=2.2, back=1.7, dash=(9,5.0), backdash=(12,4.0,5),
      vy=11.0, jx=3.2, sh=72, ch=46,
      moves={
        'p': dict(s=3, a=2, r=6, dmg=60, hs=7, bs=8, kind='mid', push=8, cancel=True, reach=(8, 40), hy=(40, 62)),
        'h': dict(s=7, a=3, r=14, dmg=160, hs=18, bs=10, kind='mid', push=9, cancel=True, reach=(10, 54), hy=(46, 68)),
        'k': dict(s=6, a=3, r=14, dmg=120, hs=15, bs=9, kind='mid', push=9, reach=(12, 62), hy=(18, 40)),
        's': dict(s=7, a=3, r=18, dmg=110, hs=0, bs=12, kind='low', push=7, kd=True, crouch=True, reach=(10, 60), hy=(0, 12)),
        'air': dict(s=4, a=10, r=0, dmg=130, hs=16, bs=12, kind='high', push=6, reach=(0, 40), hy=(-14, 26)),
        't': dict(s=2, a=1, r=20, dmg=240, throw=38, throw_arc=(26, 46)),
        'z': dict(s=12, a=1, r=24, proj=dict(v=5.0,dmg=116,hs=18,bs=14,chip=16,hy=(38, 56),w=12,look='fire',push=8)),
        'a': dict(s=4, a=8, r=26, dmg=220, hs=0, bs=16, kind='mid', push=6, kd=True, inv=(1, 6), vx=1.2, vy=7.0, reach=(2, 34), hy=(28, 112)),
        'x': dict(s=6, a=15, r=30, dmg=124, hs=10, bs=8, kind='mid', push=3, chip=12, cost=100, kd_last=True, inv=(1, 9), vx=6.0, hits=(1, 4, 7, 10, 13), reach=(4, 50), hy=(10, 80)),
      }),
  'tie': dict(hp=1250, walk=1.9, back=1.4, dash=(8,4.6), backdash=(11,3.4,4),
      vy=10.2, jx=2.6, sh=78, ch=50,
      moves={
        'p': dict(s=4, a=2, r=7, dmg=70, hs=7, bs=9, kind='mid', push=8, cancel=True, reach=(8, 42), hy=(40, 64)),
        'h': dict(s=9, a=4, r=17, dmg=210, hs=19, bs=14, kind='mid', push=11, cancel=True, armor=(1, 8), reach=(10, 58), hy=(46, 70)),
        'k': dict(s=7, a=3, r=14, dmg=140, hs=15, bs=10, kind='mid', push=9, reach=(12, 64), hy=(16, 40)),
        's': dict(s=8, a=3, r=20, dmg=120, hs=0, bs=12, kind='low', push=7, kd=True, crouch=True, reach=(10, 60), hy=(0, 12)),
        'air': dict(s=5, a=9, r=0, dmg=160, hs=17, bs=12, kind='high', push=6, reach=(0, 40), hy=(-14, 26)),
        't': dict(s=2, a=1, r=20, dmg=260, throw=40, throw_arc=(30, -44)),
        'z': dict(s=5, a=2, r=30, dmg=430, throw=62, cmd=True, throw_arc=(64, -40)),
        'a': dict(s=5, a=6, r=34, dmg=210, hs=0, bs=16, kind='mid', push=6, kd=True, inv=(1, 5), vy=3.0, reach=(2, 32), hy=(40, 116)),
        'x': dict(s=3, a=3, r=48, dmg=640, cost=100, inv=(1, 4), throw=74, cmd=True, throw_arc=(90, 20)),
      }),
  'yan': dict(hp=890, walk=2.7, back=2.1, dash=(8,6.2), backdash=(11,4.6,6),
      vy=11.6, jx=3.8, sh=68, ch=42,
      moves={
        'p': dict(s=3, a=2, r=5, dmg=52, hs=7, bs=7, kind='mid', push=8, cancel=True, reach=(8, 38), hy=(40, 60)),
        'h': dict(s=6, a=3, r=13, dmg=124, hs=16, bs=9, kind='mid', push=8, cancel=True, reach=(10, 48), hy=(42, 64)),
        'k': dict(s=5, a=3, r=14, dmg=116, hs=15, bs=10, kind='mid', push=9, reach=(12, 64), hy=(30, 62)),
        's': dict(s=6, a=3, r=15, dmg=100, hs=0, bs=12, kind='low', push=7, kd=True, crouch=True, reach=(10, 62), hy=(0, 12)),
        'air': dict(s=3, a=10, r=0, dmg=116, hs=16, bs=12, kind='high', push=6, reach=(0, 42), hy=(-14, 26)),
        't': dict(s=2, a=1, r=20, dmg=220, throw=36, throw_arc=(24, 50)),
        'z': dict(s=6, a=9, r=18, dmg=170, hs=0, bs=12, kind='mid', push=7, kd=True, vx=5.5, reach=(4, 44), hy=(30, 70)),
        'a': dict(s=3, a=7, r=24, dmg=190, hs=0, bs=16, kind='mid', push=6, kd=True, inv=(1, 5), vx=-0.6, vy=6.0, reach=(0, 32), hy=(30, 110)),
        'x': dict(s=5, a=18, r=28, dmg=104, hs=10, bs=8, kind='mid', push=3, chip=12, cost=100, kd_last=True, inv=(1, 8), vx=7.0, hits=(1, 4, 7, 10, 13, 16), reach=(4, 48), hy=(20, 72)),
      }),
  'rei': dict(hp=990, walk=1.9, back=1.7, dash=(9,4.4), backdash=(12,4.2,5),
      vy=10.6, jx=3.0, sh=74, ch=46,
      moves={
        'p': dict(s=3, a=2, r=7, dmg=60, hs=7, bs=9, kind='mid', push=8, cancel=True, reach=(8, 46), hy=(42, 66)),
        'h': dict(s=9, a=3, r=16, dmg=160, hs=18, bs=12, kind='mid', push=10, cancel=True, reach=(10, 72), hy=(46, 70)),
        'k': dict(s=7, a=3, r=15, dmg=124, hs=15, bs=11, kind='mid', push=10, reach=(12, 80), hy=(22, 46)),
        's': dict(s=8, a=3, r=19, dmg=100, hs=0, bs=12, kind='low', push=7, kd=True, crouch=True, reach=(10, 70), hy=(0, 12)),
        'air': dict(s=5, a=8, r=0, dmg=120, hs=16, bs=12, kind='high', push=6, reach=(0, 44), hy=(-14, 26)),
        't': dict(s=2, a=1, r=20, dmg=230, throw=38, throw_arc=(26, 46)),
        'z': dict(s=14, a=1, r=22, proj=dict(v=3.6,dmg=128,hs=20,bs=15,chip=20,hy=(36, 58),w=16,look='bolt',push=9)),
        'a': dict(s=6, a=8, r=24, dmg=200, hs=0, bs=16, kind='mid', push=6, kd=True, inv=(1, 4), reach=(16, 52), hy=(40, 130)),
        'x': dict(s=10, a=1, r=34, cost=100, proj=dict(v=8.0,dmg=460,hs=0,bs=20,chip=80,hy=(10, 80),w=26,look='beam',push=12,kd=True)),
      }),
}

GROUND_OK = ("stand", "walk", "crouch")
NOT_THROWABLE = ("hitstun", "blockstun", "knock", "wake", "thrown", "throw", "ko", "air", "prejump")


def _mv(cd, key):
    return cd["moves"].get(key)


def _len(m):
    return m["s"] + m["a"] + m["r"]


def _ph(mf, m):
    if mf <= 0:
        return None
    if mf <= m["s"]:
        return "startup"
    if mf <= m["s"] + m["a"]:
        return "active"
    if mf <= _len(m):
        return "recovery"
    return None


def _hitk(m):
    if m.get("hits"):
        return list(m["hits"])
    return list(range(m["s"] + 1, m["s"] + m["a"] + 1))


def _scale(combo, sup=False):
    return max(0.7 if sup else 0.4, 1.0 - 0.15 * combo)


def _clip(x):
    return max(WALL, min(STAGE_W - WALL, x))


def _top(st, y, cd, mv=None):
    if st == "air":
        return y + 56.0
    if st == "crouch" or (mv == "s" and st == "attack"):
        return float(cd["ch"])
    return float(cd["sh"])


def _bot(st, y):
    return max(0.0, float(y))


def _hits(m, ox, my_x, bot, top, face):
    """对手中心 ox、我 my_x：横向纵向是否重叠（不含无敌）。"""
    rr = m.get("reach")
    if not rr:
        return False
    x0, x1 = sorted((my_x + face * rr[0], my_x + face * rr[1]))
    return x0 <= ox + 11.0 and ox - 11.0 <= x1 and m["hy"][0] <= top and bot <= m["hy"][1]


def _ox_at(on, m, hf):
    """对手招式进行到 hf 帧时对手中心 x（考虑 vx 前进）。"""
    x = on["x"]
    vx = m.get("vx") or 0.0
    if vx:
        n = sum(1 for f in _hitk(m) if f <= hf)
        x += on["face"] * vx * n
    return _clip(x)


class Brain:
    def __init__(self):
        self.rnd = random.Random(918273645)
        self.projs = []
        self.hist = []
        self.opp_true = None

    # ---------- 延迟补偿：把 6 帧前的对手状态推到当前 ----------
    def predict(self, o):
        p = dict(o)
        cd = CHARS[o["char"]]
        st = o["st"]
        n = DELAY
        if st in ("attack", "throw") and o["mv"]:
            m = _mv(cd, o["mv"])
            if not m:
                return p
            mf = o["mf"] + n
            vx = m.get("vx") or 0.0
            if vx:
                cnt = sum(1 for f in _hitk(m) if f <= mf)
                p["x"] = _clip(o["x"] + o["face"] * vx * cnt)
            if mf > _len(m):
                p.update(st=("crouch" if m.get("crouch") else "stand"), mv=None, mf=0, phase=None)
            else:
                p.update(mf=mf, phase=_ph(mf, m))
            return p
        if st == "air":
            y = o["y"] + o["vy"] * n - 0.5 * GRAV * n * n
            x = _clip(o["x"] + o["vx"] * n)
            if y <= 0:
                p.update(st="land", mf=n, y=0.0, vy=0.0, x=x, mv=None)
            else:
                p.update(st="air", y=y, vy=o["vy"] - GRAV * n, x=x)
            return p
        if st == "prejump":
            t = n - 3
            if t <= 0:
                p.update(stun=max(0, o["stun"] - n))
            else:
                y = cd["vy"] * t - 0.5 * GRAV * t * t
                x = _clip(o["x"] + o["vx"] * n)
                if y <= 0:
                    p.update(st="land", y=0.0, vy=0.0, x=x, mf=0)
                else:
                    p.update(st="air", y=y, vy=cd["vy"] - GRAV * t, x=x, mv=None, mf=0)
            return p
        if st == "land":
            t = o["mf"] + n
            p.update(st="stand" if t >= 3 else "land", mf=t, stun=0)
            return p
        if st in ("hitstun", "blockstun", "knock", "wake", "thrown", "dash", "backdash"):
            s2 = o["stun"] - n
            if s2 <= 0:
                if st == "knock":
                    p.update(st="wake", stun=10)
                elif st in ("thrown", "wake", "dash", "backdash"):
                    p.update(st="stand", stun=0)
                else:
                    p.update(st="stand", stun=0)
            else:
                p.update(stun=s2)
            return p
        if st == "ko":
            return p
        # stand / walk / crouch：按当前速度外推
        x = _clip(o["x"] + o.get("vx", 0.0) * n)
        p.update(x=x, stun=0)
        return p

    # ---------- 对手剩余不可动窗口 ----------
    def window(self, on, ocd):
        st = on["st"]
        if st in ("hitstun",):
            return on["stun"], False
        if st == "blockstun":
            return on["stun"], True
        if st in ("attack", "throw") and on["mv"]:
            m = ocd["moves"].get(on["mv"])
            if m:
                return max(0, _len(m) - on["mf"]), False
            return 0, False
        if st == "air":
            return max(0, int(on["y"] / 6.0) + 3), False
        if st == "prejump":
            return max(1, on["stun"]), False
        if st in ("knock", "wake", "land", "thrown", "dash", "backdash"):
            return max(1, on["stun"] if st not in ("land", "wake") else on["mf"] if st == "land" else 10 - on.get("mf", 0)), False
        return 0, True

    # ---------- 威胁列表 ----------
    def threats(self, on, ocd, me, mcd):
        out = []
        my_top = _top(me["st"], me["y"], mcd, me["mv"] if me["st"] == "attack" else None)
        my_bot = _bot(me["st"], me["y"])
        st = on["st"]
        if st in ("attack", "throw") and on["mv"]:
            m = ocd["moves"].get(on["mv"])
            if m:
                f_ = on["face"]
                for hf in _hitk(m):
                    dt = hf - on["mf"]
                    if dt < 1:
                        continue
                    if "throw" in m:
                        if abs(on["x"] - me["x"]) <= m["throw"] + 6:
                            out.append(dict(t=dt, kind="grab", dmg=m["dmg"], mv=on["mv"], lvl=None))
                        break
                    if m.get("proj"):
                        pp = m["proj"]
                        h0, h1 = pp["hy"]
                        if not (h0 <= my_top and my_bot <= h1):
                            continue
                        sx = on["x"] + f_ * 22.0
                        gap = (sx - me["x"]) * f_ - 11.0 - pp["w"] / 2.0
                        t = dt + (0 if gap <= 0 else int(gap // pp["v"]) + 1)
                        out.append(dict(t=max(1, t), kind="proj", lvl="mid", dmg=pp["dmg"],
                                        mv=on["mv"], chip=pp.get("chip", 0)))
                        break
                    ox = _ox_at(on, m, hf)
                    if _hits(m, ox, me["x"], my_bot, my_top, f_):
                        kd = bool(m.get("kd") or (m.get("kd_last") and hf == _hitk(m)[-1]))
                        out.append(dict(t=dt, kind="strike", lvl=m.get("kind"), dmg=m["dmg"],
                                        mv=on["mv"], chip=0, kd=kd))
                        break
        for p in self.projs:
            if p.get("mine"):
                continue
            vx = p.get("vx", 0.0)
            if not vx:
                continue
            w = p.get("w", 12)
            gap = (p["x"] - me["x"]) * (1 if vx > 0 else -1) - 11.0 - w / 2.0
            t = 1 if gap <= 0 else int(gap // abs(vx)) + 1
            dmg, chip = (460, 80) if p.get("look") == "beam" else (128, 20)
            out.append(dict(t=max(1, t), kind="proj", lvl="mid", dmg=dmg, mv="proj", chip=chip))
        return out

    def usable(self, me, mcd, key):
        m = mcd["moves"].get(key)
        if not m:
            return None
        c = m.get("cost", 0)
        if c and me["meter"] < c:
            return None
        if m.get("proj") and any(p.get("mine") for p in self.projs):
            return None
        return m

    # ---------- 主决策 ----------
    def decide(self, s):
        me = s["me"]
        o6 = s["opp"]
        self.projs = s.get("projectiles") or []
        mcd = CHARS[me["char"]]
        ocd = CHARS[o6["char"]]
        on = self.predict(o6)
        self.on = on
        d = abs(me["x"] - on["x"])
        score = s.get("score") or [0, 0]
        tf = s.get("timer_frames", 1350)
        my_r = me["hp"] / float(me["max_hp"])
        op_r = on["hp"] / float(on["max_hp"])
        my_combo = me.get("combo", 0) or 0

        can = me["st"] in GROUND_OK
        if not can:
            if me["st"] == "blockstun":
                th = self.threats(on, ocd, me, mcd)
                th.sort(key=lambda t: t["t"])
                return self.guard_input(on, ocd, th)
            if me["st"] == "attack" and me["mv"]:
                return self.cancel(me, mcd, on, ocd, d, my_combo)
            if me["st"] == "air":
                return self.air_attack(me, mcd, on)
            return "n"

        th = self.threats(on, ocd, me, mcd)
        th.sort(key=lambda t: t["t"])
        win, grabbable = self.window(on, ocd)
        if win >= 3:
            a = self.punish(me, mcd, on, ocd, d, win, grabbable, my_combo, me["guard"])
            if a:
                return a
        if th and th[0]["t"] <= 16:
            a = self.defend(me, mcd, on, ocd, d, th)
            if a:
                return a
        if on["st"] in ("air", "prejump") and on["y"] < 96 and d < 70:
            m = self.usable(me, mcd, "a")
            if m and d <= m["reach"][1] + 11:
                return "a"
        return self.neutral(me, mcd, on, ocd, d, tf, score, my_r, op_r, s)

    # ---------- 取消接招 ----------
    def cancel(self, me, mcd, on, ocd, d, my_combo):
        m = mcd["moves"].get(me["mv"])
        if not m or not m.get("cancel") or not me.get("contact"):
            return "n"
        if me["mf"] > m["s"] + m["a"] + 4:
            return "n"
        opp_block = (on["st"] == "blockstun")
        best, bestv = None, 0.0
        for key in ("z", "a", "x"):
            c = self.usable(me, mcd, key)
            if not c:
                continue
            sup = bool(c.get("cost"))
            if "throw" in c:
                if not opp_block:
                    continue
                v = c["dmg"] * _scale(my_combo, sup)
            else:
                tot = 0.0
                for i in range(min(3, len(_hitk(c)))):
                    tot += c["dmg"] * _scale(my_combo + i, sup)
                v = tot if not opp_block else tot * 0.1 + c.get("chip", 0)
                if c.get("proj"):
                    v *= 0.8
            if v > bestv:
                bestv, best = v, key
        return best or "n"

    # ---------- 空中攻击 ----------
    def air_attack(self, me, mcd, on):
        if me["mv"]:
            return "n"
        m = mcd["moves"].get("air")
        if not m:
            return "n"
        oc = CHARS[on["char"]]
        t_top = _top(on["st"], on["y"], oc, on["mv"] if on["st"] == "attack" else None)
        t_bot = _bot(on["st"], on["y"])
        if _hits(m, on["x"], me["x"], t_bot, t_top, me["face"]):
            return "k"
        if abs(on["x"] - me["x"]) < m["reach"][1] and me["y"] > 8:
            return "k"
        return "n"

    # ---------- 防法 ----------
    def guard_input(self, on, ocd, th):
        lvl = None
        for t in th:
            if t["t"] <= 3 and t["kind"] == "strike":
                lvl = t.get("lvl") or lvl
        if lvl == "low":
            return "g"
        if lvl == "high":
            return "b"
        if on["st"] in ("air", "prejump") or on["y"] > 0:
            return "b"
        # 未知来袭：默认蹲防（挡下段与中段，受击框更小）
        return "g"

    # ---------- 惩罚 ----------
    def punish(self, me, mcd, on, ocd, d, win, grabbable, my_combo, guard):
        best, bestv = None, 1.0
        leth = on["hp"] + 1
        for key in ("p", "h", "k", "s", "z", "a", "x", "t"):
            m = self.usable(me, mcd, key)
            if not m:
                continue
            sup = bool(m.get("cost"))
            if "throw" in m:
                if not grabbable or d > m["throw"]:
                    continue
                t_hit = m["s"] + 1
                if t_hit > win:
                    continue
                v = m["dmg"] * _scale(my_combo, sup)
                if m.get("cmd"):
                    v *= 1.15
                if v >= leth:
                    v *= 5
                if v > bestv:
                    bestv, best = v, key
                continue
            if not m.get("reach"):
                continue
            t_bot = _bot(on["st"], on["y"])
            t_top = _top(on["st"], on["y"], ocd, on["mv"] if on["st"] == "attack" else None)
            hf = None
            for f in _hitk(m):
                if _hits(m, on["x"], me["x"], t_bot, t_top, me["face"]):
                    hf = f
                    break
                if (m.get("vx") or 0) and f > m["s"] + m["a"]:
                    continue
            if hf is None or hf > win:
                continue
            tot = 0.0
            for i, f in enumerate(_hitk(m)):
                tot += m["dmg"] * _scale(my_combo + i, sup)
                if i >= 2:
                    break
            v = tot
            if m.get("kd") or m.get("kd_last"):
                v *= 1.1
            if tot >= leth:
                v *= 5
            v *= 1.0 - 0.006 * _len(m)
            if m.get("proj"):
                v *= 0.7
            if v > bestv:
                bestv, best = v, key
        return best

    # ---------- 防守 ----------
    def defend(self, me, mcd, on, ocd, d, th):
        f0 = th[0]
        t, kind = f0["t"], f0["kind"]
        bd_inv = mcd["backdash"][2]
        if kind == "grab":
            if t >= 5:
                return "u"
            if t <= bd_inv:
                return "e"
            if d <= mcd["moves"]["t"]["throw"]:
                return "t"
            return "e"
        # 反打断：我有更快的招
        if kind == "strike":
            for key in ("p", "k", "a", "s", "h", "z"):
                m = self.usable(me, mcd, key)
                if not m or not m.get("reach"):
                    continue
                inv = m.get("inv")
                if inv and inv[0] <= 1 and t <= inv[1]:
                    hf = _hitk(m)[0]
                    if hf < t and _hits(m, on["x"], me["x"], _bot(on["st"], on["y"]),
                                        _top(on["st"], on["y"], ocd, None), me["face"]):
                        return key
                if t >= 4 and key in ("p", "k") and me["st"] in GROUND_OK:
                    hf = _hitk(m)[0]
                    if hf < t and _hits(m, on["x"], me["x"], _bot(on["st"], on["y"]),
                                        _top(on["st"], on["y"], ocd, None), me["face"]):
                        return key
        # 超必杀反制
        xm = self.usable(me, mcd, "x")
        if xm and xm.get("inv") and me["meter"] >= 100 and kind in ("strike", "proj"):
            if xm["inv"][0] <= t <= xm["inv"][1] + 1 and d < 74:
                return "x"
        # 破防风险 -> 闪
        dmg = f0.get("dmg", 100)
        if me["guard"] - dmg * 0.45 <= 1:
            if t <= bd_inv:
                return "e"
            if t >= 5:
                return "u"
        return self.guard_input(on, ocd, th)

    # ---------- 中立 ----------
    def neutral(self, me, mcd, on, ocd, d, tf, score, my_r, op_r, s):
        reach = {}
        for key in ("p", "h", "k", "s", "a", "z"):
            m = self.usable(me, mcd, key)
            if m and m.get("reach"):
                reach[key] = m["reach"][1] + 11
        mx = max(reach.values()) if reach else 40
        aggro = 1.0
        if tf < 300:
            if my_r > op_r + 0.04:
                aggro = 0.2
            elif op_r > my_r + 0.04:
                aggro = 1.9
        if score[0] == score[1] - 1 and tf < 200 and my_r > op_r:
            aggro = 0.3
        # 对手倒地/起身：拉开或压起身
        if on["st"] in ("knock", "thrown", "land"):
            if d < 70:
                return "b"
            return "n"
        if on["st"] == "wake":
            if 40 < d < mx + 10:
                r = self.rnd.random()
                if r < 0.35:
                    return "s"
                if r < 0.5:
                    return "g"
                return "b"
            return "f" if d > 60 else "n"
        # 远程角色放波
        zm = self.usable(me, mcd, "z")
        if zm and zm.get("proj"):
            if d > 130 and self.rnd.random() < 0.5:
                return "z"
            if d > 90 and on["st"] in ("attack", "blockstun", "hitstun") and self.rnd.random() < 0.3:
                return "z"
        # 远距离
        if d > mx + 40:
            if self.rnd.random() < 0.45:
                return "r"
            return "f"
        if d > mx + 4:
            if aggro > 1.3 and self.rnd.random() < 0.55:
                return "r"
            if aggro < 0.5:
                return "b"
            return "f"
        # 攻击范围
        r = self.rnd.random()
        if r < 0.30 * aggro:
            best, bestv = None, 0.0
            for key, rng in reach.items():
                if d <= rng:
                    m = mcd["moves"][key]
                    v = m["dmg"] / float(_len(m))
                    if m.get("kd"):
                        v *= 1.4
                    if key == "s" and on["st"] == "blockstun":
                        v *= 0.2
                    if v > bestv:
                        bestv, best = v, key
            if best:
                return best
        if r < 0.42 * aggro:
            tm = self.usable(me, mcd, "z")
            if tm and tm.get("cmd") and d <= tm["throw"] and on["st"] in GROUND_OK + ("blockstun",):
                return "z"
            if d <= mcd["moves"]["t"]["throw"] and self.rnd.random() < 0.4:
                return "t"
        if r < 0.55:
            return "f" if d > mx * 0.8 else "g"
        return "g" if on["y"] <= 0 else "b"


BR = None


def decide(state):
    global BR
    ph = state.get("phase")
    if ph == "select":
        BR = Brain()
        return PICK
    if BR is None:
        BR = Brain()
    if ph != "fight" or state.get("freeze", 0) > 0:
        return "n"
    try:
        return BR.decide(state)
    except Exception:
        return "g"
