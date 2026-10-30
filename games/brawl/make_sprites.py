"""把 art/ 里的精灵、特效和场地打成 sprites.js（出片和网页都用）。

图都内嵌成 data URI，放进文档里的隐藏 <img>（会拖住页面 load，出片截帧时已解码）；
window.__boardReady 等全部图加载完再放行，做法照 games/bomb_party/make_sprites.py。

    .venv/bin/python games/brawl/make_sprites.py
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ART = HERE / "art"


def main():
    spr = json.loads((ART / "sprites.json").read_text(encoding="utf-8"))
    fx = json.loads((ART / "fx.json").read_text(encoding="utf-8"))["fx"]
    stage = Image.open(ART / "stage-1080.png").convert("RGB")
    buf = io.BytesIO()
    stage.save(buf, "JPEG", quality=82, optimize=True)
    stage_uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    meta = {c: {k: {kk: v[kk] for kk in ("w", "h", "ax", "ay")} for k, v in poses.items()} for c, poses in spr.items()}
    src = {c: {k: v["src"] for k, v in poses.items()} for c, poses in spr.items()}
    fxmeta = {k: {kk: v[kk] for kk in ("w", "h", "ax", "ay")} for k, v in fx.items()}
    fxsrc = {k: v["src"] for k, v in fx.items()}
    js = ("// 生成文件：games/brawl/make_sprites.py。角色精灵、特效、场地图都内嵌；画法在 render.js。\n"
          "(function () {\n"
          f"  const META = {json.dumps(meta, separators=(',', ':'))};\n"
          f"  const SRC = {json.dumps(src, separators=(',', ':'))};\n"
          f"  const FXM = {json.dumps(fxmeta, separators=(',', ':'))};\n"
          f"  const FXS = {json.dumps(fxsrc, separators=(',', ':'))};\n"
          "  const box = document.createElement('div'); box.style.display = 'none';\n"
          "  (document.body || document.documentElement).appendChild(box);\n"
          "  const add = (s) => { const im = document.createElement('img'); im.src = s; box.appendChild(im); return im; };\n"
          "  const all = [];\n"
          "  window.SPR = {};\n"
          "  for (const c in META) { window.SPR[c] = {}; for (const k in META[c]) { const im = add(SRC[c][k]); all.push(im); window.SPR[c][k] = Object.assign({ img: im }, META[c][k]); } }\n"
          "  window.FX = {};\n"
          "  for (const k in FXM) { const im = add(FXS[k]); all.push(im); window.FX[k] = Object.assign({ img: im }, FXM[k]); }\n"
          f"  window.STAGE = add({json.dumps(stage_uri)}); all.push(window.STAGE);\n"
          "  window.__boardReady = Promise.all(all.map((im) => im.complete && im.naturalWidth ? null : new Promise((ok) => { im.onload = im.onerror = ok; })));\n"
          "})();\n")
    out = HERE / "sprites.js"
    out.write_text(js, encoding="utf-8")
    print(f"{out.relative_to(HERE.parents[1])} {out.stat().st_size // 1024} KB（场地 {len(buf.getvalue()) // 1024} KB）")


if __name__ == "__main__":
    main()
