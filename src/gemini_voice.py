"""Gemini "Leda" narration: long passages per request (few requests), cached between runs,
and sentence timings recovered from the natural pauses in the audio.

Never mixes voices: if the daily free limit runs out, GeminiQuota is raised, the chunks voiced
so far stay in the cache, and the next run continues with the same voice.
"""
import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import time
import wave

import numpy as np
import requests

from config import GEMINI_CHUNK_CHARS, GEMINI_STYLE, GEMINI_TEMPO, GEMINI_VOICE, TTS_CACHE

log = logging.getLogger(__name__)
API = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiQuota(RuntimeError):
    pass


def _key():
    k = os.environ.get("LLM_API_KEY", "").strip()
    if not k:
        raise GeminiQuota("LLM_API_KEY not set")
    return k


def tts_model(key):
    r = requests.get(API, headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=60)
    r.raise_for_status()
    names = [m["name"].split("/")[-1] for m in r.json().get("models", []) if "tts" in m["name"]]
    names = [n for n in names if "lite" not in n] or names
    names.sort(key=lambda n: ("preview" in n, [-int(x) for x in re.findall(r"\d+", n)[:2]]))
    if not names:
        raise GeminiQuota("no Gemini TTS model available for this key")
    return names[0]


def chunks_for(sentences):
    """Group sentence indexes into long passages (fewer requests)."""
    out, cur, chars = [], [], 0
    for i, s in enumerate(sentences):
        if cur and chars + len(s) > GEMINI_CHUNK_CHARS:
            out.append(cur)
            cur, chars = [], 0
        cur.append(i)
        chars += len(s) + 1
    if cur:
        out.append(cur)
    return out


def _punct(s):
    s = s.strip()
    return s if re.search(r"[.!?…]$", s) else s + "."


def _request(model, key, text):
    body = {"contents": [{"parts": [{"text": f"{GEMINI_STYLE}:\n\n{text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_VOICE}}}}}
    for attempt in range(4):
        r = requests.post(f"{API}/{model}:generateContent", headers={"x-goog-api-key": key},
                          json=body, timeout=600)
        if r.status_code == 200:
            part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
            rate = re.search(r"rate=(\d+)", part.get("mimeType", ""))
            return base64.b64decode(part["data"]), int(rate.group(1)) if rate else 24000
        if r.status_code == 429:
            raise GeminiQuota(f"Gemini voice daily limit reached: {r.text[:160]}")
        log.warning("Gemini TTS HTTP %d (attempt %d): %s", r.status_code, attempt + 1, r.text[:160])
        time.sleep(20 * (attempt + 1))
    raise RuntimeError("Gemini TTS kept failing")


def _pcm_to_wav(pcm, rate, out_wav):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0",
                    "-af", f"atempo={GEMINI_TEMPO}", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
                    str(out_wav)], input=pcm, check=True)


def _read_mono(path):
    with wave.open(str(path)) as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        x = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768
    return (x.reshape(-1, ch).mean(axis=1) if ch > 1 else x), sr


def _letters(s):
    return len(re.sub(r"[^\w஀-௿]|_", "", s))


def align_by_pauses(wav_path, sentences):
    """Sentence spans [(start, end)] in seconds inside one passage: estimate boundaries from
    letter counts, then snap each to the nearest real pause in the audio."""
    x, sr = _read_mono(wav_path)
    hop = int(0.01 * sr)
    n = len(x) // hop
    e = np.sqrt(np.mean(x[:n * hop].reshape(n, hop) ** 2, axis=1)) + 1e-9
    db = 20 * np.log10(e)
    voiced = db > (np.percentile(db, 95) - 32)
    idx = np.where(voiced)[0]
    if len(idx) == 0:
        raise RuntimeError("silent audio")
    t0, t1 = idx[0] * 0.01, (idx[-1] + 1) * 0.01
    # pauses = runs of silence >= 0.12 s inside the speech
    pauses, run_start = [], None
    for i in range(idx[0], idx[-1] + 1):
        if not voiced[i]:
            run_start = i if run_start is None else run_start
        elif run_start is not None:
            if (i - run_start) * 0.01 >= 0.12:
                pauses.append((run_start * 0.01, i * 0.01))
            run_start = None
    weights = np.array([max(1, _letters(s)) for s in sentences], dtype=float)
    cum = np.cumsum(weights)[:-1] / weights.sum()
    estimates = t0 + cum * (t1 - t0)
    avg = (t1 - t0) / len(sentences)
    bounds, last = [], t0
    for est in estimates:
        win = max(1.0, 0.45 * avg)
        cands = [p for p in pauses if p[0] > last + 0.3 and abs((p[0] + p[1]) / 2 - est) <= win]
        if cands:
            p = min(cands, key=lambda p: (abs((p[0] + p[1]) / 2 - est), -(p[1] - p[0])))
            bounds.append(p)
            last = p[1]
        else:
            bounds.append((est, est))
            last = est
    spans, start = [], t0
    for (ps, pe) in bounds:
        spans.append((round(start, 3), round(max(ps, start + 0.2), 3)))
        start = pe
    spans.append((round(start, 3), round(t1, 3)))
    return spans


def synthesize(sentences, cache_key):
    """Voice all sentences with Leda. Returns pieces [(wav, [(idx, start, end)])].
    Raises GeminiQuota if the daily limit stops it (finished passages stay cached)."""
    key = _key()
    cache = TTS_CACHE / cache_key
    cache.mkdir(parents=True, exist_ok=True)
    model = None
    pieces, made = [], 0
    for k, idxs in enumerate(chunks_for(sentences)):
        text = " ".join(_punct(sentences[i]) for i in idxs)
        h = hashlib.sha1(f"{GEMINI_VOICE}|{GEMINI_STYLE}|{GEMINI_TEMPO}|{text}".encode()).hexdigest()[:16]
        wav = cache / f"c{k:03d}_{h}.wav"
        if not wav.exists():
            model = model or tts_model(key)
            log.info("Leda: voicing passage %d (%d sentences, %d chars) with %s", k + 1, len(idxs), len(text), model)
            pcm, rate = _request(model, key, text)
            _pcm_to_wav(pcm, rate, wav)
            made += 1
        spans = align_by_pauses(wav, [sentences[i] for i in idxs])
        pieces.append((wav, [(i, s, e) for i, (s, e) in zip(idxs, spans)]))
    log.info("Leda: %d passages (%d new requests, %d from cache)", len(pieces), made, len(pieces) - made)
    (cache / "done.json").write_text(json.dumps({"passages": len(pieces)}))
    return pieces
