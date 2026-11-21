"""Draws the Nila Kathaigal logo (800x800) and channel banner (2560x1440). Run once:
python src/brand_assets.py  -> assets/brand/logo.png, assets/brand/banner.png
"""
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import ROOT, THUMB_FONT

OUT = ROOT / "assets" / "brand"
NIGHT_TOP, NIGHT_BOTTOM = (14, 22, 58), (52, 36, 92)
GOLD, CREAM = (255, 205, 92), (255, 244, 214)
REG_FONT = THUMB_FONT.replace("-Bold", "-Regular")


def font(size, bold=True):
    return ImageFont.truetype(THUMB_FONT if bold else REG_FONT, size,
                              layout_engine=ImageFont.Layout.RAQM)


def sky(w, h, seed=7, stars=180):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(NIGHT_TOP, NIGHT_BOTTOM)))
    rnd = random.Random(seed)
    for _ in range(stars):
        x, y, r = rnd.randrange(w), rnd.randrange(int(h * 0.85)), rnd.choice([1, 1, 1, 2, 2, 3])
        a = rnd.randint(120, 255)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(a, a, min(255, a + 20)))
    return img


def crescent(size, glow=True):
    """Gold crescent moon on a transparent layer, with a soft glow."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    m = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(m)
    pad = size * 0.12
    md.ellipse([pad, pad, size - pad, size - pad], fill=255)
    off = size * 0.22
    md.ellipse([pad + off, pad - off * 0.55, size - pad + off, size - pad - off * 0.55], fill=0)
    if glow:
        g = m.filter(ImageFilter.GaussianBlur(size * 0.06))
        layer.paste(Image.new("RGBA", (size, size), GOLD + (150,)), (0, 0), g)
    layer.paste(Image.new("RGBA", (size, size), GOLD + (255,)), (0, 0), m)
    return layer


def book(w):
    """Simple open book in cream, transparent background."""
    h = int(w * 0.42)
    layer = Image.new("RGBA", (w, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    mid = w / 2
    for side in (-1, 1):
        pts = [(mid, h * 0.18), (mid + side * w * 0.48, 0), (mid + side * w * 0.48, h * 0.82), (mid, h)]
        d.polygon(pts, fill=CREAM + (255,))
        for k in range(1, 4):  # page lines
            y0 = h * (0.25 + k * 0.15)
            d.line([(mid + side * w * 0.08, y0), (mid + side * w * 0.4, y0 - h * 0.12)],
                   fill=(205, 175, 120, 255), width=max(2, w // 120))
    d.line([(mid, h * 0.18), (mid, h)], fill=(200, 160, 90, 255), width=max(3, w // 80))
    return layer


def logo(path=None):
    S = 800
    img = sky(S, S, seed=3, stars=70).convert("RGBA")
    moon = crescent(380)
    img.alpha_composite(moon, (int(S / 2 - 190), 95))
    bk = book(290)
    img.alpha_composite(bk, (int(S / 2 - 145), 385))
    d = ImageDraw.Draw(img)
    f = font(66)
    text = "நிலா கதைகள்"
    w = d.textlength(text, font=f)
    d.text(((S - w) / 2, 545), text, font=f, fill=GOLD, stroke_width=4, stroke_fill=(20, 16, 40),
           language="ta")
    # circular-safe: YouTube crops the avatar to a circle; content stays inside it
    out = img.convert("RGB")
    out.save(path or OUT / "logo.png")
    return out


def banner(path=None):
    W, H = 2560, 1440
    img = sky(W, H, seed=11, stars=520).convert("RGBA")
    d = ImageDraw.Draw(img)
    # soft hills at the bottom for a village-night feel
    for k, col in enumerate([(30, 26, 60), (22, 20, 48)]):
        pts = [(0, H)] + [(x, H * (0.78 + 0.05 * k) - 40 * math.sin(x / (300 + 120 * k) + k))
                          for x in range(0, W + 40, 40)] + [(W, H)]
        d.polygon(pts, fill=col + (255,))
    # everything important sits inside YouTube's 1546x423 safe area in the centre
    moon = crescent(330)
    img.alpha_composite(moon, (W // 2 - 760, H // 2 - 170))
    f1, f2 = font(150), font(58, bold=False)
    t1, t2 = "நிலா கதைகள்", "தினமும் மாலை 7 மணிக்கு ஒரு புது கதை"
    d.text((W // 2 - 400, H // 2 - 140), t1, font=f1, fill=GOLD, stroke_width=5,
           stroke_fill=(15, 12, 35), language="ta")
    d.text((W // 2 - 395, H // 2 + 60), t2, font=f2, fill=CREAM, language="ta")
    d.text((W // 2 - 393, H // 2 + 140), "Nila Kathaigal  •  Original Tamil Stories",
           font=ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 40),
           fill=(200, 190, 230))
    out = img.convert("RGB")
    out.save(path or OUT / "banner.png")
    return out


ART = OUT / "logo_art.png"


def logo_from_art(path=None):
    """Profile picture from the channel artwork, with the Tamil name on the clouds."""
    S = 800
    img = Image.open(ART).convert("RGBA").resize((S, S), Image.LANCZOS)
    shade = Image.new("L", (S, S), 0)
    ImageDraw.Draw(shade).rectangle([0, int(S * 0.72), S, S], fill=120)
    img.paste(Image.new("RGBA", (S, S), (10, 10, 30, 255)), (0, 0), shade.filter(ImageFilter.GaussianBlur(30)))
    d = ImageDraw.Draw(img)
    f = font(64)
    text = "நிலா கதைகள்"
    w = d.textlength(text, font=f)
    d.text(((S - w) / 2, 600), text, font=f, fill=GOLD, stroke_width=5, stroke_fill=(15, 12, 35),
           language="ta")
    img.convert("RGB").save(path or OUT / "logo.png")


def banner_from_art(path=None):
    """Channel banner. Everything sits inside YouTube's "all devices" safe area (1546x423 in the
    centre of 2560x1440), measured, with a margin, so nothing is cut on phones."""
    W, H = 2560, 1440
    SW, SH, M = 1546, 423, 24
    x0, y0 = (W - SW) // 2 + M, (H - SH) // 2 + M
    x1, y1 = (W + SW) // 2 - M, (H + SH) // 2 - M
    img = sky(W, H, seed=11, stars=520).convert("RGBA")
    size = y1 - y0                                   # moon artwork fills the safe height
    art = Image.open(ART).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", art.size, 0)
    ImageDraw.Draw(mask).ellipse([6, 6, size - 6, size - 6], fill=255)
    img.paste(art, (x0, y0), mask.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    tx, tw = x0 + size + 40, x1 - (x0 + size + 40)   # text column
    lines = [("நிலா கதைகள்", True, GOLD, 170), ("தினமும் ஒரு புது தமிழ் கதை", False, CREAM, 70)]
    fonts = []
    for text, bold, col, sz in lines:
        f = font(sz, bold=bold)
        while d.textlength(text, font=f, language="ta") > tw and sz > 20:
            sz -= 4
            f = font(sz, bold=bold)
        fonts.append(f)
    sub = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 40)
    h1 = d.textbbox((0, 0), lines[0][0], font=fonts[0], language="ta")
    h2 = d.textbbox((0, 0), lines[1][0], font=fonts[1], language="ta")
    total = (h1[3] - h1[1]) + 30 + (h2[3] - h2[1]) + 30 + 44
    y = y0 + ((y1 - y0) - total) // 2
    d.text((tx, y - h1[1]), lines[0][0], font=fonts[0], fill=GOLD, stroke_width=5,
           stroke_fill=(15, 12, 35), language="ta")
    y += (h1[3] - h1[1]) + 30
    d.text((tx, y - h2[1]), lines[1][0], font=fonts[1], fill=CREAM, language="ta")
    y += (h2[3] - h2[1]) + 30
    d.text((tx, y), "Nila Kathaigal  •  Original Tamil Stories", font=sub, fill=(200, 190, 230))
    img.convert("RGB").save(path or OUT / "banner.png")


def intro_background(path):
    """Intro card background for videos: the channel artwork, softly darkened, 1280x720."""
    from PIL import ImageEnhance
    art = Image.open(ART).convert("RGB")
    bg = art.resize((1280, 1280), Image.LANCZOS).filter(ImageFilter.GaussianBlur(22))
    bg = ImageEnhance.Brightness(bg.crop((0, 280, 1280, 1000))).enhance(0.45)
    side = art.resize((560, 560), Image.LANCZOS)
    m = Image.new("L", side.size, 0)
    ImageDraw.Draw(m).ellipse([0, 0, 559, 559], fill=255)
    bg.paste(ImageEnhance.Brightness(side).enhance(0.42), (360, 80), m.filter(ImageFilter.GaussianBlur(25)))
    bg.save(path)
    return path


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    if ART.exists():
        logo_from_art()
        banner_from_art()
    else:
        logo()
        banner()
    print("saved", OUT)
