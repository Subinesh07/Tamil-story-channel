"""Phase 4 subtitles: ASS file from timings.json + automated Tamil glyph check."""
import glob
import logging
import subprocess

from PIL import Image

from config import FONT_NAME, FONT_SIZE, HEIGHT, WIDTH
from ffutil import run

log = logging.getLogger(__name__)

HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},{FONT_SIZE},&H0000FFFF,&H0000FFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,1,2,60,60,48,1
Style: Brand,{FONT_NAME},40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,2,1,8,60,60,70,1
Style: Title,{FONT_NAME},72,&H0000D7FF,&H0000D7FF,&H00000000,&H78000000,1,0,0,0,100,100,0,0,1,4,2,5,80,80,0,1
Style: Sub,{FONT_NAME},40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,0,0,0,0,100,100,0,0,1,2,1,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text):
    return text.replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(timings, out_path, cards=()):
    """cards: (start, end, brand, title, subtitle) title-card overlays for intro/outro."""
    lines = [HEADER]
    for s in timings["sentences"]:
        lines.append(f"Dialogue: 0,{_ts(s['start'])},{_ts(s['end'])},Default,,0,0,0,,{_escape(s['text'])}\n")
    fade = r"{\fad(500,500)}"
    for start, end, brand, title, sub in cards:
        if brand:
            lines.append(f"Dialogue: 1,{_ts(start)},{_ts(end)},Brand,,0,0,0,,{fade}{_escape(brand)}\n")
        if title:
            grow = r"{\fscx70\fscy70\t(0,700,\fscx100\fscy100)}"
            lines.append(f"Dialogue: 1,{_ts(start)},{_ts(end)},Title,,0,0,0,,{fade}{grow}{{\\pos(640,300)}}{_escape(title)}\n")
        if sub:
            lines.append(f"Dialogue: 1,{_ts(start)},{_ts(end)},Sub,,0,0,0,,{fade}{{\\pos(640,400)}}{_escape(sub)}\n")
    out_path.write_text("".join(lines), encoding="utf-8-sig")
    return len(timings["sentences"])


def count_dialogues(ass_path):
    """Spoken-sentence subtitles only (title-card overlays are not counted)."""
    return sum(1 for ln in ass_path.read_text(encoding="utf-8-sig").splitlines()
               if ln.startswith("Dialogue:") and ln.split(",")[3] == "Default")


# ---------------- glyph check ----------------

def _font_file():
    out = subprocess.run(["fc-match", "-f", "%{family}|%{file}", FONT_NAME],
                         capture_output=True, text=True).stdout
    family, _, path = out.partition("|")
    return family, path


def _libass_has_harfbuzz():
    """libass needs HarfBuzz for correct Tamil conjuncts and vowel signs."""
    libs = glob.glob("/usr/lib/*/libass.so*") + glob.glob("/usr/lib/libass.so*") + \
        glob.glob("/usr/local/lib/libass.so*")
    for lib in libs:
        out = subprocess.run(["ldd", lib], capture_output=True, text=True).stdout
        if "harfbuzz" in out:
            return True
    return not libs  # statically linked ffmpeg builds: can't tell, rely on frame check


def glyph_check(video, timings, frame_png):
    """Return (ok, reasons). Saves a subtitle frame so a human can eyeball it in the artifacts."""
    reasons = []
    family, path = _font_file()
    if FONT_NAME not in family:
        reasons.append(f"font '{FONT_NAME}' not installed (fontconfig gave '{family}')")
    else:
        try:
            from fontTools.ttLib import TTFont
            cmap = TTFont(path).getBestCmap()
            text = "".join(s["text"] for s in timings["sentences"])
            missing = sorted({c for c in text if 0x0B80 <= ord(c) <= 0x0BFF and ord(c) not in cmap})
            if missing:
                reasons.append(f"font lacks glyphs: {''.join(missing)}")
        except ImportError:
            log.warning("fontTools not installed; skipping cmap coverage check")
    if not _libass_has_harfbuzz():
        reasons.append("libass built without HarfBuzz (Tamil would render broken)")

    # pick a sentence in the middle of the video and grab a frame from it
    s = timings["sentences"][len(timings["sentences"]) // 2]
    t = (s["start"] + s["end"]) / 2
    run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(frame_png)])
    img = Image.open(frame_png).convert("RGB")
    band = img.crop((0, int(HEIGHT * 0.7), WIDTH, HEIGHT))
    yellow = sum(1 for r, g, b in band.getdata() if r > 200 and g > 200 and b < 90)
    if yellow < 400:
        reasons.append(f"subtitle text not visible in frame ({yellow} yellow pixels)")
    return (not reasons), reasons
