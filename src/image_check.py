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

QUESTION = """You are checking an illustration for a family story video.
The illustration was requested with this description:
"{prompt}"

Reject it if ANY of these is true:
- a deformed or broken object (e.g. bicycle with missing/merged wheels, melted furniture)
- deformed people: extra or missing limbs, extra fingers, distorted or duplicated faces
- people who should not be there (more people than described, random extra figures)
- a person's age clearly does not match the description (a child drawn for an adult, an adult
  for a child, a young person for an elderly one; allow about ±10 years)
- facial hair contradicts the description (beard when it says "NO beard" or "clean-shaven",
  no beard when it says "beard")
- visible text, letters, watermarks or logos
- it clearly does not match the description

Answer only JSON: {{"ok": true or false, "problem": "short reason or empty"}}"""


def _pick_model(key):
    global _model
    if _model is None:
        from llm import gemini_models
        models = gemini_models(key)
        _model = models[0] if models else ""
    return _model


def check(png_bytes, prompt):
    """Return (ok, reason)."""
    global _disabled, _fails
    key = os.environ.get("LLM_API_KEY", "")
    if not key or os.environ.get("IMAGE_CHECK", "on") == "off":
        return True, "check skipped (no key)"
    if _disabled:
        return True, "check skipped (Gemini limit reached this run)"
    if "No people in the picture" in prompt:
        return True, "check skipped (no people: low risk)"   # save Gemini quota
    try:
        model = _pick_model(key)
        if not model:
            return True, "check skipped (no vision model)"
        body = {
            "contents": [{"parts": [
                {"inline_data": {"mime_type": "image/png",
                                 "data": base64.b64encode(png_bytes).decode()}},
                {"text": QUESTION.format(prompt=prompt[:900])},
            ]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                 "maxOutputTokens": 300},
        }
        for attempt in range(1):
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key}, json=body, timeout=20)
            if r.status_code not in (429, 503):
                break
            time.sleep(30)   # free tier: a few requests per minute
        if r.status_code == 429:
            _disabled = True
            log.warning("Gemini image-check limit reached; remaining images are not checked")
        if r.status_code != 200:
            _fails += 1
            if _fails >= 3:
                _disabled = True
                log.warning("Gemini busy: image checks switched off for the rest of this run")
            return True, f"check skipped (HTTP {r.status_code})"
        _fails = 0
        text = "".join(p.get("text", "") for p in
                       r.json()["candidates"][0]["content"]["parts"])
        verdict = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()))
        return bool(verdict.get("ok", True)), verdict.get("problem", "")
    except Exception as e:  # never block a video because the checker failed
        _fails += 1
        if _fails >= 3:
            _disabled = True
        log.warning("Image check skipped: %s", str(e)[:120])
        return True, "check skipped (error)"
