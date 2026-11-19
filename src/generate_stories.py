"""Phase 1: write original Tamil stories automatically and append them to stories.csv.

python src/generate_stories.py --count 3          # write up to 3 stories now
python src/generate_stories.py --auto             # top up: 30 total at first, then keep >= MIN_PENDING

Each story: plan (JSON) -> script in two halves -> automatic self-check and repair -> saved.
The CSV is saved after every story, so a quota stop never loses finished work.
"""
import argparse
import json
import logging
import random
import re
import sys
from collections import Counter
from pathlib import Path

from config import (GENRE_MIX, IMAGE_STYLE, MAX_SCENES, MAX_WORDS, MAX_WORDS_PER_SENTENCE,
                    MIN_PENDING, MIN_SCENES, MIN_WORDS, OPENING_STYLES, PROMPT_SEP,
                    SENTENCE_SEP, STORY_INDEX)
from llm import LLMError, complete
from strategy import load as load_strategy
from stories import load_rows, save_rows, word_count

log = logging.getLogger("generate")

RULES = """Hard rules:
- The story must be completely ORIGINAL. Do not copy or closely paraphrase any YouTube channel,
  book, film, TV serial, folk tale or song. No song lyrics at all.
- CASUAL everyday Tamil, the way people in Tamil Nadu actually talk today (light "Tanglish").
  Mix in common English words naturally, as real people do, but WRITE THEM IN TAMIL LETTERS:
    ஆபீஸ், டென்ஷன், சாரி, ஓகே, போன், பிராப்ளம், தேங்க்ஸ், ஹாஸ்பிடல், பஸ், ஸ்கூல், ஆக்சுவலா,
    சூப்பர், ஃப்ரெண்ட், லவ், மிஸ் பண்றேன், கால் பண்ணு, வெயிட் பண்ணு.
  Never pure literary Tamil; never English in Latin letters. Use colloquial verb forms:
    இருக்கு (not உள்ளது), போனா (not சென்றாள்), வந்தான் (not வருகை தந்தான்),
    சொன்னாங்க (not கூறினார்கள்), பார்த்தா (not கண்டாள்), என்ன பண்றது (not என்ன செய்வது),
    ரொம்ப (not மிகவும்), அப்புறம் (not பின்னர்), இல்ல (not இல்லை) in dialogue.
  Light everyday Tamil-English mixing is fine where people really talk that way.
- Sentences of 6-14 words: natural spoken rhythm, not choppy fragments. Never 15 or more.
- Show feelings through small actions and dialogue, not by naming the emotion.
- Hook in the first 30 seconds, rising tension, a turning point around 60%, emotional climax,
  and a satisfying ending that resolves the main conflict with a specific, earned moment
  (not a generic "everything ended well" summary).
- Family-friendly. No graphic violence."""


# ---------------- index of premises and names ----------------

def read_index():
    if not STORY_INDEX.exists():
        return [], set()
    premises, names = [], set()
    for line in STORY_INDEX.read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            premises.append(line[2:])
            m = re.search(r"names: (.*)$", line)
            if m:
                names.update(n.strip() for n in m.group(1).split(","))
    return premises, names


def append_index(row_id, genre, title_en, premise, names):
    header = "# Story index\nOne line per story, so no two stories repeat a plot or reuse names.\n\n"
    text = STORY_INDEX.read_text(encoding="utf-8") if STORY_INDEX.exists() else header
    text += f"- {row_id} | {genre} | {title_en} | {premise} | names: {', '.join(names)}\n"
    STORY_INDEX.write_text(text, encoding="utf-8")


# ---------------- choosing what to write ----------------

def next_genre(rows):
    """Keep every block of 30 at the strategy's genre mix (starts at 12 / 8 / 5 / 5)."""
    from strategy import load
    mix = load().get("genre_mix") or GENRE_MIX
    block = rows[-(len(rows) % 30):] if len(rows) % 30 else []
    have = Counter(r["genre"] for r in block)
    need = [g for g, n in mix.items() for _ in range(max(0, n - have[g]))]
    return random.choice(need or list(mix))


def next_opening(rows):
    recent = [r.get("_opening", "") for r in rows[-5:]]
    options = [o for o in OPENING_STYLES if o not in recent] or OPENING_STYLES
    return random.choice(options)


# ---------------- LLM steps ----------------

def plan_story(genre, opening, premises, used_names, topic=None):
    n_beats = random.randint(MIN_SCENES + 1, MAX_SCENES)
    avoid = "\n".join(premises[-80:]) or "(none yet)"
    prompt = f"""You are planning an original Tamil {genre} story for a YouTube narration channel.
It will be narrated for 20-25 minutes (about 2,200 Tamil words).
The story opens with {opening}.
{('STORY IDEA (build the whole story on this idea, with your own original characters and twists): ' + topic) if topic else ''}
{RULES}
- Do NOT make it a mother-sacrifice plot unless the genre truly needs it, and vary the setting
  (village, Chennai flat, small town, bus depot, school, market, hospital, farm, coastal town ...).
- Use fresh Tamil character names. Do not use any of these names: {', '.join(sorted(used_names)) or 'none'}.
- Themes viewers are enjoying right now (use loosely as inspiration, never copy anyone's story):
  {', '.join(load_strategy().get('trending_themes', [])) or 'any'}
- The premise must be clearly different from every premise already used:
{avoid}

Return JSON with exactly these keys:
{{
 "title_ta": "YouTube title in casual Tamil, 50-90 characters: a conflict or a shocking line plus a concrete detail (an age, a number of days, a status contrast like auto driver vs IPS officer) and a curiosity ending (…என்ன நடந்தது? / கடைசியில் அதிர்ச்சி!). No ending spoilers.",
 "thumb_quote_ta": "the most shocking line a character says in the story, casual Tamil, max 10 words",
 "thumb_hook_ta": "thumbnail hook, max 6 Tamil words, ending in a punch word like அதிர்ச்சி! / ரகசியம்! / என்ன?",
 "thumb_scene_en": "the thumbnail picture: 2-3 named characters in the story's key confrontation, with clear positions, faces and strong emotions (e.g. young woman crying on the left, angry mother-in-law pointing at her on the right)",
 "title_en": "English title",
 "premise_en": "one-line English premise",
 "description_ta": "2-3 line Tamil YouTube description that hooks the viewer without spoiling the ending",
 "characters": [{{"name": "...", "role": "...", "age": 0,
                  "appearance_en": "fixed look: face, hair, clothes, so images stay consistent"}}],
 "beats": [{{"summary_en": "what happens", "characters": ["names in scene"],
             "setting_en": "place", "time_of_day": "morning/afternoon/evening/night",
             "emotion": "dominant feeling"}}]
}}
Give exactly {n_beats} beats in story order, covering hook, rising tension, turning point
around beat {round(n_beats * 0.6)}, climax and ending.
Each beat becomes ONE illustration, so describe a simple, paintable moment:
- at most 2 people in the picture, named in "characters"; list [] if nobody is in it
- no small objects held in hands, no vehicles or bicycles in close-up, no written text
- a clear setting and one visible emotion"""
    plan = complete(prompt, want_json=True, max_tokens=8000)
    if not MIN_SCENES <= len(plan.get("beats", [])) <= MAX_SCENES:
        raise LLMError(f"plan has {len(plan.get('beats', []))} beats")
    return plan


PARTS = 4  # smaller pieces suit free models with short output limits


def write_part(plan, part, previous_text=""):
    beats = plan["beats"]
    size = -(-len(beats) // PARTS)
    chunk = beats[part * size:(part + 1) * size]
    chars = "\n".join(f"- {c['name']}: {c['role']}, {c.get('age', '')}" for c in plan["characters"])
    beat_text = "\n".join(f"{i + 1}. {b['summary_en']} ({b['emotion']})" for i, b in enumerate(chunk))
    context = ("" if part == 0 else
               "The story so far ends like this; continue seamlessly from it:\n" + previous_text[-1200:])
    last = part == PARTS - 1
    ending = ("Finish the story with these beats and give it a satisfying, complete ending."
              if last else "Stop at the end of these beats, mid-story; do not conclude.")
    prompt = f"""Write part {part + 1} of {PARTS} of this Tamil story script, in Tamil.
Title: {plan['title_ta']} ({plan['title_en']})
Premise: {plan['premise_en']}
Characters:
{chars}
Beats for this part:
{beat_text}
{context}
{RULES}
Length: about 550-610 Tamil words for this part (count carefully). Write the full narration, not an outline.
Format: ONE sentence per line. No numbering, no headings, no stage directions, no English
translation. Dialogue is fine inside a sentence. {ending}"""
    return complete(prompt, max_tokens=16000)


def fix_long_sentences(sentences):
    """Split at commas; ask the model to shorten whatever is still too long; hard-split last."""
    out, todo = [], []
    for s in sentences:
        if word_count(s) <= MAX_WORDS_PER_SENTENCE:
            out.append(s)
            continue
        pieces = [p.strip() for p in re.split(r"[,،]\s*", s) if p.strip()]
        if len(pieces) > 1 and all(3 <= word_count(p) <= MAX_WORDS_PER_SENTENCE for p in pieces):
            out.extend(pieces)
        else:
            out.append(s)
            todo.append(s)
    if todo:
        try:
            fixed = complete(
                "Rewrite each Tamil sentence below as 2 or 3 shorter natural spoken-Tamil "
                f"sentences, each under {MAX_WORDS_PER_SENTENCE} words, keeping the meaning. "
                "Return JSON: a list of lists of strings, same order.\n"
                + json.dumps(todo, ensure_ascii=False), want_json=True, max_tokens=8000)
            mapping = dict(zip(todo, fixed)) if len(fixed) == len(todo) else {}
        except (LLMError, ValueError):
            mapping = {}
        result = []
        for s in out:
            if s in mapping and all(word_count(x) <= MAX_WORDS_PER_SENTENCE for x in mapping[s]):
                result.extend(x.strip() for x in mapping[s] if x.strip())
            elif word_count(s) > MAX_WORDS_PER_SENTENCE:
                w = s.split()
                result.extend(" ".join(w[i:i + 12]) for i in range(0, len(w), 12))
            else:
                result.append(s)
        out = result
    return out


def to_sentences(text):
    sents = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", line).strip().strip("\"“”")
        if not line or line.startswith("#"):
            continue
        for s in re.split(r"(?<=[.!?।])\s+", line):
            s = s.strip().rstrip(".।").strip()
            if s:
                sents.append(s)
    return sents


SEG_MIN, SEG_MAX = 4, 7       # sentences per picture (~20-40 s of narration at ~5 s per sentence)


def segment_scenes(plan, sentences):
    """Ask the model where the picture must change (new place, time or characters) and
    what each picture shows, based on the ACTUAL script. Returns [(start_idx, prompt)]."""
    looks = {c["name"]: f"{c['name']} ({c.get('age', '')}, {c['appearance_en']})"
             for c in plan["characters"]}
    numbered = "\n".join(f"{i}: {x}" for i, x in enumerate(sentences))
    data = complete(
        f"""Below is a Tamil story script, one numbered sentence per line.
Split it into picture segments for an illustrated video. Start a NEW segment whenever the
place, time of day or the people present change (e.g. beach -> house), and otherwise every
{SEG_MIN}-{SEG_MAX} sentences. The first segment starts at sentence 0.
Characters (keep their look identical in every picture): {json.dumps(looks, ensure_ascii=False)}
For each segment return the sentence number where it starts and an English description of ONE
simple, paintable moment from that part: who is visible (max 2 people, by name), the place,
time of day and the mood. No text, no small objects held in hands, no vehicles in close-up.
Return JSON: [{{"start": 0, "characters": ["Name"], "setting": "...", "time_of_day": "...",
"moment": "...", "mood": "..."}}]

{numbered}""", want_json=True, max_tokens=12000)
    segs, last = [], -1
    for d in data:
        st = int(d.get("start", -1))
        if st <= last or st >= len(sentences):
            continue
        names = (d.get("characters") or [])[:2]
        who = (f"Only these people in the picture: {', '.join(looks.get(n, n) for n in names)}. "
               "No other people") if names else "No people in the picture"
        p = (f"{d.get('moment', '')}. {who}. Setting: {d.get('setting', '')}, "
             f"{d.get('time_of_day', '')}. Mood: {d.get('mood', '')}. "
             f"Simple composition, natural hands and faces. {IMAGE_STYLE}")
        segs.append((st, p.replace(PROMPT_SEP, "/").replace("::", ":")))
        last = st
    if not segs or segs[0][0] != 0:
        raise LLMError("scene segmentation returned no usable segments")
    # split segments that are too long so a picture never stays more than SEG_MAX sentences
    fixed = []
    for k, (st, p) in enumerate(segs):
        end = segs[k + 1][0] if k + 1 < len(segs) else len(sentences)
        for sub in range(st, end, SEG_MAX):
            fixed.append((sub, p))
    return fixed


def thumb_prompt(plan):
    from thumbnail import THUMB_STYLE
    looks = "; ".join(f"{c['name']}: {c.get('age', '')}, {c['appearance_en']}" for c in plan["characters"])
    scene = plan.get("thumb_scene_en", "")
    return f"{scene}. Characters look: {looks}. South Indian setting. {THUMB_STYLE}".replace(PROMPT_SEP, "/") if scene else ""


def scene_prompts(plan):
    looks = {c["name"]: f"{c['name']} ({c.get('age', '')}, {c['appearance_en']})"
             for c in plan["characters"]}
    prompts = []
    for b in plan["beats"]:
        names = b.get("characters", [])[:2]
        if names:
            who = (f"Only these people in the picture: {', '.join(looks.get(n, n) for n in names)}. "
                   "No other people")
        else:
            who = "No people in the picture"
        p = (f"{b['summary_en']}. {who}. Setting: {b['setting_en']}, {b['time_of_day']}. "
             f"Mood: {b['emotion']}. Simple composition, natural hands and faces. {IMAGE_STYLE}")
        prompts.append(p.replace(PROMPT_SEP, "/"))
    return prompts


def self_check(plan, sentences):
    words = sum(word_count(s) for s in sentences)
    problems = []
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"{words} words (need {MIN_WORDS}-{MAX_WORDS})")
    long_ = [s for s in sentences if word_count(s) > MAX_WORDS_PER_SENTENCE]
    if long_:
        problems.append(f"{len(long_)} sentences over {MAX_WORDS_PER_SENTENCE} words")
    if not MIN_SCENES <= len(plan["beats"]) <= MAX_SCENES:
        problems.append("scene count out of range")
    return words, problems


def originality_and_ending_check(plan, sentences):
    ending = " ".join(sentences[-25:])
    verdict = complete(
        "Answer as JSON {\"resolves_conflict\": true/false, \"resembles_known_work\": "
        "\"name of a known film/book/serial/YouTube story it closely copies, or empty\"}.\n"
        f"Premise: {plan['premise_en']}\nEnding (Tamil): {ending}",
        want_json=True, max_tokens=1000)
    problems = []
    if not verdict.get("resolves_conflict", False):
        problems.append("ending does not resolve the conflict")
    if verdict.get("resembles_known_work"):
        problems.append(f"too close to: {verdict['resembles_known_work']}")
    return problems


def _expand(plan, sentences, need):
    cut = int(len(sentences) * 0.55)
    extra = complete(
        f"This Tamil story needs about {need} more words. Write about {need} Tamil words of new "
        "scene detail, feelings and dialogue that fit naturally right after the passage below "
        "(before the turning point). Same characters, same style, one sentence per line, "
        f"every sentence under {MAX_WORDS_PER_SENTENCE} words. Do not end the story.\n\n"
        + "\n".join(sentences[max(0, cut - 30):cut]), max_tokens=16000)
    new = fix_long_sentences(to_sentences(extra))
    # never let one expansion overshoot wildly
    budget, kept = need + 300, []
    for x in new:
        if sum(word_count(k) for k in kept) + word_count(x) > budget:
            break
        kept.append(x)
    return sentences[:cut] + kept + sentences[cut:]


def _trim(sentences):
    """Drop whole sentences from the middle, never the hook (first 10%) or the ending (last 25%)."""
    lo, hi = int(len(sentences) * 0.10), int(len(sentences) * 0.75)
    step = 0
    while sum(word_count(x) for x in sentences) > MAX_WORDS - 50 and hi - lo > 5:
        idx = lo + (step * 7) % (hi - lo)   # spread the cuts out instead of one big hole
        del sentences[idx]
        hi -= 1
        step += 1
    return sentences


def adjust_length(plan, sentences, passes=3):
    """Expand (up to `passes` times) until long enough, then trim to the maximum."""
    for _ in range(passes):
        words = sum(word_count(x) for x in sentences)
        if words >= MIN_WORDS:
            break
        sentences = _expand(plan, sentences, MIN_WORDS + 150 - words)
    return _trim(sentences)


TOPICS = Path(__file__).resolve().parent.parent / "topics.json"


def next_topic():
    """Next unused hand-picked topic from topics.json (None when the list is used up)."""
    if not TOPICS.exists():
        return None
    for i, t in enumerate(json.loads(TOPICS.read_text(encoding="utf-8"))):
        if not t.get("used"):
            return i, t
    return None


def mark_topic_used(i):
    data = json.loads(TOPICS.read_text(encoding="utf-8"))
    data[i]["used"] = True
    TOPICS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_story(rows):
    premises, used_names = read_index()
    picked = next_topic()
    genre = picked[1]["genre"] if picked else next_genre(rows)
    opening = next_opening(rows)
    topic = picked[1]["topic"] if picked else None
    log.info("Planning a %s story opening with %s", genre, opening)
    for attempt in range(2):
        plan = plan_story(genre, opening, premises, used_names, topic)
        names = [c["name"] for c in plan["characters"]]
        if not set(names) & used_names:
            break
        log.warning("Plan reused names %s, re-planning", set(names) & used_names)
    text = ""
    for part in range(PARTS):
        text += "\n" + write_part(plan, part, text)
    sentences = fix_long_sentences(to_sentences(text))
    sentences = fix_long_sentences(adjust_length(plan, sentences))
    sentences = _trim(sentences)
    words, problems = self_check(plan, sentences)
    problems += originality_and_ending_check(plan, sentences)
    if problems:
        raise LLMError("self-check failed: " + "; ".join(problems))
    next_id = max([int(r["id"]) for r in rows if r["id"].isdigit()] or [0]) + 1
    script = " ".join(f"{i + 1}. {s}{SENTENCE_SEP}" for i, s in enumerate(sentences))
    try:
        segs = segment_scenes(plan, sentences)
        prompts_field = f" {PROMPT_SEP} ".join(f"{st}::{p}" for st, p in segs)
        n_pics = len(segs)
    except (LLMError, ValueError, TypeError) as e:
        log.warning("Scene segmentation failed (%s); using beat-based pictures", str(e)[:120])
        prompts_field = f" {PROMPT_SEP} ".join(scene_prompts(plan))
        n_pics = len(plan["beats"])
    row = {"id": str(next_id), "genre": genre, "title_ta": plan["title_ta"],
           "title_en": plan["title_en"], "script_ta": script,
           "scene_prompts": prompts_field,
           "publish_at": "", "status": "pending", "video_id": "", "fail_reason": "",
           "description_ta": plan.get("description_ta", ""),
           "thumb_quote_ta": plan.get("thumb_quote_ta", ""), "thumb_hook_ta": plan.get("thumb_hook_ta", ""),
           "thumb_prompt": thumb_prompt(plan)}
    log.info("Story %s ok: %d words, %d sentences, %d pictures", next_id, words, len(sentences),
             n_pics)
    if picked:
        mark_topic_used(picked[0])
    return row, plan["premise_en"], names


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--auto", action="store_true",
                    help="30 stories in total at first, then refill to 20 pending when below 10")
    ap.add_argument("--max-per-run", type=int, default=5)
    args = ap.parse_args()

    rows = load_rows()
    pending = sum(r["status"] == "pending" for r in rows)
    if args.auto:
        if len(rows) < 30:
            want = 30 - len(rows)
        elif pending < MIN_PENDING:
            want = 20 - pending
        else:
            want = 0
    else:
        want = args.count
    want = min(want, args.max_per_run)
    log.info("%d rows, %d pending -> writing %d stories this run", len(rows), pending, want)

    written, failures, stopped_early = 0, 0, False
    while written < want and failures < 3:
        try:
            row, premise, names = write_story(rows)
        except LLMError as e:
            if str(e).startswith(("RATE_LIMIT", "BUSY")):
                log.warning("Stopping: %s. The next scheduled run will continue.", str(e)[:200])
                stopped_early = True
                break
            failures += 1
            log.warning("Story attempt failed (%s); trying a new plan", e)
            continue
        rows.append(row)
        save_rows(rows)
        append_index(row["id"], row["genre"], row["title_en"], premise, names)
        written += 1
    log.info("Wrote %d stories", written)
    # quota / busy servers are temporary: not a failure, the next run continues
    return 0 if written or want == 0 or stopped_early else 1


if __name__ == "__main__":
    sys.exit(main())
