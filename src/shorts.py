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


def window_at(timings, centre_idx, intro_len, end_at_idx=None):
    """30-55 s of whole sentences: ending at end_at_idx, or centred on centre_idx."""
    sents = timings["sentences"]
    n = len(sents)
    if end_at_idx is not None:
        j = min(end_at_idx, n - 1)
        i = j
        while i - 1 >= intro_len and sents[j]["end"] - sents[i - 1]["start"] <= MAX_S:
            i -= 1
    else:
        i = j = max(intro_len, min(centre_idx, n - 1))
        while True:
            grew = False
            if j + 1 < n and sents[j + 1]["end"] - sents[i]["start"] <= MAX_S:
                j += 1; grew = True
            if i - 1 >= intro_len and sents[j]["end"] - sents[i - 1]["start"] <= MAX_S:
                i -= 1; grew = True
            if not grew:
                break
    a, b = sents[i]["start"], sents[j]["end"]
    if b - a < MIN_S:
        return None
    return max(0.0, a - 0.2), min(b + 0.4, timings["total"]), i, j


def pick_extra_segments(timings, intro_len, sentences_text=None, final=False):
    """Two more Shorts from the same video: the strongest middle moment and the cliffhanger
    (for a final part / standalone story: a late twist instead of the ending, so nothing is spoiled).
    Gemini picks the moments if it can (text only, tiny); otherwise fixed positions."""
    sents = timings["sentences"]
    n = len(sents)
    story = list(range(intro_len, n))
    if len(story) < 30:
        return []
    picks = []
    if sentences_text:
        try:
            from llm import complete
            numbered = "\n".join(f"{k}. {sentences_text[k]}" for k in story if k < len(sentences_text))
            data = complete(
                "These are numbered sentences of a Tamil story video. Pick the 2 most gripping moments for "
                "YouTube Shorts (each about 45 seconds = 8-12 sentences): a shocking twist or reveal in the "
                "MIDDLE, and the tensest moment near the end" +
                (" (but NOT the final resolution - never spoil the ending)" if final else " (the cliffhanger)") +
                ". The two must not overlap and must not be in the first 15% of the story. "
                "Return JSON {\"moments\": [last_sentence_number_of_moment_1, last_sentence_number_of_moment_2]}"
                "\n\n" + numbered[:24000], want_json=True, max_tokens=300, rounds=1)
            picks = [int(x) for x in data["moments"]][:2]
        except Exception as e:
            log.warning("Shorts moment pick by AI failed (%s); using fixed positions", str(e)[:100])
            picks = []
    if len(picks) < 2:
        L = len(story)
        picks = [story[int(L * 0.55)], story[int(L * 0.8)] if final else story[-1]]
    out, used = [], []
    first_end = intro_len
    for k in picks:
        w = window_at(timings, None, intro_len, end_at_idx=max(intro_len + 8, k))
        if not w:
            continue
        a, b, i, j = w
        if i < intro_len + max(6, len(story) // 7):
            continue   # too close to the opening Short
        if any(not (j < ui or i > uj) for ui, uj in used):
            continue
        used.append((i, j))
        out.append((a, b))
    return out


def overlay_png(title, out_path, cta="முழு கதை சேனல்ல பாருங்க!"):
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


def make_short(video, timings, intro_len, title, out_path, seg=None, cta="முழு கதை சேனல்ல பாருங்க!"):
    seg = seg or pick_segment(timings, intro_len)
    if not seg:
        log.warning("Story too short for a Short trailer")
        return None
    a, b = seg
    dur = b - a
    layer = overlay_png(title, Path(out_path).with_suffix(".png"), cta)
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


EXTRA = [  # (title ending, call to action) for Short 2 and Short 3 - different every time they appear
    (" – இதுக்கப்புறம் என்ன? 😱", "அடுத்து என்ன? முழு கதை சேனல்ல!"),
    (" – கடைசில என்ன ஆச்சு? 🔥", "முடிவு தெரியணுமா? முழு கதை சேனல்ல!"),
]


def extra_when(long_publish_at, k):
    """Short 2 next day 1 PM IST, Short 3 the day after (afternoon gap between long videos)."""
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    base = datetime.fromisoformat(long_publish_at).astimezone(ist) if long_publish_at else datetime.now(ist)
    when = (base + timedelta(days=k)).replace(hour=13, minute=0, second=0, microsecond=0)
    soon = datetime.now(timezone.utc) + timedelta(minutes=10)
    return max(when, soon.astimezone(ist))


def upload_short(path, row, long_video_id, long_publish_at, when=None, ending=""):
    """Upload as a Short, scheduled 30 minutes after the full video (or soon, if that has passed)."""
    from youtube_upload import upload as yt_upload
    if when is None:
        when = datetime.fromisoformat(long_publish_at) + timedelta(minutes=30) if long_publish_at else None
    soon = datetime.now(timezone.utc) + timedelta(minutes=10)
    if not when or when < soon:
        when = soon
    head = row["title_ta"].split(" | ")[0].strip()
    room = 88 - len(ending)
    head = (head[:room].rsplit(" ", 1)[0] + "…") if len(head) > room else head
    title = head + ending + " #shorts"
    desc = (f"முழு கதை 👉 https://youtu.be/{long_video_id}\n\n"
            f"{(row.get('description_ta') or '').strip()[:300]}\n\n#shorts #tamilstory #tamilkathaigal")
    short_row = {**row, "title_ta": title, "description_ta": desc, "publish_at": when.isoformat(),
                 "chapters": ""}
    vid = yt_upload(path, short_row)
    log.info("Short uploaded: %s (goes public %s)", vid, when.isoformat())
    return vid
