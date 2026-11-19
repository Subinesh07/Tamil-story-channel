"""Produce one video end to end:  story row -> voice -> images -> render -> quality gate -> upload.

python src/make_video.py                 # earliest pending row
python src/make_video.py --row-id 7
python src/make_video.py --no-upload     # stop after the quality gate
"""
import argparse
import json
import logging
import shutil
import sys
import traceback

import re

from config import CHANNEL_NAME_EN, CHANNEL_NAME_TA, INTRO_LINES, OUTPUT_DIR, OUTRO_LINES, WORK_DIR
from ffutil import run
from image_provider import generate_all, get_provider, make_card
from quality import quality_gate
from render import render_video
from scenes import plan_scenes
from stories import (load_rows, long_sentences, pick_row, prompt_marks, split_prompts,
                     split_sentences, update_row)
from subtitles import build_ass
from thumbnail import make_thumbnail
from tts import build_narration, synthesize

log = logging.getLogger("make_video")


def produce(row, upload=True, check_duration=True):
    rid = row["id"]
    work = (WORK_DIR / f"row_{rid}").resolve()
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    out = OUTPUT_DIR.resolve()
    out.mkdir(exist_ok=True)

    story = split_sentences(row["script_ta"])
    prompts = split_prompts(row["scene_prompts"])
    if not story or not prompts:
        raise ValueError("script_ta or scene_prompts is empty")
    if upload and not row["publish_at"] and check_duration:
        raise ValueError("no publish_at date: run the Generate stories workflow with a start_date")
    if long_sentences(story):
        log.warning("%d sentences exceed the word limit", len(long_sentences(story)))

    # intro + story + outro; the wording rotates by story id so videos don't sound templated
    title = re.sub(r"\s*\(.*?\)\s*$", "", row["title_ta"]).strip() or row["title_ta"]
    n = int(rid) if rid.isdigit() else 0
    intro = split_sentences(INTRO_LINES[n % len(INTRO_LINES)].format(title=title))
    from strategy import load as load_strategy
    outro_pool = OUTRO_LINES
    if load_strategy().get("engagement_push"):
        outro_pool = [o for o in OUTRO_LINES if "?" in o or "கமெண்ட்" in o] or OUTRO_LINES
    outro = split_sentences(outro_pool[n % len(outro_pool)])
    sentences = intro + story + outro
    log.info("Row %s '%s': %d story sentences (+%d intro, +%d outro), %d prompts", rid,
             row["title_en"], len(story), len(intro), len(outro), len(prompts))

    log.info("== Voice ==")
    clips, voice = synthesize(sentences, work / "tts")
    narration, timings = build_narration(clips, sentences, work)
    log.info("Narration %.1f min", timings["total"] / 60)

    log.info("== Images ==")
    marks = [i for i, _ in prompt_marks(row["scene_prompts"])]
    marks = marks if all(i is not None for i in marks) else None
    scenes = plan_scenes(timings, len(prompts), intro=len(intro), outro=len(outro), marks=marks)
    log.info("%d pictures (%s)", sum(s["kind"] == "story" for s in scenes),
             "follow the story's scene changes" if marks else "evenly timed")
    story_scenes = [s for s in scenes if s["kind"] == "story"]
    provider = get_provider()
    story_imgs, img_warnings = generate_all(provider, [prompts[s["prompt_index"]] for s in story_scenes],
                                            work / "images", base_seed=n * 1000 + 7)
    it = iter(story_imgs)
    images = []
    for s in scenes:
        if s["kind"] == "intro":
            from brand_assets import ART, intro_background
            card = work / "images" / "intro_card.png"
            images.append(intro_background(card) if ART.exists()
                          else make_card(story_imgs[0], card))
        elif s["kind"] == "outro":
            images.append(make_card(story_imgs[-1], work / "images" / "outro_card.png"))
        else:
            images.append(next(it))

    log.info("== Render ==")
    cards = []
    for s in scenes:
        if s["kind"] == "intro":
            cards.append((s["start"] + 0.3, s["end"] - 0.2, CHANNEL_NAME_TA, title, CHANNEL_NAME_EN))
        elif s["kind"] == "outro":
            cards.append((s["start"] + 0.3, s["end"], CHANNEL_NAME_TA, "Subscribe பண்ணுங்க!",
                          "தினமும் மாலை 7 மணிக்கு ஒரு புது கதை"))
    ass = work / "subs.ass"
    build_ass(timings, ass, cards)
    video = work / f"story_{rid}.mp4"
    render_video(scenes, images, narration, ass, timings["total"], work, video)

    log.info("== Quality gate ==")
    frame = out / f"story_{rid}_subtitle_frame.png"
    ok, failures, warnings = quality_gate(video, ass, timings, sentences, images, frame,
                                          check_duration=check_duration)
    for w in warnings + img_warnings:
        log.warning("QC warning: %s", w)
    shutil.copy(video, out / video.name)
    shutil.copy(work / "timings.json", out / f"story_{rid}_timings.json")
    (out / f"story_{rid}_scenes.json").write_text(json.dumps(scenes, indent=1))
    # intro frame too, so the title card can be checked in the artifacts
    run(["ffmpeg", "-y", "-ss", f"{max(0.5, scenes[0]['duration'] / 2):.2f}", "-i", str(video),
         "-frames:v", "1", str(out / f"story_{rid}_intro_frame.png")], check=False)
    thumb = None
    try:
        thumb = make_thumbnail(story_imgs[min(1, len(story_imgs) - 1)], title,
                               out / f"story_{rid}_thumbnail.jpg", variant=n)
    except Exception as e:
        log.warning("Thumbnail failed: %s", e)
    if not ok:
        raise RuntimeError("Quality gate failed: " + " | ".join(failures))

    if not upload:
        log.info("Upload skipped (--no-upload)")
        return None
    log.info("== Upload ==")
    from youtube_upload import set_thumbnail
    from youtube_upload import upload as yt_upload
    video_id = yt_upload(out / video.name, {**row, "chapters": chapters(scenes)})
    if thumb:
        set_thumbnail(video_id, thumb)
    try:
        from community import draft
        (out / "community_post.md").write_text(draft(row, video_id), encoding="utf-8")
    except Exception as e:
        log.warning("Community post draft failed: %s", e)
    return video_id


CHAPTER_MARKS = [(0.0, "கதை ஆரம்பம்"), (0.35, "கதை நகர்கிறது"), (0.6, "திருப்புமுனை"),
                 (0.85, "உச்சக்கட்டம்")]


def _stamp(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def chapters(scenes):
    """YouTube chapters (need 0:00 first, at least 3, each at least 10 s), snapped to scene cuts."""
    story = [s for s in scenes if s["kind"] == "story"]
    if not story:
        return ""
    s0, s1 = story[0]["start"], story[-1]["end"]
    marks = [(0.0, "அறிமுகம்")] if scenes[0]["kind"] == "intro" else []
    for frac, label in CHAPTER_MARKS:
        target = s0 + frac * (s1 - s0)
        t = min((s["start"] for s in story), key=lambda x: abs(x - target))
        marks.append((t, label))
    if scenes[-1]["kind"] == "outro":
        marks.append((scenes[-1]["start"], "முடிவு"))
    clean = []
    for t, label in sorted(marks):
        if not clean:
            clean.append((0.0, label))
        elif t - clean[-1][0] >= 10:
            clean.append((t, label))
    return "\n".join(f"{_stamp(t)} {label}" for t, label in clean) if len(clean) >= 3 else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--row-id", default="")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--test", action="store_true",
                    help="short test story: skip the 19-26 minute length check and never upload")
    ap.add_argument("--test-upload", action="store_true",
                    help="with --test: upload the test video as a PRIVATE video (no schedule)")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(OUTPUT_DIR / "run.log", encoding="utf-8")])
    rows = load_rows()
    if not args.row_id and not any(r["status"] == "pending" for r in rows):
        log.info("No pending stories yet - nothing to produce today.")
        return 0
    row = pick_row(rows, args.row_id or None)
    update_row(row["id"], status="processing", fail_reason="")
    try:
        upload = args.test_upload if args.test else not args.no_upload
        video_id = produce(row, upload=upload,
                           check_duration=not args.test)
    except Exception as e:
        log.error("Row %s failed: %s", row["id"], e)
        log.debug(traceback.format_exc())
        update_row(row["id"], status="failed", fail_reason=str(e)[:500].replace("\n", " "))
        return 1
    if video_id:
        update_row(row["id"], status="done", video_id=video_id)
    else:
        update_row(row["id"], status="pending")
    log.info("Row %s finished", row["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
