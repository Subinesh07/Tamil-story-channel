"""Pluggable text model for story writing.

LLM_PROVIDER = gemini (default, free tier) | anthropic (paid)
LLM_API_KEY  = the provider's key (GitHub secret)
LLM_MODEL    = optional model override
"""
import json
import logging
import os
import re
import time

import requests

log = logging.getLogger(__name__)
DEFAULT_MODELS = {"gemini": "gemini-3.8-flash", "anthropic": "claude-sonnet-5-5"}
_resolved = {}


def _latest_gemini_flash(key):
    """Ask Google which models this key can use and pick the newest plain 'flash' text model."""
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=60)
    r.raise_for_status()
    names = []
    for m in r.json().get("models", []):
        name = m["name"].split("/")[-1]
        if ("generateContent" in m.get("supportedGenerationMethods", [])
                and re.fullmatch(r"gemini-[\d.]+-flash", name)):
            names.append(name)
    if not names:
        raise LLMError("no Gemini flash model available for this key")
    def version(n):
        return [int(x) for x in re.findall(r"\d+", n)]
    return max(names, key=version)


class LLMError(RuntimeError):
    pass


def _gemini(prompt, model, key, want_json, max_tokens):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    cfg = {"temperature": 0.9, "maxOutputTokens": max_tokens}
    if want_json:
        cfg["responseMimeType"] = "application/json"
    r = requests.post(url, headers={"x-goog-api-key": key},
                      json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg},
                      timeout=300)
    if r.status_code == 429:
        raise LLMError("RATE_LIMIT: Gemini free-tier quota reached for today")
    if r.status_code in (500, 502, 503, 504):
        raise LLMError(f"BUSY: Gemini HTTP {r.status_code} (servers overloaded)")
    if r.status_code != 200:
        raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    try:
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError):
        raise LLMError(f"Gemini returned no text: {str(data)[:300]}")


def _anthropic(prompt, model, key, want_json, max_tokens):
    if want_json:
        prompt += "\n\nReturn only valid JSON, with no markdown fences."
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                               "content-type": "application/json"},
                      json={"model": model, "max_tokens": max_tokens,
                            "messages": [{"role": "user", "content": prompt}]},
                      timeout=600)
    if r.status_code == 429:
        raise LLMError("RATE_LIMIT: Anthropic rate limit")
    if r.status_code != 200:
        raise LLMError(f"Anthropic HTTP {r.status_code}: {r.text[:300]}")
    return "".join(b.get("text", "") for b in r.json()["content"] if b["type"] == "text")


def complete(prompt, want_json=False, max_tokens=32000, retries=5):
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    key = os.environ.get("LLM_API_KEY", "")
    if not key:
        raise LLMError("LLM_API_KEY is not set")
    model = _resolved.get(provider) or os.environ.get("LLM_MODEL") or DEFAULT_MODELS[provider]
    fn = {"gemini": _gemini, "anthropic": _anthropic}[provider]
    last = None
    for attempt in range(retries):
        try:
            text = fn(prompt, model, key, want_json, max_tokens)
            _resolved[provider] = model
            return parse_json(text) if want_json else text
        except LLMError as e:
            if str(e).startswith("RATE_LIMIT"):
                raise
            if provider == "gemini" and "HTTP 404" in str(e):
                # model retired: switch to the newest flash model this key can use
                new = _latest_gemini_flash(key)
                if new != model:
                    log.warning("Gemini model %s unavailable, switching to %s", model, new)
                    model = _resolved[provider] = new
                    continue
            last = e
        except (ValueError, requests.RequestException) as e:
            last = e
        log.warning("LLM attempt %d failed: %s", attempt + 1, str(last)[:200])
        busy = str(last).startswith("BUSY") or isinstance(last, requests.RequestException)
        time.sleep((30 if busy else 10) * 2 ** attempt if busy else 10 * (attempt + 1))
    if str(last).startswith("BUSY") or isinstance(last, requests.RequestException):
        raise LLMError(f"BUSY: {last}")
    raise LLMError(str(last))


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)
