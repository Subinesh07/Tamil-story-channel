"""Auto thumbnail: a story scene + big Tamil title + channel name (1280x720 JPEG under 2 MB)."""
import logging

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, features

from config import CHANNEL_NAME_TA, HEIGHT, THUMB_FONT, WIDTH

log = logging.getLogger(__name__)


def _wrap(draw, text, font, max_w):
    words, lines, line = text.split(), [], ""
    for w in words:
        test = f"{line} {w}".strip()
        if draw.textlength(test, font=font) <= max_w or not line:
            line = test
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


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
