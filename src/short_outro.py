"""Ending card added to every Short (about 5 s).

Asks viewers to tap the Related video button for the full story, like, subscribe and answer the daily quiz.
The card is drawn with PIL (no picture credits). The Leda voice line is made ONCE
(`python src/short_outro.py voice`, Whisper-checked like every passage) and saved as
assets/brand/short_outro.wav, then reused by every Short - no voice credits per Short.
Without that file the card plays with a soft chime only.
"""
import logging
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from ffutil import ffprobe_duration, run

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
VOICE = ROOT / "assets" / "brand" / "short_outro.wav"
W, H = 1080, 1920
SECONDS = 5.0

LINES = [  # (text, colour) - what is written on the card
    ("👇 கீழே உள்ள பட்டனை அழுத்துங்க", "yellow"),
    ("முழு கதையை பாருங்க!", "yellow"),
    ("👍 Like பண்ணுங்க", "white"),
    ("🔔 Subscribe பண்ணுங்க", "white"),
    ("🧠 தினமும் குவிஸ்ல கலந்துக்கோங்க!", "yellow"),
    ("கமெண்ட்ல பதில் சொல்லுங்க", "white"),
]
SPOKEN = [  # what Leda says (once, saved)
    "முழு கதையை பார்க்க, கீழே உள்ள பட்டனை அழுத்துங்க.",
    "வீடியோ பிடிச்சிருந்தா லைக் பண்ணுங்க, சேனலை சப்ஸ்கிரைப் பண்ணுங்க.",
    "தினமும் குவிஸ்ல கலந்துக்கோங்க!",
]


def card(bg_frame, out_png):
    """Blurred last frame of the Short + the call-to-action lines + an arrow pointing at the button."""
    import re
    from thumb_v2 import RED, WHITE, YELLOW, _font, heavy
    base = Image.open(bg_frame).convert("RGB").resize((W, H)).filter(ImageFilter.GaussianBlur(28))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.blend(base, dark, 0.55)
    d = ImageDraw.Draw(img)
    y = 400
    for text, col in LINES:
        text = re.sub(r"[^஀-௿\w\s!?.,–-]", "", text).strip()   # emoji show as boxes
        size = 84
        while size > 36 and d.textlength(text, font=_font(size)) > W - 160:
            size -= 4
        f = _font(size)
        x = (W - int(d.textlength(text, font=f))) // 2
        heavy(d, (x, y), text, f, YELLOW if col == "yellow" else WHITE, outline=8, shadow=5)
        y += int(size * 1.55) + (40 if text.startswith(("முழு", "Subscribe")) else 0)
    # big red arrow pointing down at the Related video button (bottom-left of a Short)
    ax, ay = 300, 1430
    d.rectangle([ax - 26, ay, ax + 26, ay + 150], fill=RED, outline=(0, 0, 0), width=4)
    d.polygon([(ax - 90, ay + 150), (ax + 90, ay + 150), (ax, ay + 270)], fill=RED, outline=(0, 0, 0))
    f = _font(46)
    heavy(d, ((W - int(d.textlength("நிலா கதைகள்", font=f))) // 2, 300), "நிலா கதைகள்", f, WHITE,
          outline=5, shadow=3)
    img.save(out_png)
    return out_png


def append(short_mp4):
    """Add the ending card to a finished Short (in place). Never breaks the Short on failure."""
    short_mp4 = Path(short_mp4)
    try:
        tmp = short_mp4.with_name(short_mp4.stem + "_outro")
        frame, png, clip, joined = (tmp.with_suffix(".jpg"), tmp.with_suffix(".png"),
                                    tmp.with_suffix(".mp4"), short_mp4.with_name(short_mp4.stem + "_full.mp4"))
        run(["ffmpeg", "-y", "-sseof", "-0.5", "-i", str(short_mp4), "-frames:v", "1", str(frame)])
        card(frame, png)
        if VOICE.exists():
            audio = ["-i", str(VOICE)]
            afilter = f"[1:a]aresample=48000,apad,atrim=0:{SECONDS},afade=t=out:st={SECONDS - 0.4}:d=0.4[a]"
        else:   # soft chime instead of voice
            audio = ["-f", "lavfi", "-i", f"sine=frequency=880:duration={SECONDS}"]
            afilter = (f"[1:a]volume=0.08,afade=t=in:d=0.05,afade=t=out:st=0.6:d=0.6,aresample=48000,"
                       f"apad,atrim=0:{SECONDS}[a]")
        if VOICE.exists():
            dur = ffprobe_duration(VOICE)
            secs = max(SECONDS, dur + 0.6)
            afilter = afilter.replace(f"atrim=0:{SECONDS},afade=t=out:st={SECONDS - 0.4}",
                                      f"atrim=0:{secs:.2f},afade=t=out:st={secs - 0.4:.2f}")
        else:
            secs = SECONDS
        run(["ffmpeg", "-y", "-loop", "1", "-t", f"{secs:.2f}", "-i", str(png), *audio,
             "-filter_complex", f"[0:v]scale={W}:{H},fps=30,format=yuv420p[v];{afilter}",
             "-map", "[v]", "-map", "[a]", "-t", f"{secs:.2f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k", str(clip)])
        run(["ffmpeg", "-y", "-i", str(short_mp4), "-i", str(clip), "-filter_complex",
             "[0:v]fps=30,format=yuv420p[v0];[0:a]aresample=48000[a0];[1:v]fps=30,format=yuv420p[v1];"
             "[1:a]aresample=48000[a1];[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(joined)])
        joined.replace(short_mp4)
        log.info("Short ending card added (%.1f s, %s)", secs, "Leda voice" if VOICE.exists() else "chime")
    except Exception as e:
        log.warning("Short ending card skipped: %s", str(e)[:150])
    return short_mp4


def make_voice():
    """One-time: voice the ending line with Leda (listening + Whisper checks), save it to assets/brand."""
    import shutil
    import subprocess
    from gemini_voice import synthesize
    pieces = synthesize(SPOKEN, "short_outro")
    wavs = [str(p[0]) for p in pieces]
    VOICE.parent.mkdir(parents=True, exist_ok=True)
    if len(wavs) == 1:
        shutil.copy(wavs[0], VOICE)
    else:
        lst = VOICE.with_suffix(".txt")
        lst.write_text("".join(f"file '{w}'\n" for w in wavs))
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), str(VOICE)], check=True)
        lst.unlink()
    from langcheck import english_windows
    bad = english_windows(str(VOICE), win=2)
    if bad:
        VOICE.unlink()
        raise SystemExit(f"Whisper heard English in the ending line {bad} - not saved")
    log.info("Saved %s", VOICE)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if sys.argv[1:] == ["voice"]:
        make_voice()
    elif sys.argv[1:2] == ["test"]:
        append(sys.argv[2])
