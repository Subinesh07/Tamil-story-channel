"""Playlist covers (1280x720) in the same style as the video thumbnails.

python src/playlist_covers.py   -> previews/covers/<name>.jpg
Backgrounds: the series' own saved story pictures (cache/images/row_<id>) or hand-made overrides.
"""
import sys

from PIL import Image, ImageDraw, ImageEnhance

import thumb_v2
from config import ROOT
from thumb_v2 import RED, WHITE, YELLOW, _fit_line, badge, heavy

COVERS = [
    {"name": "doomsday", "rows": ["7"], "genre": "doomsday", "pick": 0,
     "texts": {"title": "டூம்ஸ்டே", "tagline": "சனி, ஞாயிறு காலை 11 மணிக்கு புதிய பகுதி!"}},
    {"name": "nizhal_nijamanal", "rows": ["5", "11"], "genre": "family serial", "pick": "middle",
     "texts": {"line1": "நிழல் நிஜமானால்", "line2": "அப்பா மறைச்ச உயில்… அடுத்து என்ன?",
               "ribbon": "குடும்ப தொடர் கதை"}},
]


def doomsday_cover(bg, t, out):
    """Apocalypse look: the sky burns red, the people stay visible, title in the sky."""
    img = Image.open(bg).convert("RGB").resize((1280, 720), Image.LANCZOS)
    img = ImageEnhance.Contrast(ImageEnhance.Brightness(img).enhance(0.8)).enhance(1.15)
    sky = Image.new("RGB", img.size, (200, 30, 10))
    mask = Image.linear_gradient("L").resize(img.size).point(lambda v: int(max(0, 255 - v * 1.6) * 0.75))
    img = Image.composite(sky, img, mask)                 # red glow strongest at the top
    glow = Image.new("RGB", img.size, (255, 120, 0))
    gm = Image.new("L", img.size, 0)
    ImageDraw.Draw(gm).ellipse([820, -260, 1400, 260], fill=170)
    from PIL import ImageFilter
    img = Image.composite(glow, img, gm.filter(ImageFilter.GaussianBlur(90)))   # the storm-sun
    d = ImageDraw.Draw(img)
    f = _fit_line(d, t["title"], 620, 170)
    heavy(d, (600, 40), t["title"], f, RED, outline=12, shadow=9)
    f2 = _fit_line(d, "தொடர் கதை 😱".replace(" 😱", ""), 520, 80)
    heavy(d, (640, 250), "தொடர் கதை", f2, YELLOW, outline=9)
    d.rectangle([0, 610, 1280, 720], fill=(120, 0, 0))
    f3 = _fit_line(d, t["tagline"], 1200, 58)
    heavy(d, (40, 625), t["tagline"], f3, WHITE, outline=6, shadow=4)
    badge(d, 30, 30)
    img.save(out, quality=92)
    return out


def pictures(rows):
    found = []
    for rid in rows:
        for d in (ROOT / "assets" / "overrides" / f"row_{rid}", ROOT / "cache" / "images" / f"row_{rid}"):
            found += sorted(d.glob("*.png")) if d.exists() else []
    return found


def main():
    out = ROOT / "previews" / "covers"
    out.mkdir(parents=True, exist_ok=True)
    for c in COVERS:
        pics = pictures(c["rows"])
        if not pics:
            print(f"no pictures for {c['name']}")
            continue
        bg = pics[len(pics) // 2] if c["pick"] == "middle" else pics[c["pick"]]
        if c["name"] == "doomsday":
            path = doomsday_cover(bg, c["texts"], out / f"{c['name']}.jpg")
            print(f"made {path} from {bg.name}")
            continue
        path, layout = thumb_v2.make(bg, c["texts"], out / f"{c['name']}.jpg", c["genre"], 0, "")
        print(f"made {path} ({layout}) from {bg.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
