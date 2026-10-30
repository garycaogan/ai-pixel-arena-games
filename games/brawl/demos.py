"""四段真实引擎演示（规则讲解用）：连段取消、上中下段防御、投破防御、超必杀定格。"""
from .engine import LETTER, Game, export_game


def setup(chars, xs=(160, 210), meter=(0, 0)):
    g = Game(0, {"chars": list(chars)})
    g.phase, g.pt = "fight", 0
    for f, x, m in zip(g.f, xs, meter):
        f.reset(x)
        f.meter = m
    g.f[0].face, g.f[1].face = 1, -1
    g.hist, g.phist = [], []
    g._remember()
    return g


def run(g, script, seats=("示范甲", "示范乙")):
    rows = []
    for a, b, n in script:
        rows += ["".join(LETTER[x] for x in (a, b))] * n
    return export_game(g, rows, list(seats))


def build():
    combo = setup(("lie", "rei"), (170, 205))
    guard = setup(("yan", "tie"), (175, 212))
    throw = setup(("tie", "lie"), (175, 210))
    sup = setup(("yan", "lie"), (165, 205), meter=(100, 0))
    return {
        # 阿烈重拳打中，取消成烈波：两下连上
        "combo": run(combo, [("h", "n", 9), ("z", "n", 1), ("n", "n", 50)]),
        # 飞燕扫腿：铁山站防挡不住被扫倒；起身后蹲防就挡住了
        "guard": run(guard, [("s", "b", 1), ("n", "b", 60), ("f", "n", 6), ("s", "g", 1), ("n", "g", 30)]),
        # 阿烈一直站防，铁山走近用指令投抓起来摔
        "throw": run(throw, [("f", "b", 6), ("z", "b", 1), ("n", "b", 60)]),
        # 飞燕攒满一格气放超必杀：全场定格，连环腿冲过去
        "super": run(sup, [("x", "n", 1), ("n", "n", 70)]),
    }


make_all = all_demos = build
