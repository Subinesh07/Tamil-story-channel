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

    def __init__(self, seed=None):
        import requests
        self.session = requests.Session()
        self.account = os.environ.get("CF_ACCOUNT_ID", "").strip()
        self.token = os.environ.get("CF_API_TOKEN", "").strip()
        self.seed = seed

    def available(self):
        return bool(self.account and self.token)

    def generate(self, prompt, seed=None):
        import base64
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account}/ai/run/{self.MODEL}"
        body = {"prompt": prompt[:2000], "steps": 4}   # this model takes no seed (random each time)
        r = self.session.post(url, json=body, headers={"Authorization": f"Bearer {self.token}"}, timeout=120)
        text = r.text[:300]
        if r.status_code == 429 or "4006" in text or "allocation" in text.lower() or "neurons" in text.lower():
            raise ImageQuota("Cloudflare daily free allowance used up")
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
                return p.generate(prompt, seed=seed)
            except ImageQuota as e:
                log.warning("%s", e)
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
        cf = CloudflareProvider(seed=seed)
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


def generate_all(provider, prompts, out_dir, check=True, base_seed=1000, cache_dir=None):
    """Generate every scene image.

    Each image goes through the automatic checker (image_check.py). A rejected image is
    regenerated with a new seed (up to IMAGE_RETRIES more times); if all attempts are rejected
    the last one is kept with a warning.
    A scene that cannot be generated at all STOPS the video (PictureFailed): no test pattern and
    no repeated picture is ever put into a real video. Pictures made so far stay cached.
    """
    from image_check import check as vision_check
    out_dir.mkdir(parents=True, exist_ok=True)
    paths, warnings = [], []
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
    for i, prompt in enumerate(prompts):
        path = out_dir / f"scene_{i:02d}.png"
        key = hashlib.md5(prompt.encode()).hexdigest()[:12]
        cached = cache_dir / f"{i:02d}_{key}.png" if cache_dir else None
        if cached and cached.exists() and is_placeholder(cached.read_bytes(), prompt):
            log.warning("Scene %d: cached picture is a test pattern - discarding it", i)
            cached.unlink()
        if cached and cached.exists():
            path.write_bytes(cached.read_bytes())
            paths.append(path)
            continue
        data, reason = None, ""
        for attempt in range(1 + IMAGE_RETRIES):
            try:
                candidate = provider.generate(prompt, seed=base_seed + i * 10 + attempt)
            except ImageQuota:
                raise   # pictures made so far are cached; the next run continues from here
            except Exception as e:
                log.warning("Image %d attempt %d failed: %s", i, attempt + 1, e)
                time.sleep(5 * (attempt + 1))
                continue
            data = candidate
            if not check:
                break
            ok, reason = vision_check(candidate, prompt)
            if ok:
                if reason:
                    log.info("Image %d: %s", i, reason)
                break
            log.warning("Image %d rejected by checker (%s); regenerating", i, reason)
        else:
            if data is not None and check:
                msg = f"Scene {i}: kept image although checker said: {reason}"
                log.warning(msg)
                warnings.append(msg)
        if data is None:
            if isinstance(provider, PlaceholderProvider):
                data = provider.generate(prompt)
            else:
                raise PictureFailed(f"scene {i}: picture could not be made; pausing instead of "
                                    "using a test pattern or a repeated picture")
        path.write_bytes(data)
        if cached and not isinstance(provider, PlaceholderProvider):
            cached.write_bytes(data)
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
