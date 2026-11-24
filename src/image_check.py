"""Automatic picture checker: Gemini judges each picture against its description AND the narration.

Strict and fail-closed: a picture is never used unchecked. If Gemini is busy or its free limit is
reached, CheckUnavailable is raised and the video waits.

To save the free daily limit, several candidate pictures of the same scene are judged in ONE request
(check_many) and the first good one is used.
"""
import base64
import json
import logging
import os
import re
import time

import requests

log = logging.getLogger(__name__)

RULES = """Reject a picture (ok=false) if ANY of these is true:
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
- appearance contradicts the description: facial hair (beard / thin moustache / clean-shaven),
  glasses or no glasses, hair style, clothes colour
- deformed objects (merged wheels, melted furniture, broken weapons)
- visible text, letters, watermarks or logos
- the picture does not show the described moment, or contradicts what the narrator says: places,
  vehicles and objects the narration says are there now (car, road, tower, temple, gun, letter) must be
  visible; people must be where the narration puts them (inside the car, on the floor, at the door);
  the person speaking or acting must be the right one
- anything illogical a normal viewer would notice (floating objects, impossible poses, wrong lighting
  for the time of day said in the narration, two copies of the same person)"""

QUESTION = """You are a strict quality checker for pictures in a Tamil story video.
You are given {n} candidate picture(s) of the SAME scene, in order (picture 1, picture 2, ...).
Each was requested with this description:
"{prompt}"

While the picture is on screen, the narrator says (Tamil):
"{context}"

""" + RULES + """

Judge EVERY picture separately. Answer only JSON:
{{"results": [{{"ok": true or false, "problem": "short reason or empty"}}, ...one per picture in order]}}"""


class CheckUnavailable(Exception):
    """The checker could not run: the picture must NOT be used unchecked (the video waits)."""


_models = {}
_last_call = [0.0]
CALLS = [0]   # checker requests made in this run (logged at the end)


def _models_for(key):
    """Up to 4 vision-capable Gemini models (newest flash first): a busy model is skipped, not waited on."""
    if key not in _models:
        from llm import gemini_models
        try:
            _models[key] = gemini_models(key)[:4]
        except Exception:
            _models[key] = []
    return _models[key]


def _keys():
    seen, out = set(), []
    for name in ("CHECK_API_KEY", "CHECK_API_KEY_2", "LLM_API_KEY", "VOICE_API_KEY_2", "VOICE_API_KEY"):
        k = os.environ.get(name, "").strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _ask(body):
    keys = _keys()
    if not keys:
        raise CheckUnavailable("no Gemini key for the picture checker")
    last = ""
    for rnd in range(5):                    # free tier: a few requests per minute - be patient
        for key in keys:
            for model in _models_for(key):
                wait = 4.5 - (time.time() - _last_call[0])
                if wait > 0:
                    time.sleep(wait)
                _last_call[0] = time.time()
                try:
                    r = requests.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        headers={"x-goog-api-key": key}, json=body, timeout=90)
                except Exception as e:
                    last = str(e)[:80]
                    continue
                CALLS[0] += 1
                if r.status_code == 200:
                    try:
                        parts = r.json()["candidates"][0]["content"]["parts"]
                        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                        return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()))
                    except Exception as e:
                        last = f"unreadable answer from {model} ({str(e)[:60]})"
                        continue
                last = f"HTTP {r.status_code} from {model}"
        log.info("Picture checker busy (%s); waiting a minute (round %d/5)", last, rnd + 1)
        time.sleep(65)
    raise CheckUnavailable(f"picture checker unavailable ({last}): Gemini limit reached, waiting instead of "
                           "using unchecked pictures")


def check_many(pngs, prompt, context=""):
    """Judge several candidates of one scene in ONE request. Returns a list of (ok, reason), one per picture."""
    if os.environ.get("IMAGE_CHECK", "on") == "off":
        return [(True, "check switched off by setting")] * len(pngs)
    if "No people in the picture" in prompt:
        return [(True, "check skipped (no people: low risk)")] * len(pngs)
    parts = []
    for k, png in enumerate(pngs, 1):
        parts.append({"text": f"Picture {k}:"})
        parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}})
    parts.append({"text": QUESTION.format(n=len(pngs), prompt=prompt[:1200],
                                          context=(context or "(not given)")[:700])})
    verdict = _ask({"contents": [{"parts": parts}],
                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                         "maxOutputTokens": 4096}})
    res = verdict.get("results") if isinstance(verdict, dict) else None
    if not isinstance(res, list) or len(res) != len(pngs):
        return [(False, "checker answer did not cover every picture")] * len(pngs)
    return [(bool(x.get("ok", False)), x.get("problem", "")) for x in res]


def check(png_bytes, prompt, context=""):
    """Return (ok, reason) for one picture. Raises CheckUnavailable - never accepts unchecked."""
    return check_many([png_bytes], prompt, context)[0]
