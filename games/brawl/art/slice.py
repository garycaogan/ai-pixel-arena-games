"""像素拳斗切图：四个角色八张品红底精灵图 → 原生像素单帧 → sprites.json；
同时把场地图出 1920x1080 和 384x216 原生版，特效图切成 fx.json，并拼检查图 contact.png。

运行：../../../.venv/bin/python slice.py （在 games/brawl/art 目录下）
改自 research/fighting-20261027/sprite-test/slice.py。
"""
import base64, io, json
import numpy as np
from PIL import Image

A_POSES = ["stance", "walk", "jab", "heavy", "kick", "crouch", "jump", "lying"]
POSES = A_POSES + ["hit", "block", "sweep", "grab", "special", "upper", "super", "win"]
SHEETS = {
    "lie": [("lie.png", A_POSES),
            # 旧名 palms→special, upper→upper, rush→super
            ("lie-b.png", ["hit", "block", "sweep", "grab", "special", "upper", "super", "win"])],
    "tie": [("tie-a.png", A_POSES),
            # 旧图第 5–7 格是 lift / slam / headbutt。改映射：headbutt(前冲头槌)→special，
            # lift(双臂上举)→upper(对空)，slam(下砸)→super
            ("tie-b.png", ["hit", "block", "sweep", "grab", "upper", "super", "special", "win"])],
    "yan": [("yan-a.png", A_POSES),
            ("yan-b.png", ["hit", "block", "sweep", "grab", "special", "upper", "super", "win"])],
    "rei": [("rei-a.png", A_POSES),
            ("rei-b.png", ["hit", "block", "sweep", "grab", "special", "upper", "super", "win"])],
}
TARGET = {"lie": 78, "tie": 86, "yan": 74, "rei": 82}  # 站姿在原生画布上的高度（像素）
# 扫腿伸出去的腿贴地，锚点放在身体那头（从背后算起 30% 处）；踢腿类用站立脚，自动就是身体那头
ANCHOR_BACK = {"sweep": 0.30}
# 腾空姿势用外框中心（没有站立脚可对）
AIR = {"jump", ("yan", "upper"), ("yan", "special")}
STAGE_W, STAGE_H = 384, 216
GROUND_Y = 178  # 原生场地上脚底所在的行（木栈道上沿在 159 行）


def fg_mask(a):
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    return (np.minimum(r, b) - g) < 95


def label(m):
    """四连通标记（迭代泛洪，不依赖 scipy）。"""
    h, w = m.shape
    lab = np.zeros((h, w), np.int32)
    n, sizes = 0, []
    for y0, x0 in zip(*np.where(m)):
        if lab[y0, x0]:
            continue
        n += 1
        stack = [(y0, x0)]
        lab[y0, x0] = n
        cnt = 0
        while stack:
            y, x = stack.pop()
            cnt += 1
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    stack.append((yy, xx))
        sizes.append(cnt)
    return lab, sizes


def cut(path, names, big_min=2000, pad=12):
    a = np.asarray(Image.open(path).convert("RGB"))
    m = fg_mask(a)
    lab, sizes = label(m)
    comps = []
    for k, sz in enumerate(sizes, 1):
        if sz < 40:
            continue
        ys, xs = np.where(lab == k)
        comps.append([xs.min(), xs.max(), ys.min(), ys.max(), sz, k])
    big = sorted([c for c in comps if c[4] > big_min], key=lambda c: c[0])
    if len(big) != len(names):
        raise SystemExit(f"{path}: 切出 {len(big)} 个大块，应为 {len(names)}")
    out = {}
    for c, nm in zip(big, names):
        keep = lab == c[5]
        # 小碎块（拳头、马尾、电弧）并到最近的大块
        for d in comps:
            if d[4] <= big_min and c[0] - pad <= (d[0] + d[1]) / 2 <= c[1] + pad and c[2] - pad <= (d[2] + d[3]) / 2 <= c[3] + pad:
                keep |= lab == d[5]
        ys, xs = np.where(keep)
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        out[nm] = (a[y0:y1 + 1, x0:x1 + 1], keep[y0:y1 + 1, x0:x1 + 1], (x0, y0, x1, y1))
    return out


def shrink(rgb, mask, f):
    h, w = mask.shape
    nw, nh = max(1, round(w * f)), max(1, round(h * f))
    al = mask.astype(np.float32)
    pre = rgb.astype(np.float32) * al[..., None]
    Pc = np.asarray(Image.fromarray(pre.clip(0, 255).astype(np.uint8)).resize((nw, nh), Image.BOX)).astype(np.float32)
    A = np.asarray(Image.fromarray((al * 255).astype(np.uint8)).resize((nw, nh), Image.BOX)).astype(np.float32) / 255
    col = np.where(A[..., None] > 0.01, Pc / np.maximum(A[..., None], 1e-3), 0).clip(0, 255)
    alpha = (A > 0.42).astype(np.uint8) * 255
    return col.astype(np.uint8), alpha


def despill(rgb, alpha):
    """只处理轮廓边上的像素：颜色接近品红（红≈蓝、绿明显低）的压回灰暗描边色。
    雷娜的紫风衣、电光球本身是紫色（红明显低于蓝），不会被误伤。"""
    c = rgb.astype(int)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    a = alpha > 0
    pad = np.pad(a, 1)
    edge = a & ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])
    magenta = ((np.minimum(r, b) - g) > 60) & (r > 0.8 * b) & (b > 0.8 * r)
    m = edge & magenta
    lim = g + 20
    c[..., 0] = np.where(m, np.minimum(r, lim), r)
    c[..., 2] = np.where(m, np.minimum(b, lim), b)
    return c.clip(0, 255).astype(np.uint8)


def to_src(rgba):
    b = io.BytesIO()
    Image.fromarray(rgba.astype(np.uint8), "RGBA").save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def from_src(src):
    return Image.open(io.BytesIO(base64.b64decode(src.split(",")[1]))).convert("RGBA")


def build_char(ch, sheets):
    frames = {}
    sheet_of = {}
    for path, names in sheets:
        for nm, v in cut(path, names).items():
            frames[nm] = v
            sheet_of[nm] = path
    # 两张图同一模型同一参考，像素颗粒一致：整个角色用 A 张站姿定一个缩放比例
    # （B 张防御站姿膝盖微屈，比站姿矮 0–8%，不能拿来单独定比例）
    f = TARGET[ch] / frames["stance"][1].shape[0]
    ratio = frames["stance"][1].shape[0] / frames["block"][1].shape[0]
    f_of = {nm: f for nm in frames}
    shr = {nm: shrink(rgb, m, f_of[nm]) for nm, (rgb, m, _) in frames.items()}
    shr = {nm: (despill(c, a), a) for nm, (c, a) in shr.items()}
    allpix = np.concatenate([c[a > 0] for c, a in shr.values()])
    pal_img = Image.fromarray(allpix.reshape(1, -1, 3)).quantize(32, method=Image.Quantize.MEDIANCUT)
    out = {}
    for nm in POSES:
        c, a = shr[nm]
        q = np.asarray(Image.fromarray(c).quantize(palette=pal_img, dither=Image.Dither.NONE).convert("RGB"))
        rgba = np.concatenate([q, a[..., None]], -1)
        h, w = a.shape
        ys, xs = np.where(a > 0)
        foot = xs[ys >= h - max(2, int(h * 0.1))]
        if nm in ANCHOR_BACK:
            ax = xs.min() + (xs.max() - xs.min()) * ANCHOR_BACK[nm]
        elif nm == "lying" or nm in AIR or (ch, nm) in AIR:
            ax = (xs.min() + xs.max()) / 2
        else:
            ax = (foot.min() + foot.max()) / 2
        out[nm] = dict(w=w, h=h, ax=round(float(ax), 1), ay=h, src=to_src(rgba))
    return out, ratio


def build_stage():
    im = Image.open("stage.png").convert("RGB")  # 1536x864，已经是 16:9
    im.resize((1920, 1080), Image.LANCZOS).save("stage-1080.png")
    nat = im.resize((STAGE_W, STAGE_H), Image.BOX).quantize(64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGB")
    nat.save("stage-384.png")
    json.dump(dict(w=STAGE_W, h=STAGE_H, ground_y=GROUND_Y, floor_top=159, src_1080="stage-1080.png", src_native="stage-384.png"),
              open("stage.json", "w"), ensure_ascii=False, indent=1)
    return nat


def build_fx():
    names = ["ki_0", "ki_1", "ki_2", "zap_0", "zap_1", "zap_2"]
    frames = cut("fx.png", names, big_min=1500, pad=40)
    f = 24 / max(v[1].shape[0] for v in frames.values())  # 能量球约 24 原生像素高（人物胸口附近发射）
    out = {}
    for nm, (rgb, m, _) in frames.items():
        c, a = shrink(rgb, m, f)
        c = despill(c, a)
        h, w = a.shape
        out[nm] = dict(w=w, h=h, ax=round(w * 0.75, 1), ay=round(h / 2, 1), src=to_src(np.concatenate([c, a[..., None]], -1)))
    json.dump({"fx": out}, open("fx.json", "w"))
    return out


def contact(atlas, stage, fx):
    """检查拼图：每个角色一行，16 个姿势按原生像素排在场地原生图上，脚底对齐 GROUND_Y，再整体 ×3。"""
    gap = 6
    rows = []
    for ch in ["lie", "tie", "yan", "rei"]:
        width = sum(v["w"] + gap for v in atlas[ch].values()) + gap
        bg = Image.new("RGB", (width, STAGE_H))
        for x in range(0, width, STAGE_W):
            bg.paste(stage, (x, 0))
        bg = bg.convert("RGBA")
        x = gap
        for nm in POSES:
            v = atlas[ch][nm]
            bg.alpha_composite(from_src(v["src"]), (x, GROUND_Y - v["h"]))
            x += v["w"] + gap
        rows.append(bg)
    fxrow = Image.new("RGBA", (max(r.width for r in rows), 40), (30, 20, 40, 255))
    x = gap
    for v in fx.values():
        fxrow.alpha_composite(from_src(v["src"]), (x, 20 - v["h"] // 2)); x += v["w"] + gap
    W = max(r.width for r in rows)
    sheet = Image.new("RGBA", (W, STAGE_H * 4 + 40), (0, 0, 0, 255))
    for i, r in enumerate(rows):
        sheet.paste(r, (0, i * STAGE_H))
    sheet.paste(fxrow, (0, STAGE_H * 4))
    sheet.resize((W * 3, sheet.height * 3), Image.NEAREST).convert("RGB").save("contact.png")


def main():
    atlas, ratios = {}, {}
    for ch, sheets in SHEETS.items():
        atlas[ch], ratios[ch] = build_char(ch, sheets)
    json.dump(atlas, open("sprites.json", "w"))
    stage = build_stage()
    fx = build_fx()
    contact(atlas, stage, fx)
    for ch, d in atlas.items():
        print(ch, "stance/block 高度比", round(ratios[ch], 3), {nm: (v["w"], v["h"]) for nm, v in d.items()})
    print("fx", {nm: (v["w"], v["h"]) for nm, v in fx.items()})


if __name__ == "__main__":
    main()
