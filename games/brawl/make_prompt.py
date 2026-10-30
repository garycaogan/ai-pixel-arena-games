"""从 engine.py 的数值生成 PROMPT.md 里的角色和招式表（改了数值就重跑），其余文字在 PROMPT.head.md。

    python3 -m games.brawl.make_prompt
"""
from pathlib import Path

from games.brawl import engine as E

HERE = Path(__file__).resolve().parent
KEYS = ("p", "h", "k", "s", "air", "t", "z", "a", "x")
LABEL = {"p": "轻拳 p", "h": "重拳 h", "k": "脚 k", "s": "扫腿 s", "air": "跳攻（空中按 p/h/k）", "t": "投 t",
         "z": "必杀技 z", "a": "对空技 a", "x": "超必杀 x"}
KIND = {"mid": "中段", "low": "下段", "high": "上段"}


def row(key, m):
    if "proj" in m:
        p = m["proj"]
        what = (f"飞行道具：起手 {m['s']} 帧后发出，速度 {p['v']}/帧，宽 {p['w']}，高度 {p['hy'][0]}–{p['hy'][1]}，"
                f"伤害 {p['dmg']}，防住削血 {p.get('chip', 0)}" + ("，打中击倒" if p.get("kd") else f"，硬直 {p['hs']}")
                + f"，防硬直 {p['bs']}；同一时间自己最多一个")
        return f"| {LABEL[key]} | {m['s']} | {m['a']} | {m['r']} | — | — | {what} |"
    if "throw" in m:
        what = f"投，抓取距离 ≤{m['throw']}（中心距），伤害 {m['dmg']}，防不住；对方在空中、硬直、倒地、无敌时抓不到"
        if m.get("cmd"):
            what = "指令投：" + what
        return f"| {LABEL[key]} | {m['s']} | {m['a']} | {m['r']} | — | — | {what} |"
    notes = [KIND[m["kind"]], f"伤害 {m['dmg']}"]
    notes.append("打中击倒" if m.get("kd") else f"打中硬直 {m['hs']}")
    notes.append(f"防硬直 {m['bs']}")
    if m.get("hits"):
        notes.append(f"{len(m['hits'])} 段（判定第 {'/'.join(map(str, m['hits']))} 帧），最后一段击倒")
    if m.get("chip"):
        notes.append(f"防住每段削血 {m['chip']}")
    if m.get("inv"):
        notes.append(f"第 {m['inv'][0]}–{m['inv'][1]} 帧无敌")
    if m.get("armor"):
        notes.append(f"第 {m['armor'][0]}–{m['armor'][1]} 帧挨一下不硬直（照样掉血，非超必杀）")
    if m.get("vx"):
        notes.append(f"判定期间每帧前进 {m['vx']}")
    if m.get("vy"):
        notes.append(f"判定期间每帧升高 {m['vy']}")
    if m.get("cancel"):
        notes.append("打中或被防后可取消")
    if m.get("cost"):
        notes.append(f"耗气 {m['cost']}")
    if m.get("crouch"):
        notes.append("出招时是蹲姿受击框")
    reach = f"{m['reach'][0]}–{m['reach'][1]}"
    hy = f"{m['hy'][0]}–{m['hy'][1]}"
    return f"| {LABEL[key]} | {m['s']} | {m['a']} | {m['r']} | {reach} | {hy} | {'，'.join(notes)} |"


def table():
    out = []
    for c in E.CHAR_KEYS:
        ch = E.CHARS[c]
        out.append(f"### {ch['name']} `{c}`（{ch['style']}）\n")
        out.append(f"血 {ch['hp']}；走 {ch['walk']}/帧，后退 {ch['back']}/帧；前冲 {ch['dash'][0]} 帧每帧 {ch['dash'][1]}；"
                   f"后撤步 {ch['backdash'][0]} 帧每帧 {ch['backdash'][1]}、前 {ch['backdash'][2]} 帧无敌；"
                   f"跳起速度 {ch['jump_v']}、横向 {ch['jump_x']}；站高 {ch['height']}、蹲高 {ch['crouch']}。"
                   + (" 超必杀和必杀技是投（抓到才有效果）。" if c == "tie" else "") + "\n")
        out.append("| 招 | 起手 | 判定 | 收招 | 横向范围 | 高度 | 说明 |\n| --- | --- | --- | --- | --- | --- | --- |")
        for k in KEYS:
            out.append(row(k, ch["moves"][k]))
        out.append("")
    return "\n".join(out)


def main():
    head = (HERE / "PROMPT.head.md").read_text(encoding="utf-8")
    text = head.replace("{{MOVES}}", table())
    for k, v in dict(STAGE_W=E.STAGE_W, WALL=E.WALL, DELAY=E.DELAY, FPS=E.FPS, PUSH_W=E.PUSH_W,
                     METER_MAX=E.METER_MAX, GUARD_MAX=E.GUARD_MAX, INTRO=E.INTRO, OUTRO=E.OUTRO,
                     X0=E.START_X[0], X1=E.START_X[1]).items():
        text = text.replace("{{" + k + "}}", str(v))
    assert "{{" not in text
    (HERE / "PROMPT.md").write_text(text, encoding="utf-8")
    print("PROMPT.md", len(text), "字")


if __name__ == "__main__":
    main()
