"""Which language is SPOKEN in each stretch of audio? Uses Whisper (speech recognition, plain code - it does not
translate or judge). Usage: python src/langcheck.py <file.mp4|wav> [window_seconds]
Prints one line per window: start time, language, confidence."""
import subprocess
import sys

import numpy as np
from faster_whisper import WhisperModel


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


_MODEL = None


def english_windows(path, win=5, threshold=0.5, skip_start=0, skip_end=0):
    """Every stretch where Whisper hears English. 27 Nov: Leda read our English instructions aloud at 3:45-4:02;
    Whisper flagged it at 76-90% while Gemini's own checks said 'all Tamil'. Returns [(start_sec, english_prob)]."""
    global _MODEL
    _MODEL = _MODEL or WhisperModel("small", device="cpu", compute_type="int8")
    audio = load(str(path))
    bad = []
    total = len(audio) // 16000
    for start in range(skip_start, max(1, total - 1 - skip_end), win):
        seg = audio[start * 16000:(start + win) * 16000]
        if len(seg) < 16000 * 2 or float(np.abs(seg).mean()) < 0.003:   # too short or silence/music only
            continue
        lang, prob, probs = _MODEL.detect_language(seg)
        en = dict(probs).get("en", 0.0)
        if lang == "en" and en >= threshold:   # top language English, clearly
            bad.append((start, round(en, 2)))
    return bad


EN_WORDS = ("story", "teller", "tamil", "warm", "storyteller", "narrat", "speak", "like a")


def english_strict(path, skip_start=0, skip_end=0):
    """28 Nov 2026: 'Tamil storyteller' (about 1 second) inside Tamil speech slipped past the 5-second check.
    Two extra listens: (a) 2-second steps, 1 second apart, flag English at a lower bar; (b) Whisper writes down
    what it hears and any English word in Latin letters (or the words of our old instructions) fails the passage."""
    import re as _re
    global _MODEL
    _MODEL = _MODEL or WhisperModel("small", device="cpu", compute_type="int8")
    audio = load(str(path))
    total = len(audio) / 16000
    bad, hits = [], []
    t = float(skip_start)
    while t + 2 <= total - skip_end:
        seg = audio[int(t * 16000):int((t + 2) * 16000)]
        if float(np.abs(seg).mean()) >= 0.003:
            lang, prob, probs = _MODEL.detect_language(seg)
            en = dict(probs).get("en", 0.0)
            if (lang == "en" and en >= 0.4) or en >= 0.6:
                hits.append(int(t))
        t += 1.0
    # English loanwords written in Tamil (ப்ளீஸ், ஸ்டோர் ரூம்) are fine: need 2 English windows in a row
    bad += [(h, 0.9) for h in hits if h + 1 in hits]
    a = int(skip_start * 16000)
    b = int((total - skip_end) * 16000)
    segs, _ = _MODEL.transcribe(audio[a:b], task="transcribe", vad_filter=False)
    for sg in segs:
        txt = sg.text.lower()
        latin = _re.findall(r"[a-z]{3,}", txt)
        if any(e in txt for e in EN_WORDS if " " in e) or any(w.startswith(e) for w in latin for e in EN_WORDS):
            bad.append((int(skip_start + sg.start), 1.0))
    return sorted(set(bad))


def windows_range(path, a, b, win, model):
    audio = load(path)
    out = []
    t = a
    while t + win <= b:
        lang, prob, probs = model.detect_language(audio[int(t * 16000):int((t + win) * 16000)])
        out.append((t, lang, prob, dict(probs).get("en", 0.0)))
        t += win
    return out


def windows(path, win=20, model=None):
    model = model or WhisperModel("small", device="cpu", compute_type="int8")
    audio = load(path)
    out = []
    for start in range(0, len(audio) // 16000, win):
        seg = audio[start * 16000:(start + win) * 16000]
        if len(seg) < 16000 * 3:
            break
        lang, prob, probs = model.detect_language(seg)
        en = dict(probs).get("en", 0.0)
        out.append((start, lang, prob, en))
    return out


def words(path, a, b, model=None):
    """What Whisper hears between a and b seconds, in the language it detects (no translation)."""
    model = model or WhisperModel("small", device="cpu", compute_type="int8")
    audio = load(path)[int(a * 16000):int(b * 16000)]
    segs, info = model.transcribe(audio, task="transcribe", vad_filter=False)
    return [(a + s.start, a + s.end, s.text.strip()) for s in segs]


if __name__ == "__main__":
    if len(sys.argv) > 3:   # zoom: python langcheck.py file start end
        f, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
        m = WhisperModel("small", device="cpu", compute_type="int8")
        for start, lang, prob, en in windows_range(f, a, b, 5, m):
            print(f"ZOOM {int(start) // 60}:{int(start) % 60:02d}  {lang} {prob:.2f} (english {en:.2f})")
        for s0, s1, t in words(f, a, b, m):
            print(f"HEARD {int(s0) // 60}:{int(s0) % 60:02d}-{int(s1) // 60}:{int(s1) % 60:02d}  {t}")
        sys.exit(0)
    if len(sys.argv) > 2 and sys.argv[2] == "strict":
        found = english_strict(sys.argv[1], skip_start=3, skip_end=25)
        print("STRICT", ", ".join(f"{s // 60}:{s % 60:02d}" for s, _ in found) or "clean")
        sys.exit(0)
    win = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    for start, lang, prob, en in windows(sys.argv[1], win):
        flag = "  <<< ENGLISH" if lang == "en" or en > 0.3 else ""
        print(f"LANG {start // 60}:{start % 60:02d}  {lang} {prob:.2f}  (english {en:.2f}){flag}")
