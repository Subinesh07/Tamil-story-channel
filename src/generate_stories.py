"""Phase 1: write original Tamil stories automatically and append them to stories.csv.

python src/generate_stories.py --count 3          # write up to 3 stories now
python src/generate_stories.py --auto             # top up: 30 total at first, then keep >= MIN_PENDING

Each story: plan (JSON) -> script in two halves -> automatic self-check and repair -> saved.
The CSV is saved after every story, so a quota stop never loses finished work.
"""
import argparse
from datetime import datetime
import json
import os
import logging
import random
import re
import sys
from collections import Counter
from pathlib import Path

from config import (GENRE_MIX, IMAGE_STYLE, MAX_SCENES, MAX_WORDS, MAX_WORDS_PER_SENTENCE,
                    MIN_SCENES, MIN_WORDS, OPENING_STYLES, PROMPT_SEP,
                    SENTENCE_SEP, STORY_INDEX)
from llm import LLMError, complete
from strategy import load as load_strategy
from stories import load_rows, save_rows, word_count

log = logging.getLogger("generate")

def write(prompt, **kw):
    """Story text is written ONLY by Gemini: the small free models write broken, bookish Tamil.
    If Gemini is busy the run stops and the next scheduled run tries again."""
    return complete(prompt, providers=("gemini",), **kw)


STYLE_EXAMPLE = """நைட் பதினொன்னே முக்கால் மணி. லேப்ல மீராவைத் தவிர யாருமே இல்ல.
திடீர்னு ஸ்க்ரீன்ல ஒரு ரெட் லைட் மின்னுச்சு.
"என்னடா இது…" மீரா காபி கப்பைக் கீழே வச்சா.
சூரியன் மேல ஒரு பெரிய கரும்புள்ளி. இதுவரை யாருமே பார்க்காத சைஸ்.
அவ கணக்குப் போட்டா. ஒரு தடவை இல்ல, மூணு தடவை. ஒவ்வொரு தடவையும் அதே ஆன்சர்.
இன்னும் ஏழு நாள்ல ஒரு பெரிய சோலார் ஸ்டார்ம் பூமியை அடிக்கப் போகுது.
கரண்ட், போன், இன்டர்நெட், ஹாஸ்பிடல்… எல்லாமே ஒரே செகண்ட்ல ஆஃப் ஆயிடும்.
மீரா முதல்ல நினைச்சது உலகத்தைப் பத்தி இல்ல. சென்னையில இருக்குற அப்பாவையும் தம்பியையும் தான்.
போனை எடுத்தா. "அப்பா, நான் சொல்றதை கவனமா கேளுங்க…"
அப்போ தான் லேப் கதவு மெதுவா திறந்துச்சு."""

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
- Tell it like a friend narrating a gripping story out loud, NOT like a novel:
  * The PLOT must move in almost every line: something happens, someone speaks, a new problem,
    a discovery. At least 35% of the lines are dialogue.
  * NO flowery description: no poetic metaphors, no lines about hair blowing in the wind, mist,
    shivering, heartbeats, the colour of the sky. At most ONE short line to set a scene, then action.
  * A feeling is shown in a few words or a line of dialogue ("மீராவுக்கு கை நடுங்க ஆரம்பிச்சுது."),
    then the story moves on. Never describe the same feeling twice.
  * Simple words a 12-year-old in Chennai understands. No rare or bookish Tamil words.
- Write in exactly this voice and rhythm (style sample, do not copy its content):
""" + "\n".join("    " + x for x in STYLE_EXAMPLE.splitlines()) + """
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

def plan_story(genre, opening, premises, used_names, topic=None, series_brief=None,
               minutes="20-25", words="2,650"):
    n_beats = random.randint(MIN_SCENES + 1, MAX_SCENES)
    avoid = "\n".join(premises[-80:]) or "(none yet)"
    prompt = f"""You are planning {'one part of a Tamil story series' if series_brief else 'an original Tamil ' + genre + ' story'} for a YouTube narration channel.
It will be narrated for {minutes} minutes (about {words} Tamil words).
{series_brief or ''}
The part opens with {opening}.
{('STORY IDEA (build the whole story on this idea, with your own original characters and twists): ' + topic) if topic else ''}
{RULES}
- Do NOT make it a mother-sacrifice plot unless the genre truly needs it, and vary the setting
  (village, Chennai flat, small town, bus depot, school, market, hospital, farm, coastal town ...).
- {'Keep the series characters; any NEW characters need fresh names.' if series_brief else 'Use fresh Tamil character names.'} Do not use any of these names: {', '.join(sorted(used_names)) or 'none'}.
- Themes viewers are enjoying right now (use loosely as inspiration, never copy anyone's story):
  {', '.join(load_strategy().get('trending_themes', [])) or 'any'}
{'' if series_brief else '- The premise must be clearly different from every premise already used:' + chr(10) + avoid}

Return JSON with exactly these keys:
{{
 "title_ta": "YouTube title in casual Tamil, 50-90 characters: a conflict or a shocking line plus a concrete detail (an age, a number of days, a status contrast like auto driver vs IPS officer) and a curiosity ending (…என்ன நடந்தது? / கடைசியில் அதிர்ச்சி!). No ending spoilers.",
 "thumb_line1_ta": "thumbnail SETUP line, casual Tamil, 4-7 words ending with … (e.g. டிரைவர் என்று காதலித்தாள்… / அம்மாவை தனியாக தவிக்கவிட்ட மகன்…)",
 "thumb_line2_ta": "thumbnail REVEAL tease, 3-6 Tamil words that cut off before the answer, ending ..! or ? (e.g. அவன் யார் என்று தெரிந்ததும்..! / கடைசியில் நடந்தது என்ன?)",
 "thumb_ribbon_ta": "optional extra ribbon, 3-5 Tamil words of shocking contrast (e.g. கோடீஸ்வரியாக திரும்பி வந்த அம்மா!), or empty",
 "thumb_title_ta": "HORROR/DOOMSDAY ONLY: a 1-3 word big Tamil title (e.g. கடைசி பேருந்து), else empty",
 "thumb_tagline_ta": "HORROR/DOOMSDAY ONLY: a 4-7 word mystery tagline with a clue (e.g. 14 பயணிகள்… 15 டிக்கெட் யாருக்கு?), else empty",
 "thumb_scene_en": "the thumbnail PICTURE that makes people ask 'how is this possible?'. Family/moral/real-life: a SPLIT composition: LEFT half = the setup moment, RIGHT half = the surprising twist (e.g. left: old mother crying alone at an airport with a suitcase; right: same mother smiling, richly dressed beside a luxury car). Horror: one dark night scene with the scared main character in close-up in the foreground, an eerie figure in the background and a clue object or place sign. Adventure: the hero small in front of a huge danger or discovery. Name the characters and give their positions, faces and strong emotions.",
 "title_en": "English title",
 "premise_en": "one-line English premise",
 "description_ta": "2-3 line Tamil YouTube description that hooks the viewer without spoiling the ending",
 "episode_summary_en": "3-4 sentence summary of what happens in this story/part, including how it ends",
 "characters": [{{"name": "...", "role": "...", "age": 0,
                  "appearance_en": "fixed look: face, hair, clothes, so images stay consistent"}}],
 "beats": [{{"summary_en": "what happens", "characters": ["names in scene"],
             "setting_en": "place", "time_of_day": "morning/afternoon/evening/night",
             "emotion": "dominant feeling"}}]
}}
Give exactly {n_beats} beats in story order, covering hook, rising tension, turning point
around beat {round(n_beats * 0.6)}, climax and {'the ending or cliffhanger the series brief asks for' if series_brief else 'ending'}.
Each beat becomes ONE illustration, so describe a simple, paintable moment:
- at most 2 people in the picture, named in "characters"; list [] if nobody is in it
- no small objects held in hands, no vehicles or bicycles in close-up, no written text
- a clear setting and one visible emotion"""
    plan = write(prompt, want_json=True, max_tokens=8000)
    if not MIN_SCENES <= len(plan.get("beats", [])) <= MAX_SCENES:
        raise LLMError(f"plan has {len(plan.get('beats', []))} beats")
    return plan


PARTS = 4  # smaller pieces suit free models with short output limits


def write_part(plan, part, previous_text="", final_note=None, parts=PARTS, part_words="660-720"):
    PARTS = parts
    beats = plan["beats"]
    size = -(-len(beats) // PARTS)
    chunk = beats[part * size:(part + 1) * size]
    chars = "\n".join(f"- {c['name']}: {c['role']}, {c.get('age', '')}" for c in plan["characters"])
    beat_text = "\n".join(f"{i + 1}. {b['summary_en']} ({b['emotion']})" for i, b in enumerate(chunk))
    context = ("" if part == 0 else
               "The story so far ends like this; continue seamlessly from it:\n" + previous_text[-1200:])
    last = part == PARTS - 1
    ending = ((final_note or "Finish the story with these beats and give it a satisfying, complete ending.")
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
Length: about {part_words} Tamil words for this part (count carefully). Write the full narration, not an outline.
Format: ONE sentence per line. No numbering, no headings, no stage directions, no English
translation. Dialogue is fine inside a sentence. {ending}"""
    return write(prompt, max_tokens=16000)


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
    data = write(
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


def self_check(plan, sentences, lo=MIN_WORDS, hi=MAX_WORDS):
    words = sum(word_count(s) for s in sentences)
    problems = []
    if not lo <= words <= hi:
        problems.append(f"{words} words (need {lo}-{hi})")
    long_ = [s for s in sentences if word_count(s) > MAX_WORDS_PER_SENTENCE]
    if long_:
        problems.append(f"{len(long_)} sentences over {MAX_WORDS_PER_SENTENCE} words")
    if not MIN_SCENES <= len(plan["beats"]) <= MAX_SCENES:
        problems.append("scene count out of range")
    return words, problems


def style_check(sentences):
    """Gemini scores a sample of the script; bookish or flowery scripts are rewritten."""
    n = len(sentences)
    sample = sentences[:30] + ["…"] + sentences[n // 2:n // 2 + 20] + ["…"] + sentences[-25:]
    v = write(
        "You judge Tamil YouTube story narration for a casual Tamil Nadu audience. Score 1-10:\n"
        "spoken: casual spoken Tanglish (இருக்கு/போனா/ரொம்ப, English words in Tamil letters), not bookish Tamil;\n"
        "pace: the plot moves in almost every line, plenty of dialogue, no flowery description;\n"
        "clear: every sentence is correct, meaningful Tamil a 12-year-old understands.\n"
        'Return JSON {"spoken": n, "pace": n, "clear": n, "worst_problem": "short reason"}.\n\n'
        + "\n".join(sample), want_json=True, max_tokens=1500)
    scores = [int(v.get(k, 0) or 0) for k in ("spoken", "pace", "clear")]
    problems = []
    if min(scores) < 7:
        problems.append(f"style {scores} ({str(v.get('worst_problem', ''))[:100]})")
    log.info("Style scores spoken/pace/clear: %s", scores)
    return problems


def originality_and_ending_check(plan, sentences, must_resolve=True, true_story=False):
    ending = " ".join(sentences[-25:])
    verdict = write(
        "Answer as JSON {\"resolves_conflict\": true/false, \"resembles_known_work\": "
        "\"name of a specific film/book/serial whose PLOT AND CHARACTERS this story copies almost "
        "scene by scene, or empty\"}. Sharing a genre, a common trope or a theme (treasure maps, "
        "property disputes, haunted villages, family drama) is NOT copying: answer empty for that.\n"
        f"Premise: {plan['premise_en']}\nEnding (Tamil): {ending}",
        want_json=True, max_tokens=1000)
    problems = []
    if must_resolve and not verdict.get("resolves_conflict", False):
        problems.append("ending does not resolve the conflict")
    if verdict.get("resembles_known_work") and not true_story:
        problems.append(f"too close to: {verdict['resembles_known_work']}")
    return problems


def _expand(plan, sentences, need):
    cut = int(len(sentences) * 0.55)
    extra = write(
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


def _trim(sentences, max_words=MAX_WORDS):
    """Drop whole sentences from the middle, never the hook (first 10%) or the ending (last 25%)."""
    lo, hi = int(len(sentences) * 0.10), int(len(sentences) * 0.75)
    step = 0
    while sum(word_count(x) for x in sentences) > max_words - 50 and hi - lo > 5:
        idx = lo + (step * 7) % (hi - lo)   # spread the cuts out instead of one big hole
        del sentences[idx]
        hi -= 1
        step += 1
    return sentences


def adjust_length(plan, sentences, passes=3, lo=MIN_WORDS, hi=MAX_WORDS):
    """Expand (up to `passes` times) until long enough, then trim to the maximum."""
    for _ in range(passes):
        words = sum(word_count(x) for x in sentences)
        if words >= lo:
            break
        sentences = _expand(plan, sentences, lo + 150 - words)
    return _trim(sentences, hi)


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


def write_story(rows, doomsday=False, redo=None):
    """Write the next part of whichever series owns the next publish date
    (doomsday=True: the next weekend 12 PM Doomsday part instead)."""
    import series as S
    from config import DOOM_HOUR, DOOM_MAX_WORDS, DOOM_MIN_WORDS
    premises, used_names = read_index()
    data = S.load()
    if redo:
        doomsday = redo["genre"] == "doomsday"
        ser = next(s for s in data["series"] if s["id"] == redo["series_id"])
    if redo:
        day, genre, why = datetime.fromisoformat(redo["publish_at"]).date(), redo["genre"], "rewrite"
        if doomsday:
            lo, hi, n_parts, part_words, mins, approx = DOOM_MIN_WORDS, DOOM_MAX_WORDS, 2, "620-700", "10-12", "1,300"
        else:
            lo, hi, n_parts, part_words, mins, approx = MIN_WORDS, MAX_WORDS, PARTS, "660-720", "20-25", "2,650"
    elif doomsday:
        ser = S.doomsday_series(data)
        if not ser:
            raise LLMError("NO_DOOMSDAY: season finished")
        day, genre, why = S.next_doom_date(rows), "doomsday", "weekend 12 PM"
        lo, hi, n_parts, part_words, mins, approx = DOOM_MIN_WORDS, DOOM_MAX_WORDS, 2, "620-700", "10-12", "1,300"
    else:
        day = S.next_publish_date(rows)
        genre, why = S.genre_for(day, rows, data)
        lo, hi, n_parts, part_words, mins, approx = MIN_WORDS, MAX_WORDS, PARTS, "660-720", "20-25", "2,650"
    prefer = why.split(":", 1)[1] if why.startswith("weekend:") else None
    if not doomsday and not redo:
        ser = S.active_series(data, genre, prefer) or S.create_series(genre, data, complete, used_names)
    part = int(redo["part"]) if redo else ser["parts_done"] + 1
    brief_ser = ser
    if redo:   # same part again: same outline and the same events, so later parts still follow on
        brief_ser = {**ser, "parts_done": part - 1, "so_far": ser["so_far"][:part - 1]}
    final = part >= ser["parts_total"]
    opening = next_opening(rows)
    log.info("%s %s -> %s part %d/%d (%s)", day, day.strftime("%a"), ser["title_en"], part,
             ser["parts_total"], why)
    series_names = {c["name"] for c in ser.get("characters") or []}
    brief = S.episode_brief(brief_ser)
    if redo and len(ser["so_far"]) >= part:
        brief += ("\nThis part has ALREADY been outlined. Tell exactly these events, in this order, "
                  "with the same ending/cliffhanger: " + ser["so_far"][part - 1])
    plan = plan_story(genre, opening, premises, used_names - series_names, series_brief=brief,
                      minutes=mins, words=approx)
    plan["characters"] = (ser.get("characters") or []) + [c for c in plan.get("characters", [])
                                                           if c["name"] not in series_names]
    names = [c["name"] for c in plan["characters"]]
    final_note = (None if final else "End on a strong cliffhanger: the main conflict continues in the next part.")
    text = ""
    for p in range(n_parts):
        text += "\n" + write_part(plan, p, text, final_note=final_note, parts=n_parts, part_words=part_words)
    sentences = fix_long_sentences(to_sentences(text))
    sentences = fix_long_sentences(adjust_length(plan, sentences, lo=lo, hi=hi))
    sentences = _trim(sentences, hi)
    from text_fix import bad_lines
    garbled = len(bad_lines(sentences))
    if garbled > max(8, len(sentences) * 0.06):
        raise LLMError(f"model mixed other scripts into {garbled} sentences; rewriting with a new plan")
    words, problems = self_check(plan, sentences, lo, hi)
    problems += style_check(sentences)
    problems += originality_and_ending_check(plan, sentences, must_resolve=final,
                                             true_story=(genre == "real lives"))
    if problems:
        raise LLMError("self-check failed: " + "; ".join(problems))
    next_id = int(redo["id"]) if redo else max([int(r["id"]) for r in rows if r["id"].isdigit()] or [0]) + 1
    script = " ".join(f"{i + 1}. {s}{SENTENCE_SEP}" for i, s in enumerate(sentences))
    try:
        segs = segment_scenes(plan, sentences)
        prompts_field = f" {PROMPT_SEP} ".join(f"{st}::{p}" for st, p in segs)
        n_pics = len(segs)
    except (LLMError, ValueError, TypeError) as e:
        log.warning("Scene segmentation failed (%s); using beat-based pictures", str(e)[:120])
        prompts_field = f" {PROMPT_SEP} ".join(scene_prompts(plan))
        n_pics = len(plan["beats"])
    gta = S.GENRES[genre]["ta"]
    suffix = f" | {ser['title_ta']} - பகுதி {part}"
    title = plan["title_ta"].strip()
    if len(title) + len(suffix) > 100:   # cut at a word boundary, never mid-word
        title = title[:100 - len(suffix) - 1].rsplit(" ", 1)[0].rstrip(" ,:-") + "…"
    title += suffix
    desc = plan.get("description_ta", "")
    if genre == "doomsday":
        desc += ("\n\n⏳ டூம்ஸ்டே தொடர்: ஒவ்வொரு சனி, ஞாயிறு காலை 11 மணிக்கு புதிய பகுதி!"
                 "\n(இது முழுக்க கற்பனைக் கதை / This is a work of fiction)")
    if genre == "real lives":
        desc += "\n\n(நிஜ வாழ்க்கை நிகழ்வுகளை அடிப்படையாகக் கொண்ட நாடகமாக்கல் / Dramatised from documented real events)"
    row = {"id": str(next_id), "genre": genre, "title_ta": title,
           "title_en": f"{plan['title_en']} | {ser['title_en']} Part {part}", "script_ta": script,
           "scene_prompts": prompts_field,
           "publish_at": redo["publish_at"] if redo else S.publish_at(day, DOOM_HOUR if doomsday else None),
           "status": "pending", "video_id": "", "fail_reason": "",
           "description_ta": desc, "series_id": ser["id"], "part": str(part),
           "thumb_quote_ta": plan.get("thumb_line1_ta", ""), "thumb_hook_ta": plan.get("thumb_line2_ta", ""),
           "thumb_text": json.dumps({k: plan.get(f"thumb_{k}_ta", "") for k in
                                     ("line1", "line2", "ribbon", "title", "tagline")}, ensure_ascii=False),
           "thumb_prompt": thumb_prompt(plan)}
    from text_fix import foreign, repair_row
    repair_row(row, write)   # fix the few stray foreign-letter words before saving (Gemini only)
    if foreign(row["script_ta"]):
        raise LLMError("story still has foreign letters after repair")
    if redo:
        return row, None, names
    ser["so_far"].append(plan.get("episode_summary_en") or plan.get("premise_en", ""))
    ser["parts_done"] = part
    if final:
        ser["status"] = "done"
    S.save(data)
    log.info("Story %s ok (%s %s part %d): %d words, %d sentences, %d pictures", next_id, gta,
             ser["title_en"], part, words, len(sentences), n_pics)
    return row, f"[{ser['title_en']} part {part}] " + plan["premise_en"], names


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--auto", action="store_true",
                    help="30 stories in total at first, then refill to 20 pending when below 10")
    ap.add_argument("--max-per-run", type=int, default=5)
    ap.add_argument("--redo", default="", help="comma-separated row ids to rewrite in the new style")
    args = ap.parse_args()
    if args.redo:
        rows = load_rows()
        done = 0
        for rid in [x.strip() for x in args.redo.split(",") if x.strip()]:
            old = next(r for r in rows if r["id"] == rid)
            if old["status"] not in ("pending", "hold"):
                log.info("Row %s is %s: not rewritten", rid, old["status"])
                continue
            for attempt in range(3):
                try:
                    new, _, _ = write_story(rows, redo=old)
                    break
                except LLMError as e:
                    log.warning("Rewrite of %s failed (%s)", rid, str(e)[:200])
                    if str(e).startswith(("RATE_LIMIT", "BUSY")):
                        return 0 if done else 1
            else:
                continue
            keep_hold = "Studio" in (old.get("fail_reason") or "")   # broken upload still to delete
            new["status"] = "hold" if keep_hold else "pending"
            new["video_id"] = old.get("video_id", "") if keep_hold else ""
            new["fail_reason"] = old.get("fail_reason", "") if keep_hold else ""
            rows[rows.index(old)] = {**old, **new}
            save_rows(rows)
            done += 1
            log.info("Row %s rewritten in the new style", rid)
        return 0

    rows = load_rows()
    pending = sum(r["status"] == "pending" for r in rows)
    if args.auto:
        # keep about a week of parts written ahead (each part depends on the one before)
        want = max(0, 7 - pending)
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
    if args.auto and not stopped_early and os.environ.get("DOOMSDAY", "on") != "off":
        import series as S
        doom_pending = sum(r["status"] == "pending" and S.is_doom(r) for r in rows)
        if doom_pending < 2:
            try:
                row, premise, names = write_story(rows, doomsday=True)
                rows.append(row)
                save_rows(rows)
                append_index(row["id"], row["genre"], row["title_en"], premise, names)
                written += 1
            except LLMError as e:
                log.warning("Doomsday part not written this run: %s", str(e)[:200])
    log.info("Wrote %d stories", written)
    # quota / busy servers are temporary: not a failure, the next run continues
    return 0 if written or want == 0 or stopped_early else 1


if __name__ == "__main__":
    sys.exit(main())
