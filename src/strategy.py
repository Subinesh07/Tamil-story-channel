"""Channel strategy that tunes itself every week from the competitor report and our own results.

channel_strategy.json is read by the story writer, the scheduler and the video maker.
Every change stays inside safe limits and is logged in the weekly report. To freeze it, set
"auto": false in channel_strategy.json.
"""
import json
import re
import statistics
from collections import Counter

from config import GENRE_MIX, PUBLISH_HOUR, ROOT

PATH = ROOT / "channel_strategy.json"
HOUR_RANGE = (17, 21)          # evening family-viewing window we allow
MIN_PER_GENRE = 3              # every genre keeps at least 3 of 30, for variety
STOPWORDS = {"ஒரு", "இந்த", "அந்த", "எந்த", "என்ன", "ஏன்", "வரை", "மட்டும்", "உன்", "என்", "நான்",
             "நீ", "அவள்", "அவன்", "இது", "அது", "எப்படி", "யார்", "எல்லாம்", "கூட", "தான்", "ஊரே",
             "இவள", "இவன்", "இருக்க", "பண்ண", "சொல்லும்", "என்று", "இல்லை", "வேண்டும்", "கதை", "கதைகள்",
             "தமிழ்", "story", "tamil"}
DEFAULT = {"auto": True, "publish_hour": PUBLISH_HOUR, "genre_mix": dict(GENRE_MIX),
           "trending_themes": [], "engagement_push": False, "history": []}

GENRE_WORDS = {
    "family emotional": ["அம்மா", "அப்பா", "மகன்", "மகள்", "மாமியார்", "மருமகள்", "குடும்ப", "தாத்தா",
                         "பாட்டி", "அண்ணன்", "தங்கை", "கணவன்", "மனைவி", "family", "mother", "amma"],
    "moral or life-lesson": ["நீதி", "பாடம்", "moral", "lesson", "நல்ல", "கர்மா", "ஏழை", "பணக்கார"],
    "suspense or mystery": ["மர்ம", "ரகசிய", "பேய்", "திகில்", "mystery", "horror", "secret", "crime"],
    "friendship or romance": ["நட்பு", "நண்பன்", "தோழி", "காதல்", "love", "friend", "romance"],
}


def load():
    if PATH.exists():
        data = json.loads(PATH.read_text(encoding="utf-8"))
        return {**DEFAULT, **data}
    return dict(DEFAULT)


def save(data):
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def top_videos(others, n, per_channel=3):
    """Best videos by views/day, at most `per_channel` from any one channel (no single channel dominates)."""
    picked, count = [], Counter()
    for name, v in sorted(((o["name"], v) for o in others for v in o["videos"]), key=lambda x: -x[1]["per_day"]):
        if count[name] < per_channel:
            picked.append(v)
            count[name] += 1
        if len(picked) >= n:
            break
    return picked


def _genre_of_title(title):
    t = title.lower()
    scores = {g: sum(w in t for w in words) for g, words in GENRE_WORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else None


def update(ours, others, stories, today):
    """Return (new_strategy, list_of_changes). Does nothing if auto is off."""
    s = load()
    changes = []
    if not s.get("auto", True) or not others:
        return s, ["Automatic changes are switched off." if not s.get("auto", True)
                   else "Not enough competitor data: nothing changed."]

    # 1. publish hour: follow the competitors' usual evening hour, only inside 17-21 IST
    hours = [o["top_hour"] for o in others if o.get("top_hour") is not None]
    if hours:
        common = Counter(hours).most_common(1)[0][0]
        if HOUR_RANGE[0] <= common <= HOUR_RANGE[1] and abs(common - s["publish_hour"]) >= 2:
            new = s["publish_hour"] + (1 if common > s["publish_hour"] else -1)  # move 1 hour per week
            changes.append(f"Publish time {s['publish_hour']}:00 → {new}:00 IST "
                           f"(competitors mostly post around {common}:00)")
            s["publish_hour"] = new

    # 2. genres: what works for competitors (weight 1) and for us (weight 2)
    signal = Counter()
    best = top_videos(others, 20)
    for v in best:
        g = _genre_of_title(v["title"])
        if g:
            signal[g] += 1
    if ours and ours.get("videos"):
        by_id = {r.get("video_id"): r.get("genre") for r in stories if r.get("video_id")}
        mine = [(by_id.get(v["id"]), v["per_day"]) for v in ours["videos"] if by_id.get(v["id"])]
        if len(mine) >= 5:
            med = statistics.median(p for _, p in mine)
            for g, p in mine:
                if p > med:
                    signal[g] += 2
    if signal:
        top = signal.most_common(1)[0][0]
        low = min(GENRE_MIX, key=lambda g: (signal[g], s["genre_mix"].get(g, 0)))
        mix = dict(s["genre_mix"])
        if top != low and mix.get(low, 0) > MIN_PER_GENRE:
            mix[top] = mix.get(top, 0) + 1
            mix[low] -= 1
            changes.append(f"Genre mix: +1 '{top}', -1 '{low}' per 30 stories (now "
                           + ", ".join(f"{k} {v}" for k, v in mix.items()) + ")")
            s["genre_mix"] = mix

    # 3. trending themes: inspiration words for the story planner (never titles or plots)
    words = Counter(w for v in best for w in re.findall(r"[஀-௿]{3,}", v["title"]))
    themes = [w for w, _ in words.most_common(8)]
    if themes and themes != s.get("trending_themes"):
        s["trending_themes"] = themes
        changes.append("Story writer will lean towards these popular themes (ideas only): "
                       + ", ".join(themes))

    # 4. engagement: if ours is below the competitor median, use question-style outros
    if ours and len(ours.get("videos", [])) >= 5 and ours.get("median_views", 0) >= 50:
        med = statistics.median(o["engagement"] for o in others)
        push = ours["engagement"] < med
        if push != s.get("engagement_push"):
            s["engagement_push"] = push
            changes.append("Outros now ask viewers a question to get more comments" if push
                           else "Engagement is healthy: outros back to normal rotation")

    if not changes:
        changes = ["Everything is on track: no changes needed this week."]
    s["history"] = (s.get("history", []) + [{"date": today, "changes": changes}])[-20:]
    save(s)
    return s, changes
