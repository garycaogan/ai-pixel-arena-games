"""Offline static build: python3 build.py [--out dist] [--pyodide LOCAL_DIR]."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ART = ROOT / "art/bomb-party"
PYODIDE_VERSION = "0.29.5"
PYODIDE_DIR = HERE / ("pyodide-" + PYODIDE_VERSION)   # 从 Pyodide 的 GitHub Release 下载解压到这里
PYODIDE_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
# Append a manifest entry here and point source at a reviewed single-file bot.
# 炸弹派对杯（10/28）各家交卷的程序，按杯赛名次排（冠军排第一，开局默认对手取前几个），最后是主办方的陪练。
AI_BOTS = ROOT / "bots/bomb_party"
CAST = [
    {"slug": "opus", "name": "Claude", "color": "#FF9838", "source": AI_BOTS / "opus.py"},
    {"slug": "gemini", "name": "Gemini", "color": "#A57BFF", "source": AI_BOTS / "gemini.py"},
    {"slug": "astra", "name": "GPT", "color": "#1FC77E", "source": AI_BOTS / "astra.py"},
    {"slug": "minimax", "name": "MiniMax", "color": "#FF4B4B", "source": AI_BOTS / "minimax.py"},
    {"slug": "glm", "name": "GLM", "color": "#FFDD3C", "source": AI_BOTS / "glm.py"},
    {"slug": "deepseek", "name": "DeepSeek", "color": "#4567FF", "source": AI_BOTS / "deepseek.py"},
    {"slug": "kimi", "name": "Kimi", "color": "#F2F2F2", "source": AI_BOTS / "kimi.py"},
    {"slug": "qwen", "name": "千问", "color": "#F05BC9", "source": AI_BOTS / "qwen.py"},
    {"slug": "doubao", "name": "豆包", "color": "#2FD3E6", "source": AI_BOTS / "doubao.py"},
    {"slug": "grok", "name": "Grok", "color": "#9BE23A", "source": AI_BOTS / "grok.py"},
    {"slug": "baseline", "name": "陪练", "color": "#7D838F", "source": ROOT / "games/bomb_party/baseline.py"},
]
# Replace these two placeholders before publication. No platform access at build time.
LINKS = {"video": "https://space.bilibili.com/351426642", "source": "https://github.com/garycaogan/ai-pixel-arena-games"}


def build(out=HERE / "dist", pyodide=PYODIDE_DIR):
    out, pyodide = Path(out).resolve(), Path(pyodide).resolve()
    if out == HERE or out in HERE.parents or HERE / "tests" == out:
        raise ValueError("output must be a separate build directory")
    sources = {name: HERE / name for name in ("index.html", "style.css", "app.js", "input.js", "audio.js", "worker.js", "driver.py")}
    sources.update({"engine.py": ROOT / "games/bomb_party/engine.py", "stage.jpg": HERE / "assets/stage.jpg",
                    "render-bomber.js": ART / "render-bomber.js", "atlas.json": ART / "atlas.json"})
    cast = []
    for entry in CAST:
        slug = entry["slug"]
        if not re.fullmatch(r"[a-z0-9_-]+", slug) or any(c["slug"] == slug for c in cast):
            raise ValueError("invalid or duplicate slug")
        public = {key: entry[key] for key in ("slug", "name", "color")}
        public["file"] = "bots/" + slug + ".py"
        cast.append(public)
        sources[public["file"]] = Path(entry.get("source", ROOT / "bots/bomb_party" / (slug + ".py")))
    for name in PYODIDE_FILES:
        sources[f"pyodide-{PYODIDE_VERSION}/{name}"] = pyodide / name
    for path in [*sources.values(), ART / "stage-1080.png"]:
        if not path.is_file():
            raise FileNotFoundError(f"local build input missing: {path}; no downloads attempted")
    out.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    worker = (out / "worker.js").read_text().replace("__PYODIDE__", "pyodide-" + PYODIDE_VERSION)
    (out / "worker.js").write_text(worker, encoding="utf-8")
    page = (out / "index.html").read_text()
    for name, url in LINKS.items():
        page = page.replace("__LINK_" + name.upper() + "__", html.escape(url, quote=True))
    (out / "index.html").write_text(page, encoding="utf-8")
    names = sorted(sources)
    hashes = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in names}
    metadata = {"cast": cast, "links": LINKS, "pyodide": PYODIDE_VERSION, "hashes": hashes}
    version = hashlib.sha256(json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    (out / "index.html").write_text(page.replace("__VERSION__", version), encoding="utf-8")
    hashes["index.html"] = hashlib.sha256((out / "index.html").read_bytes()).hexdigest()
    manifest = {"version": version, "cast": cast, "links": LINKS, "pyodide": PYODIDE_VERSION,
                "files": ["engine.py", "driver.py", *[c["file"] for c in cast]], "hashes": hashes}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"out": str(out), "version": version, "bots": [c["slug"] for c in cast],
            "bytes": sum((out / name).stat().st_size for name in [*names, "manifest.json"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=HERE / "dist")
    parser.add_argument("--pyodide", type=Path, default=PYODIDE_DIR)
    args = parser.parse_args()
    print(json.dumps(build(args.out, args.pyodide), ensure_ascii=False))
