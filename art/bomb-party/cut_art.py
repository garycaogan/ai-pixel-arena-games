"""切炸弹人美术：品红底连通块切图，缩到原生像素（一格 32 像素），导出 atlas.json；场地背景缩成 1920×1080。"""
import base64, io, json, sys
import numpy as np
from PIL import Image
sys.path.insert(0, "../fighting-20261027/sprite-test")
from slice import fg_mask, label, shrink  # 复用拳皇那套切图

TILE = 32
HERO = ["down", "down_walk", "up", "up_walk", "right", "right_walk", "place", "victory", "dizzy", "ko", "wave", "thumb"]
ITEMS = ["floor", "pillar", "crate", "bomb", "bomb_hot", "crate_break", "fire_c", "fire_h", "fire_end", "pu_fire", "pu_bomb", "pu_kick"]


def comps(path, n, rows=2):
    a = np.asarray(Image.open(path).convert("RGB"))
    m = fg_mask(a)
    lab, sizes = label(m)
    cs = []
    for k, sz in enumerate(sizes, 1):
        if sz < 30:
            continue
        ys, xs = np.where(lab == k)
        cs.append(dict(k=k, x0=xs.min(), x1=xs.max(), y0=ys.min(), y1=ys.max(), sz=sz, cx=xs.mean(), cy=ys.mean()))
    big = sorted([c for c in cs if c["sz"] > 3000], key=lambda c: (int(c["cy"] / (a.shape[0] / rows)), c["cx"]))
    if len(big) != n:
        raise SystemExit(f"{path}: {len(big)} 个大块，应为 {n}")
    out = []
    for c in big:
        keep = lab == c["k"]
        for d in cs:
            if d["sz"] <= 3000 and min(abs(d["cx"] - b["cx"]) + abs(d["cy"] - b["cy"]) for b in big) == abs(d["cx"] - c["cx"]) + abs(d["cy"] - c["cy"]):
                keep |= lab == d["k"]
        ys, xs = np.where(keep)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        out.append((a[y0:y1 + 1, x0:x1 + 1], keep[y0:y1 + 1, x0:x1 + 1]))
    return out


def enc(rgb, alpha):
    b = io.BytesIO()
    Image.fromarray(np.concatenate([rgb, alpha[..., None]], -1).astype(np.uint8), "RGBA").save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def quant(parts, colors=40):
    allpix = np.concatenate([c[a > 0] for c, a in parts])
    pal = Image.fromarray(allpix.reshape(1, -1, 3)).quantize(colors, method=Image.Quantize.MEDIANCUT)
    return [(np.asarray(Image.fromarray(c).quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")), a) for c, a in parts]


atlas = {}
hero = comps("hero.png", 12)
f = 46 / max(r.shape[0] for r, _ in hero[:6])  # 站姿约 46 像素高（比一格高，俯视角站在格子里）
hs = quant([shrink(r, m, f) for r, m in hero])
for nm, (c, a) in zip(HERO, hs):
    atlas["hero_" + nm] = dict(w=c.shape[1], h=c.shape[0], src=enc(c, a))
items = comps("tiles.png", 12)
sq = items[0][1].shape[0]  # 草地方块的边长
its = quant([shrink(r, m, TILE / sq) for r, m in items])
for nm, (c, a) in zip(ITEMS, its):
    atlas[nm] = dict(w=c.shape[1], h=c.shape[0], src=enc(c, a))
json.dump(atlas, open("atlas.json", "w"))
Image.open("stage.png").convert("RGB").resize((1920, 1080), Image.NEAREST).save("stage-1080.png")
print({k: (v["w"], v["h"]) for k, v in atlas.items()})
