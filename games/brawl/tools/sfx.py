"""像素拳斗样片音效：按回放事件合成打击、防御、必杀、超必杀、投、KO 声，垫一段芯片音乐。
    python games/brawl/tools/sfx.py <回放.json> <输出.wav>"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sfxlib import SR, event  # noqa: E402
import numpy as np  # noqa: E402
from chiptune import bgm_track, write_wav  # noqa: E402

R = json.load(open(sys.argv[1]))
out = sys.argv[2]
fr = R["frames"]
dur = len(fr) / 30
buf = np.zeros(int(SR * (dur + 1)))
for i, f in enumerate(fr):
    for e in f["ev"]:
        event(buf, i / 30, e, i)
music = bgm_track(dur, "brisk") * 0.8
write_wav(Path(out), buf[: len(music)] + music[: len(buf)])
