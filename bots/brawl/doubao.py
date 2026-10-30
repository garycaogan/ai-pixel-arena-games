# 全局变量，本场比赛保留
opp_char = None
opp_type = None  # ranged/speed/throw/balanced

def decide(state):
    global opp_char, opp_type
    
    # 选角：雷娜rei，远程消耗天花板，超杀波伤害爆炸，对波无敌
    if state["phase"] == "select":
        return "rei"
    
    # 无效阶段直接返回空
    if state["phase"]!= "fight" or state["freeze"] > 0:
        return "n"
    
    me = state["me"]
    opp = state["opp"]
    projectiles = state["projectiles"]
    
    # 首次战斗帧记录对手角色和类型，针对性调整策略
    if opp_char is None:
        opp_char = opp["char"]
        if opp_char == "rei":
            opp_type = "ranged"
        elif opp_char == "yan":
            opp_type = "speed"
        elif opp_char == "tie":
            opp_type = "throw"
        else:
            opp_type = "balanced"
    
    my_x = me["x"]
    opp_x_6 = opp["x"]
    my_st = me["st"]
    opp_st_6 = opp["st"]
    my_meter = me["meter"]
    opp_mv = opp["mv"]
    opp_stun = opp["stun"]
    
    # 6帧前的距离
    dist_6 = abs(my_x - opp_x_6)
    # 根据对手速度估算当前最小距离，加足够余量防突进
    min_dist = max(0, dist_6 - {
        "speed": 60,    # 飞燕最快，前冲6帧最多60，加10余量
        "throw": 45,    # 铁山慢，前冲6帧最多35，加10余量
        "balanced": 50, # 阿烈中等，加10余量
        "ranged": 50    # 雷娜中等，加10余量
    }[opp_type])
    
    # 检查自己是否有飞行道具在场上（雷娜同一时间最多1个）
    has_my_proj = any(p["mine"] for p in projectiles)
    
    # 检查是否有对手的飞行道具朝我们飞来
    incoming_proj = None
    for p in projectiles:
        if not p["mine"]:
            p_x = p["x"] + p["vx"] * 6
            moving_towards = (my_x > p_x and p["vx"] > 0) or (my_x < p_x and p["vx"] < 0)
            if moving_towards and abs(my_x - p_x) < 250:
                incoming_proj = p
                break
    
    # 不能出招的情况：只做防御
    if my_st not in ("stand", "walk", "crouch"):
        if incoming_proj is not None:
            return "b"
        return "g" if opp_mv == "s" else "b"
    
    # ============== 核心优化逻辑 ==============
    # 1. 对手硬直/防御硬直：放波必中，稳赚
    if opp_stun > 0 or opp["st"] == "blockstun":
        if my_meter >= 100 and not has_my_proj:
            return "x"
        if not has_my_proj:
            return "z"
    
    # 2. 对手前冲/跳跃：优先拉开距离，再放波
    if opp_st_6 == "dash":
        # 快角色前冲直接后撤，不让近身
        if opp_type == "speed":
            return "e"
        # 其他角色放波打他，前冲不能变招必吃
        if my_meter >= 100 and not has_my_proj:
            return "x"
        if not has_my_proj:
            return "z"
    
    # 对手跳跃：近距对空，远距后撤
    if opp_st_6 in ("prejump", "air"):
        if min_dist < 150:
            return "a"  # 对空技击落
        else:
            return "e"  # 距离远直接后撤拉开
    
    # 3. 气够立刻放超杀波：优先级最高，消波+高伤害+击倒
    if my_meter >= 100 and not has_my_proj:
        return "x"
    
    # 4. 近距离处理：分层级拉开/抢招，绝对不让投
    close_threshold = {
        "speed": 120,  # 速度快，更早拉开
        "throw": 100,  # 投技远，更早拉开
        "balanced": 90,
        "ranged": 90
    }[opp_type]
    
    if min_dist < close_threshold:
        # 投技型<70就后撤，躲超杀投74范围；其他<50就后撤，躲普通投38范围
        if (opp_type == "throw" and min_dist < 70) or min_dist < 50:
            return "e"
        # 50-70：扫腿s，下段击倒，倒地30帧足够拉开
        if min_dist < 70:
            return "s"
        # 70-72：重拳h，伤害160
        if min_dist < 72:
            return "h"
        # 72-80：脚k，范围80全角色最远
        return "k"
    
    # 5. 中距离处理：对空+防波+持续消耗
    # 对手波过来：站防涨气，比跳稳
    if incoming_proj is not None:
        return "b"
    # 无波就放普通波，持续磨血
    if not has_my_proj:
        return "z"
    # 有波在场上：对投/均衡前压，对速度/远程后退保持距离
    return "f" if opp_type in ("throw", "balanced") else "b"
    
    # 6. 远距离：稳定放波
    if not has_my_proj:
        return "z"
    return "n"