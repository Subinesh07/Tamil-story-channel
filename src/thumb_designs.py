"""Bold Tamil thumbnail designs (rotate per video so the channel never looks templated).

Each design takes the background scene, a quoted dialogue line and a short hook, and returns
a 1280x720 image. Text is always Tamil (English words fall back to a Latin font).
"""
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from config import CHANNEL_NAME_TA, HEIGHT, WIDTH
from thumbnail import _font, _wrap, draw_mixed, text_w

RED, YELLOW, WHITE, BLACK = (220, 20, 30), (255, 214, 0), (255, 255, 255), (0, 0, 0)


def _prep(bg):
    img = Image.open(bg).convert("RGB").resize((WIDTH, HEIGHT))
    return ImageEnhance.Color(ImageEnhance.Contrast(img).enhance(1.2)).enhance(1.3)


def _fit(d, text, max_w, start, min_size, max_lines):
    size = start
    while True:
        f = _font(size)
        lines = _wrap(d, text, f, max_w)
        if (len(lines) <= max_lines and max(text_w(d, ln, f) for ln in lines) <= max_w) or size <= min_size:
            return f, lines
        size -= 4


def _text3d(d, xy, text, f, fill, depth=5, outline=6):
    """Chunky 3D text: dark offset layers + thick outline."""
    x, y = xy
    for k in range(depth, 0, -1):
        draw_mixed(d, (x + k, y + k), text, f, fill=(40, 0, 0), stroke_width=outline, stroke_fill=(40, 0, 0))
    draw_mixed(d, (x, y), text, f, fill=fill, stroke_width=outline, stroke_fill=BLACK)


def _glow_border(img, colour=RED, width=14):
    d = ImageDraw.Draw(img)
    for k in range(width):
        a = int(255 * (1 - k / width))
        d.rectangle([k, k, WIDTH - 1 - k, HEIGHT - 1 - k], outline=tuple(int(c * a / 255) for c in colour))
    return img


def _badge(d, x, y, right=False):
    """Channel badge; with right=True, x is the right edge (badge never runs off the image)."""
    f = _font(30)
    w = text_w(d, CHANNEL_NAME_TA, f) + 32
    if right:
        x = x - w
    d.rounded_rectangle([x, y, x + w, y + 50], radius=12, fill=(15, 15, 40))
    draw_mixed(d, (x + 16, y + 4), CHANNEL_NAME_TA, f, fill=(255, 205, 92))


def _quote(q):
    return "“" + q.strip().strip('“”"') + "”"


def _split_hook(hook):
    w = hook.split()
    return (" ".join(w[:-1]), w[-1]) if len(w) > 1 else ("", hook)


def _shade(img, top=None, bottom=None, left=None):
    m = Image.new("L", (WIDTH, HEIGHT))
    md = ImageDraw.Draw(m)
    for y in range(HEIGHT):
        v = 0
        if bottom and y > HEIGHT * (1 - bottom):
            v = max(v, int(235 * (y - HEIGHT * (1 - bottom)) / (HEIGHT * bottom)))
        if top and y < HEIGHT * top:
            v = max(v, int(200 * (1 - y / (HEIGHT * top))))
        md.line([(0, y), (WIDTH, y)], fill=v)
    if left:
        for x in range(int(WIDTH * left)):
            md.line([(x, 0), (x, HEIGHT)], fill=int(225 * (1 - x / (WIDTH * left))))
    return Image.composite(Image.new("RGB", img.size, BLACK), img, m)


# ---------------------------------------------------------------- 1. speech bubble
def bubble(bg, quote, hook):
    img = _shade(_prep(bg), bottom=0.4)
    d = ImageDraw.Draw(img)
    f, lines = _fit(d, _quote(quote), 700, 56, 34, 3)
    lh = f.size * 1.3
    bw = max(text_w(d, ln, f) for ln in lines) + 60
    bh = len(lines) * lh + 40
    x0, y0 = 40, 40
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=36, fill=WHITE, outline=BLACK, width=5)
    d.polygon([(x0 + bw * 0.55, y0 + bh - 3), (x0 + bw * 0.72, y0 + bh - 3), (x0 + bw * 0.78, y0 + bh + 55)],
              fill=WHITE, outline=BLACK)
    d.line([(x0 + bw * 0.55, y0 + bh - 2), (x0 + bw * 0.72, y0 + bh - 2)], fill=WHITE, width=8)
    y = y0 + 18
    for ln in lines:
        draw_mixed(d, (x0 + 30, y), ln, f, fill=(170, 0, 0))
        y += lh
    hf, hl = _fit(d, hook, WIDTH - 140, 80, 44, 1)
    hw = text_w(d, hl[0], hf)
    hx, hy = (WIDTH - hw) / 2, HEIGHT - hf.size * 1.6 - 36
    d.rounded_rectangle([hx - 26, hy - 8, hx + hw + 26, hy + hf.size * 1.45], radius=16, fill=YELLOW)
    draw_mixed(d, (hx, hy), hl[0], hf, fill=(170, 0, 0), stroke_width=2, stroke_fill=(170, 0, 0))
    _badge(d, WIDTH - 40, 40, right=True)
    return _glow_border(img)


# ---------------------------------------------------------------- 2. colour bars
def bars(bg, quote, hook):
    img = _shade(_prep(bg), left=0.62)
    d = ImageDraw.Draw(img)
    first, last = _split_hook(hook)
    rows = [(_quote(quote), WHITE, (170, 0, 0)), (first, RED, YELLOW), (last, YELLOW, (150, 0, 0))]
    y = 50
    for text, box, col in rows:
        if not text:
            continue
        start = 52 if text.startswith("“") else 78
        f, lines = _fit(d, text, 720, start, 34, 3 if text.startswith("“") else 2)
        for ln in lines:
            w = text_w(d, ln, f)
            d.rectangle([36, y, 36 + w + 40, y + f.size * 1.42], fill=box)
            draw_mixed(d, (56, y + 2), ln, f, fill=col)
            y += f.size * 1.42 + 10
        y += 12
    _badge(d, 40, HEIGHT - 76)
    return img


# ---------------------------------------------------------------- 3. split panel + arrow
def split(bg, quote, hook):
    base = _prep(bg)
    img = Image.new("RGB", (WIDTH, HEIGHT), (12, 8, 24))
    # right: zoomed emotional crop of the scene in a framed panel
    w, h = base.size
    crop = base.crop((int(w * 0.25), int(h * 0.05), int(w * 0.75), int(h * 0.80))).resize((560, 600))
    img.paste(ImageEnhance.Brightness(base.filter(ImageFilter.GaussianBlur(18))).enhance(0.35), (0, 0))
    img.paste(crop, (WIDTH - 600, 60))
    d = ImageDraw.Draw(img)
    d.rectangle([WIDTH - 606, 54, WIDTH - 34, 666], outline=YELLOW, width=8)
    # left: quote + hook, scaled down together until everything fits above the badge
    first, last = _split_hook(hook)
    for scale in (1.0, 0.9, 0.8, 0.7, 0.6):
        qf, ql = _fit(d, _quote(quote), 560, int(50 * scale), 28, 4)
        hf, hl = _fit(d, first or last, 560, int(70 * scale), 32, 2)
        lf, _ = _fit(d, last, 560, int(92 * scale), 40, 1)
        height = len(ql) * qf.size * 1.35 + 30 + len(hl) * hf.size * 1.4 + (lf.size * 1.5 if first else 0)
        if 60 + height <= HEIGHT - 100:
            break
    y = 60
    for ln in ql:
        draw_mixed(d, (44, y), ln, qf, fill=WHITE, stroke_width=4, stroke_fill=BLACK)
        y += qf.size * 1.35
    y += 30
    for ln in hl:
        _text3d(d, (44, y), ln, hf, YELLOW, depth=4)
        y += hf.size * 1.4
    if first:
        _text3d(d, (44, y), last, lf, (255, 60, 60), depth=6)
    # red arrow from text to the face
    ax, ay = 620, int(HEIGHT * 0.55)
    d.line([(ax - 40, ay + 40), (ax + 40, ay - 20)], fill=RED, width=18)
    d.polygon([(ax + 70, ay - 45), (ax + 15, ay - 40), (ax + 55, ay + 10)], fill=RED)
    _badge(d, 44, HEIGHT - 76)
    return img


# ---------------------------------------------------------------- 4. big shock word
def shock(bg, quote, hook):
    img = _shade(_prep(bg), top=0.3, bottom=0.45)
    d = ImageDraw.Draw(img)
    f, lines = _fit(d, _quote(quote), WIDTH - 120, 44, 30, 2)
    y = 26
    for ln in lines:
        draw_mixed(d, (50, y), ln, f, fill=WHITE, stroke_width=4, stroke_fill=BLACK)
        y += f.size * 1.3
    first, last = _split_hook(hook)
    if first:
        sf, sl = _fit(d, first, WIDTH - 120, 54, 34, 1)
        sw = text_w(d, sl[0], sf)
        draw_mixed(d, ((WIDTH - sw) / 2, HEIGHT - 300), sl[0], sf, fill=WHITE, stroke_width=5, stroke_fill=BLACK)
    bf, bl = _fit(d, last, WIDTH - 100, 150, 70, 1)
    bw = text_w(d, bl[0], bf)
    _text3d(d, ((WIDTH - bw) / 2, HEIGHT - bf.size * 1.55 - 20), bl[0], bf, YELLOW, depth=9, outline=9)
    _badge(d, WIDTH - 40, y + 10, right=True)
    return img


# ---------------------------------------------------------------- 5. banner (improved)
def banner(bg, quote, hook):
    img = _shade(_prep(bg), bottom=0.45)
    d = ImageDraw.Draw(img)
    f, lines = _fit(d, _quote(quote), WIDTH - 80, 60, 34, 2)
    band_h = int(len(lines) * f.size * 1.35 + 30)
    d.rectangle([0, 0, WIDTH, band_h], fill=RED)
    d.rectangle([0, band_h, WIDTH, band_h + 8], fill=YELLOW)
    y = 14
    for ln in lines:
        w = text_w(d, ln, f)
        draw_mixed(d, ((WIDTH - w) / 2, y), ln, f, fill=WHITE, stroke_width=3, stroke_fill=(90, 0, 0))
        y += f.size * 1.35
    first, last = _split_hook(hook)
    hf, _ = _fit(d, hook, WIDTH - 100, 88, 44, 1)
    total = text_w(d, hook, hf)
    x, y = (WIDTH - total) / 2, HEIGHT - hf.size * 1.55 - 26
    if first:
        _text3d(d, (x, y), first + " ", hf, WHITE, depth=4)
        x += text_w(d, first + " ", hf)
    _text3d(d, (x, y), last, hf, YELLOW, depth=6)
    _badge(d, WIDTH - 30, band_h + 22, right=True)
    return img


DESIGNS = [bubble, bars, split, shock, banner]


def make(bg, quote, hook, out_path, variant=0):
    img = DESIGNS[variant % len(DESIGNS)](bg, quote, hook)
    img.save(out_path, "JPEG", quality=90, optimize=True)
    return out_path
