"""Phase 5: quality gate. Returns (passed, failures, warnings)."""
from config import HARD_MAX, HARD_MIN, MAX_AV_DRIFT, SOFT_MAX, SOFT_MIN
from ffutil import ffprobe_duration, ffprobe_streams, run
from subtitles import count_dialogues, glyph_check


def quality_gate(video, ass_path, timings, sentences, images, frame_png,
                 check_duration=True, hard=(HARD_MIN, HARD_MAX), soft=(SOFT_MIN, SOFT_MAX)):
    failures, warnings = [], []

    if check_duration:
        minutes = ffprobe_duration(video) / 60
        if not hard[0] <= minutes <= hard[1]:
            failures.append(f"duration {minutes:.1f} min outside {hard[0]}-{hard[1]}")
        elif not soft[0] <= minutes <= soft[1]:
            warnings.append(f"duration {minutes:.1f} min is near the limit")

    n_subs = count_dialogues(ass_path)
    if n_subs != len(sentences) or len(timings["sentences"]) != len(sentences):
        failures.append(f"subtitles {n_subs} != sentences {len(sentences)}")

    v = ffprobe_duration(video, "v:0")
    a = ffprobe_duration(video, "a:0")
    if abs(v - a) > MAX_AV_DRIFT:
        failures.append(f"audio {a:.2f}s vs video {v:.2f}s differ by more than {MAX_AV_DRIFT}s")

    missing = [str(p) for p in images if not p.exists() or p.stat().st_size == 0]
    if missing:
        failures.append(f"missing images: {missing}")

    errs = run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], check=False).stderr.strip()
    if errs:
        failures.append("ffmpeg decode errors: " + errs[:300])

    streams = {s["codec_type"]: s for s in ffprobe_streams(video)}
    vs, as_ = streams.get("video", {}), streams.get("audio", {})
    if vs.get("pix_fmt") != "yuv420p" or vs.get("codec_name") != "h264" or vs.get("profile") != "High":
        failures.append(f"video not H.264 High yuv420p ({vs.get('codec_name')}/{vs.get('profile')}/{vs.get('pix_fmt')})")
    if as_.get("codec_name") != "aac" or as_.get("sample_rate") != "44100" or as_.get("channels") != 2:
        failures.append("audio not AAC 44.1 kHz stereo")

    ok, reasons = glyph_check(video, timings, frame_png)
    if not ok:
        failures.append("Tamil glyph check: " + "; ".join(reasons))

    return (not failures), failures, warnings
