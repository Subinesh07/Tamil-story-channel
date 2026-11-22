"""Weekly story series: each weekday has its own genre and an ongoing serial (Part 1, 2, 3 ...).

Mon Adventure | Tue Horror | Wed Family serial | Thu Real lives | Fri Family moral stories
Sat + Sun: the next part of whichever series is gaining views fastest (family serial and
adventure until there is view data).

series.json keeps every series' "bible": title, premise, fixed characters, the planned arc and
a running summary, so each new part continues the same story.
"""
import json
import logging
import os
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from config import PUBLISH_HOUR, ROOT, TIMEZONE

log = logging.getLogger(__name__)
PATH = ROOT / "series.json"
TZ = ZoneInfo(TIMEZONE)

WEEKLY = {0: "adventure", 1: "horror", 2: "family serial", 3: "real lives", 4: "family moral"}
WEEKEND_DEFAULT = {5: "family serial", 6: "adventure"}

GENRES = {
    "adventure": {"ta": "சாகசத் தொடர்", "parts": 5,
                  "brief": "a Tamil adventure serial: treasure hunts, forests, seas, hill temples, ancient "
                           "secrets, survival and courage. Family-friendly thrills"},
    "horror": {"ta": "திகில் தொடர்", "parts": 4,
               "brief": "a suspense and horror serial: eerie houses, villages, night journeys, mysteries "
                        "with a satisfying explanation. Scary atmosphere but NO gore, blood or graphic "
                        "violence (advertiser-friendly)"},
    "family serial": {"ta": "குடும்பத் தொடர்", "parts": 8,
                      "brief": "an emotional Tamil family drama serial like a TV mega-serial: in-laws, "
                               "siblings, property, betrayal, a calm and clever heroine, and justice in the end"},
    "real lives": {"ta": "நிஜ வாழ்க்கைக் கதை", "parts": 4,
                   "brief": "the TRUE life story of one famous person from anywhere in the world and any era, "
                            "told dramatically but strictly based on well-documented facts. Never invent "
                            "events, dates or quotes and present them as real; dialogue may be lightly "
                            "dramatised but must fit known facts. Respectful, no defamation"},
    "family moral": {"ta": "நீதிக் கதைகள்", "parts": 6,
                     "brief": "gentle moral stories for the whole family, framed as a series: the same "
                              "grandparent and grandchildren in one village meet every week and one complete "
                              "moral story is told each part (a full story every time, the frame continues)"},
}


GENRES["doomsday"] = {
    "ta": "டூம்ஸ்டே தொடர்", "parts": 7,
    "brief": "an ORIGINAL realistic sci-fi disaster thriller (fiction): a giant solar storm will black out "
             "Earth in 7 days; each part is one day of the countdown. Suspense, chases, family emotion, "
             "brave ordinary people. NO gore or graphic violence, no real politicians, agencies or brands, "
             "and nothing from Marvel, DC or any film (no superheroes, no famous villain names)"}

# Sunday 5 PM "golden shot": one COMPLETE family-emotional story every week, written to be shared
# (our best video so far is a family-emotional story). Same playlist every week.
GENRES["family emotional"] = {
    "ta": "குடும்பக் கதை", "parts": 1000,
    "brief": "ONE complete, standalone, deeply emotional Tamil family story (amma, appa, patti, thatha, "
             "son, daughter, in-laws, siblings) that people will want to share on WhatsApp with their family. "
             "A relatable everyday situation, a hidden sacrifice or secret, a big emotional twist near the end "
             "that brings tears, and a warm, satisfying ending with a quiet life lesson (never preachy). "
             "The very first line must be a gripping hook. Title = a family member + a secret / one object, "
             "like 'அம்மா மறைச்ச அந்த ஒரு கடிதம்'"}
GOLDEN_BIBLE = {
    "id": "golden-1", "genre": "family emotional", "status": "active", "parts_total": 1000, "parts_done": 0,
    "so_far": [], "title_ta": "தமிழ் குடும்ப கதைகள்", "title_en": "Tamil Family Stories",
    "premise_en": "Standalone emotional family stories, a new family every week.", "characters": [], "arc": []}


def golden_series(data):
    for x in data["series"]:
        if x["genre"] == "family emotional" and x["status"] == "active":
            return x
    data["series"].append(json.loads(json.dumps(GOLDEN_BIBLE)))
    return data["series"][-1]


# Pre-written bible (approved sample), so no AI tokens are spent creating it
DOOMSDAY_BIBLE = {
    "id": "doomsday-1", "genre": "doomsday", "status": "active", "parts_total": 7, "parts_done": 0,
    "so_far": [], "title_ta": "டூம்ஸ்டே: கடைசி 7 நாட்கள்", "title_en": "Doomsday: The Last 7 Days",
    "premise_en": "Meera, a young astronomer at a Kodaikanal observatory, discovers that a giant solar "
                  "storm will black out the whole world in 7 days. Nobody believes her, secretive "
                  "officials try to silence her, and she races to Chennai to protect her father and "
                  "little brother, and finally to save the city's power grid.",
    "characters": [
        {"name": "மீரா", "role": "young astronomer, brave and clever heroine", "age": 28,
         "appearance_en": "slim Tamil woman, black hair in a loose braid, round black glasses, "
                          "maroon kurta with a grey hoodie, ID card lanyard"},
        {"name": "செல்வம்", "role": "Meera's father, a kind Chennai auto-rickshaw driver", "age": 58,
         "appearance_en": "thin Tamil man, grey moustache, short grey hair, khaki shirt, white veshti"},
        {"name": "அர்ஜுன்", "role": "Meera's 10-year-old brother, curious and funny", "age": 10,
         "appearance_en": "small Tamil boy, messy hair, blue school t-shirt, red backpack"},
        {"name": "ராகவன்", "role": "cold, secretive senior official who wants the news hidden", "age": 50,
         "appearance_en": "tall Tamil man, neat grey beard, black coat, rimless glasses"},
        {"name": "கார்த்திக்", "role": "Meera's journalist friend who slowly believes her", "age": 30,
         "appearance_en": "Tamil man, short beard, checked shirt, camera bag"},
    ],
    "arc": [
        "Day 7: at night in the Kodaikanal lab Meera finds a giant sunspot; her maths says a solar storm "
        "hits in 7 days and every light, phone and hospital machine will die. She calls her father. Two "
        "men in black coats walk in and order her to stop. Cliffhanger: she escapes with a copy of the data.",
        "Day 6: a tense escape down the misty ghat road to Chennai; the men follow; small strange signs "
        "begin (phones glitching, a faint red glow in the sky). Cliffhanger: Raghavan is waiting at her home.",
        "Day 5: Raghavan says the panic would be worse than the storm. Meera and journalist Karthik "
        "try to warn the public; their video vanishes. Cliffhanger: Arjun overhears something terrible.",
        "Day 4: the family prepares while neighbours laugh at them; Arjun finds a secret list of the "
        "few people who will be protected. Cliffhanger: their names are not on it, and Raghavan's is.",
        "Day 3: the sky turns red at night and people start to believe; panic in the city. Meera learns "
        "why Raghavan hid the truth. Cliffhanger: Selvam goes missing in the crowd.",
        "Day 2: Meera finds the real hope: if the city switches off its grid just before the storm, the "
        "transformers survive. She must reach the control centre. Cliffhanger: Raghavan blocks the door.",
        "Day 1 to zero hour: Raghavan finally helps; the switch-off happens seconds before the storm; "
        "the whole world goes dark, but Chennai's lights come back first. The family is together, "
        "Selvam is a hero, and a final quiet twist about the next storm sets up a possible season 2.",
    ],
}


def load():
    if PATH.exists():
        return json.loads(PATH.read_text(encoding="utf-8"))
    return {"series": []}


def save(data):
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_doom(r):
    return (r.get("series_id") or "").startswith("doomsday") or r.get("genre") == "doomsday"


def next_publish_date(rows):
    """The day after the last scheduled 7 PM story (never today after 15:00, never in the past)."""
    now = datetime.now(TZ)
    earliest = now.date() if now.hour < 15 else now.date() + timedelta(days=1)
    taken = [datetime.fromisoformat(r["publish_at"]).date() for r in rows
             if r.get("publish_at") and not is_doom(r)]
    day = max(taken) + timedelta(days=1) if taken else earliest
    return max(day, earliest)


def next_doom_date(rows):
    """Next free Saturday/Sunday after the last Doomsday part (12 PM slot)."""
    now = datetime.now(TZ)
    earliest = now.date() if now.hour < 6 else now.date() + timedelta(days=1)
    taken = [datetime.fromisoformat(r["publish_at"]).date() for r in rows if r.get("publish_at") and is_doom(r)]
    day = max(max(taken) + timedelta(days=1), earliest) if taken else earliest
    while day.weekday() not in (5, 6):
        day += timedelta(days=1)
    return day


# Weekend 11 AM serial: after Doomsday, a new original season on a theme people already search for.
# tag = Tamil word that leads every title and the thumbnail; search = English YouTube search tags.
WEEKEND_THEMES = [
    {"tag": "ஜாம்பி", "search": ["zombie tamil story", "zombie tamil", "zombie outbreak story"],
     "brief": "a zombie-virus outbreak spreading through a Tamil Nadu town; a family and strangers try to "
              "survive and reach safety"},
    {"tag": "ஏலியன்", "search": ["alien tamil story", "alien invasion tamil", "ufo tamil story"],
     "brief": "mysterious alien ships appear over Chennai; ordinary people uncover what the visitors want"},
    {"tag": "சுனாமி", "search": ["tsunami tamil story", "survival story tamil", "disaster story tamil"],
     "brief": "a giant tsunami warning for the Tamil Nadu coast; a fishing family races to save their village"},
    {"tag": "டைம் லூப்", "search": ["time loop tamil story", "time travel tamil", "sci fi tamil story"],
     "brief": "a young woman keeps reliving the same day before a disaster and must find how to stop it"},
    {"tag": "கடைசி மனிதன்", "search": ["last man on earth tamil", "apocalypse tamil story", "survival tamil"],
     "brief": "a man wakes up to find Chennai completely empty and slowly discovers who else survived and why"},
    {"tag": "வைரஸ்", "search": ["virus outbreak tamil story", "pandemic story tamil", "thriller tamil story"],
     "brief": "a strange new virus makes people forget who they are; a doctor and her brother search for the cure"},
    {"tag": "எரிமலை", "search": ["volcano tamil story", "disaster survival tamil", "end of the world tamil"],
     "brief": "an ancient volcano wakes under the Western Ghats; a hill-station family must escape in time"},
]


def doomsday_series(data, complete=None, used_names=()):
    """The active weekend serial. Season 1 is the approved Doomsday bible; when a season ends, a new
    original season starts on a popular theme that has not been used yet."""
    for s in data["series"]:
        if s["genre"] == "doomsday" and s["status"] == "active":
            return s
    if not any(s["genre"] == "doomsday" for s in data["series"]):
        s = json.loads(json.dumps(DOOMSDAY_BIBLE))
        s.update({"title_tag": "டூம்ஸ்டே", "search_tags": ["doomsday", "doomsday tamil", "doomsday tamil story",
                                                         "end of the world tamil"]})
        data["series"].append(s)
        return s
    if complete is None:
        return None
    used = {s.get("title_tag") for s in data["series"] if s["genre"] == "doomsday"}
    theme = next((t for t in WEEKEND_THEMES if t["tag"] not in used), WEEKEND_THEMES[len(used) % len(WEEKEND_THEMES)])
    old = GENRES["doomsday"]["brief"]
    GENRES["doomsday"]["brief"] = (f"an ORIGINAL weekend survival thriller series (fiction): {theme['brief']}. "
                                   "Each part ends on a cliffhanger. Suspense, chases, family emotion, brave "
                                   "ordinary people. No gore, no real politicians, agencies or brands, nothing "
                                   "from any film or series")
    try:
        s = create_series("doomsday", data, complete, set(used_names))
    finally:
        GENRES["doomsday"]["brief"] = old
    s.update({"title_tag": theme["tag"], "search_tags": theme["search"]})
    log.info("New weekend season: %s (%s)", s.get("title_en"), theme["tag"])
    return s


def publish_at(day, hour=None):
    """Day-wise time from config.PUBLISH_HOURS, shifted by the weekly auto-tuner (max +-2 h)."""
    if hour is None:
        from config import PUBLISH_HOURS
        try:
            from strategy import load as load_strategy
            shift = int(load_strategy().get("publish_hour", PUBLISH_HOUR)) - PUBLISH_HOUR
        except Exception:
            shift = 0
        hour = min(21, max(16, PUBLISH_HOURS[day.weekday()] + max(-2, min(2, shift))))
    return datetime.combine(day, time(hour), TZ).isoformat()


def views_per_day_by_series(rows):
    """{series_id: views/day} over our recent videos, via the YouTube API (readonly)."""
    vids = {r["video_id"]: r.get("series_id") for r in rows
            if r.get("video_id") and r.get("series_id") and not is_doom(r)}
    if not vids or not os.environ.get("YT_REFRESH_TOKEN"):
        return {}
    try:
        from competitors import client
        yt = client()
        out, now = {}, datetime.now(TZ)
        ids = list(vids)
        for k in range(0, len(ids), 50):
            for v in yt.videos().list(part="statistics,snippet", id=",".join(ids[k:k + 50])).execute()["items"]:
                pub = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
                days = max(0.5, (now - pub).total_seconds() / 86400)
                if days > 21:
                    continue
                s = vids[v["id"]]
                out.setdefault(s, []).append(int(v["statistics"].get("viewCount", 0)) / days)
        return {s: sum(v) / len(v) for s, v in out.items()}
    except Exception as e:
        log.warning("Could not read view counts: %s", str(e)[:150])
        return {}


def genre_for(day, rows, data):
    wd = day.weekday()
    if wd in WEEKLY:
        return WEEKLY[wd], "weekday"
    if wd == 6:
        return "family emotional", "sunday-golden"
    speed = views_per_day_by_series(rows)
    active = {s["id"]: s for s in data["series"] if s["status"] == "active" and s["genre"] != "family emotional"}
    ranked = [sid for sid in sorted(speed, key=speed.get, reverse=True) if sid in active]
    if ranked:
        log.info("Weekend pick: fastest-growing series %s (%.0f views/day)", ranked[0], speed[ranked[0]])
        return active[ranked[0]]["genre"], f"weekend:{ranked[0]}"
    return WEEKEND_DEFAULT[wd], "weekend-default"


def active_series(data, genre, prefer_id=None):
    for s in data["series"]:
        if s["status"] == "active" and (s["id"] == prefer_id if prefer_id else s["genre"] == genre):
            return s
    return None


def create_series(genre, data, complete, used_names):
    g = GENRES[genre]
    done = [s["title_en"] + (f" ({s.get('person')})" if s.get("person") else "") for s in data["series"]]
    person_rule = ("Pick ONE famous real person (anywhere in the world, any era) whose life is very well "
                   "documented and dramatic, and who is NOT in the list of done series. Include \"person\" "
                   "and \"key_facts_en\" (10-15 well-documented facts in life order). Characters must be "
                   "the real people in their life.") if genre == "real lives" else (
                   "Invent original characters with fresh Tamil names (not: "
                   f"{', '.join(sorted(used_names)) or 'none'}). Fully original: do not copy any film, "
                   "serial, book or YouTube story.")
    plan = complete(f"""Create a new Tamil YouTube story SERIES: {g['brief']}.
It will run for {g['parts']} weekly parts of about 22 minutes each.
Series already done (make this clearly different): {'; '.join(done) or 'none'}.
{person_rule}
Return JSON:
{{"title_ta": "short catchy Tamil series name (max 30 characters)",
  "title_en": "English series name",
  "premise_en": "2-3 sentence premise",
  {'"person": "full name", "key_facts_en": ["..."],' if genre == 'real lives' else ''}
  "characters": [{{"name": "...", "role": "...", "age": 0,
                   "gender": "male/female", "appearance_en": "fixed look: face, hair, facial hair (beard / moustache only / clean-shaven), clothes - identical in every picture"}}],
  "arc": ["one-line outline of part 1", "... part 2", "... (exactly {g['parts']} items)"]}}""",
                    want_json=True, max_tokens=6000)
    if len(plan.get("arc", [])) < 2:
        raise ValueError("series plan has no arc")
    sid = f"{genre.split()[0]}-{len(data['series']) + 1}"
    s = {"id": sid, "genre": genre, "status": "active", "parts_total": len(plan["arc"]),
         "parts_done": 0, "so_far": [], **{k: plan.get(k) for k in
                                            ("title_ta", "title_en", "premise_en", "characters", "arc",
                                             "person", "key_facts_en")}}
    data["series"].append(s)
    log.info("New %s series: %s (%d parts)", genre, s["title_en"], s["parts_total"])
    return s


def episode_brief(s):
    """Prompt text that makes the next part continue the series."""
    if s["genre"] == "family emotional":
        done = "; ".join(t[:120] for t in s["so_far"][-12:]) or "none yet"
        return (f"STANDALONE STORY (not a serial): {GENRES['family emotional']['brief']}.\n"
                f"A NEW family, new names and a clearly different situation from these earlier stories: {done}.\n"
                "No recap, no 'part', no cliffhanger: the story is complete and resolved in this one video.")
    n, total = s["parts_done"] + 1, s["parts_total"]
    g = GENRES[s["genre"]]
    chars = "\n".join(f"- {c['name']}: {c.get('role', '')}, {c.get('age', '')}, look: {c.get('appearance_en', '')}"
                      for c in s.get("characters") or [])
    so_far = "\n".join(f"Part {i + 1}: {t}" for i, t in enumerate(s["so_far"])) or "(this is the first part)"
    facts = ("\nWell-documented facts to stay true to:\n- " + "\n- ".join(s.get("key_facts_en") or [])
             if s["genre"] == "real lives" else "")
    ending = ("This is the FINAL part: resolve every thread with a satisfying, earned ending."
              if n >= total else
              "End this part on a strong cliffhanger that makes viewers want the next part "
              "(the main conflict continues).")
    recap = ("" if n == 1 else
             "Start with a short 2-3 sentence recap of the previous part (\"போன பகுதியில…\"), then continue.")
    return f"""SERIES: {s['title_ta']} ({s['title_en']}), {g['ta']}: {g['brief']}.
This is PART {n} of {total}.
Series premise: {s['premise_en']}
Main characters (keep names and looks identical; you may add minor characters):
{chars}
Story so far:
{so_far}
Planned outline for this part: {s['arc'][min(n, total) - 1]}{facts}
{recap}
{ending}"""
