"""Produce one video end to end:  story row -> voice -> images -> render -> quality gate -> upload.

python src/make_video.py                 # earliest pending row
python src/make_video.py --row-id 7
python src/make_video.py --no-upload     # stop after the quality gate
"""
import argparse
import json
import subprocess
import os
import logging
import shutil
import sys
import traceback

import re

from config import (ROOT, CHANNEL_NAME_EN, CHANNEL_NAME_TA, IMAGE_STYLE, INTRO_LINES, OUTPUT_DIR,
                    OUTRO_LINES, TTS_ENGINE, WORK_DIR)
from ffutil import run
from image_provider import generate_all, get_provider, make_card, make_outro_card
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
    # older stories were written with the watercolour style: swap in the current picture style
    old_style = "warm watercolor illustration, South Indian home, soft natural light, no text, no logos"
    from config import OLD_IMAGE_STYLE
    row = {**row, "scene_prompts": row["scene_prompts"].replace(old_style, IMAGE_STYLE)
           .replace(OLD_IMAGE_STYLE, IMAGE_STYLE)}
    prompts = split_prompts(row["scene_prompts"])
    if not story or not prompts:
        raise ValueError("script_ta or scene_prompts is empty")
    if upload and not row["publish_at"] and check_duration:
        raise ValueError("no publish_at date: run the Generate stories workflow with a start_date")
    if long_sentences(story):
        log.warning("%d sentences exceed the word limit", len(long_sentences(story)))

    # intro + story + outro; the wording rotates by story id so videos don't sound templated
    title = re.sub(r"\s*\(.*?\)\s*$", "", row["title_ta"].split("|")[0]).strip() or row["title_ta"]
    part = row.get("part") or ""
    if part:
        title = f"{title}, பகுதி {part}"
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
    if TTS_ENGINE == "gemini":
        from gemini_voice import synthesize as leda
        clips, voice = leda(sentences, cache_key=f"row_{rid}"), "Leda (Gemini)"
    else:
        clips, voice = synthesize(sentences, work / "tts")
    narration, timings = build_narration(clips, sentences, work)
    from tts import count_clicks
    clicks, at = count_clicks(narration)
    if clicks:
        log.warning("Audio: %d click(s) found at %s s - removing them", clicks, at)
        fixed = narration.with_name("narration_fixed.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(narration), "-af",
                        "adeclick=w=55:o=75:t=2,adeclick=w=55:o=75:t=2", str(fixed)], check=True)
        fixed.replace(narration)
        clicks, at = count_clicks(narration)
        if clicks > 2:
            raise RuntimeError(f"audio still has {clicks} click sounds at {at} s - not uploading")
    log.info("Audio click check passed")
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
                                            work / "images", base_seed=n * 1000 + 7,
                                            cache_dir=ROOT / "cache" / "images" / f"row_{rid}")
    from image_provider import PictureFailed, validate_pictures
    bad_pics = validate_pictures(story_imgs)
    if bad_pics:
        raise PictureFailed("picture check failed: " + "; ".join(bad_pics[:5]))
    it = iter(story_imgs)
    images = []
    for s in scenes:
        if s["kind"] == "intro":
            from brand_assets import ART, intro_background
            card = work / "images" / "intro_card.png"
            images.append(intro_background(card) if ART.exists()
                          else make_card(story_imgs[0], card))
        elif s["kind"] == "outro":
            images.append(make_outro_card(story_imgs[-1], work / "images" / "outro_card.png"))
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
    sfx = []
    for s in scenes:
        if s["kind"] == "intro":
            sfx.append(("chime", s["start"] + 0.2))
        elif s["kind"] == "outro":
            sfx.append(("bell", s["start"] + 1.0))
    render_video(scenes, images, narration, ass, timings["total"], work, video, sfx=sfx)

    log.info("== Quality gate ==")
    frame = out / f"story_{rid}_subtitle_frame.png"
    from config import DOOM_HARD, DOOM_SOFT
    bounds = {"hard": DOOM_HARD, "soft": DOOM_SOFT} if row.get("genre") == "doomsday" else {}
    ok, failures, warnings = quality_gate(video, ass, timings, sentences, images, frame,
                                          check_duration=check_duration, **bounds)
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
        thumb = drama_thumbnail(row, provider, work, out / f"story_{rid}_thumbnail.jpg", n)
        if not thumb:
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
    prev = previous_part_link(row)
    desc = row.get("description_ta", "") + (f"\n\n👉 முந்தைய பகுதி: {prev}" if prev else "")
    video_id = yt_upload(out / video.name, {**row, "description_ta": desc, "chapters": chapters(scenes)})
    if thumb:
        set_thumbnail(video_id, thumb)
    try:
        from community import draft
        (out / "community_post.md").write_text(draft(row, video_id), encoding="utf-8")
    except Exception as e:
        log.warning("Community post draft failed: %s", e)
    return video_id


def previous_part_link(row):
    """Link to the previous part of the same series (keeps viewers watching the whole series)."""
    if not row.get("series_id") or not (row.get("part") or "").isdigit():
        return ""
    want = str(int(row["part"]) - 1)
    for r in load_rows():
        if r.get("series_id") == row["series_id"] and r.get("part") == want and r.get("video_id"):
            return f"https://youtu.be/{r['video_id']}"
    return ""


def drama_thumbnail(row, provider, work, out_path, n):
    """Viral-style thumbnail (thumb_v2): curiosity picture + huge yellow/red/white Tamil text.
    Older stories without thumbnail text get it from one small AI request (title fallback if busy)."""
    import random

    import thumb_v2
    from thumbnail import THUMB_STYLE
    texts, prompt = {}, row.get("thumb_prompt")
    if row.get("thumb_text"):
        try:
            texts = json.loads(row["thumb_text"])
        except ValueError:
            texts = {}
    if not texts.get("line1") and row.get("thumb_quote_ta"):
        texts = {"line1": row["thumb_quote_ta"], "line2": row.get("thumb_hook_ta", "")}
    if not (texts.get("line1") and texts.get("line2") and prompt):
        try:
            from llm import complete
            story = " ".join(split_sentences(row["script_ta"])[:120])
            d = complete(
                "From this Tamil story, write YouTube thumbnail text and picture. Return JSON "
                "{\"line1\": \"setup, casual Tamil, 4-7 words ending with …\", \"line2\": \"reveal tease, 3-6 Tamil "
                "words ending ..! or ?\", \"ribbon\": \"optional 3-5 word shocking contrast or empty\", "
                "\"title\": \"horror only: 1-3 word title else empty\", \"tagline\": \"horror only: 4-7 word clue "
                "tagline else empty\", \"scene\": \"English: a 'how is this possible?' picture; split before/after "
                "for family stories, dark scene with a clue for horror; characters, positions, strong emotions\"}"
                "\n\n" + story, want_json=True, max_tokens=1500, rounds=1)
            texts = {k: d.get(k, "") for k in ("line1", "line2", "ribbon", "title", "tagline")}
            prompt = f"{d['scene']}. South Indian setting. {THUMB_STYLE}"
        except Exception as e:
            log.warning("Thumbnail text AI busy (%s); using the title", str(e)[:120])
            texts = {"line1": re.sub(r"\s*\(.*?\)\s*$", "", row["title_ta"].split("|")[0]).strip() + "…",
                     "line2": random.Random(n).choice(["கடைசியில் நடந்தது என்ன?", "அடுத்து நடந்தது என்ன?",
                                                       "அந்த ரகசியம் என்ன?", "யாரும் எதிர்பார்க்காத திருப்பம்..!"])}
            prompt = None
    bg = work / "images" / "thumb_bg.png"
    bg.parent.mkdir(parents=True, exist_ok=True)
    if prompt:
        try:
            bg.write_bytes(provider.generate(prompt, seed=n * 1000 + 999))
        except Exception as e:   # picture allowance used up: use the story's most dramatic picture
            log.warning("Thumbnail picture failed (%s); using a story picture", str(e)[:100])
            prompt = None
    if not prompt:
        pics = sorted((work / "images").glob("scene_*.png")) or sorted(
            (ROOT / "cache" / "images" / f"row_{row['id']}").glob("*.png"))
        bg.write_bytes(pics[min(len(pics) - 1, max(0, len(pics) // 2))].read_bytes())
    path, layout = thumb_v2.make(bg, texts, out_path, genre=row.get("genre", ""), variant=n,
                                 part=row.get("part") or "")
    log.info("Thumbnail layout: %s", layout)
    return path


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
    if not args.row_id and row.get("publish_at"):
        from datetime import datetime, timedelta, timezone
        due = datetime.fromisoformat(row["publish_at"])
        if due - datetime.now(timezone.utc) > timedelta(days=3):
            log.info("Next story is due %s (more than 3 days away) - nothing to make yet.", row["publish_at"])
            return 0
    # safety net: never voice a script with stray Hindi/Malayalam/Korean... letters
    from text_fix import foreign, repair_row
    if any(foreign(row.get(k, "")) for k in ("script_ta", "title_ta", "description_ta", "thumb_text")):
        try:
            from llm import complete
            if repair_row(row, complete):
                update_row(row["id"], **{k: row[k] for k in ("script_ta", "title_ta", "description_ta",
                                                              "thumb_quote_ta", "thumb_hook_ta", "thumb_text")})
        except Exception as e:
            log.warning("Text repair failed: %s", str(e)[:150])
    # a remake waits until the old broken upload has been deleted in YouTube Studio
    old = re.search(r"replaces:([\w-]{11})", row.get("fail_reason") or "")
    if old and not args.test and os.environ.get("YT_REFRESH_TOKEN"):
        try:
            from competitors import client
            if client().videos().list(part="id", id=old.group(1)).execute().get("items"):
                log.warning("Row %s: old video %s is still on YouTube - delete it in Studio; not uploading yet",
                            row["id"], old.group(1))
                return 0
        except Exception as e:
            log.warning("Could not check the old video: %s", str(e)[:120])
    # never upload the same story twice (e.g. if a previous run uploaded but could not save its status)
    if not args.test and not args.no_upload and os.environ.get("YT_REFRESH_TOKEN"):
        try:
            from competitors import client
            yt = client()
            ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
            pl = ch["contentDetails"]["relatedPlaylists"]["uploads"]
            items = yt.playlistItems().list(part="snippet", playlistId=pl, maxResults=25).execute().get("items", [])
            same = [i for i in items if i["snippet"]["title"].strip() == row["title_ta"].strip()[:100]]
            if same:
                vid = same[0]["snippet"]["resourceId"]["videoId"]
                log.warning("Row %s is already on YouTube as %s - marking done, not uploading again", row["id"], vid)
                update_row(row["id"], status="done", video_id=vid, fail_reason="")
                return 0
        except Exception as e:
            log.warning("Duplicate check skipped: %s", str(e)[:150])
    update_row(row["id"], status="processing", fail_reason="")
    try:
        upload = args.test_upload if args.test else not args.no_upload
        video_id = produce(row, upload=upload,
                           check_duration=not args.test)
    except Exception as e:
        if type(e).__name__ in ("ImageQuota", "PictureFailed"):
            log.warning("Paused: %s. Pictures made so far are saved; the next run continues.", e)
            update_row(row["id"], status="pending", fail_reason="waiting for free picture allowance")
            return 0
        if type(e).__name__ in ("GeminiQuota", "VoiceCheckFailed"):
            log.warning("Paused: %s. Voiced parts are saved; the next run continues with Leda.", e)
            update_row(row["id"], status="pending", fail_reason="waiting for Gemini voice daily limit")
            return 0
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
