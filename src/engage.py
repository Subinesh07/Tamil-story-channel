"""Viewer engagement spoken at the end of every video (before the outro), plus the fiction note.

- comment shout-out: one warm line about a real viewer comment from a recent video
- quiz winner: the first correct answer to the last video's quiz is named and gets a reply
- today's quiz: one easy question from this story, answer in the comments

Every step is optional: on any error it is skipped, the video is never blocked.
Lines are checked: Tamil letters only (names written in Tamil), no foreign scripts.
"""
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
log = logging.getLogger("engage")
FICTION_LINE = "இது ஒரு கற்பனை கதை"
FICTION_DESC = "⚠️ இது முழுக்க முழுக்க ஒரு கற்பனை கதை. கதாபாத்திரங்களும் சம்பவங்களும் கற்பனையே."
_BAD = re.compile(r"[A-Za-z]{2,}|[\u0080-ɏͰ-ॣ०-୿ఀ-῿]|https?://")


def _ok(line):
    return bool(line) and not _BAD.search(line) and len(line) < 220


def _clean(lines):
    out = [l.strip().replace(".", "।").rstrip("।") for l in lines if l and l.strip()]
    return [l for l in out if _ok(l)]


def _yt():
    from competitors import client
    return client()


def _comments(video_id, n=60):
    try:
        res = _yt().commentThreads().list(part="snippet", videoId=video_id, maxResults=n,
                                          order="time", textFormat="plainText").execute()
    except Exception as e:
        log.info("Comments not readable for %s: %s", video_id, str(e)[:100])
        return []
    out = []
    for it in res.get("items", []):
        s = it["snippet"]["topLevelComment"]["snippet"]
        if s.get("authorChannelId", {}).get("value") == s.get("channelId"):
            continue   # our own comments
        out.append({"id": it["snippet"]["topLevelComment"]["id"], "author": s["authorDisplayName"].lstrip("@"),
                    "text": s["textDisplay"][:300], "at": s["publishedAt"], "likes": s.get("likeCount", 0)})
    return sorted(out, key=lambda c: c["at"])


def _llm(prompt):
    from llm import complete
    return complete(prompt, want_json=True, max_tokens=1200, rounds=1)


def make_quiz(script_sentences):
    """One easy question whose answer is clearly in the story."""
    story = " ".join(script_sentences)[:9000]
    d = _llm("From this Tamil story, write ONE easy quiz question for viewers whose answer is clearly "
             "stated in the story (a name, an object, a place or a number). Casual spoken Tamil, Tamil "
             "letters only, no English letters. Return JSON {\"question\": \"...?\", \"answer\": \"short answer\"}"
             "\n\n" + story)
    q, a = d["question"].strip(), d["answer"].strip()
    if not q.endswith("?"):
        q += "?"
    return (q, a) if _ok(q) and a else (None, None)


def quiz_lines(q):
    return _clean([f"இன்னைக்கு கதை குவிஸ்: {q}",
                   "சரியான பதிலை கமெண்ட்ல சொல்லுங்க, முதல்ல சரியா சொல்றவங்க பெயரை அடுத்த வீடியோவுல சொல்லுவோம்"])


def winner_line(rows):
    """Name the first correct answer to the most recent quiz that has had at least 12 hours."""
    now = datetime.now(timezone.utc)
    cands = [r for r in rows if r.get("quiz_a") and r.get("video_id") and not r.get("quiz_winner")
             and r.get("publish_at") and now - datetime.fromisoformat(r["publish_at"]) > timedelta(hours=12)]
    if not cands:
        return [], None
    r = max(cands, key=lambda x: x["publish_at"])
    after = datetime.fromisoformat(r["publish_at"])
    coms = [c for c in _comments(r["video_id"], 100) if datetime.fromisoformat(c["at"].replace("Z", "+00:00")) >= after]
    if not coms:
        return [], (r["id"], "-")
    listing = "\n".join(f"{i}. {c['text']}" for i, c in enumerate(coms))
    d = _llm(f"Quiz question: {r.get('quiz_q', '')}\nCorrect answer: {r['quiz_a']}\n"
             "Which of these numbered viewer comments give the correct answer (any spelling, Tamil or English)? "
             "Return JSON {\"correct\": [numbers in the given order]}\n\n" + listing)
    ok = [int(i) for i in d.get("correct", []) if str(i).isdigit() and int(i) < len(coms)]
    if not ok:
        return [], (r["id"], "-")
    win = coms[min(ok)]
    t = _llm("Write this YouTube viewer name in Tamil letters only, as it sounds (keep it short, first name "
             f"only). Return JSON {{\"name\": \"...\"}}\n\nName: {win['author']}")
    name = t.get("name", "").strip()
    lines = _clean([f"போன வீடியோ குவிஸ்க்கு முதல்ல சரியான பதில் சொன்னது {name}! வாழ்த்துக்கள்"]) if name else []
    try:
        _yt().comments().insert(part="snippet", body={"snippet": {
            "parentId": win["id"],
            "textOriginal": "🎉 சரியான பதில்! முதல்ல சொன்னது நீங்க தான் – அடுத்த வீடியோவுல உங்க பெயர் வருது! 🌙"}}).execute()
    except Exception as e:
        log.info("Winner reply failed: %s", str(e)[:100])
    return lines, (r["id"], win["author"])


def shoutout_lines(rows, row):
    """One warm reaction to a real viewer comment (previous part of the same series first)."""
    done = [r for r in rows if r.get("video_id") and r.get("status") == "done" and r["id"] != row["id"]]
    same = [r for r in done if row.get("series_id") and r.get("series_id") == row["series_id"]]
    pool = sorted(same or done, key=lambda r: r.get("publish_at", ""), reverse=True)[:3]
    coms = []
    for r in pool:
        coms += [c for c in _comments(r["video_id"]) if len(c["text"]) > 8]
    if not coms:
        return []
    coms = sorted(coms, key=lambda c: -c["likes"])[:25]
    listing = "\n".join(f"{i}. ({c['author']}) {c['text']}" for i, c in enumerate(coms))
    d = _llm("You are the warm storyteller of a Tamil story channel. From these viewer comments pick ONE that "
             "is kind, funny, emotional or a good guess about the story (skip rude, negative, spam, links, "
             "self-promotion, quiz answers). Write 1-2 short spoken lines in casual Tamil reacting to it, naming "
             "the viewer by first name written in Tamil letters. Tamil letters only, no English letters, no emoji. "
             "If none is suitable return empty. Return JSON {\"lines\": [\"...\"]}\n\n" + listing)
    return _clean(d.get("lines", []))[:2]


def end_segment(row, story_sentences):
    """Spoken lines before the outro + fields to save on the row. Never raises."""
    import csv
    from config import ROOT
    rows = list(csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")))
    lines, fields = [], {}
    for name, fn in (("winner", lambda: winner_line(rows)), ("shoutout", lambda: (shoutout_lines(rows, row), None))):
        try:
            got, mark = fn()
            lines += got
            if name == "winner" and mark:
                fields["_winner_for"] = mark
        except Exception as e:
            log.info("Engagement %s skipped: %s", name, str(e)[:120])
    try:
        q, a = make_quiz(story_sentences)
        if q:
            lines += quiz_lines(q)
            fields.update(quiz_q=q, quiz_a=a)
    except Exception as e:
        log.info("Quiz skipped: %s", str(e)[:120])
    return lines, fields
