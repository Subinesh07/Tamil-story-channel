"""Phase 3: pluggable image providers.  Every provider implements generate(prompt) -> PNG bytes.

Pick one with the IMAGE_PROVIDER env var:  auto (default) | cloudflare | pollinations | placeholder
auto = Cloudflare Workers AI (free 10,000 units a day, ~150 pictures) first, Pollinations as backup.
When every free allowance is used up, ImageQuota is raised and the video waits for the next run
instead of repeating pictures.
"""
import hashlib
import io
import logging
import os
import re
import time
import urllib.parse
from pathlib import Path

from PIL import Image, ImageDraw

from config import HEIGHT, IMAGE_RETRIES, WIDTH

log = logging.getLogger(__name__)


def to_png_1280x720(raw: bytes) -> bytes:
    """Cover-fit any image to exactly WIDTHxHEIGHT and return PNG bytes."""
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    scale = max(WIDTH / img.width, HEIGHT / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - WIDTH) // 2, (img.height - HEIGHT) // 2
    img = img.crop((left, top, left + WIDTH, top + HEIGHT))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


class ImageQuota(Exception):
    """The free picture allowance is used up (never pay: wait for the daily reset)."""


class PictureFailed(ImageQuota):
    """A picture failed after every retry: the video waits for the next run."""


def is_placeholder(data, prompt):
    """True if these bytes are the offline test pattern (grid + yellow circle) for this prompt."""
    try:
        return data == PlaceholderProvider().generate(prompt)
    except Exception:
        return False


class ImageProvider:
    name = "base"

    def generate(self, prompt: str, seed=None) -> bytes:  # pragma: no cover - interface
        raise NotImplementedError


class PollinationsProvider(ImageProvider):
    """Pollinations.ai (FLUX). One secret key from https://enter.pollinations.ai -> IMAGE_API_KEY."""
    name = "pollinations"
    URL = "https://gen.pollinations.ai/image/{prompt}"

    def __init__(self, api_key=None, model="flux", seed=None, delay=3.0):
        import requests
        self.session = requests.Session()
        self.api_key = api_key or os.environ.get("IMAGE_API_KEY", "")
        self.model, self.seed, self.delay = model, seed, delay

    def generate(self, prompt, seed=None):
        params = {"model": self.model, "width": WIDTH, "height": HEIGHT, "nologo": "true",
                  "enhance": "false", "safe": "true"}
        if seed is not None or self.seed is not None:
            params["seed"] = seed if seed is not None else self.seed
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        url = self.URL.format(prompt=urllib.parse.quote(prompt, safe=""))
        r = self.session.get(url, params=params, headers=headers, timeout=180)
        if r.status_code in (402, 429) and ("balance" in r.text.lower() or "limit" in r.text.lower()):
            raise ImageQuota("Pollinations free allowance used up")
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
            # never echo headers/URL with the key
            raise RuntimeError(f"Pollinations HTTP {r.status_code}: {r.text[:200]}")
        time.sleep(self.delay)
        return to_png_1280x720(r.content)


class CloudflareProvider(ImageProvider):
    """Cloudflare Workers AI, FLUX.1 schnell. Free plan: 10,000 neurons a day (~57 per picture),
    requests simply fail above that, so it can never cost money. Secrets: CF_ACCOUNT_ID, CF_API_TOKEN."""
    name = "cloudflare"
    MODEL = "@cf/black-forest-labs/flux-1-schnell"

    def __init__(self, seed=None, suffix=""):
        import requests
        self.session = requests.Session()
        self.account = os.environ.get("CF_ACCOUNT_ID" + suffix, "").strip()
        self.token = os.environ.get("CF_API_TOKEN" + suffix, "").strip()
        self.seed = seed
        if suffix:
            self.name = "cloudflare" + suffix.lower()

    def available(self):
        return bool(self.account and self.token)

    def generate(self, prompt, seed=None):
        import base64
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account}/ai/run/{self.MODEL}"
        # first try at 4 steps (cheap: about twice as many pictures per day); redraws after a rejection
        # use 8 steps, the model's best quality for hands and faces (STEPS is set by generate_all)
        body = {"prompt": prompt[:2000], "steps": STEPS[0]}   # this model takes no seed (random each time)
        r = self.session.post(url, json=body, headers={"Authorization": f"Bearer {self.token}"}, timeout=120)
        text = r.text[:300]
        if r.status_code == 429 or "4006" in text or "allocation" in text.lower() or "neurons" in text.lower():
            raise ImageQuota(f"Cloudflare daily free allowance used up (HTTP {r.status_code}: {text[:200]})")
        if r.status_code != 200:
            raise RuntimeError(f"Cloudflare HTTP {r.status_code}: {text}")
        img = (r.json().get("result") or {}).get("image")
        if not img:
            raise RuntimeError("Cloudflare returned no image")
        return to_png_1280x720(base64.b64decode(img))


class ChainProvider(ImageProvider):
    """Try each free provider in order; one whose allowance is used up is skipped for the rest of the run."""
    name = "auto"

    def __init__(self, providers):
        self.providers = providers
        self.spent = set()

    def generate(self, prompt, seed=None):
        last = None
        for p in self.providers:
            if p.name in self.spent:
                continue
            try:
                out = p.generate(prompt, seed=seed)
                if p.name not in getattr(self, "ok_noted", set()):
                    import status as ST
                    ST.limit(p.name, True)
                    self.ok_noted = getattr(self, "ok_noted", set()) | {p.name}
                return out
            except ImageQuota as e:
                log.warning("%s", e)
                import status as ST
                ST.limit(p.name, False, str(e)[:150])
                self.spent.add(p.name)
                last = e
            except Exception as e:
                last = e
                log.warning("%s picture failed: %s", p.name, str(e)[:150])
        if all(p.name in self.spent for p in self.providers):
            raise ImageQuota("all free picture allowances are used up for today")
        raise RuntimeError(str(last)[:200] if last else "no picture provider")


class PlaceholderProvider(ImageProvider):
    """Offline provider for tests: a coloured card per prompt. Makes no network calls."""
    name = "placeholder"

    def generate(self, prompt, seed=None):
        h = hashlib.md5(prompt.encode()).digest()
        img = Image.new("RGB", (WIDTH, HEIGHT), (60 + h[0] % 150, 60 + h[1] % 150, 60 + h[2] % 150))
        d = ImageDraw.Draw(img)
        for i in range(0, WIDTH, 80):  # grid makes zoom motion visible
            d.line([(i, 0), (i, HEIGHT)], fill=(255, 255, 255), width=1)
        for j in range(0, HEIGHT, 80):
            d.line([(0, j), (WIDTH, j)], fill=(255, 255, 255), width=1)
        d.ellipse([WIDTH / 2 - 120, HEIGHT / 2 - 120, WIDTH / 2 + 120, HEIGHT / 2 + 120],
                  outline=(255, 230, 0), width=8)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()


def get_provider(seed=None) -> ImageProvider:
    name = os.environ.get("IMAGE_PROVIDER", "auto").lower()
    if name == "placeholder":
        return PlaceholderProvider()
    if name == "pollinations":
        return PollinationsProvider(seed=seed)
    if name == "cloudflare":
        return CloudflareProvider(seed=seed)
    if name == "auto":
        chain = []
        for suffix in ("", "_2", "_3"):   # extra free Cloudflare accounts add their own daily allowance
            cf = CloudflareProvider(seed=seed, suffix=suffix)
            if cf.available():
                chain.append(cf)
        if os.environ.get("IMAGE_API_KEY"):
            chain.append(PollinationsProvider(seed=seed))
        if not chain:
            raise SystemExit("No picture service set: add CF_ACCOUNT_ID + CF_API_TOKEN (or IMAGE_API_KEY)")
        return ChainProvider(chain)
    raise SystemExit(f"Unknown IMAGE_PROVIDER '{name}'")


def make_card(png_path, out_path, darken=0.45, blur=6):
    """Darkened, blurred copy of a scene image: background for intro/outro title cards."""
    from PIL import ImageEnhance, ImageFilter
    img = Image.open(png_path).convert("RGB").filter(ImageFilter.GaussianBlur(blur))
    ImageEnhance.Brightness(img).enhance(darken).save(out_path, "PNG")
    return out_path


def make_outro_card(png_path, out_path):
    """Darkened last scene + a red SUBSCRIBE button with a bell icon."""
    from PIL import ImageFont
    make_card(png_path, out_path, darken=0.4)
    img = Image.open(out_path).convert("RGB")
    d = ImageDraw.Draw(img)
    bw, bh = 420, 92
    x0, y0 = (WIDTH - bw) // 2 - 40, 500
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=16, fill=(204, 0, 0))
    try:
        f = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", 46)
    except OSError:
        f = ImageFont.load_default()
    tw = d.textlength("SUBSCRIBE", font=f)
    d.text((x0 + (bw - tw) / 2, y0 + 16), "SUBSCRIBE", font=f, fill=(255, 255, 255))
    # bell icon in a white circle to the right of the button
    cx, cy, r = x0 + bw + 70, y0 + bh // 2, 46
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255))
    gold = (60, 60, 60)
    d.pieslice([cx - 24, cy - 30, cx + 24, cy + 18], 180, 360, fill=gold)      # bell dome
    d.rectangle([cx - 24, cy - 6, cx + 24, cy + 14], fill=gold)                # bell body
    d.polygon([(cx - 32, cy + 18), (cx + 32, cy + 18), (cx + 24, cy + 8), (cx - 24, cy + 8)], fill=gold)
    d.ellipse([cx - 8, cy + 18, cx + 8, cy + 30], fill=gold)                   # clapper
    d.ellipse([cx - 5, cy - 38, cx + 5, cy - 28], fill=gold)                   # top knob
    img.save(out_path, "PNG")
    return out_path


STATS = {"drawn": 0, "rounds": 0, "scenes": []}
STEPS = [4]   # FLUX steps for the next picture: 4 on the first round, 8 on redraws   # picture tries in this run (reported per video)


def with_style(p):
    """Every drawn picture starts with the short house style (the model may ignore the end of a long prompt);
    the full style text stays at the end."""
    from config import IMAGE_STYLE, STYLE_PREFIX
    if not p.startswith(STYLE_PREFIX):
        p = STYLE_PREFIX + p
    return p if IMAGE_STYLE[:60] in p else f"{p.rstrip('. ')}. {IMAGE_STYLE}"


def simpler_prompt(prompt, reasons, context=""):
    """After two rejected pictures: Gemini rewrites the description so the same story moment is easier to
    draw correctly (fewer people in frame, one clear action, explicit positions). Keeps character looks."""
    try:
        from llm import complete
        d = complete(
            "A picture generator keeps drawing this story picture wrong. Rewrite the picture description so the "
            "SAME story moment is much easier to draw correctly. The picture model cannot reliably decide WHICH "
            "of two people does an action, so: show ONLY the one person doing the main action or speaking, "
            "framed close (the other person may appear only from behind or just a shoulder, never doing "
            "anything), one clear action, a simple camera angle (e.g. 'Oviya in a car passenger seat, pointing "
            "ahead, seen from the front'). Keep every character's age, look, clothes and facial-hair wording exactly as given, "
            "and keep the art style sentence unchanged. Never mention things that should NOT appear.\n\n"
            f"Description:\n{prompt}\n\nWhat went wrong:\n- " + "\n- ".join(reasons[-3:]) +
            f"\n\nNarration at this moment (Tamil): {context[:500]}\n\n"
            'Return JSON {"prompt": "..."}', want_json=True, max_tokens=2000, rounds=1)
        new = d["prompt"].strip()
        if len(new) > 80:
            log.info("Rewrote a hard picture description: %s", new[:200])
            return new
    except Exception as e:
        log.info("Prompt rewrite skipped: %s", str(e)[:100])
    return prompt


def drawable_prompts(prompts, contexts=None):
    """ONE Gemini request for the whole video: rewrite every picture description so the free picture model
    can draw it right the first time (one main person acting, simple positions, simple camera), keeping the
    same story moment, character looks and art style. Falls back to the originals on any problem."""
    if not prompts:
        return prompts
    try:
        from llm import complete
        items = "\n\n".join(f"[{k}] narration: {(contexts[k] if contexts and k < len(contexts) else '')[:300]}"
                             f"\ndescription: {p}" for k, p in enumerate(prompts))
        d = complete(
            "These are picture descriptions for one Tamil story video. A free picture model (FLUX) will draw them. "
            "Rewrite EACH one with this exact template, in this order, under 70 words:\n"
            "1) camera shot first: 'Medium shot, whole heads visible with space above,' (or close-up / wide shot)\n"
            "2) ONE main person and the ONE action they do (only one person acts in a picture)\n"
            "3) any other person only present and still, placed with 'on the left of the frame' / 'on the right of the "
            "frame' (never 'beside him', never two people interacting or touching)\n"
            "4) each character as a short ID line: age + gender + 3-4 identity details (hair, glasses, facial hair, main "
            "clothes colour) copied from the original; facial hair only in positive words (e.g. 'thin moustache, smooth "
            "shaved chin'), never the words 'no beard'\n"
            "5) hands given a simple job ('hands on the steering wheel', 'hands resting on her lap') or out of frame\n"
            "6) place and time of day in a few words, then the light\n"
            "- only positive words: never mention what should NOT appear; drop decoration (jewellery, sleeves, patterns)\n"
            "- for vehicles say where the camera is (e.g. 'seen through the windshield from outside the car')\n"
            "- papers, letters, phones and signs are seen from the back or blurred, with no readable writing\n"
            "- every person faces the camera or is seen in profile, never from the back unless the moment needs it\n"
            "- keep the same story moment as the narration; leave out the art style (it is added automatically)\n"
            f"Return JSON {{\"prompts\": [exactly {len(prompts)} strings in the same order]}}\n\n" + items,
            want_json=True, max_tokens=30000, rounds=1)
        out = [x.strip() for x in d["prompts"]]
        if len(out) == len(prompts) and all(len(x) > 80 for x in out):
            log.info("Picture descriptions made easier to draw (%d)", len(out))
            return out
        log.info("Drawable rewrite returned %d of %d descriptions - using originals", len(out), len(prompts))
    except Exception as e:
        log.info("Drawable rewrite skipped: %s", str(e)[:120])
    return prompts


def generate_all(provider, prompts, out_dir, check=True, base_seed=1000, cache_dir=None, contexts=None,
                 draw_prompts=None):
    """Generate every scene image.

    Each image goes through the automatic checker (image_check.py). A rejected image is
    regenerated (up to IMAGE_RETRIES more times); if all attempts are rejected, or the checker
    cannot run, the video PAUSES (PictureFailed) - a picture is never used unchecked or rejected.
    Saved pictures carry a ".ok" mark once checked; unchecked saved pictures are checked before use.
    FRESH_PICTURES=1 ignores saved pictures (redo every picture of a video).
    A scene that cannot be generated at all STOPS the video (PictureFailed): no test pattern and
    no repeated picture is ever put into a real video. Pictures made so far stay cached.
    """
    from image_check import CHECK_VERSION, CheckUnavailable, check as vision_check, check_many
    fresh = bool(os.environ.get("FRESH_PICTURES"))
    if isinstance(provider, PlaceholderProvider):
        check = False   # offline test pictures (sample test / --test runs) are never uploaded
    out_dir.mkdir(parents=True, exist_ok=True)
    paths, warnings = [], []
    used, loaded = set(), set()
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        if fresh:   # redo every picture: forget all saved pictures of this video (a paused run continues from new ones)
            for f in cache_dir.glob("*"):
                f.unlink()
            log.info("Redoing every picture: saved pictures of this video removed")
    for i, prompt in enumerate(prompts):
        ctx = contexts[i] if contexts and i < len(contexts) else ""
        path = out_dir / f"scene_{i:02d}.png"
        key = hashlib.md5(prompt.encode()).hexdigest()[:12]
        cached = cache_dir / f"{i:02d}_{key}.png" if cache_dir else None
        # reuse a saved picture of the same scene even if the picture numbering moved or the
        # style text changed (each saved file is used once, so repeated scenes stay different)
        from config import IMAGE_STYLE, PREVIOUS_IMAGE_STYLES
        if cached and not cached.exists():
            keys = {key} | {hashlib.md5(prompt.replace(IMAGE_STYLE, st).encode()).hexdigest()[:12]
                            for st in PREVIOUS_IMAGE_STYLES}
            for f in sorted(cache_dir.glob("*.png")):
                if f.stem.split("_", 1)[-1] in keys and f not in used:
                    cached = f
                    break
        if cached:
            used.add(cached)
        # a hand-made picture (e.g. from ChatGPT) in assets/overrides/row_<id>/NN.png|jpg wins
        if cache_dir:
            for ext in ("png", "jpg", "jpeg", "webp"):
                o = Path(__file__).resolve().parent.parent / "assets" / "overrides" / cache_dir.name / f"{i:02d}.{ext}"
                if o.exists():
                    path.write_bytes(to_png_1280x720(o.read_bytes()))
                    paths.append(path)
                    log.info("Scene %d: using the hand-made picture %s", i, o.name)
                    break
            else:
                o = None
            if o is not None:
                continue
        if cached and cached.exists() and is_placeholder(cached.read_bytes(), prompt):
            log.warning("Scene %d: cached picture is a test pattern - discarding it", i)
            cached.unlink()
        if cached and cached.exists() and hashlib.md5(cached.read_bytes()).hexdigest() in loaded:
            log.warning("Scene %d: saved picture is a copy of an earlier scene - making a new one", i)
            cached.unlink()
        if cached and cached.exists() and check and not os.environ.get("NO_NEW_ASSETS") \
                and not (cached.with_suffix(".ok").exists()
                         and (cached.with_suffix(".ok").read_text().strip() == CHECK_VERSION
                              # v4 checks were complete except for scenes without people (style unchecked)
                              or (cached.with_suffix(".ok").read_text().strip() == "v4"
                                  and "No people in the picture" not in prompt))):
            try:
                ok, reason = vision_check(cached.read_bytes(), prompt, ctx)
            except CheckUnavailable as e:
                raise PictureFailed(str(e))
            if ok:
                cached.with_suffix(".ok").write_text(CHECK_VERSION)
            else:
                log.warning("Scene %d: saved picture fails the check (%s) - making a new one", i, reason)
                cached.unlink()
        if cached and cached.exists():
            loaded.add(hashlib.md5(cached.read_bytes()).hexdigest())
            path.write_bytes(cached.read_bytes())
            paths.append(path)
            continue
        if os.environ.get("NO_NEW_ASSETS"):
            raise ImageQuota(f"Short-only run: saved picture {i} is missing - not making new pictures")
        data, reason = None, ""
        first = with_style(draw_prompts[i] if draw_prompts and i < len(draw_prompts) else prompt)
        draw_prompt, reasons = first, []
        # rounds of BATCH candidates; the checker judges a whole batch in ONE request (saves its daily limit)
        batch = 1 if not check else 2
        for rnd in range(3 if check else 1 + IMAGE_RETRIES):
            if check and draw_prompt == first and reasons:
                draw_prompt = with_style(simpler_prompt(first, reasons, ctx))   # same moment, easier to draw
            STEPS[0] = 4 if rnd == 0 else 8
            cands = []
            for k in range(batch):
                try:
                    cands.append(provider.generate(draw_prompt, seed=base_seed + i * 10 + rnd * batch + k))
                except ImageQuota:
                    if cands:
                        break   # check what we have
                    log.warning("Scene %02d still needs a picture. Prompt: %s", i, prompt[:400])
                    raise   # pictures made so far are cached; the next run continues from here
                except Exception as e:
                    log.warning("Image %d candidate failed: %s", i, e)
                    time.sleep(5)
            STATS["drawn"] += len(cands)
            STATS["rounds"] += 1
            cands = [c for c in cands if hashlib.md5(c).hexdigest() not in loaded]
            if not cands:
                continue
            if not check:
                data = cands[0]
                break
            try:
                verdicts = check_many(cands, draw_prompt, ctx)
            except CheckUnavailable as e:
                raise PictureFailed(str(e))   # pictures accepted so far stay saved
            good = [c for c, (ok, _) in zip(cands, verdicts) if ok]
            if good:
                data = good[0]
                STATS["scenes"].append({"scene": i, "rounds": rnd + 1,
                                        "first_try": rnd == 0 and verdicts[0][0]})
                break
            data = cands[0]
            if cache_dir:   # keep rejected pictures with the reason, for review (show-pictures workflow)
                rej = cache_dir / "rejected"
                rej.mkdir(exist_ok=True)
                for k, (c, (_, why)) in enumerate(zip(cands, verdicts)):
                    stem = f"{i:02d}_r{rnd}{k}_{hashlib.md5(c).hexdigest()[:6]}"
                    (rej / f"{stem}.png").write_bytes(c)
                    (rej / f"{stem}.txt").write_text(f"REJECTED: {why}\n\nPROMPT:\n{draw_prompt}", encoding="utf-8")
            reasons += [r for _, r in verdicts if r]
            reason = reasons[-1] if reasons else "rejected"
            log.warning("Scene %d: all %d candidates rejected (%s)", i, len(cands), "; ".join(r for _, r in verdicts)[:300])
        else:
            if data is not None and check:
                raise PictureFailed(f"scene {i}: every candidate was rejected by the checker ({reason}); "
                                    "pausing - the next run tries again")
        if data is None:
            if isinstance(provider, PlaceholderProvider):
                data = provider.generate(prompt)
            else:
                raise PictureFailed(f"scene {i}: picture could not be made; pausing instead of "
                                    "using a test pattern or a repeated picture")
        path.write_bytes(data)
        if cached and not isinstance(provider, PlaceholderProvider):
            cached.write_bytes(data)
            cached.with_suffix(".prompt.txt").write_text(draw_prompt if check else prompt, encoding="utf-8")
            if check:
                cached.with_suffix(".ok").write_text(CHECK_VERSION)
        paths.append(path)
    return paths, warnings


def validate_pictures(paths):
    """Final check before rendering: every story picture must be a real, different picture.
    Catches test patterns, blank/flat images and the same picture used twice."""
    import hashlib as _h
    from PIL import ImageStat
    problems, seen = [], {}
    for i, p in enumerate(paths):
        data = Path(p).read_bytes()
        h = _h.md5(data).hexdigest()
        if h in seen:
            problems.append(f"picture {i} is the same as picture {seen[h]}")
        seen[h] = i
        img = Image.open(io.BytesIO(data)).convert("L").resize((160, 90))
        if max(ImageStat.Stat(img).stddev) < 5:
            problems.append(f"picture {i} is almost blank")
        # test-pattern signature: thin white lines every 80 px on a flat colour
        big = Image.open(io.BytesIO(data)).convert("RGB")
        if big.size == (WIDTH, HEIGHT):
            col = [big.getpixel((x, 40)) for x in range(0, WIDTH, 80)]
            if all(c == (255, 255, 255) for c in col):
                problems.append(f"picture {i} looks like the test pattern")
    return problems
