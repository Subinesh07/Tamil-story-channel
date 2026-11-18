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


def make_thumbnail(scene_png, title, out_path):
    if not features.check("raqm"):
        log.warning("Pillow has no Tamil text shaping (libraqm); skipping thumbnail")
        return None
    img = Image.open(scene_png).convert("RGB").resize((WIDTH, HEIGHT))
    img = ImageEnhance.Contrast(img).enhance(1.15)
    # dark gradient on the left so the text stays readable
    shade = Image.new("L", (WIDTH, HEIGHT))
    sd = ImageDraw.Draw(shade)
    for x in range(WIDTH):
        sd.line([(x, 0), (x, HEIGHT)], fill=int(200 * max(0, 1 - x / (WIDTH * 0.75))))
    img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, shade)

    d = ImageDraw.Draw(img)
    size = 104
    while size > 56:
        font = ImageFont.truetype(THUMB_FONT, size, layout_engine=ImageFont.Layout.RAQM)
        lines = _wrap(d, title, font, WIDTH * 0.62)
        if len(lines) <= 3:
            break
        size -= 8
    y = HEIGHT / 2 - len(lines) * size * 0.75
    for ln in lines:
        d.text((60, y), ln, font=font, fill=(255, 215, 0), stroke_width=7, stroke_fill=(0, 0, 0),
               language="ta")
        y += size * 1.45
    brand = ImageFont.truetype(THUMB_FONT, 40, layout_engine=ImageFont.Layout.RAQM)
    d.text((60, HEIGHT - 90), CHANNEL_NAME_TA, font=brand,
           fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0), language="ta")
    img.save(out_path, "JPEG", quality=90, optimize=True)
    return out_path
