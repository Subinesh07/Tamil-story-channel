"""Viewers' Corner: a short video in the creator's OWN voice reacting to viewer comments.

Step 1 (this file, twice a month): pick the best recent comments (funny, emotional, kind, good guesses)
and write a short, casual Tanglish script - one line per comment, with simple reading tips.
Saves voice/next.json; the recording page (docs/record.html) shows it line by line.

python src/voice_script.py
"""
import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import ROOT  # noqa: E402

log = logging.getLogger("voice_script")
OUT = ROOT / "voice" / "next.json"


def gather_comments(limit_videos=12):
    import csv
    from engage import _comments
    rows = [r for r in csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8"))
            if r.get("video_id") and r.get("status") == "done"]
    rows = sorted(rows, key=lambda r: r.get("publish_at", ""), reverse=True)[:limit_videos]
    out = []
    for r in rows:
        for c in _comments(r["video_id"], 80):
            if 8 < len(c["text"]) < 280 and "http" not in c["text"]:
                out.append({**c, "video": r["title_ta"].split(" | ")[0][:60]})
    return out


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    coms = gather_comments()
    if len(coms) < 3:
        log.info("Only %d usable comments - not enough for a Viewers' Corner yet", len(coms))
        return 1
    coms = sorted(coms, key=lambda c: -c["likes"])[:40]
    listing = "\n".join(f"{i}. [{c['author']}] (on: {c['video']}) {c['text']}" for i, c in enumerate(coms))
    from llm import complete
    d = complete(
        "You write a short 'Viewers Corner' video script for the Tamil story channel 'நிலா கதைகள்'. "
        "The channel's creator (a friendly young man, NOT a professional voice artist) reads it in his own voice. "
        "Pick 5 to 8 of these viewer comments that are funny, emotional, kind or good guesses about the story "
        "(skip rude, negative, spam, self-promotion). For each, write ONE or TWO short lines he says reacting to "
        "it - casual spoken Tamil with natural English words (Tanglish) written in Tamil letters, warm and "
        "light, like talking to a friend, max 22 words per line, easy to read aloud. Also give a 3-6 word "
        "English reading tip for each line (e.g. 'smile, relaxed', 'slow, emotional', 'laugh a little'). "
        "Add an opening line (greeting, what this video is) and a closing line (thank you, ask for more comments, "
        "subscribe). Use the viewer's name (Tamil letters) in his reaction.\n"
        "Return JSON {\"title\": \"short catchy Tamil title\", \"lines\": [{\"text\": \"...\", \"tip\": \"...\", "
        "\"comment\": index or null}]}\n\n" + listing, want_json=True, max_tokens=4000, rounds=1)
    lines = []
    for ln in d["lines"]:
        c = coms[ln["comment"]] if isinstance(ln.get("comment"), int) and 0 <= ln["comment"] < len(coms) else None
        lines.append({"text": ln["text"].strip(), "tip": ln.get("tip", "natural, friendly"),
                      "comment": {"author": c["author"], "text": c["text"], "video": c["video"]} if c else None})
    n = len(list((ROOT / "voice").glob("done_*.json"))) + 1 if (ROOT / "voice").exists() else 1
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"episode": n, "date": str(date.today()), "title": d.get("title", ""),
                               "lines": lines}, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Viewers' Corner #%d script ready: %d lines", n, len(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
