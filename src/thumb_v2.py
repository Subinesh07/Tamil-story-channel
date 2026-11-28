"""Viral-style Tamil thumbnails, modelled on top Tamil story channels.

* HUGE heavy text: yellow main words, a red key word, white setup line, thick black outline + shadow
* two-line curiosity: a setup line ("டிரைவர் என்று காதலித்தாள்…") + a cut-off reveal ("அவன் யார் என்று தெரிந்ததும்..!")
* red ribbon boxes with white text, an optional extra ribbon, a big red "?"
* picture asks "how is this possible?": split before/after scenes, a clue, intense faces (written by the story AI)
* horror gets its own look: blood-red title with white outline and glow + yellow tagline on a dark scene

make(bg, texts, out_path, genre, variant, part)
texts = {"line1": setup, "line2": reveal, "ribbon": optional extra, "title": horror title, "tagline": horror tagline}
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from config import CHANNEL_NAME_TA, HEIGHT, WIDTH

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
BLACK_F = FONTS / "NotoSansTamil-Black.ttf"
COND_F = FONTS / "NotoSansTamil-BlackCondensed.ttf"
LATIN_F = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
YELLOW, RED, WHITE, BLACK = (255, 222, 0), (230, 20, 30), (255, 255, 255), (0, 0, 0)
BLUE = (20, 70, 200)


def _font(size, condensed=False):
    path = COND_F if condensed else BLACK_F
    if not path.exists():
        path = "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf"
    return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)


def _w(d, text, f):
    from thumbnail import text_w   # handles English words with a Latin font
    return text_w(d, text, f)


def _draw(d, xy, text, f, **kw):
    from thumbnail import draw_mixed
    draw_mixed(d, xy, text, f, **kw)


def _fit_line(d, text, max_w, start, min_size=46):
    """Largest font (normal, then condensed) that fits one line."""
    for condensed in (False, True):
        size = start
        while size >= min_size:
            f = _font(size, condensed)
            if _w(d, text, f) <= max_w:
                return f
            size -= 4
    return _font(min_size, True)


def _split_lines(d, text, max_w, start, max_lines=2, min_size=46):
    """Split text over up to max_lines lines with the biggest font that fits."""
    words = text.split()
    if not words:
        return [""], _font(start)
    best = None
    for n in range(1, max_lines + 1):
        if n > len(words):
            break
        per = -(-len(words) // n)
        lines = [" ".join(words[i:i + per]) for i in range(0, len(words), per)]
        fonts = [_fit_line(d, ln, max_w, start, min_size) for ln in lines]
        size = min(f.size for f in fonts)
        cond = any(f.path == str(COND_F) for f in fonts)
        if best is None or size > best[0] + 6:
            best = (size, lines, cond)
    size, lines, cond = best
    return lines, _font(size, cond)


def heavy(d, xy, text, f, fill, outline=10, shadow=7):
    """Thick black outline + drop shadow, like hand-made thumbnails."""
    x, y = xy
    if shadow:
        _draw(d, (x + shadow, y + shadow), text, f, fill=BLACK, stroke_width=outline, stroke_fill=BLACK)
    _draw(d, (x, y), text, f, fill=fill, stroke_width=outline, stroke_fill=BLACK)


def heavy_two_tone(d, xy, text, f, main, last_col, outline=10):
    """Last word in a second colour (the punch word)."""
    words = text.split()
    if len(words) < 2:
        heavy(d, xy, text, f, last_col, outline)
        return
    first = " ".join(words[:-1]) + " "
    heavy(d, xy, first, f, main, outline)
    heavy(d, (xy[0] + _w(d, first, f), xy[1]), words[-1], f, last_col, outline)


def ribbon(d, x, y, text, f, bg=RED, fg=WHITE, pad=22, slant=18):
    w = _w(d, text, f) + pad * 2
    h = f.size * 1.32
    d.polygon([(x + slant, y), (x + w + slant, y), (x + w, y + h), (x, y + h)], fill=BLACK)
    d.polygon([(x + slant - 6, y - 6), (x + w + slant - 6, y - 6), (x + w - 6, y + h - 6), (x - 6, y + h - 6)], fill=bg)
    _draw(d, (x + pad + slant / 2 - 6, y + f.size * 0.02 - 6), text, f, fill=fg, stroke_width=2, stroke_fill=BLACK)
    return w, h


def ribbons(d, x, y, text, max_w, start=66, min_size=44, bg=RED, fg=WHITE):
    """Setup line as 1-2 stacked ribbons, as big as fits."""
    lines, f = _split_lines(d, text, max_w - 120, start, 2, min_size)
    for ln in lines:
        _, h = ribbon(d, x, y, ln, f, bg=bg, fg=fg)
        y += h + 10
    return y


def part_ribbon(d, part, series=""):
    f = _font(52)
    label = f"பகுதி {part}"
    w = _w(d, label, f) + 50
    x, y = WIDTH - w - 30, 26
    d.rounded_rectangle([x + 6, y + 6, x + w + 6, y + 82], radius=18, fill=BLACK)
    d.rounded_rectangle([x, y, x + w, y + 76], radius=18, fill=RED, outline=YELLOW, width=5)
    heavy(d, (x + 25, y - 2), label, f, YELLOW, outline=5, shadow=0)
    if series:
        series_tag(d, series, y + 94)


def series_tag(d, name, y=26):
    """Series name strip (top-right) so viewers can spot every part of a serial on the channel page."""
    f = _fit_line(d, name, 420, 46, min_size=30)
    w = _w(d, name, f) + 40
    x = WIDTH - w - 30
    d.rounded_rectangle([x + 5, y + 5, x + w + 5, y + f.size * 1.35 + 5], radius=14, fill=BLACK)
    d.rounded_rectangle([x, y, x + w, y + f.size * 1.35], radius=14, fill=WHITE, outline=BLACK, width=3)
    _draw(d, (x + 20, y + f.size * 0.04), name, f, fill=(150, 0, 0))


def badge(d, x, y):
    f = _font(30)
    w = _w(d, CHANNEL_NAME_TA, f) + 30
    d.rounded_rectangle([x, y, x + w, y + 48], radius=12, fill=(12, 12, 40))
    _draw(d, (x + 15, y + 2), CHANNEL_NAME_TA, f, fill=(255, 205, 92))


def _prep(bg, horror=False):
    img = Image.open(bg).convert("RGB").resize((WIDTH, HEIGHT))
    img = ImageEnhance.Contrast(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(1.35 if not horror else 1.1)
    img = ImageEnhance.Sharpness(img).enhance(1.4)
    if horror:   # cold blue shadows + red rim
        tint = Image.new("RGB", img.size, (10, 25, 70))
        img = Image.blend(img, tint, 0.28)
    return img


def _shade(img, top=0.0, bottom=0.0, strength=230):
    m = Image.new("L", (WIDTH, HEIGHT))
    md = ImageDraw.Draw(m)
    for y in range(HEIGHT):
        v = 0
        if bottom and y > HEIGHT * (1 - bottom):
            v = int(strength * (y - HEIGHT * (1 - bottom)) / (HEIGHT * bottom))
        if top and y < HEIGHT * top:
            v = max(v, int(strength * 0.85 * (1 - y / (HEIGHT * top))))
        md.line([(0, y), (WIDTH, y)], fill=v)
    return Image.composite(Image.new("RGB", img.size, BLACK), img, m)


def _arrow(d, x0, y0, x1, y1, col=RED, width=22):
    d.line([(x0, y0), (x1, y1)], fill=BLACK, width=width + 10)
    d.line([(x0, y0), (x1, y1)], fill=col, width=width)
    import math
    ang = math.atan2(y1 - y0, x1 - x0)
    tip = [(x1 + 28 * math.cos(ang), y1 + 28 * math.sin(ang)),
           (x1 + 40 * math.cos(ang + 2.4), y1 + 40 * math.sin(ang + 2.4)),
           (x1 + 40 * math.cos(ang - 2.4), y1 + 40 * math.sin(ang - 2.4))]
    d.polygon(tip, fill=col, outline=BLACK)


# ------------------------------------------------------------ layouts
def ribbon_top(img, t):
    """Red ribbon (setup) on top, huge yellow reveal at the bottom, big red ?"""
    img = _shade(img, top=0.32, bottom=0.42)
    d = ImageDraw.Draw(img)
    ribbons(d, 40, 34, t["line1"], WIDTH - t.get("_reserve", 120))
    if t.get("ribbon"):
        fr = _fit_line(d, t["ribbon"], WIDTH * 0.6, 50, 34)
        ribbon(d, int(WIDTH * 0.3), int(HEIGHT * 0.46), t["ribbon"], fr, bg=BLUE, fg=YELLOW)
    lines, f2 = _split_lines(d, t["line2"], WIDTH - 200, 118, 2, 56)
    y = HEIGHT - len(lines) * f2.size * 1.3 - 30
    for k, ln in enumerate(lines):
        x = (WIDTH - 90 - _w(d, ln, f2)) / 2
        if k == len(lines) - 1:
            heavy_two_tone(d, (x, y), ln, f2, YELLOW, RED)
        else:
            heavy(d, (x, y), ln, f2, YELLOW)
        y += f2.size * 1.3
    q = _font(220)
    heavy(d, (WIDTH - 150, HEIGHT - 300), "?", q, RED, outline=12)
    return img


def bottom_heavy(img, t):
    """White setup line + huge yellow reveal stacked at the bottom (classic story-channel look)."""
    img = _shade(img, bottom=0.55)
    d = ImageDraw.Draw(img)
    f1 = _fit_line(d, t["line1"], WIDTH - 120, 92, 50)
    lines, f2 = _split_lines(d, t["line2"], WIDTH - 120, 130, 2, 60)
    total = f1.size * 1.28 + len(lines) * f2.size * 1.25
    y = HEIGHT - total - 34
    heavy(d, ((WIDTH - _w(d, t["line1"], f1)) / 2, y), t["line1"], f1, WHITE)
    y += f1.size * 1.28
    for k, ln in enumerate(lines):
        x = (WIDTH - _w(d, ln, f2)) / 2
        if k == len(lines) - 1:
            heavy_two_tone(d, (x, y), ln, f2, YELLOW, RED)
        else:
            heavy(d, (x, y), ln, f2, YELLOW)
        y += f2.size * 1.25
    badge(d, 30, 30)
    return img


def split_arrow(img, t):
    """Before/after split scene: setup ribbon left-top, arrow across, reveal in yellow at the bottom."""
    img = _shade(img, top=0.25, bottom=0.40)
    d = ImageDraw.Draw(img)
    d.line([(WIDTH // 2, 0), (WIDTH // 2, HEIGHT)], fill=WHITE, width=6)
    ribbons(d, 30, 30, t["line1"], WIDTH - t.get("_reserve", 120), start=60)
    _arrow(d, WIDTH * 0.36, HEIGHT * 0.50, WIDTH * 0.58, HEIGHT * 0.40)
    if t.get("ribbon"):
        fr = _fit_line(d, t["ribbon"], WIDTH * 0.48, 48, 32)
        ribbon(d, int(WIDTH * 0.5), int(HEIGHT * 0.50), t["ribbon"], fr, bg=BLUE, fg=WHITE)
    lines, f2 = _split_lines(d, t["line2"], WIDTH - 140, 112, 2, 56)
    y = HEIGHT - len(lines) * f2.size * 1.28 - 26
    for k, ln in enumerate(lines):
        x = (WIDTH - _w(d, ln, f2)) / 2
        if k == len(lines) - 1:
            heavy_two_tone(d, (x, y), ln, f2, YELLOW, RED)
        else:
            heavy(d, (x, y), ln, f2, YELLOW)
        y += f2.size * 1.28
    return img


def horror_title(img, t):
    """Blood-red title with white outline and red glow + yellow tagline, on a dark eerie scene."""
    img = _shade(img, top=0.15, bottom=0.6, strength=245)
    title = t.get("title") or t["line1"]
    tagline = t.get("tagline") or t["line2"]
    lines, ft = _split_lines(ImageDraw.Draw(img), title, WIDTH * 0.62, 150, 2, 70)
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    x0 = int(WIDTH * 0.36)
    y = HEIGHT * 0.30
    pos = []
    for ln in lines:
        pos.append((x0, y))
        _draw(gd, (x0, y), ln, ft, fill=(255, 0, 0, 255), stroke_width=22, stroke_fill=(255, 0, 0, 255))
        y += ft.size * 1.15
    img = Image.alpha_composite(img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(18))).convert("RGB")
    d = ImageDraw.Draw(img)
    for (x, yy), ln in zip(pos, lines):
        _draw(d, (x + 6, yy + 6), ln, ft, fill=BLACK, stroke_width=12, stroke_fill=BLACK)
        _draw(d, (x, yy), ln, ft, fill=(200, 0, 0), stroke_width=9, stroke_fill=WHITE)
    fl = _fit_line(d, tagline, WIDTH - 100, 78, 44)
    tx = (WIDTH - _w(d, tagline, fl)) / 2
    d.rectangle([0, HEIGHT - fl.size * 1.6 - 30, WIDTH, HEIGHT], fill=(140, 0, 0))
    heavy_two_tone(d, (tx, HEIGHT - fl.size * 1.45 - 24), tagline, fl, YELLOW, WHITE, outline=8)
    badge(d, 30, 30)
    return img


LAYOUTS = {"ribbon_top": ribbon_top, "bottom_heavy": bottom_heavy, "split_arrow": split_arrow,
           "horror_title": horror_title}
GENRE_LAYOUTS = {
    "horror": ["horror_title", "bottom_heavy"],
    "doomsday": ["horror_title", "bottom_heavy"],
    "family serial": ["split_arrow", "ribbon_top", "bottom_heavy"],
    "family emotional": ["split_arrow", "ribbon_top", "bottom_heavy"],
    "family moral": ["ribbon_top", "bottom_heavy", "split_arrow"],
    "real lives": ["ribbon_top", "bottom_heavy"],
    "adventure": ["bottom_heavy", "ribbon_top"],
}


def make(bg, texts, out_path, genre="", variant=0, part="", series=""):
    choices = GENRE_LAYOUTS.get(genre, list(LAYOUTS))
    name = choices[variant % len(choices)]
    texts = {k: (v or "").strip() for k, v in texts.items()}
    # any layout works with any texts: horror title/tagline and setup/reveal stand in for each other
    texts.setdefault("line1", "")
    texts.setdefault("line2", "")
    texts["line1"] = texts["line1"] or texts.get("title", "") or texts.get("tagline", "") or "யாரும் எதிர்பார்க்காத கதை…"
    texts["line2"] = texts["line2"] or texts.get("tagline", "") or "கடைசியில் நடந்தது என்ன?"
    if genre in ("horror", "doomsday") and texts.get("title"):
        name = "horror_title"
    texts = {**texts, "_reserve": (460 if series else 340) if part else (460 if series else 100)}
    img = LAYOUTS[name](_prep(bg, horror=(genre in ("horror", "doomsday"))), texts)
    if part:
        part_ribbon(ImageDraw.Draw(img), part, series)
    elif series:
        series_tag(ImageDraw.Draw(img), series)
    img.save(out_path, "JPEG", quality=92, optimize=True)
    return out_path, name
