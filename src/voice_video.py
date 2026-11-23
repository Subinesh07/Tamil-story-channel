"""Viewers' Corner step 2: build the video from the creator's recordings and upload it PRIVATE
(no schedule) for approval. Recordings arrive as unlisted git blobs (never committed, so nobody
browsing the repo sees them).

python src/voice_video.py EPISODE BLOB_SHA,BLOB_SHA,...
"""
import base64
import json
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import ROOT  # noqa: E402

log = logging.getLogger("voice_video")
W, H = 1920, 1080
WORK = ROOT / "output" / "voice"
FONT_B = ROOT / "assets" / "fonts" / "NotoSansTamil-Black.ttf"
FONT_M = ROOT / "assets" / "fonts" / "MuktaMalar-ExtraBold.ttf"
REPO = os.environ.get("GITHUB_REPOSITORY", "Subinesh07/Tamil-story-channel")


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                 "default=nw=1:nk=1", str(p)], capture_output=True, text=True).stdout.strip())


def fetch_blob(sha, dest):
    import requests
    r = requests.get(f"https://api.github.com/repos/{REPO}/git/blobs/{sha}",
                     headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                              "Accept": "application/vnd.github+json"}, timeout=60)
    r.raise_for_status()
    dest.write_bytes(base64.b64decode(r.json()["content"]))


def clean_audio(src, dst):
    """Human voice, gently cleaned: rumble cut, light noise reduction, even loudness, silence trimmed."""
    ff("-i", str(src), "-ac", "1", "-ar", "48000", "-af",
       "highpass=f=80,afftdn=nf=-25,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,"
       "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.25,areverse,"
       "dynaudnorm=f=200:g=15,alimiter=limit=0.9", str(dst))


def _font(path, size):
    from PIL import ImageFont
    return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)


def background():
    from PIL import Image, ImageFilter
    bg = Image.new("RGB", (W, H), (15, 18, 32))
    art = ROOT / "assets" / "brand" / "banner.png"
    if art.exists():
        a = Image.open(art).convert("RGB").resize((W, H)).filter(ImageFilter.GaussianBlur(18))
        bg = Image.blend(bg, a, 0.35)
    return bg


def card(line, title, out):
    from PIL import Image, ImageDraw
    img = background()
    d = ImageDraw.Draw(img, "RGBA")
    d.text((70, 50), "நிலா கதைகள் – உங்க கமெண்ட்ஸ்", font=_font(FONT_B, 46), fill=(245, 197, 66))
    c = line.get("comment")
    if c:
        box = (160, 200, W - 160, 700)
        d.rounded_rectangle(box, 36, fill=(255, 255, 255, 235))
        d.text((220, 240), f"{c['author']}", font=_font(FONT_B, 48), fill=(30, 40, 90))
        body = textwrap.wrap(c["text"], 42)[:5]
        y = 330
        for ln in body:
            d.text((220, y), ln, font=_font(FONT_M, 50), fill=(25, 25, 25))
            y += 72
        d.text((220, 640), f"– {c.get('video', '')}", font=_font(FONT_M, 32), fill=(110, 110, 130))
    else:
        d.text((W // 2, 420), title or "உங்க கமெண்ட்ஸ்க்கு என் பதில்", font=_font(FONT_B, 84),
               fill=(255, 255, 255), anchor="mm")
    sub = textwrap.wrap(line["text"], 46)[:3]
    y = H - 90 - 70 * len(sub)
    for ln in sub:
        d.text((W // 2, y), ln, font=_font(FONT_B, 54), fill=(255, 230, 90), anchor="mm",
               stroke_width=4, stroke_fill=(0, 0, 0))
        y += 70
    img.save(out)


def thumbnail(title, out):
    from PIL import ImageDraw
    img = background().resize((1280, 720))
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle((60, 120, 1220, 600), 40, fill=(0, 0, 0, 150))
    d.text((640, 260), "உங்க கமெண்ட்ஸ்", font=_font(FONT_B, 92), fill=(245, 197, 66), anchor="mm")
    for k, ln in enumerate(textwrap.wrap(title, 22)[:2]):
        d.text((640, 410 + k * 95), ln, font=_font(FONT_B, 74), fill=(255, 255, 255), anchor="mm",
               stroke_width=4, stroke_fill=(0, 0, 0))
    img.convert("RGB").save(out, quality=92)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    episode, shas = sys.argv[1], sys.argv[2].split(",")
    script = json.loads((ROOT / "voice" / "next.json").read_text(encoding="utf-8"))
    if str(script["episode"]) != str(episode) or len(shas) != len(script["lines"]):
        raise SystemExit(f"Recordings ({len(shas)}) do not match script #{script['episode']} "
                         f"({len(script['lines'])} lines)")
    WORK.mkdir(parents=True, exist_ok=True)
    segs = []
    for i, (sha, line) in enumerate(zip(shas, script["lines"])):
        raw, wav, png, seg = (WORK / f"raw_{i}", WORK / f"v_{i}.wav", WORK / f"c_{i}.png", WORK / f"s_{i}.mp4")
        fetch_blob(sha, raw)
        clean_audio(raw, wav)
        card(line, script.get("title", ""), png)
        d = dur(wav) + 0.5
        ff("-loop", "1", "-i", str(png), "-i", str(wav), "-af", "apad=pad_dur=0.5", "-t", f"{d:.2f}",
           "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "30",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", str(seg))
        segs.append(seg)
        log.info("Line %d: %.1f s", i + 1, d)
    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs))
    video = WORK / f"viewers_corner_{episode}.mp4"
    ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(video))
    total = dur(video)
    title = f"💬 உங்க கமெண்ட்ஸ்க்கு என் பதில் – {script.get('title', '')}".strip(" –")[:90] + f" | #{episode}"
    desc = ("உங்க கமெண்ட்ஸ் தான் எங்க பலம்! இந்த வீடியோவில உங்க கமெண்ட்ஸ்க்கு என் குரல்ல பதில் சொல்றேன் 💛\n"
            "அடுத்த வீடியோவுல உங்க கமெண்ட் வரணுமா? கதைகளுக்கு கீழே கமெண்ட் பண்ணுங்க!\n\n"
            "🌙 நிலா கதைகள் – தினமும் ஒரு புது தமிழ் கதை")
    log.info("Viewers' Corner #%s: %.0f s", episode, total)
    if os.environ.get("YT_REFRESH_TOKEN"):
        os.environ["HOLD_FOR_APPROVAL"] = "1"   # private, no schedule: waits for approval
        from youtube_upload import set_thumbnail, upload
        vid = upload(video, {"title_ta": title, "description_ta": desc, "script_ta": "", "chapters": "",
                             "publish_at": "", "genre": "viewers corner", "series_id": ""})
        th = WORK / "thumb.jpg"
        thumbnail(script.get("title", ""), th)
        set_thumbnail(vid, th)
        script["video_id"] = vid
        log.info("Uploaded PRIVATE for approval: https://studio.youtube.com/video/%s/edit", vid)
        (ROOT / "status").mkdir(exist_ok=True)
        (ROOT / "status" / "voice_review.md").write_text(
            f"Viewers' Corner #{episode} is ready ({total / 60:.1f} min) and uploaded **private**.\n\n"
            f"1. Watch it: https://studio.youtube.com/video/{vid}/edit\n"
            f"2. Happy? Tell Claude \"approve viewers corner\" or run the **Approve video** workflow with "
            f"`video:{vid}` – it will be scheduled for the next day 4 PM.\n", encoding="utf-8")
    (ROOT / "voice" / f"done_{episode}.json").write_text(json.dumps(script, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    (ROOT / "voice" / "next.json").unlink()


if __name__ == "__main__":
    main()
