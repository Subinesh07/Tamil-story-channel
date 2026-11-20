"""Free-first text model chain for story writing.

Every request tries the providers in order and moves to the next one when a provider is
busy, out of free quota, or broken. Only providers with a key set are used.

  GEMINI   key: LLM_API_KEY          (Google AI Studio, free tier)
  OPENROUTER key: OPENROUTER_API_KEY (free ":free" models)
  GROQ     key: GROQ_API_KEY         (free tier)
  ANTHROPIC key: ANTHROPIC_API_KEY   (paid, optional; or LLM_PROVIDER=anthropic with LLM_API_KEY)

Order can be changed with LLM_ORDER, e.g. "openrouter,gemini,groq".
"""
import json
import logging
import os
import re
import time

import requests

log = logging.getLogger(__name__)
DEFAULT_ORDER = "gemini,openrouter,groq,anthropic"
TIMEOUT = 300


class LLMError(RuntimeError):
    pass


class Unavailable(LLMError):
    """Busy, out of quota, model gone: try the next model/provider."""


# ---------------------------------------------------------------- helpers

def _check(r, name):
    if r.status_code == 200:
        return
    body = r.text[:300]
    if r.status_code in (401, 403):
        raise Unavailable(f"{name}: key rejected (HTTP {r.status_code})")
    if r.status_code in (404, 410, 429, 500, 502, 503, 504, 529) or "quota" in body.lower():
        raise Unavailable(f"{name}: HTTP {r.status_code} {body[:150]}")
    raise LLMError(f"{name}: HTTP {r.status_code} {body}")


def _version_key(name):
    return [-int(x) for x in re.findall(r"\d+", name)[:3]]


# ---------------------------------------------------------------- Gemini

def gemini_models(key):
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=60)
    _check(r, "gemini")
    found = []
    for m in r.json().get("models", []):
        name = m["name"].split("/")[-1]
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if re.search(r"image|tts|audio|live|embed|vision|robotics|computer|learnlm|gemma", name):
            continue
        kind = re.match(r"gemini-([\d.]+)-(flash-lite|flash|pro)", name)
        if kind:
            # plain names first (gemini-3.8-flash), then -preview/-exp variants
            rank = {"flash": 0, "flash-lite": 1, "pro": 2}[kind.group(2)] * 2 + (name != kind.group(0))
            found.append((rank, _version_key(kind.group(1)), name))
        elif re.fullmatch(r"gemini-(flash|flash-lite|pro)-latest", name):
            found.append((7, [0], name))
    return [n for _, _, n in sorted(found)]


def gemini_call(prompt, model, key, want_json, max_tokens):
    # Gemini 3 "thinking" models spend output tokens on thinking first: give them room
    cfg = {"temperature": 0.9, "maxOutputTokens": max(max_tokens, 60000)}
    if want_json:
        cfg["responseMimeType"] = "application/json"
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key},
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg},
        timeout=TIMEOUT)
    _check(r, f"gemini/{model}")
    data = r.json()
    try:
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError):
        raise Unavailable(f"gemini/{model}: empty answer")


# ---------------------------------------------------------------- OpenAI-compatible (OpenRouter, Groq)

PREFERRED = ["deepseek", "qwen", "gemini", "llama-3.3", "llama-4", "gpt-oss", "gemma", "mistral", "llama"]


def _rank_by_family(names):
    def key(n):
        low = n.lower()
        fam = next((i for i, f in enumerate(PREFERRED) if f in low), len(PREFERRED))
        return (fam, _version_key(low))
    return sorted(names, key=key)


def openrouter_models(key):
    r = requests.get("https://openrouter.ai/api/v1/models", timeout=60)
    _check(r, "openrouter")
    free = []
    for m in r.json().get("data", []):
        p = m.get("pricing", {})
        if (m["id"].endswith(":free") and str(p.get("prompt", "1")) in ("0", "0.0")
                and (m.get("context_length") or 0) >= 32000
                and "text" in m.get("architecture", {}).get("output_modalities", ["text"])):
            free.append(m["id"])
    return _rank_by_family(free)[:6]


def groq_models(key):
    r = requests.get("https://api.groq.com/openai/v1/models",
                     headers={"Authorization": f"Bearer {key}"}, timeout=60)
    _check(r, "groq")
    names = [m["id"] for m in r.json().get("data", [])
             if m.get("active", True) and not re.search(r"whisper|tts|guard|vision|embed", m["id"])]
    return _rank_by_family(names)[:4]


def _openai_style(url, name, prompt, model, key, want_json, max_tokens, extra_headers=None):
    body = {"model": model, "temperature": 0.9, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]}
    if want_json:
        body["messages"][0]["content"] += "\n\nReturn only valid JSON, no markdown fences."
    headers = {"Authorization": f"Bearer {key}", **(extra_headers or {})}
    r = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
    if r.status_code == 400 and "max_tokens" in r.text and max_tokens > 8000:
        return _openai_style(url, name, prompt, model, key, want_json, 8000, extra_headers)
    _check(r, f"{name}/{model}")
    try:
        text = r.json()["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError):
        raise Unavailable(f"{name}/{model}: empty answer")
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def openrouter_call(prompt, model, key, want_json, max_tokens):
    return _openai_style("https://openrouter.ai/api/v1/chat/completions", "openrouter",
                         prompt, model, key, want_json, max_tokens,
                         {"X-Title": "Tamil Story Uploader"})


def groq_call(prompt, model, key, want_json, max_tokens):
    return _openai_style("https://api.groq.com/openai/v1/chat/completions", "groq",
                         prompt, model, key, want_json, min(max_tokens, 32000))


# ---------------------------------------------------------------- Anthropic (paid, optional)

def anthropic_models(key):
    return [os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")]


def anthropic_call(prompt, model, key, want_json, max_tokens):
    if want_json:
        prompt += "\n\nReturn only valid JSON, with no markdown fences."
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                      json={"model": model, "max_tokens": max_tokens,
                            "messages": [{"role": "user", "content": prompt}]},
                      timeout=TIMEOUT)
    _check(r, f"anthropic/{model}")
    return "".join(b.get("text", "") for b in r.json()["content"] if b["type"] == "text")


# ---------------------------------------------------------------- chain

PROVIDERS = {
    "gemini": (lambda: os.environ.get("LLM_API_KEY") if os.environ.get("LLM_PROVIDER", "gemini") == "gemini" else None,
               gemini_models, gemini_call),
    "openrouter": (lambda: os.environ.get("OPENROUTER_API_KEY"), openrouter_models, openrouter_call),
    "groq": (lambda: os.environ.get("GROQ_API_KEY"), groq_models, groq_call),
    "anthropic": (lambda: os.environ.get("ANTHROPIC_API_KEY") or
                  (os.environ.get("LLM_API_KEY") if os.environ.get("LLM_PROVIDER") == "anthropic" else None),
                  anthropic_models, anthropic_call),
}
_model_cache = {}
_benched = {}   # model -> time it failed; skipped for 10 minutes
_last_good = None


def _candidates(providers=None):
    order = [p.strip() for p in (os.environ.get("LLM_ORDER") or DEFAULT_ORDER).split(",") if p.strip()]
    if providers:
        order = [p for p in order if p in providers] or list(providers)
    out = []
    for p in order:
        get_key, list_models, call = PROVIDERS[p]
        key = get_key()
        if not key:
            continue
        if p not in _model_cache:
            try:
                _model_cache[p] = list_models(key)
                log.info("%s models: %s", p, ", ".join(_model_cache[p][:4]) or "none")
            except (LLMError, requests.RequestException) as e:
                log.warning("Could not list %s models: %s", p, str(e)[:150])
                _model_cache[p] = []
        for m in _model_cache[p]:
            out.append((p, m, key, call))
    if not out:
        raise LLMError("No AI model available: check the keys (LLM_API_KEY / OPENROUTER_API_KEY / "
                       "GROQ_API_KEY) and the model lists above")
    return out


def complete(prompt, want_json=False, max_tokens=32000, rounds=3, providers=None):
    """Try every available free model; wait and go round again if all are busy.
    providers=("gemini",) limits a request to strong models (story writing)."""
    global _last_good
    for rnd in range(rounds):
        cands = _candidates(providers)
        if _last_good in [(p, m) for p, m, _, _ in cands]:
            cands.sort(key=lambda c: (c[0], c[1]) != _last_good)
        for provider, model, key, call in cands:
            if time.time() - _benched.get(model, 0) < 600:
                continue
            for attempt in range(2):
                try:
                    text = call(prompt, model, key, want_json, max_tokens)
                    result = parse_json(text) if want_json else text
                    if not want_json and len(text.strip()) < 20:
                        raise Unavailable("too short")
                    if (provider, model) != _last_good:
                        log.info("Using %s / %s", provider, model)
                    _last_good = (provider, model)
                    return result
                except Unavailable as e:
                    log.warning("%s", str(e)[:200])
                    _benched[model] = time.time()
                    break
                except (ValueError, requests.RequestException) as e:
                    log.warning("%s/%s attempt %d: %s", provider, model, attempt + 1, str(e)[:150])
                    time.sleep(10)
            else:
                _benched[model] = time.time()
        wait = 120 * (rnd + 1)
        log.warning("All AI models busy (round %d/%d); waiting %d s", rnd + 1, rounds, wait)
        time.sleep(wait)
        _benched.clear()
    raise LLMError("BUSY: every free AI model is busy or out of quota right now")


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.loads(text[start:])
