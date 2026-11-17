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

from config import OUTPUT_DIR, WORK_DIR
from image_provider import generate_all, get_provider
from quality import quality_gate
from render import render_video
from scenes import plan_scenes
from stories import load_rows, long_sentences, pick_row, split_prompts, split_sentences, update_row
from subtitles import build_ass
from tts import build_narration, synthesize

log = logging.getLogger("make_video")


def produce(row, upload=True):
    rid = row["id"]
    work = (WORK_DIR / f"row_{rid}").resolve()
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    out = OUTPUT_DIR.resolve()
    out.mkdir(exist_ok=True)

    sentences = split_sentences(row["script_ta"])
    prompts = split_prompts(row["scene_prompts"])
    if not sentences or not prompts:
        raise ValueError("script_ta or scene_prompts is empty")
    if upload and not row["publish_at"]:
        raise ValueError("no publish_at date: run the Generate stories workflow with a start_date")
    if long_sentences(sentences):
        log.warning("%d sentences exceed the word limit", len(long_sentences(sentences)))
    log.info("Row %s '%s': %d sentences, %d prompts", rid, row["title_en"], len(sentences), len(prompts))

    log.info("== Voice ==")
    clips, voice = synthesize(sentences, work / "tts")
    narration, timings = build_narration(clips, sentences, work)
    log.info("Narration %.1f min", timings["total"] / 60)

    log.info("== Images ==")
    scenes = plan_scenes(timings, len(prompts))
    needed = [prompts[s["prompt_index"]] for s in scenes]
    provider = get_provider(seed=int(rid) * 1000 + 7)  # same seed per story keeps style steady
    images, img_warnings = generate_all(provider, needed, work / "images")

    log.info("== Render ==")
    ass = work / "subs.ass"
    build_ass(timings, ass)
    video = work / f"story_{rid}.mp4"
    render_video(scenes, images, narration, ass, timings["total"], work, video)

    log.info("== Quality gate ==")
    frame = out / f"story_{rid}_subtitle_frame.png"
    ok, failures, warnings = quality_gate(video, ass, timings, sentences, images, frame)
    for w in warnings + img_warnings:
        log.warning("QC warning: %s", w)
    shutil.copy(video, out / video.name)
    shutil.copy(work / "timings.json", out / f"story_{rid}_timings.json")
    (out / f"story_{rid}_scenes.json").write_text(json.dumps(scenes, indent=1))
    if not ok:
        raise RuntimeError("Quality gate failed: " + " | ".join(failures))

    if not upload:
        log.info("Upload skipped (--no-upload)")
        return None
    log.info("== Upload ==")
    from youtube_upload import upload as yt_upload
    return yt_upload(out / video.name, row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--row-id", default="")
    ap.add_argument("--no-upload", action="store_true")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(OUTPUT_DIR / "run.log", encoding="utf-8")])
    row = pick_row(load_rows(), args.row_id or None)
    update_row(row["id"], status="processing", fail_reason="")
    try:
        video_id = produce(row, upload=not args.no_upload)
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
