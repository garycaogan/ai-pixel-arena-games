"""像素拳斗 · 阿烈（lie）—— 抢先手的节奏型选手。

核心思路
--------
* 延迟是双向的：对手状态晚 7 帧才到我这里。起手 <= 6 帧的招（p/t/a/k）对手来不及防；
  起手 >= 7 帧的招（h/s/z）才来得及防。所以近身用快招抢节奏，中距用 h，远距用火球。
* 破防是最大收益：h 被防住扣 72 防御值，紧接一记 a 再扣 99，必定破防（42 帧白挨打）。
* 取消：p / h 打中或被防住后 4 帧内可取消成 a（220 伤害 + 击倒）。
* 超必杀 x：起手 6 帧、9 帧无敌、5 段，第一段对手来不及防；防住两段就破防。
* 自己的防御值见底时不要硬防：用后撤步 e 躲，或者直接抢招。
* 对手在硬直/倒地/起身/被投时不可被投；对手在收招时是白挨打窗口。
* 对手有飞行道具来袭时站防（所有飞行道具都是中段）。
"""

# ------------------------------------------------------------------ 招式表
def _m(s, a, r, r0, r1, hy0, hy1, kind, dmg, hs, bs, **kw):
    d = {'s': s, 'a': a, 'r': r, 'reach': (r0, r1), 'hy': (hy0, hy1), 'kind': kind,
         'dmg': dmg, 'hs': hs, 'bs': bs}
    d.update(kw)
    return d


T = {
    'lie': {
        'p': _m(3, 2, 6, 8, 40, 40, 62, 'm', 60, 7, 8, cancel=1),
        'h': _m(7, 3, 14, 10, 54, 46, 68, 'm', 160, 18, 10, cancel=1),
        'k': _m(6, 3, 14, 12, 62, 18, 40, 'm', 120, 15, 9),
        's': _m(7, 3, 18, 10, 60, 0, 12, 'l', 110, 0, 12, kd=1),
        't': _m(2, 1, 20, 0, 0, 0, 0, 'm', 240, 0, 0, grab=38),
        'z': _m(12, 1, 24, 0, 0, 38, 56, 'm', 116, 18, 14, proj=1),
        'a': _m(4, 8, 26, 2, 34, 28, 112, 'm', 220, 0, 16, kd=1, inv=6, vx=1.2, vy=7.0),
        'x': _m(6, 15, 30, 4, 50, 10, 80, 'm', 124, 10, 8, inv=9, vx=6.0, cost=100, multi=5),
    },
    'tie': {
        'p': _m(4, 2, 7, 8, 42, 40, 64, 'm', 70, 7, 9, cancel=1),
        'h': _m(9, 4, 17, 10, 58, 46, 70, 'm', 210, 19, 14, cancel=1, armor=1),
        'k': _m(7, 3, 14, 12, 64, 16, 40, 'm', 140, 15, 10),
        's': _m(8, 3, 20, 10, 60, 0, 12, 'l', 120, 0, 12, kd=1),
        't': _m(2, 1, 20, 0, 0, 0, 0, 'm', 260, 0, 0, grab=40),
        'z': _m(5, 2, 30, 0, 0, 0, 0, 'm', 430, 0, 0, grab=62),
        'a': _m(5, 6, 34, 2, 32, 40, 116, 'm', 210, 0, 16, kd=1, inv=5, vy=3.0),
        'x': _m(3, 3, 48, 0, 0, 0, 0, 'm', 640, 0, 0, grab=74, cost=100),
    },
    'yan': {
        'p': _m(3, 2, 5, 8, 38, 40, 60, 'm', 52, 7, 7, cancel=1),
        'h': _m(6, 3, 13, 10, 48, 42, 64, 'm', 124, 16, 9, cancel=1),
        'k': _m(5, 3, 14, 12, 64, 30, 62, 'm', 116, 15, 10),
        's': _m(6, 3, 15, 10, 62, 0, 12, 'l', 100, 0, 12, kd=1),
        't': _m(2, 1, 20, 0, 0, 0, 0, 'm', 220, 0, 0, grab=36),
        'z': _m(6, 9, 18, 4, 44, 30, 70, 'm', 170, 0, 12, kd=1, vx=5.5),
        'a': _m(3, 7, 24, 0, 32, 30, 110, 'm', 190, 0, 16, kd=1, inv=5, vy=6.0, vx=-0.6),
        'x': _m(5, 18, 28, 4, 48, 20, 72, 'm', 104, 10, 8, inv=8, vx=7.0, cost=100, multi=6),
    },
    'rei': {
        'p': _m(3, 2, 7, 8, 46, 42, 66, 'm', 60, 7, 9, cancel=1),
        'h': _m(9, 3, 16, 10, 72, 46, 70, 'm', 160, 18, 12, cancel=1),
        'k': _m(7, 3, 15, 12, 80, 22, 46, 'm', 124, 15, 11),
        's': _m(8, 3, 19, 10, 70, 0, 12, 'l', 100, 0, 12, kd=1),
        't': _m(2, 1, 20, 0, 0, 0, 0, 'm', 230, 0, 0, grab=38),
        'z': _m(14, 1, 24, 0, 0, 36, 58, 'm', 128, 20, 15, proj=1),
        'a': _m(6, 8, 24, 16, 52, 40, 130, 'm', 200, 0, 16, kd=1, inv=4),
        'x': _m(10, 1, 34, 0, 0, 10, 80, 'm', 460, 0, 20, proj=1, cost=100, kd=1),
    },
}
AIR_S = {'lie': 4, 'tie': 5, 'yan': 3, 'rei': 5}
MY = 'lie'
MYT = T[MY]
GRAB = MYT['t']['grab']            # 38
HEAVY = {'h', 'x', 'z'}           # 削防御值很疼的招


def _threat(opp):
    """对手这一招什么时候可能打到我：返回 (kind, 还有几帧命中, 招式)。"""
    ch = opp.get('char', 'lie')
    tbl = T.get(ch)
    if tbl is None:
        return None
    st = opp.get('st')
    mv = opp.get('mv')
    if st == 'attack':
        m = tbl.get(mv)
        if m is None:
            return None
        if 'grab' in m:
            return ('T', -1, mv)
        s, omf = m['s'], opp.get('mf') or 0
        if omf + 7 > s + m['a']:
            return None
        j = s - 6 - omf
        return (m['kind'], j, mv) if j >= 0 else None
    if st == 'air' and mv == 'air':
        s = AIR_S.get(ch, 4)
        omf = opp.get('mf') or 0
        j = s - 6 - omf
        return ('h', j, 'air') if j >= 0 else None
    return None


def _incoming(state, me, opp):
    """对手的飞行道具多久之后打到我（帧）。没有就返回 None。"""
    best = None
    for p in state.get('projectiles') or ():
        if p.get('mine'):
            continue
        x = p.get('x', 0) + p.get('vx', 0) * 6      # 对手的道具位置是 6 帧前的
        vx = p.get('vx', 0)
        if vx == 0:
            continue
        gap = x - me['x']
        if gap * vx <= 0:                            # 不朝我来
            continue
        t = gap / vx
        if t < 0:
            t = 0
        if t < 14 and (best is None or t < best):
            best = t
    return best


def decide(state):
    if state.get('phase') == 'select':
        return MY
    if state.get('phase') != 'fight' or state.get('freeze', 0) > 0:
        return 'n'

    me = state['me']
    opp = state['opp']
    st = me['st']
    mv = me['mv']
    dist = abs(opp['x'] - me['x'])
    ost = opp['st']
    omv = opp.get('mv')
    meter = me.get('meter', 0)
    guard = me.get('guard', 100)
    ochar = opp.get('char', 'lie')
    otbl = T.get(ochar, T['lie'])

    # --- 正在出招：只有 p / h 能取消 ---
    if st == 'attack':
        if mv in ('p', 'h') and me.get('contact'):
            m = MYT[mv]
            if (me.get('mf') or 0) <= m['s'] + m['a'] + 4:
                return 'a' if dist <= 40 else ('x' if meter >= 100 else 'a')
        return 'n'

    if st not in ('stand', 'walk', 'crouch'):
        return 'n'

    # --- 对空 ---
    if ost == 'air' and (opp.get('y') or 0) > 4 and dist <= 52:
        return 'a'

    # --- 飞行道具来袭：站防 ---
    inc = _incoming(state, me, opp)
    if inc is not None and inc <= 9:
        return 'b'

    # --- 防守：只对来得及的招防（起手 >= 7 帧）---
    thr = _threat(opp)
    if thr is not None:
        kind, j, tmv = thr
        if kind in ('m', 'h', 'l') and 1 <= j <= 4:
            if tmv in HEAVY and guard < 45:
                # 防御值快没了，硬防会被破防：躲开
                return 'e' if dist <= 46 else 'b'
            return 'g' if kind == 'l' else 'b'

    # --- 对手在起跳（3 帧内离地，抓不到）---
    if ost == 'prejump':
        if dist <= 44:
            return 'a'
        return 'f'

    # --- 对手不能动的时候 ---
    if ost in ('hitstun', 'knock', 'wake', 'thrown', 'ko'):
        if ost == 'hitstun':
            if dist <= 32:
                return 'p'
            if dist <= 54:
                return 'h'
            return 'f'
        if dist > 30:
            return 'f'
        return 'n'

    # --- 对手在收招（判定已过）→ 白挨窗口 ---
    if ost == 'attack' and omv in otbl:
        m = otbl[omv]
        if 'grab' not in m and (opp.get('mf') or 0) + 7 > m['s'] + m['a']:
            if dist <= 32:
                return 't'
            if dist <= 54:
                return 'h'
            if dist <= 62:
                return 'k'

    # --- 对手在防御硬直里：马上要站起来了 ---
    if ost == 'blockstun':
        if (opp.get('stun') or 0) <= 6:
            if dist <= 34:
                return 'a'          # 破防（-99 防御值）
            if dist <= 54:
                return 'h'
        return 'n'

    # --- 超必杀：起手无敌、破防能力强 ---
    if meter >= 100 and dist <= 58:
        return 'x'

    # --- 收尾阶段：领先就保命，落后就拼命 ---
    tf = state.get('timer_frames')
    if tf is not None and tf <= 120 and ost not in ('hitstun', 'knock', 'wake', 'thrown', 'ko'):
        myr = me['hp'] / float(me.get('max_hp') or 1)
        opr = opp['hp'] / float(opp.get('max_hp') or 1)
        if myr > opr + 0.03:
            return 'b'            # 边退边防，别再冒险

    # --- 中立：按距离 ---
    if dist <= 30:
        return 't'                # 贴脸投技：防不住
    if dist <= 36:
        return 'a'                # 对空技：起手 4 帧无敌 + 220 伤害
    if dist <= 54:
        return 'h'                # 重拳：可取消
    if dist <= 62:
        return 'k'
    if dist <= 120:
        return 'r'                # 前冲：快速拉近距离（9 帧 45 距离）
    return 'z'                    # 远距离火球控场
