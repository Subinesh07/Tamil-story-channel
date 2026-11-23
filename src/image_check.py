"""Automatic image checker: a free vision model rejects broken or wrong pictures.

Uses the Gemini key (LLM_API_KEY). If no key is set or the service is busy, the check is
skipped (the image is accepted) so a video is never blocked by the checker itself.
"""
import base64
import json
import logging
import os
import re
import time

import requests

log = logging.getLogger(__name__)
_model = None
_disabled = False   # set after Gemini says "too many requests": stop checking for this run
_fails = 0          # consecutive failures; after 3 the checker switches off for this run

QUESTION = """You are a strict quality checker for pictures in a Tamil story video.
The picture was requested with this description:
"{prompt}"

While this picture is on screen, the narrator says (Tamil):
"{context}"

Reject it (ok=false) if ANY of these is true:
- HANDS: look at every visible hand. Reject any hand with more or fewer than five fingers, fused or
  merged hands, two hands joined together, an extra hand or arm, a hand not attached to an arm
- deformed people: missing head, headless or disembodied body parts, extra or missing limbs,
  distorted, melted or duplicated faces, a face pasted on the wrong body, twisted necks or bodies
- a person's head or face is cut off by the edge of the picture
- the number of people differs from the description, or random extra figures appear
- the action or positions differ from the description (who is sitting, standing, lying, driving,
  pointing, holding what, who is inside or outside a car / room)
- a person's age clearly does not match (a child or teenager drawn for an adult, an adult for a
  child, a young person for an elderly one; allow about plus or minus 8 years)
- appearance contradicts the description: facial hair (beard / moustache only / clean-shaven),
  glasses or no glasses, hair style, clothes colour
- deformed objects (merged wheels, melted furniture, broken weapons)
- visible text, letters, watermarks or logos
- the picture does not show the described moment, or contradicts what the narrator says: places,
  vehicles and objects the narration says are there now (car, road, tower, temple, gun, letter) must be
  visible; people must be where the narration puts them (inside the car, on the floor, at the door);
  the person speaking or acting must be the right one
- anything illogical a normal viewer would notice (floating objects, impossible poses, wrong lighting
  for the time of day said in the narration, two copies of the same person)

Answer only JSON: {{"ok": true or false, "problem": "short reason or empty"}}"""


def _pick_model(key):
    global _model
    if _model is None:
        from llm import gemini_models
        models = gemini_models(key)
        _model = models[0] if models else ""
    return _model


class CheckUnavailable(Exception):
    """The checker could not run: the picture must NOT be used unchecked (the video waits)."""


_last_call = [0.0]


def _keys():
    seen, out = set(), []
    for name in ("LLM_API_KEY", "VOICE_API_KEY_2", "VOICE_API_KEY"):
        k = os.environ.get(name, "").strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def check(png_bytes, prompt, context=""):
    """Return (ok, reason). Raises CheckUnavailable if no check is possible - never accepts unchecked."""
    if os.environ.get("IMAGE_CHECK", "on") == "off":
        return True, "check switched off by setting"
    if "No people in the picture" in prompt:
        return True, "check skipped (no people: low risk)"
    keys = _keys()
    if not keys:
        raise CheckUnavailable("no Gemini key for the picture checker")
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png_bytes).decode()}},
            {"text": QUESTION.format(prompt=prompt[:1200], context=(context or "(not given)")[:700])},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 300},
    }
    last = ""
    for rnd in range(5):                    # free tier: a few requests per minute - be patient
        for key in keys:
            wait = 4.5 - (time.time() - _last_call[0])
            if wait > 0:
                time.sleep(wait)
            _last_call[0] = time.time()
            try:
                model = _pick_model(key)
                if not model:
                    last = "no vision model"
                    continue
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": key}, json=body, timeout=40)
            except Exception as e:
                last = str(e)[:80]
                continue
            if r.status_code == 200:
                try:
                    text = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
                    verdict = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()))
                    return bool(verdict.get("ok", False)), verdict.get("problem", "")
                except Exception as e:
                    last = f"unreadable answer ({str(e)[:60]})"
                    continue
            last = f"HTTP {r.status_code}"
        log.info("Picture checker busy (%s); waiting a minute (round %d/5)", last, rnd + 1)
        time.sleep(65)
    raise CheckUnavailable(f"picture checker unavailable ({last}); waiting instead of using unchecked pictures")
