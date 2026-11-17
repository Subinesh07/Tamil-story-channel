"""Phase 3: pluggable image providers.  Every provider implements generate(prompt) -> PNG bytes.

Pick one with the IMAGE_PROVIDER env var:  pollinations (default) | placeholder
"""
import hashlib
import io
import logging
import os
import time
import urllib.parse

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


class ImageProvider:
    name = "base"

    def generate(self, prompt: str) -> bytes:  # pragma: no cover - interface
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

    def generate(self, prompt):
        params = {"model": self.model, "width": WIDTH, "height": HEIGHT, "nologo": "true",
                  "enhance": "false", "safe": "true"}
        if self.seed is not None:
            params["seed"] = self.seed
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        url = self.URL.format(prompt=urllib.parse.quote(prompt, safe=""))
        r = self.session.get(url, params=params, headers=headers, timeout=180)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
            # never echo headers/URL with the key
            raise RuntimeError(f"Pollinations HTTP {r.status_code}: {r.text[:200]}")
        time.sleep(self.delay)
        return to_png_1280x720(r.content)


class PlaceholderProvider(ImageProvider):
    """Offline provider for tests: a coloured card per prompt. Makes no network calls."""
    name = "placeholder"

    def generate(self, prompt):
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
    name = os.environ.get("IMAGE_PROVIDER", "pollinations").lower()
    if name == "placeholder":
        return PlaceholderProvider()
    if name == "pollinations":
        return PollinationsProvider(seed=seed)
    raise SystemExit(f"Unknown IMAGE_PROVIDER '{name}'")


def generate_all(provider, prompts, out_dir):
    """Generate every scene image. A failed scene is retried, then reuses the previous image."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths, warnings, prev = [], [], None
    for i, prompt in enumerate(prompts):
        path = out_dir / f"scene_{i:02d}.png"
        data = None
        for attempt in range(1 + IMAGE_RETRIES):
            try:
                data = provider.generate(prompt)
                break
            except Exception as e:
                log.warning("Image %d attempt %d failed: %s", i, attempt + 1, e)
                time.sleep(5 * (attempt + 1))
        if data is None:
            if prev is None:
                # first scene failed: try later prompts' images later; use a neutral card for now
                data = PlaceholderProvider().generate(prompt)
            else:
                data = prev
            msg = f"Scene {i}: image failed, reused previous image"
            log.warning(msg)
            warnings.append(msg)
        path.write_bytes(data)
        prev = data
        paths.append(path)
    return paths, warnings
