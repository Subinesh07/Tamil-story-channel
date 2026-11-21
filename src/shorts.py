"""Shorts trailers: a 35-55 second vertical clip of each story's opening hook, uploaded as a
YouTube Short that points to the full video. Made from the finished video, so it costs no voice
or picture credits.

Layout (1080x1920): blurred, darkened copy of the video as background; the video itself in the
middle (with its Tamil subtitles); the story title on top; "முழு கதை சேனல்ல" at the bottom.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from ffutil import run

log = logging.getLogger("shorts")
W, H = 1080, 1920
MIN_S, MAX_S = 30.0, 55.0


def pick_segment(timings, intro_len):
    """Story opening: from the first story sentence to a sentence end at most 55 s later."""
    sents = timings["sentences"]
    if len(sents) <= intro_len + 2:
        return None
    start = sents[intro_len]["start"]
    end = None
    for s in sents[intro_len:]:
        if s["end"] - start > MAX_S:
            break
        end = s["end"]
    if end is None or end - start < MIN_S:
        return None
    return max(0.0, start - 0.2), min(end + 0.4, timings["total"])


def overlay_png(title, out_path):
    """Transparent 1080x1920 layer: title at the top, call to action at the bottom."""
    from thumb_v2 import RED, WHITE, YELLOW, _font, _split_lines, heavy
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    import re
    title = re.sub(r"[^\u0B80-\u0BFF\w\s!?.,'’:-]", "", title).strip()   # no emoji (they show as boxes)
    words = title.split()
    lines, f = [title], _font(56)
    for n in (2, 3, 4):
        per = -(-len(words) // n)
        cand = [" ".join(words[i:i + per]) for i in range(0, len(words), per)]
        size = 96
        while size > 52 and any(d.textlength(c, font=_font(size)) > W - 100 for c in cand):
            size -= 4
        lines, f = cand, _font(size)
        if size >= 64:
            break
    y = 200
    for ln in lines:
        heavy(d, (50, y), ln, f, YELLOW, outline=9, shadow=6)
        y += int(f.size * 1.35)
    cta = "முழு கதை சேனல்ல பாருங்க!"
    lines2, f2 = _split_lines(d, cta, W - 160, 70, max_lines=1, min_size=44)
    bw = int(d.textlength(lines2[0], font=f2)) + 80
    x0, y0 = (W - bw) // 2, 1480
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + int(f2.size * 1.6)], radius=28, fill=RED)
    heavy(d, (x0 + 40, y0 + int(f2.size * 0.18)), lines2[0], f2, WHITE, outline=4, shadow=3)
    sub = "🔔 Subscribe – நிலா கதைகள்".replace("🔔 ", "")
    f3 = _split_lines(d, sub, W - 200, 50, max_lines=1, min_size=36)[1]
    heavy(d, ((W - int(d.textlength(sub, font=f3))) // 2, y0 + int(f2.size * 1.6) + 40), sub, f3, WHITE,
          outline=5, shadow=3)
    img.save(out_path)
    return out_path


def make_short(video, timings, intro_len, title, out_path):
    seg = pick_segment(timings, intro_len)
    if not seg:
        log.warning("Story too short for a Short trailer")
        return None
    a, b = seg
    dur = b - a
    layer = overlay_png(title, Path(out_path).with_suffix(".png"))
    graph = (f"[0:v]split[a][b];"
             f"[a]scale=-2:{H},crop={W}:{H},boxblur=22:2,eq=brightness=-0.18[bg];"
             f"[b]scale={W}:-2[fg];"
             f"[bg][fg]overlay=0:(H-h)/2[v1];"
             f"[v1][1:v]overlay=0:0,format=yuv420p[v];"
             f"[0:a]afade=t=in:d=0.3,afade=t=out:st={max(0, dur - 0.6):.2f}:d=0.6[aout]")
    run(["ffmpeg", "-y", "-ss", f"{a:.2f}", "-t", f"{dur:.2f}", "-i", str(video), "-i", str(layer),
         "-filter_complex", graph, "-map", "[v]", "-map", "[aout]", "-r", "30",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(out_path)])
    log.info("Short trailer: %.0f s from %.0f s", dur, a)
    return Path(out_path)


def upload_short(path, row, long_video_id, long_publish_at):
    """Upload as a Short, scheduled 30 minutes after the full video (or soon, if that has passed)."""
    from youtube_upload import upload as yt_upload
    when = datetime.fromisoformat(long_publish_at) + timedelta(minutes=30) if long_publish_at else None
    soon = datetime.now(timezone.utc) + timedelta(minutes=10)
    if not when or when < soon:
        when = soon
    head = row["title_ta"].split(" | ")[0].strip()
    title = (head[:88] + " #shorts") if len(head) > 88 else head + " #shorts"
    desc = (f"முழு கதை 👉 https://youtu.be/{long_video_id}\n\n"
            f"{(row.get('description_ta') or '').strip()[:300]}\n\n#shorts #tamilstory #tamilkathaigal")
    short_row = {**row, "title_ta": title, "description_ta": desc, "publish_at": when.isoformat(),
                 "chapters": ""}
    vid = yt_upload(path, short_row)
    log.info("Short uploaded: %s (goes public %s)", vid, when.isoformat())
    return vid
