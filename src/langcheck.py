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


if __name__ == "__main__":
    win = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    for start, lang, prob, en in windows(sys.argv[1], win):
        flag = "  <<< ENGLISH" if lang == "en" or en > 0.3 else ""
        print(f"LANG {start // 60}:{start % 60:02d}  {lang} {prob:.2f}  (english {en:.2f}){flag}")
