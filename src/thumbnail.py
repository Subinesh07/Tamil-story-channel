"""Auto thumbnail: a story scene + big Tamil title + channel name (1280x720 JPEG under 2 MB)."""
import logging

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, features

from config import CHANNEL_NAME_TA, HEIGHT, THUMB_FONT, WIDTH

log = logging.getLogger(__name__)


def _wrap(draw, text, font, max_w):
    words, lines, line = text.split(), [], ""
    for w in words:
        test = f"{line} {w}".strip()
        if text_w(draw, test, font) <= max_w or not line:
            line = test
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


LATIN_FONT = THUMB_FONT.replace("NotoSansTamil-Bold", "NotoSans-Bold")
_RUN = __import__("re").compile(r"[A-Za-z0-9]+(?:[ .'&-]*[A-Za-z0-9]+)*")


def _runs(text):
    """Split text into (segment, is_latin) runs: the Tamil font has no English letters."""
    out, pos = [], 0
    for m in _RUN.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def _latin(size):
    try:
        return ImageFont.truetype(LATIN_FONT, size)
    except OSError:
        return ImageFont.load_default()


def text_w(draw, text, font):
    return sum(draw.textlength(seg, font=_latin(font.size) if lat else font) for seg, lat in _runs(text))


def draw_mixed(draw, xy, text, font, **kw):
    x, y = xy
    for seg, lat in _runs(text):
        f = _latin(font.size) if lat else font
        opts = dict(kw)
        if not lat:
            opts["language"] = "ta"
        else:
            opts.pop("language", None)
        draw.text((x, y + (font.size * 0.08 if lat else 0)), seg, font=f, **opts)
        x += draw.textlength(seg, font=f)


LAYOUTS = ["left", "bottom", "right"]
COLOURS = [(255, 215, 0), (255, 255, 255), (255, 170, 60)]


def _font(size):
    return ImageFont.truetype(THUMB_FONT, size, layout_engine=ImageFont.Layout.RAQM)


def make_thumbnail(scene_png, title, out_path, variant=0):
    """variant rotates layout and colour per video so thumbnails don't look templated."""
    if not features.check("raqm"):
        log.warning("Pillow has no Tamil text shaping (libraqm); skipping thumbnail")
        return None
    layout = LAYOUTS[variant % len(LAYOUTS)]
    colour = COLOURS[(variant // len(LAYOUTS)) % len(COLOURS)]
    img = Image.open(scene_png).convert("RGB").resize((WIDTH, HEIGHT))
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Color(img).enhance(1.15)

    shade = Image.new("L", (WIDTH, HEIGHT))
    sd = ImageDraw.Draw(shade)
    if layout == "bottom":
        for y in range(HEIGHT):
            sd.line([(0, y), (WIDTH, y)], fill=int(215 * max(0, (y - HEIGHT * 0.35) / (HEIGHT * 0.65))))
    else:
        for x in range(WIDTH):
            t = x / (WIDTH * 0.75) if layout == "left" else (WIDTH - x) / (WIDTH * 0.75)
            sd.line([(x, 0), (x, HEIGHT)], fill=int(205 * max(0, 1 - t)))
    img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, shade)

    d = ImageDraw.Draw(img)
    max_w = WIDTH * (0.9 if layout == "bottom" else 0.6)
    size = 110
    while size > 56:
        font = _font(size)
        lines = _wrap(d, title, font, max_w)
        if len(lines) <= (2 if layout == "bottom" else 3):
            break
        size -= 8
    line_h = size * 1.45
    if layout == "bottom":
        y = HEIGHT - 70 - len(lines) * line_h
    else:
        y = HEIGHT / 2 - len(lines) * line_h / 2 - 20
    for ln in lines:
        w = d.textlength(ln, font=font)
        x = {"left": 60, "right": WIDTH - 60 - w, "bottom": (WIDTH - w) / 2}[layout]
        d.text((x, y), ln, font=font, fill=colour, stroke_width=7, stroke_fill=(0, 0, 0),
               language="ta")
        y += line_h
    brand = _font(38)
    bw = d.textlength(CHANNEL_NAME_TA, font=brand)
    bx = {"left": 60, "right": WIDTH - 60 - bw, "bottom": 40}[layout]
    by = 40 if layout == "bottom" else HEIGHT - 90
    d.text((bx, by), CHANNEL_NAME_TA, font=brand, fill=(255, 255, 255), stroke_width=4,
           stroke_fill=(0, 0, 0), language="ta")
    img.save(out_path, "JPEG", quality=90, optimize=True)
    return out_path


# ---------------------------------------------------------------------------
# "Drama" thumbnail: what top Tamil family-story channels use.
# Realistic emotional scene + quoted shocking dialogue on top + curiosity hook at the bottom.
THUMB_STYLE = ("cinematic semi-realistic digital painting like a Tamil TV serial poster, "
               "dramatic lighting, highly detailed expressive faces, strong emotions, "
               "vibrant saturated colours, sharp focus, no text, no letters, no logos")
BANDS = [((200, 20, 20), (255, 255, 255), (255, 214, 0)),     # red band, white quote, yellow hook
         ((255, 214, 0), (150, 0, 0), (255, 255, 255)),       # yellow band, dark red quote
         ((20, 20, 20), (255, 214, 0), (255, 60, 60))]        # black band, yellow quote, red hook


def make_drama_thumbnail(bg_png, quote, hook, out_path, variant=0, part=""):
    """Bold rotating designs (thumb_designs.py); falls back to the simple banner on any error."""
    if not features.check("raqm"):
        log.warning("Pillow has no Tamil text shaping (libraqm); skipping thumbnail")
        return None
    try:
        import thumb_designs
        return thumb_designs.make(bg_png, quote, hook, out_path, variant, part)
    except Exception as e:  # never lose the thumbnail over a design bug
        log.warning("Thumbnail design failed (%s); using the simple banner", e)
    return _simple_banner(bg_png, quote, hook, out_path, variant)


def _simple_banner(bg_png, quote, hook, out_path, variant=0):
    if not features.check("raqm"):
        log.warning("Pillow has no Tamil text shaping (libraqm); skipping thumbnail")
        return None
    band_col, quote_col, hook_col = BANDS[variant % len(BANDS)]
    img = Image.open(bg_png).convert("RGB").resize((WIDTH, HEIGHT))
    img = ImageEnhance.Color(ImageEnhance.Contrast(img).enhance(1.2)).enhance(1.3)
    d = ImageDraw.Draw(img)

    # top: quoted dialogue on a solid band (max 2 lines)
    quote = "“" + quote.strip().strip('“”"') + "”"
    size = 62
    while True:   # shrink until it fits in 2 lines (3 lines if very long), never overflow
        f = _font(size)
        lines = _wrap(d, quote, f, WIDTH - 80)
        widest = max(text_w(d, ln, f) for ln in lines)
        if (len(lines) <= 2 or (len(lines) == 3 and size <= 46)) and widest <= WIDTH - 60:
            break
        if size <= 34:
            break
        size -= 4
    band_h = int(len(lines) * size * 1.35 + 30)
    d.rectangle([0, 0, WIDTH, band_h], fill=band_col)
    y = 14
    for ln in lines:
        w = text_w(d, ln, f)
        draw_mixed(d, ((WIDTH - w) / 2, y), ln, f, fill=quote_col, stroke_width=3,
                   stroke_fill=(0, 0, 0))
        y += size * 1.35

    # bottom: dark gradient + big curiosity hook (last word highlighted)
    shade = Image.new("L", (WIDTH, HEIGHT))
    sd = ImageDraw.Draw(shade)
    for yy in range(int(HEIGHT * 0.55), HEIGHT):
        sd.line([(0, yy), (WIDTH, yy)], fill=int(230 * (yy - HEIGHT * 0.55) / (HEIGHT * 0.45)))
    img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, shade)
    d = ImageDraw.Draw(img)
    size = 84
    while size > 40:
        hf = _font(size)
        if text_w(d, hook, hf) <= WIDTH - 100:
            break
        size -= 4
    if text_w(d, hook, hf) > WIDTH - 60:   # still too long: keep the first words only
        words_all = hook.split()
        while len(words_all) > 2 and text_w(d, " ".join(words_all) + "…", hf) > WIDTH - 60:
            words_all.pop()
        hook = " ".join(words_all) + "…"
    words = hook.split()
    first, last = " ".join(words[:-1]), words[-1] if words else ""
    total = text_w(d, hook, hf)
    x, y = (WIDTH - total) / 2, HEIGHT - size * 1.5 - 30
    if first:
        draw_mixed(d, (x, y), first + " ", hf, fill=hook_col, stroke_width=7, stroke_fill=(0, 0, 0))
        x += text_w(d, first + " ", hf)
    draw_mixed(d, (x, y), last, hf, fill=(255, 40, 40) if hook_col != (255, 60, 60) else (255, 214, 0),
               stroke_width=7, stroke_fill=(0, 0, 0))

    # small channel badge
    bf = _font(30)
    bw = text_w(d, CHANNEL_NAME_TA, font=bf)
    d.rounded_rectangle([WIDTH - bw - 50, band_h + 16, WIDTH - 18, band_h + 66], radius=12,
                        fill=(15, 15, 40))
    d.text((WIDTH - bw - 34, band_h + 20), CHANNEL_NAME_TA, font=bf, fill=(255, 205, 92), language="ta")
    img.save(out_path, "JPEG", quality=90, optimize=True)
    return out_path
