"""炸弹人样片音效：放弹、爆炸、碎箱、出局、缩圈，垫芯片音乐。python sfx.py match.json out.wav --rate 5"""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video"))
from chiptune import SR, tone, env, lowpass, noise, add, note, bgm_track, write_wav  # noqa: E402

G = json.load(open(sys.argv[1])); out = sys.argv[2]; rate = float(sys.argv[4]) if len(sys.argv) > 4 else 5.0
dur = (G["turns"] + 2) / rate + 0.5
buf = np.zeros(int(SR * (dur + 1)))
T = lambda turn: turn / rate


def boom(t, seed, big=False):
    n = noise(0.5 if big else 0.35, seed)
    add(buf, t, lowpass(n, 0.08) * env(len(n), 0.002, 0, 3.5), 0.9 if big else 0.6)
    m = int(SR * 0.25); f = np.linspace(120, 35, m)
    add(buf, t, np.sin(2 * np.pi * np.cumsum(f) / SR) * env(m, 0.001, 0, 4), 0.8)


def pop(t):
    s = tone(note(79), 0.06, duty=0.25)
    add(buf, t, s * env(len(s), 0.002, 0, 5), 0.12)


def crack(t, seed):
    n = noise(0.12, seed)
    add(buf, t, (n - lowpass(n, 0.3)) * env(len(n), 0.001, 0, 6), 0.25)


def ko(t):
    for k, m in enumerate((72, 67, 64, 60)):
        s = tone(note(m), 0.12, duty=0.5)
        add(buf, t + 0.05 + k * 0.11, s * env(len(s), 0.002, 0.2, 3), 0.12)


def thud(t):
    m = int(SR * 0.3); f = np.linspace(90, 40, m)
    add(buf, t, np.sin(2 * np.pi * np.cumsum(f) / SR) * env(m, 0.001, 0, 4), 0.7)


seen = set()
for e in G["events"]:
    t, ty = T(e["t"]), e["type"]
    if ty == "bomb":
        pop(t)
    elif ty == "explode" and (e["t"], "x") not in seen:
        seen.add((e["t"], "x")); boom(t, e["t"], big=sum(1 for q in G["events"] if q["t"] == e["t"] and q["type"] == "explode") > 1)
    elif ty == "brick":
        crack(t + 0.04, e["t"])
    elif ty in ("die", "death", "eliminated"):
        ko(t)
    elif ty == "pickup":
        for k, m in enumerate((84, 88, 91)):
            s_ = tone(note(m), 0.06, duty=0.25); add(buf, t + k * 0.05, s_ * env(len(s_), 0.002, 0, 4), 0.1)
    elif ty == "kick":
        n_ = noise(0.15, e["t"]); add(buf, t, lowpass(n_, 0.25) * np.sin(np.linspace(0, np.pi, len(n_))), 0.3)
    elif ty == "crush":
        m_ = int(SR * 0.12); f_ = np.linspace(110, 50, m_)
        add(buf, t, np.sin(2 * np.pi * np.cumsum(f_) / SR) * env(m_, 0.001, 0, 5), 0.25)
frames = G["frames"]
for i in range(1, len(frames)):
    if frames[i].get("zone") != frames[i - 1].get("zone"):
        thud(T(i))
music = bgm_track(dur, "brisk") * 0.7
write_wav(Path(out), buf[: len(music)] + music[: len(buf)])
