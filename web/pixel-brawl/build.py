"""像素拳斗网页版离线静态构建：python3 build.py [--out dist] [--pyodide 本地目录] [--cast opus,baseline]。

不联网、不装包、不调用任何 AI；缺文件直接报错。没有联网对战和排行榜（ququ.*、online.js 都不带）。
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GAME = ROOT / "games/brawl"
PYODIDE_VERSION = "0.29.5"
PYODIDE_DIR = HERE / ("pyodide-" + PYODIDE_VERSION)   # 从 Pyodide 的 GitHub Release 下载解压到这里
PYODIDE_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
SOURCE_DIRS = (ROOT, ROOT / "web", HERE, ROOT / "games", GAME)

# 像素拳斗杯（第 9 集）各家交卷的程序。收卷跑完杯赛后按名次重排（冠军排第一，开局默认对手取第一个），
# 陪练始终放最后。名字和颜色和炸弹派对网页版一致。
AI_BOTS = ROOT / "bots/brawl"
CAST = [
    # 像素拳斗杯（10/30）按名次排：冠军 GPT、亚军 Claude、季军 Grok、第四 MiniMax，其余按小组名次；第一家是开局默认对手。
    # Kimi 用的是修好工位后重开那一场交的程序（bots/brawl-ws/kimi.py）。
    {"slug": "astra", "name": "GPT", "color": "#1FC77E", "source": AI_BOTS / "astra.py"},
    {"slug": "opus", "name": "Claude", "color": "#FF9838", "source": AI_BOTS / "opus.py"},
    {"slug": "grok", "name": "Grok", "color": "#9BE23A", "source": AI_BOTS / "grok.py"},
    {"slug": "minimax", "name": "MiniMax", "color": "#FF4B4B", "source": AI_BOTS / "minimax.py"},
    {"slug": "gemini", "name": "Gemini", "color": "#A57BFF", "source": AI_BOTS / "gemini.py"},
    {"slug": "qwen", "name": "千问", "color": "#F05BC9", "source": AI_BOTS / "qwen.py"},
    {"slug": "glm", "name": "GLM", "color": "#FFDD3C", "source": AI_BOTS / "glm.py"},
    {"slug": "deepseek", "name": "DeepSeek", "color": "#4567FF", "source": AI_BOTS / "deepseek.py"},
    {"slug": "doubao", "name": "豆包", "color": "#2FD3E6", "source": AI_BOTS / "doubao.py"},
    {"slug": "kimi", "name": "Kimi", "color": "#F2F2F2", "source": AI_BOTS / "kimi.py"},
    {"slug": "baseline", "name": "陪练", "color": "#7D838F", "source": GAME / "baseline.py"},
]
LINKS = {"video": "https://space.bilibili.com/351426642", "source": "https://github.com/garycaogan/ai-pixel-arena-games"}
PAGE_FILES = ("index.html", "style.css", "app.js", "input.js", "audio.js", "worker.js", "driver.py")


def pick_cast(only=None):
    """only：逗号分隔的 slug，开发期只构建这几家（例如 BRAWL_CAST=baseline）。"""
    only = only if only is not None else os.environ.get("BRAWL_CAST")
    if not only:
        return list(CAST)
    want = [s.strip() for s in only.split(",") if s.strip()]
    unknown = [s for s in want if not any(c["slug"] == s for c in CAST)]
    if unknown:
        raise ValueError("CAST 里没有这些 slug：" + ", ".join(unknown))
    return [c for c in CAST if c["slug"] in want]


def check_out(out):
    out = Path(out).resolve()
    for source in SOURCE_DIRS:
        if out == source or out in source.parents:
            raise ValueError("output must be a separate build directory")
    if GAME in out.parents or out in (HERE / "tests", HERE / "assets"):
        raise ValueError("output must be a separate build directory")
    return out


def pyodide_base(value):
    if value and (value.startswith("/") or ":" in value or "?" in value or "#" in value
                  or not all(c.isalnum() or c in "./_-" for c in value)):
        raise ValueError("--pyodide-base must be a relative asset path")
    return value.rstrip("/") if value else None


def build(out=HERE / "dist", pyodide=PYODIDE_DIR, base=None, cast_only=None):
    out, pyodide, base = check_out(out), Path(pyodide).resolve(), pyodide_base(base)
    roster = pick_cast(cast_only)
    if not roster:
        raise ValueError("名单是空的")
    sources = {name: HERE / name for name in PAGE_FILES}
    sources.update({"engine.py": GAME / "engine.py", "render.js": GAME / "render.js", "sprites.js": GAME / "sprites.js"})
    cast, missing = [], []
    for entry in roster:
        slug = entry["slug"]
        if not re.fullmatch(r"[a-z0-9_-]+", slug) or any(c["slug"] == slug for c in cast):
            raise ValueError("invalid or duplicate slug: " + slug)
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", entry["color"]):
            raise ValueError("color must be #RRGGBB: " + slug)
        public = {key: entry[key] for key in ("slug", "name", "color")}
        public["file"] = "bots/" + slug + ".py"
        cast.append(public)
        source = Path(entry["source"])
        if not source.is_file():
            missing.append(f"{slug}（{entry['name']}）: {source}")
        sources[public["file"]] = source
    if missing:
        raise FileNotFoundError("AI 程序还没到位，不能构建：\n  " + "\n  ".join(missing)
                                + "\n开发期可以只构建已有的：BRAWL_CAST=baseline python3 build.py 或 --cast baseline")
    if not base:
        for name in PYODIDE_FILES:
            sources[f"pyodide-{PYODIDE_VERSION}/{name}"] = pyodide / name
    for path in sources.values():
        if not path.is_file():
            raise FileNotFoundError(f"local build input missing: {path}; no downloads attempted")
    out.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    with (out / "style.css").open("a", encoding="utf-8") as stream:
        for c in cast:
            stream.write(f'\n[data-slug="{c["slug"]}"] {{ --ai:{c["color"]}; }}')
    worker = (out / "worker.js").read_text(encoding="utf-8").replace("__PYODIDE__", base or "pyodide-" + PYODIDE_VERSION)
    (out / "worker.js").write_text(worker, encoding="utf-8")
    page = (out / "index.html").read_text(encoding="utf-8")
    for name, url in LINKS.items():
        page = page.replace("__LINK_" + name.upper() + "__", html.escape(url, quote=True))
    (out / "index.html").write_text(page, encoding="utf-8")
    names = sorted(sources)
    hashes = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in names}
    metadata = {"cast": cast, "links": LINKS, "pyodide": PYODIDE_VERSION, "hashes": hashes, "pyodide_base": base}
    version = hashlib.sha256(json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    (out / "index.html").write_text(page.replace("__VERSION__", version), encoding="utf-8")
    hashes["index.html"] = hashlib.sha256((out / "index.html").read_bytes()).hexdigest()
    manifest = {"version": version, "game": "brawl", "cast": cast, "links": LINKS, "pyodide": PYODIDE_VERSION,
                "engine": hashes["engine.py"][:12], "pyodide_base": base,
                "files": ["engine.py", "driver.py", *[c["file"] for c in cast]], "hashes": hashes}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"out": str(out), "version": version, "bots": [c["slug"] for c in cast],
            "bytes": sum((out / name).stat().st_size for name in [*names, "manifest.json"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=HERE / "dist")
    parser.add_argument("--pyodide", type=Path, default=PYODIDE_DIR)
    parser.add_argument("--pyodide-base", help="relative shared runtime path; do not copy Pyodide")
    parser.add_argument("--cast", help="只构建这几家（逗号分隔 slug），开发期用；默认整份 CAST")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.out, args.pyodide, args.pyodide_base, args.cast), ensure_ascii=False))
    except FileNotFoundError as exc:
        raise SystemExit(str(exc))
