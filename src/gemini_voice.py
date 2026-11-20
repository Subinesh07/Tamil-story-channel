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


class VoiceCheckFailed(GeminiQuota):
    """A voiced passage was not clean Tamil matching the script even after re-voicing: wait."""


def _listen_models(key):
    """Text models that can listen to audio (non-lite Flash first)."""
    from llm import gemini_models
    names = gemini_models(key)
    return [n for n in names if "lite" not in n] + [n for n in names if "lite" in n]


def verify_passage(wav, text, key):
    """Gemini listens to the voiced passage. Returns (ok, reason).
    Catches Leda switching to English, reading the instructions aloud, skipping or adding lines."""
    mp3 = wav.with_suffix(".check.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ac", "1", "-ar", "16000", "-b:a", "32k",
                    str(mp3)], check=True)
    audio = base64.b64encode(mp3.read_bytes()).decode()
    mp3.unlink(missing_ok=True)
    prompt = ("You are a strict quality checker for a Tamil YouTube story narration. Listen to the WHOLE "
              "audio and compare it with the script below. English words that are written in Tamil letters "
              "in the script (like ஆபீஸ், போன்) are fine. Return JSON: {\"tamil_only\": true/false (false if "
              "any full English sentence or English narration is spoken), \"english_seconds\": number, "
              "\"follows_script\": true/false (false if lines are skipped, added, translated or the "
              "instructions are read aloud), \"problem\": \"short description or empty\"}\n\nSCRIPT:\n" + text)
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": "audio/mp3", "data": audio}},
                                    {"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    last = ""
    try:
        models = _listen_models(key)[:4]
    except Exception as e:
        raise GeminiQuota(f"voice check could not list models ({str(e)[:100]}); will retry next run")
    for model in models:
        try:
            r = requests.post(f"{API}/{model}:generateContent", headers={"x-goog-api-key": key},
                              json=body, timeout=300)
            if r.status_code != 200:
                last = f"{model} HTTP {r.status_code}"
                continue
            parts = r.json()["candidates"][0]["content"]["parts"]
            v = json.loads("".join(p.get("text", "") for p in parts if not p.get("thought")))
            ok = bool(v.get("tamil_only")) and float(v.get("english_seconds") or 0) <= 3 \
                and bool(v.get("follows_script"))
            return ok, str(v.get("problem") or "")[:150] if not ok else ""
        except Exception as e:
            last = f"{model}: {str(e)[:100]}"
    raise GeminiQuota(f"voice check could not run ({last}); will retry next run")


def _keys():
    """Leda keys in order: VOICE_API_KEY_1..3 (extra accounts), then LLM_API_KEY.
    The same Leda voice is used on every key, so switching keys never changes how it sounds."""
    names = ["VOICE_API_KEY", "VOICE_API_KEY_2", "VOICE_API_KEY_3", "LLM_API_KEY"]
    keys = []
    for n in names:
        k = os.environ.get(n, "").strip()
        if k and k not in keys:
            keys.append(k)
    if not keys:
        raise GeminiQuota("no Gemini key set (VOICE_API_KEY or LLM_API_KEY)")
    return keys


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
    keys = _keys()
    key = keys.pop(0)
    cache = TTS_CACHE / cache_key
    cache.mkdir(parents=True, exist_ok=True)
    model = None
    pieces, made = [], 0
    for k, idxs in enumerate(chunks_for(sentences)):
        text = " ".join(_punct(sentences[i]) for i in idxs)
        h = hashlib.sha1(f"{GEMINI_VOICE}|{GEMINI_STYLE}|{GEMINI_TEMPO}|{text}".encode()).hexdigest()[:16]
        wav = cache / f"c{k:03d}_{h}.wav"
        checked = wav.with_suffix(".ok")
        tries = 0
        while not checked.exists():
          if not wav.exists():
            while True:
                try:
                    model = model or tts_model(key)
                    log.info("Leda: voicing passage %d (%d sentences, %d chars) with %s", k + 1, len(idxs),
                             len(text), model)
                    pcm, rate = _request(model, key, text)
                    break
                except GeminiQuota as e:
                    if not keys:
                        raise
                    log.warning("%s; switching to the next Leda key", str(e)[:120])
                    key, model = keys.pop(0), None
            _pcm_to_wav(pcm, rate, wav)
            made += 1
          ok, why = verify_passage(wav, text, key)
          if ok:
              checked.write_text("ok")
              log.info("Leda: passage %d passed the listening check", k + 1)
              break
          tries += 1
          log.warning("Leda: passage %d failed the listening check (%s); voicing it again", k + 1, why)
          wav.unlink(missing_ok=True)
          if tries >= 3:
              raise VoiceCheckFailed(f"passage {k + 1} kept failing the listening check: {why}")
        spans = align_by_pauses(wav, [sentences[i] for i in idxs])
        pieces.append((wav, [(i, s, e) for i, (s, e) in zip(idxs, spans)]))
    log.info("Leda: %d passages (%d new requests, %d from cache)", len(pieces), made, len(pieces) - made)
    (cache / "done.json").write_text(json.dumps({"passages": len(pieces)}))
    return pieces
