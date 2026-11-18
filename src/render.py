"""Phase 4: zoompan scene clips -> xfade chain -> burned ASS subtitles -> phone-safe MP4."""
import logging

from config import (FADE_IN, FADE_OUT, FPS, HEIGHT, MUSIC_FILE, MUSIC_VOLUME, WIDTH, X264_CRF,
                    X264_PRESET, XFADE, ZOOM_AMOUNT)
from ffutil import run

log = logging.getLogger(__name__)


def render_scene_clip(image, duration, zoom_in, out_path):
    frames = max(2, round(duration * FPS))
    z = (f"1+{ZOOM_AMOUNT}*on/{frames - 1}" if zoom_in
         else f"{1 + ZOOM_AMOUNT}-{ZOOM_AMOUNT}*on/{frames - 1}")
    vf = (f"scale={WIDTH * 2}:{HEIGHT * 2}:flags=lanczos,"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d=1:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(image),
         "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", X264_PRESET,
         "-crf", "16", "-pix_fmt", "yuv420p", str(out_path)])


def render_video(scenes, images, narration, ass_path, total, work_dir, out_path):
    clip_dir = work_dir / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for k, (sc, img) in enumerate(zip(scenes, images)):
        dur = sc["duration"] + (XFADE if k < len(scenes) - 1 else 0)
        clip = clip_dir / f"clip_{k:02d}.mp4"
        log.info("Scene %d/%d: %.1f s (%s)", k + 1, len(scenes), dur, "in" if k % 2 == 0 else "out")
        render_scene_clip(img, dur, zoom_in=(k % 2 == 0), out_path=clip)
        clips.append(clip)

    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]
    inputs += ["-i", str(narration)]
    a_idx = len(clips)
    music = MUSIC_FILE.exists()
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(MUSIC_FILE)]

    parts, prev = [], "[0:v]"
    for k in range(1, len(clips)):
        offset = scenes[k]["start"]  # == sum of previous scene durations
        label = f"[x{k}]"
        parts.append(f"{prev}[{k}:v]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}{label}")
        prev = label
    fade_out_start = max(0.0, total - FADE_OUT)
    parts.append(f"{prev}fade=t=in:st=0:d={FADE_IN},fade=t=out:st={fade_out_start:.3f}:d={FADE_OUT},"
                 f"ass={ass_path.name},format=yuv420p[v]")
    if music:
        log.info("Mixing background music from %s", MUSIC_FILE.name)
        parts.append(f"[{a_idx + 1}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
                     f"volume={MUSIC_VOLUME},atrim=0:{total:.3f}[m]")
        parts.append(f"[{a_idx}:a][m]amix=inputs=2:duration=first:normalize=0,"
                     f"afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out_start:.3f}:d={FADE_OUT}[a]")
    else:
        parts.append(f"[{a_idx}:a]afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out_start:.3f}:d={FADE_OUT}[a]")
    graph = work_dir / "filter.txt"
    graph.write_text(";\n".join(parts), encoding="utf-8")

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex_script", str(graph),
           "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.1", "-pix_fmt", "yuv420p",
           "-preset", X264_PRESET, "-crf", str(X264_CRF), "-r", str(FPS), "-g", str(FPS * 2),
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
           "-movflags", "+faststart", str(out_path)]
    # run from work_dir so the ass= filter gets a plain relative path (no escaping issues)
    import subprocess
    p = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("Final render failed:\n" + "\n".join(p.stderr.splitlines()[-20:]))
    return out_path
