"""Read/write stories.csv and split scripts into sentences and scene prompts."""
import csv
import re
import sys
from datetime import datetime

from config import CSV_COLUMNS, MAX_WORDS_PER_SENTENCE, PROMPT_SEP, SENTENCE_SEP, STORIES_CSV

csv.field_size_limit(sys.maxsize)


def load_rows(path=STORIES_CSV):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for c in CSV_COLUMNS:
            r.setdefault(c, "")
    return rows


def save_rows(rows, path=STORIES_CSV):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def update_row(row_id, **fields):
    rows = load_rows()
    for r in rows:
        if r["id"] == str(row_id):
            r.update({k: str(v) for k, v in fields.items()})
    save_rows(rows)


def pick_row(rows, row_id=None):
    """Explicit id, else the pending row with the earliest publish date still in the future."""
    if row_id:
        for r in rows:
            if r["id"] == str(row_id):
                return r
        raise SystemExit(f"Row {row_id} not found in stories.csv")
    now = datetime.now().astimezone()
    pending = [r for r in rows if r["status"] == "pending"]
    def key(r):
        try:
            return datetime.fromisoformat(r["publish_at"])
        except ValueError:
            return datetime.max.replace(tzinfo=now.tzinfo)
    future = [r for r in pending if key(r) > now]
    candidates = sorted(future or pending, key=key)
    if not candidates:
        raise SystemExit("No pending rows. Run the 'Generate stories' workflow.")
    return candidates[0]


def split_sentences(script):
    parts = [p.strip() for p in script.split(SENTENCE_SEP)]
    # strip optional leading numbering like "12." or "12)"
    return [re.sub(r"^\d+\s*[.)]\s*", "", p) for p in parts if p.strip()]


def split_prompts(prompts):
    return [p.strip() for p in prompts.split(PROMPT_SEP) if p.strip()]


def word_count(text):
    return len(text.split())


def long_sentences(sentences):
    return [s for s in sentences if word_count(s) > MAX_WORDS_PER_SENTENCE]
