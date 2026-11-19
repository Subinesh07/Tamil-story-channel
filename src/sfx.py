"""Original sound effects made from scratch (no copyright): a soft intro chime and a
subscribe bell. Run once:  python src/sfx.py  -> assets/sfx/chime.wav, assets/sfx/bell.wav
"""
import wave

import numpy as np

from config import ROOT

OUT = ROOT / "assets" / "sfx"
SR = 44100


def _write(path, sig):
    sig = sig / max(1e-9, np.max(np.abs(sig))) * 0.8
    stereo = np.repeat((sig * 32767).astype(np.int16)[:, None], 2, axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


def bell(f0=880.0, secs=2.2):
    """Bright notification bell: inharmonic partials with fast attack and long decay, rung twice."""
    t = np.arange(int(SR * secs)) / SR
    partials = [(1.0, 1.0, 2.2), (2.76, 0.55, 3.5), (5.40, 0.30, 5.0), (8.93, 0.15, 7.0), (0.5, 0.25, 1.6)]
    ring = sum(a * np.sin(2 * np.pi * f0 * r * t) * np.exp(-d * t) for r, a, d in partials)
    ring *= np.minimum(1, t / 0.004)
    out = ring.copy()
    lag = int(SR * 0.18)   # second strike: "ding-ding"
    out[lag:] += 0.8 * ring[:-lag]
    return out


def chime(secs=3.2):
    """Gentle rising three-note chime (Sa Ga Pa) for the intro title."""
    t = np.arange(int(SR * secs)) / SR
    out = np.zeros_like(t)
    for k, f in enumerate([523.25, 659.25, 783.99]):
        start = int(SR * 0.22 * k)
        tt = t[: len(t) - start]
        note = (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * 2 * f * tt)
                + 0.12 * np.sin(2 * np.pi * 3.01 * f * tt)) * np.exp(-1.6 * tt)
        note *= np.minimum(1, tt / 0.01)
        out[start:] += note
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    _write(OUT / "bell.wav", bell())
    _write(OUT / "chime.wav", chime())
    print("saved", OUT)
