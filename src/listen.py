"""Write out, word by word, what is spoken in a stretch of a finished video (Gemini listens).
Usage: python src/listen.py <row_id> <start_sec> <end_sec>   (video taken from the 'videos' release)"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models"


def transcribe(audio_mp3, keys):
    b64 = base64.b64encode(Path(audio_mp3).read_bytes()).decode()
    prompt = ("Transcribe EXACTLY what is spoken in this audio, word for word, in the language spoken "
              "(Tamil in Tamil letters, English in English letters). Do not translate, do not summarise, "
              "do not fix anything. Mark each English sentence with [EN]. Return only the transcript.")
    last = ""
    for k in keys:
        for model in ("gemini-3.5-flash", "gemini-3-flash", "gemini-2.5-flash"):
            r = requests.post(f"{API}/{model}:generateContent", headers={"x-goog-api-key": k}, timeout=300,
                              json={"contents": [{"parts": [{"inline_data": {"mime_type": "audio/mp3", "data": b64}},
                                                            {"text": prompt}]}]})
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            last = f"{model} HTTP {r.status_code}"
    raise SystemExit("could not listen: " + last)


def main():
    rid, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    keys = [os.environ[k] for k in ("CHECK_API_KEY", "CHECK_API_KEY_2", "LLM_API_KEY", "VOICE_API_KEY_2",
                                    "VOICE_API_KEY") if os.environ.get(k)]
    subprocess.run(["gh", "release", "download", "videos", "-p", f"story_{rid}.mp4", "--clobber"], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-to", str(b), "-i", f"story_{rid}.mp4",
                    "-vn", "-ac", "1", "-b:a", "64k", "clip.mp3"], check=True)
    print(f"TRANSCRIPT {a:.0f}s-{b:.0f}s:\n" + transcribe("clip.mp3", keys))


if __name__ == "__main__":
    main()
