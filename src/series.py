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


def load():
    if PATH.exists():
        return json.loads(PATH.read_text(encoding="utf-8"))
    return {"series": []}


def save(data):
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def next_publish_date(rows):
    """The day after the last scheduled story (never today after 15:00, never in the past)."""
    now = datetime.now(TZ)
    earliest = now.date() if now.hour < 15 else now.date() + timedelta(days=1)
    taken = [datetime.fromisoformat(r["publish_at"]).date() for r in rows if r.get("publish_at")]
    day = max(taken) + timedelta(days=1) if taken else earliest
    return max(day, earliest)


def publish_at(day, hour=None):
    if hour is None:
        try:
            from strategy import load as load_strategy
            hour = int(load_strategy().get("publish_hour", PUBLISH_HOUR))
        except Exception:
            hour = PUBLISH_HOUR
    return datetime.combine(day, time(hour), TZ).isoformat()


def views_per_day_by_series(rows):
    """{series_id: views/day} over our recent videos, via the YouTube API (readonly)."""
    vids = {r["video_id"]: r.get("series_id") for r in rows if r.get("video_id") and r.get("series_id")}
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
    speed = views_per_day_by_series(rows)
    active = {s["id"]: s for s in data["series"] if s["status"] == "active"}
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
                   "appearance_en": "fixed look: face, hair, clothes (kept identical in every picture)"}}],
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
