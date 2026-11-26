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
    from config import PREVIOUS_IMAGE_STYLES
    sp = row["scene_prompts"]
    for old_style in PREVIOUS_IMAGE_STYLES:
        sp = sp.replace(old_style, IMAGE_STYLE)
    # facial hair written positively (picture models draw any word they read, e.g. "beard" in "no beard")
    sp = (sp.replace("moustache only, NO beard, chin shaved", "a thick moustache, smooth shaved chin")
            .replace("clean-shaven, no beard, no moustache", "a short neatly trimmed black beard and moustache")
            .replace("a thin moustache on the upper lip, with a smooth freshly shaved chin and cheeks",
                     "a short neatly trimmed black beard and moustache"))
    # at most MAX_PICTURES pictures per video (free daily allowance): keep evenly spread scene changes
    from config import MAX_PICTURES
    from stories import PROMPT_SEP
    pm = prompt_marks(sp)
    if len(pm) > MAX_PICTURES and not os.environ.get("NO_NEW_ASSETS"):
        keep = sorted({round(k * (len(pm) - 1) / (MAX_PICTURES - 1)) for k in range(MAX_PICTURES)})
        sp = PROMPT_SEP.join((f"{pm[k][0]}::{pm[k][1]}" if pm[k][0] is not None else pm[k][1]) for k in keep)
        log.info("Using %d of %d scene pictures (limit %d)", len(keep), len(pm), MAX_PICTURES)
    row = {**row, "scene_prompts": sp}
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
    from engage import FICTION_LINE
    intro = split_sentences(INTRO_LINES[n % len(INTRO_LINES)].format(title=title)) + [FICTION_LINE]
    from strategy import load as load_strategy
    outro_pool = OUTRO_LINES
    if load_strategy().get("engagement_push"):
        outro_pool = [o for o in OUTRO_LINES if "?" in o or "கமெண்ட்" in o] or OUTRO_LINES
    outro = split_sentences(outro_pool[n % len(outro_pool)])
    # viewer engagement before the outro: quiz winner, comment shout-out, today's quiz.
    # Made once per video and saved, so a later Short-only run re-uses exactly the same lines.
    end = []
    if row.get("end_lines"):
        try:
            end = json.loads(row["end_lines"])
        except ValueError:
            end = []
    elif upload and not os.environ.get("NO_NEW_ASSETS"):
        try:
            from engage import end_segment
            end, fields = end_segment(row, story)
            mark = fields.pop("_winner_for", None)
            if mark:
                update_row(mark[0], quiz_winner=mark[1])
            update_row(rid, end_lines=json.dumps(end, ensure_ascii=False), **fields)
            row.update(end_lines=json.dumps(end, ensure_ascii=False), **fields)
        except Exception as e:
            log.warning("Engagement lines skipped: %s", str(e)[:150])
            end = []
    outro = end + outro
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
    import status as ST
    ST.stage(row["id"], "voice", "done", "Leda voice ready, listening check and click check passed")
    log.info("Narration %.1f min", timings["total"] / 60)

    log.info("== Images ==")
    marks = [i for i, _ in prompt_marks(row["scene_prompts"])]
    marks = marks if all(i is not None for i in marks) else None
    scenes = plan_scenes(timings, len(prompts), intro=len(intro), outro=len(outro), marks=marks)
    log.info("%d pictures (%s)", sum(s["kind"] == "story" for s in scenes),
             "follow the story's scene changes" if marks else "evenly timed")
    story_scenes = [s for s in scenes if s["kind"] == "story"]
    provider = get_provider()
    sents = timings["sentences"]
    contexts = [" ".join(sents[k].get("text", "") for k in range(s["first"], s["last"] + 1))
                for s in story_scenes]
    scene_prompts = [prompts[s["prompt_index"]] for s in story_scenes]
    import image_provider as IP
    from image_provider import PlaceholderProvider, drawable_prompts
    cards = {}
    try:   # fixed face + ONE dress colour per character for the whole series
        from characters import fixed_cards
        if row.get("series_id"):
            import series as S
            cards = fixed_cards(next((x for x in S.load().get("series", []) if x.get("id") == row["series_id"]), {}).get("characters"))
    except Exception as e:
        log.warning("Character cards unavailable: %s", str(e)[:100])
    draw = (None if os.environ.get("NO_NEW_ASSETS") or isinstance(provider, PlaceholderProvider)
            else drawable_prompts(scene_prompts, contexts, cards=cards, genre=row.get("genre", "")))
    from config import PICTURE_CHECK
    story_imgs, img_warnings = generate_all(provider, scene_prompts,
                                            work / "images", base_seed=n * 1000 + 7, contexts=contexts,
                                            draw_prompts=draw,
                                            cache_dir=ROOT / "cache" / "images" / f"row_{rid}",
                                            check=PICTURE_CHECK)
    _st = IP.STATS
    if _st["scenes"]:
        first = sum(1 for x in _st["scenes"] if x["first_try"])
        msg = (f"Pictures: {len(_st['scenes'])} new, {first} right on the first try, "
               f"{_st['drawn']} drawn in total ({_st['drawn'] / len(_st['scenes']):.1f} per picture)")
        log.info(msg)
        try:
            import status as ST
            ST.event(f"Row {rid}: {msg}")
        except Exception:
            pass
    from image_provider import PictureFailed, validate_pictures
    bad_pics = validate_pictures(story_imgs)
    if bad_pics:
        raise PictureFailed("picture check failed: " + "; ".join(bad_pics[:5]))
    ST.stage(row["id"], "pictures", "done", f"{len(story_imgs)} pictures, all real and different")
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
                          "தினமும் ஒரு புது தமிழ் கதை"))
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
    if row.get("genre") == "horror":
        from config import HORROR_HARD, HORROR_SOFT
        bounds = {"hard": HORROR_HARD, "soft": HORROR_SOFT}
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
    LAST.update(video=out / video.name, timings=timings, intro=len(intro), outro=len(outro), title=title)
    ST.stage(row["id"], "video", "done", f"{timings['total'] / 60:.1f} min, quality check passed")

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
    make_and_upload_short(row, video_id)
    try:
        from community import draft
        md = draft(row, video_id)
        (out / "community_post.md").write_text(md, encoding="utf-8")
    except Exception as e:
        md = ""
        log.warning("Community post draft failed: %s", e)
    try:
        from channel_tools import add_to_playlist, post_comment
        add_to_playlist(row, video_id)
        m = re.search(r"\*\*(🗳️[^*]+)\*\*", md)
        post_comment(row, video_id, m.group(1) if m else None)
    except Exception as e:
        log.warning("Playlist/comment step failed: %s", e)
    return video_id


LAST = {}   # the video just rendered (used for the Shorts trailer)


def make_and_upload_short(row, video_id):
    """Shorts trailer of the opening hook; never fails the main video."""
    try:
        from shorts import make_short, upload_short
        short = make_short(LAST["video"], LAST["timings"], LAST["intro"], row["title_ta"].split(" | ")[0],
                           OUTPUT_DIR.resolve() / f"story_{row['id']}_short.mp4")
        if short and os.environ.get("YT_REFRESH_TOKEN"):
            sid = upload_short(short, row, video_id, row.get("publish_at"))
            update_row(row["id"], fail_reason=f"short:{sid}")
            import status as ST
            ST.stage(row["id"], "short", "done", f"Short {sid} scheduled 30 min after the video")
    except Exception as e:
        log.warning("Shorts trailer failed: %s", str(e)[:200])
        return
    make_extra_shorts(row, video_id)
    if os.environ.get("HOLD_FOR_APPROVAL"):
        cur = next((r for r in load_rows() if r["id"] == row["id"]), {}).get("fail_reason", "")
        update_row(row["id"], fail_reason=f"{cur} hold".strip())


def make_extra_shorts(row, video_id):
    """Short 2: cut from the same finished video (no voice or picture credits), next day 1 PM."""
    try:
        from shorts import EXTRA, extra_when, make_short, pick_extra_segments, upload_short
        import series as S
        final = row.get("genre") == "family emotional"
        try:
            ser = next(x for x in S.load()["series"] if x["id"] == row.get("series_id"))
            final = final or int(row.get("part") or 0) >= ser["parts_total"]
        except Exception:
            pass
        t = LAST["timings"]
        story_t = {**t, "sentences": t["sentences"][:len(t["sentences"]) - LAST.get("outro", 0)]}
        texts = [x.get("text", "") for x in story_t["sentences"]]
        segs = pick_extra_segments(story_t, LAST["intro"], texts if any(texts) else None, final)
        # 2 Shorts per video in total (more near-identical Shorts can look mass-produced):
        # the cliffhanger for a serial part, the mid-story twist for a final part / standalone story
        segs = segs[:1] if final else segs[-1:]
        ids = []
        for k, seg in enumerate(segs):
            ending, cta = EXTRA[0 if final else 1]
            out = OUTPUT_DIR.resolve() / f"story_{row['id']}_short{k + 2}.mp4"
            clip = make_short(LAST["video"], LAST["timings"], LAST["intro"], row["title_ta"].split(" | ")[0],
                              out, seg=seg, cta=cta)
            if clip and os.environ.get("YT_REFRESH_TOKEN"):
                ids.append(upload_short(clip, row, video_id, row.get("publish_at"),
                                        when=extra_when(row.get("publish_at"), k + 1), ending=ending))
        if ids:
            cur = next((r for r in load_rows() if r["id"] == row["id"]), {}).get("fail_reason", "")
            update_row(row["id"], fail_reason=f"{cur} shorts:{','.join(ids)}".strip())
            import status as ST
            ST.event(f"Row {row['id']}: {len(ids)} extra Shorts scheduled (next afternoons, 1 PM)")
    except Exception as e:
        log.warning("Extra Shorts failed: %s", str(e)[:200])


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
    from config import EXPERIMENT_START
    if prompt and (row.get("publish_at") or "")[:10] >= EXPERIMENT_START:   # face thumbnails (experiment)
        if (row.get("genre") or "").startswith("family"):
            # family drama (Tamil serial / mamiyar-marumagal channels): the CONFLICT in two faces, warm light
            prompt = ("Two faces in big close-up: on the left the wronged person, eyes wet with tears and hurt; "
                      "on the right the person who wronged them, cold or angry, slightly smaller; warm indoor home "
                      "light, simple dark background, bright clear colours; " + prompt)
        else:
            face = "terrified, eyes wide with fear" if row.get("genre") in ("horror", "doomsday") else "shocked"
            prompt = (f"ONE main character's face in a huge close-up filling about half the frame, {face}, "
                      f"looking towards the viewer, background dark and simple; " + prompt)
        try:   # same fixed faces and clothes as inside the video
            import series as S
            from characters import fixed_cards, story_prompt
            ser = next((x for x in S.load().get("series", []) if x.get("id") == row.get("series_id")), {})
            cards = fixed_cards(ser.get("characters"))
            if cards:
                prompt = story_prompt(prompt, cards, row.get("genre", ""))
        except Exception as e:
            log.info("Thumbnail cards skipped: %s", str(e)[:80])
    bg = work / "images" / "thumb_bg.png"
    bg.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get("NO_NEW_ASSETS"):
        prompt = None   # Short-only run: no new pictures, use a story picture
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
    try:   # comments that failed while a video was still private
        from channel_tools import retry_pending_comments
        retry_pending_comments()
    except Exception as e:
        log.warning("Pending comments: %s", str(e)[:120])
    ap = argparse.ArgumentParser()
    ap.add_argument("--row-id", default="")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--short-for", default="", help="row id of an uploaded story: make and upload its Short")
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
    if args.short_for:
        row = next(r for r in rows if r["id"] == args.short_for)
        if "short:" in (row.get("fail_reason") or ""):
            log.info("Row %s already has a Short", row["id"])
            return 0
        os.environ["NO_NEW_ASSETS"] = "1"   # a Short of an old video must cost no voice or picture credits
        try:
            produce(row, upload=False, check_duration=False)
        except Exception as e:
            log.warning("Short for row %s skipped (saved voice/pictures not available): %s", row["id"], str(e)[:150])
            return 0
        make_and_upload_short(row, row["video_id"])
        return 0
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
    # a story marked "needs_approval" is always uploaded privately without a schedule (any run)
    if "needs_approval" in (row.get("fail_reason") or ""):
        os.environ["HOLD_FOR_APPROVAL"] = "1"
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
            from youtube_upload import seo_title
            yt = client()
            ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
            pl = ch["contentDetails"]["relatedPlaylists"]["uploads"]
            items = yt.playlistItems().list(part="snippet", playlistId=pl, maxResults=25).execute().get("items", [])
            same = [i for i in items if i["snippet"]["title"].strip() in (row["title_ta"].strip()[:100], seo_title(row).strip())]
            if same:
                vid = same[0]["snippet"]["resourceId"]["videoId"]
                log.warning("Row %s is already on YouTube as %s - marking done, not uploading again", row["id"], vid)
                update_row(row["id"], status="done", video_id=vid, fail_reason="")
                return 0
        except Exception as e:
            log.warning("Duplicate check skipped: %s", str(e)[:150])
    keep = " needs_approval" if os.environ.get("HOLD_FOR_APPROVAL") else ""   # survives pauses / retries
    update_row(row["id"], status="processing", fail_reason=keep.strip())
    import status as ST
    try:
        upload = args.test_upload if args.test else not args.no_upload
        video_id = produce(row, upload=upload,
                           check_duration=not args.test)
    except Exception as e:
        if type(e).__name__ in ("ImageQuota", "PictureFailed"):
            ST.stage(row["id"], "pictures", "waiting", str(e)[:150])
            ST.event(f"Paused: {str(e)[:150]}", row["id"], "warn")
            log.warning("Paused: %s. Pictures made so far are saved; the next run continues.", e)
            update_row(row["id"], status="pending", fail_reason="waiting for free picture allowance" + keep)
            return 0
        if type(e).__name__ in ("GeminiQuota", "VoiceCheckFailed"):
            ST.stage(row["id"], "voice", "waiting", str(e)[:150])
            ST.event(f"Paused: {str(e)[:150]}", row["id"], "warn")
            log.warning("Paused: %s. Voiced parts are saved; the next run continues with Leda.", e)
            update_row(row["id"], status="pending", fail_reason="waiting for Gemini voice daily limit" + keep)
            return 0
        log.error("Row %s failed: %s", row["id"], e)
        ST.event(f"FAILED: {str(e)[:180]}", row["id"], "error")
        log.debug(traceback.format_exc())
        update_row(row["id"], status="failed", fail_reason=str(e)[:480].replace("\n", " ") + keep)
        return 1
    if video_id:
        update_row(row["id"], status="done", video_id=video_id)
        ST.stage(row["id"], "upload", "done", f"https://youtu.be/{video_id} scheduled {row.get('publish_at', '')[:16]}")
        ST.event(f"Video scheduled on YouTube ({video_id})", row["id"])
    else:
        update_row(row["id"], status="pending")
    log.info("Row %s finished", row["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
