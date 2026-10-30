"""把陪练打包成单文件交卷（三种打法），放 games/brawl/artifacts/bots/。"""
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SRC = (HERE / "baseline.py").read_text(encoding="utf-8")
LINE = '_default = make("baseline", None, random.random())'


def main():
    assert LINE in SRC
    out = HERE / "artifacts" / "bots"
    out.mkdir(parents=True, exist_ok=True)
    for style in ("baseline", "rusher", "zoner"):
        (out / f"{style}.py").write_text(SRC.replace(LINE, LINE.replace('"baseline"', f'"{style}"')), encoding="utf-8")
    print("wrote", sorted(p.name for p in out.glob("*.py")))


if __name__ == "__main__":
    main()
