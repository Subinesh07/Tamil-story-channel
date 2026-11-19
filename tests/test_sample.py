"""Offline smoke test: renders a ~10 s sample video with placeholder images and tone audio.
No API calls. Must pass before any quota-using step runs.

Run:  python tests/test_sample.py      (or: pytest tests)
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ffutil import ffprobe_duration, ffprobe_streams, run  # noqa: E402
from image_provider import PlaceholderProvider, generate_all  # noqa: E402
from quality import quality_gate  # noqa: E402
from render import render_video  # noqa: E402
from scenes import plan_scenes  # noqa: E402
from stories import split_prompts, split_sentences  # noqa: E402
from subtitles import build_ass  # noqa: E402
from tts import build_narration  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "output" / "sample_test"

SCRIPT = ("1. அம்மா வாசல்ல நின்னு மழையைப் பார்த்துட்டு இருந்தாங்க। "
          "2. கையில ஒரு பழைய கடிதம் இருந்துச்சு। "
          "3. அதுல இருபது வருஷத்துக்கு முன்னாடி எழுதின வார்த்தைகள்। "
          "4. கொஞ்ச நேரத்துல கதவு மெதுவா தட்டுற சத்தம் கேட்டுச்சு। "
          "5. வெளியே நின்னது யாருன்னு அவங்களால நம்பவே முடியல।")
PROMPTS = ("mother at doorway in rain | old letter in hands | a knock on the wooden door")


def make_tone_clips(n, clip_dir):
    clip_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for i in range(n):
        p = clip_dir / f"s{i:04d}.wav"
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={300 + 60 * i}:sample_rate=24000",
             "-t", f"{1.5 + 0.2 * i}", "-ac", "1", str(p)])
        clips.append(p)
    return clips


def test_sample_render():
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    sentences = split_sentences(SCRIPT)
    prompts = split_prompts(PROMPTS)
    assert len(sentences) == 5 and sentences[0].startswith("அம்மா")

    clips = make_tone_clips(len(sentences), OUT / "tts")
    narration, timings = build_narration(clips, sentences, OUT)
    assert len(timings["sentences"]) == 5
    gaps = [b["start"] - a["end"] for a, b in zip(timings["sentences"], timings["sentences"][1:])]
    assert all(0 <= g < 0.05 for g in gaps), gaps   # subtitles bridge the short pause to the next line

    scenes = plan_scenes(timings, len(prompts), n_scenes=3)
    assert len(scenes) == 3 and abs(sum(s["duration"] for s in scenes) - timings["total"]) < 0.01
    images, _ = generate_all(PlaceholderProvider(), [prompts[s["prompt_index"]] for s in scenes],
                             OUT / "images")
    ass = OUT / "subs.ass"
    build_ass(timings, ass)
    video = OUT / "sample.mp4"
    render_video(scenes, images, narration, ass, timings["total"], OUT, video)

    ok, failures, warnings = quality_gate(video, ass, timings, sentences, images,
                                          OUT / "subtitle_frame.png", check_duration=False)
    assert ok, failures
    dur = ffprobe_duration(video)
    assert 9 <= dur <= 13, dur
    v = [s for s in ffprobe_streams(video) if s["codec_type"] == "video"][0]
    assert v["pix_fmt"] == "yuv420p" and v["profile"] == "High"
    (OUT / "result.json").write_text(json.dumps({"duration": dur, "warnings": warnings}))
    print(f"SAMPLE TEST PASSED: {dur:.2f}s, frame saved to {OUT / 'subtitle_frame.png'}")


def test_scene_plan_full_length():
    """22-minute story with 300 sentences and 24 prompts -> 24 scenes of 40-60 s."""
    t, sents = 0.5, []
    for i in range(300):
        d = 4.15
        sents.append({"index": i, "start": t, "end": t + d, "text": "x"})
        t += d + 0.25
    timings = {"total": t + 1.0, "sentences": sents}
    scenes = plan_scenes(timings, 24)
    assert 20 <= len(scenes) <= 25
    assert all(35 <= s["duration"] <= 65 for s in scenes), [s["duration"] for s in scenes]


def test_scene_plan_follows_story_marks():
    """Pictures change exactly where the story's scene marks say (beach -> house -> hospital)."""
    from stories import prompt_marks
    t, sents = 0.0, []
    for i in range(2 + 60 + 2):
        sents.append({"index": i, "start": t, "end": t + 5.0, "text": "x"})
        t += 5.25
    field = "0::beach | 12::house | 30::hospital | 31::too soon | 50::garden"
    marks = [i for i, _ in prompt_marks(field)]
    scenes = plan_scenes({"total": t, "sentences": sents}, len(marks), intro=2, outro=2, marks=marks)
    story = [s for s in scenes if s["kind"] == "story"]
    assert [s["first"] - 2 for s in story] == [0, 12, 30, 50]       # 31 dropped: under 8 s
    assert [s["prompt_index"] for s in story] == [0, 1, 2, 4]
    assert scenes[0]["kind"] == "intro" and scenes[-1]["kind"] == "outro"


def test_upload_metadata():
    from youtube_upload import build_metadata
    row = {"title_ta": "த" * 150, "script_ta": SCRIPT * 5,
           "publish_at": "2099-01-01T19:00:00+05:30"}
    m = build_metadata(row)
    assert len(m["snippet"]["title"]) == 100
    assert m["status"]["privacyStatus"] == "private"
    assert m["status"]["publishAt"].startswith("2099-01-01T19:00")
    assert "Original Tamil story | Narration by AI" in m["snippet"]["description"]
    assert m["snippet"]["categoryId"] == "22"


if __name__ == "__main__":
    test_scene_plan_follows_story_marks()
    test_scene_plan_full_length()
    test_upload_metadata()
    test_sample_render()
