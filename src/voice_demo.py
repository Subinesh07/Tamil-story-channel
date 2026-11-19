"""Voice demo: the same Tamil paragraph in several voices, saved to voice_demos/ to compare by ear.

python src/voice_demo.py          (run by the "Voice demo" workflow)
"""
import asyncio
import base64
import logging
import os
import re
import subprocess
import sys

import requests

from config import ROOT

log = logging.getLogger("voice_demo")
OUT = ROOT / "voice_demos"
TEXT = ("ஷாலினி கையில லேப்டாப் பேக்கோட ரொம்ப டயர்டா வீட்டுக்குள்ள வந்தா. "
        "அபிராமி அவளை ஒரு மாதிரி பார்த்துட்டு, முகத்தை திருப்பிக்கிட்டாங்க. "
        "\"இப்போ தான் வர்றியா? வீட்ல ஒரு வேலையும் ஆகல!\" அப்படின்னு கத்தினாங்க. "
        "ஷாலினி எதுவும் பேசல. அவ கண்ணுல லேசா தண்ணி வந்துச்சு. "
        "ஆனா அவளுக்கு மட்டும் தான் தெரியும், அந்த வீட்டோட கடனை யாரு கட்டிட்டு இருக்காங்கன்னு. "
        "அன்னைக்கு ராத்திரி, ஒரு பழைய கவர் அபிராமி கையில கிடைச்சுது. அதுக்குள்ள இருந்தது என்ன தெரியுமா?")
STYLE = ("Read this Tamil story aloud like a warm, emotional storyteller from Tamil Nadu: natural "
         "conversational pace, expressive, rising on questions, softer on sad lines, lively on dialogue")
GEMINI_VOICES = ["Kore", "Aoede", "Leda", "Zephyr", "Sulafat"]


def to_mp3(src, dst, fmt_args=()):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *fmt_args, "-i", str(src), "-b:a", "128k", str(dst)],
                   check=True)


async def edge(rate, path):
    import edge_tts
    await edge_tts.Communicate(TEXT, "ta-IN-PallaviNeural", rate=rate).save(str(path))


def gemini_tts_model(key):
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=60)
    r.raise_for_status()
    names = [m["name"].split("/")[-1] for m in r.json().get("models", []) if "tts" in m["name"]]
    flash = [n for n in names if "flash" in n] or names
    flash.sort(key=lambda n: [-int(x) for x in re.findall(r"\d+", n)[:2]])
    return flash[0] if flash else None


def gemini(model, voice, key, path):
    body = {"contents": [{"parts": [{"text": f"{STYLE}:\n\n{TEXT}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      headers={"x-goog-api-key": key}, json=body, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = path.with_suffix(".pcm")
    pcm.write_bytes(base64.b64decode(part["data"]))
    rate = re.search(r"rate=(\d+)", part.get("mimeType", "")) or None
    to_mp3(pcm, path, ["-f", "s16le", "-ar", rate.group(1) if rate else "24000", "-ac", "1"])
    pcm.unlink()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    OUT.mkdir(exist_ok=True)
    made = []
    for rate in ["+8%", "+20%", "+30%"]:
        p = OUT / f"1_pallavi_{rate.strip('+%')}pct.mp3"
        try:
            asyncio.run(edge(rate, p))
            made.append(p.name)
        except Exception as e:
            log.warning("Pallavi %s failed: %s", rate, e)
    key = os.environ.get("LLM_API_KEY", "")
    if key:
        model = gemini_tts_model(key)
        log.info("Gemini TTS model: %s", model)
        for v in GEMINI_VOICES if model else []:
            p = OUT / f"2_gemini_{v.lower()}.mp3"
            try:
                gemini(model, v, key, p)
                made.append(p.name)
            except Exception as e:
                log.warning("Gemini voice %s failed: %s", v, str(e)[:200])
    (OUT / "README.md").write_text(
        "# Voice demos\nSame paragraph, different voices. Tap a file, then **View raw** (or the "
        "download button) to play it.\n\n" + "\n".join(f"- [{n}]({n})" for n in made) + "\n",
        encoding="utf-8")
    log.info("Made %d demos: %s", len(made), ", ".join(made))
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
