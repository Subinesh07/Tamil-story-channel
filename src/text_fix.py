"""Guard against garbled AI text: Tamil scripts with stray Hindi / Malayalam / Korean / Arabic ... letters.

Free models sometimes mix other scripts into Tamil. Leda would read those words wrongly and the
subtitles would show odd letters, so every story is checked (and repaired) before it is saved,
and again before it is voiced.

python src/text_fix.py          # repair every pending story that has foreign letters
"""
import json
import os
import logging
import re
import sys

from config import SENTENCE_SEP

log = logging.getLogger("text_fix")

# Tamil block, Latin letters (English words), digits, spaces and common punctuation
# (emoji and symbols are fine; only letters of other languages are flagged)
# (the Devanagari danda । is our sentence separator, so it is allowed)
_FOREIGN = re.compile(r"[\u0080-ɏͰ-ॣ०-୿ఀ-῿　-퟿豈-￯]")


def foreign(text):
    return bool(_FOREIGN.search(text or ""))


def bad_lines(lines):
    return [i for i, s in enumerate(lines) if foreign(s)]


def _fix_chunk(lines, context, complete):
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(lines))
    out = complete(
        f"These are {len(lines)} lines of a Tamil YouTube story narration ({context}).\n"
        "Some lines contain words in OTHER scripts (Hindi, Malayalam, Kannada, Korean, Arabic, "
        "Russian ...) or broken half-words. Fix those lines so they are correct, natural, casual "
        "spoken Tamil (English words may stay, written in Tamil script). Keep the same meaning "
        "and keep every correct line exactly as it is. Never merge or split lines.\n"
        f'Return JSON {{"lines": [exactly {len(lines)} strings, in order, without numbers]}}.\n\n'
        + numbered, want_json=True, max_tokens=12000)
    new = [re.sub(r"^\d+\s*[.)]\s*", "", str(x)).strip().rstrip(SENTENCE_SEP) for x in out.get("lines", [])]
    if len(new) != len(lines) or any(not x for x in new):
        raise ValueError(f"repair returned {len(new)} lines for {len(lines)}")
    return new


def repair_lines(lines, context, complete, window=6):
    """Fix only the bad lines (with a little context around each) - cheap on tokens.
    Returns (lines, still_bad_count)."""
    lines = list(lines)
    bad = bad_lines(lines)
    if not bad:
        return lines, 0
    # group nearby bad lines into small windows
    groups, cur = [], []
    for i in bad:
        if cur and i - cur[-1] > window:
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    batch = []
    for g in groups:
        lo, hi = max(0, g[0] - 1), min(len(lines), g[-1] + 2)
        batch.append((lo, hi))
    # send up to ~60 lines per request
    k = 0
    while k < len(batch):
        take, size = [], 0
        while k < len(batch) and size + (batch[k][1] - batch[k][0]) <= 60:
            take.append(batch[k])
            size += batch[k][1] - batch[k][0]
            k += 1
        if not take:
            take, k = [batch[k]], k + 1
        flat = [i for lo, hi in take for i in range(lo, hi)]
        try:
            fixed = _fix_chunk([lines[i] for i in flat], context, complete)
            for i, s in zip(flat, fixed):
                if not foreign(s):
                    lines[i] = s
        except Exception as e:
            log.warning("Repair request failed: %s", str(e)[:150])
    still = bad_lines(lines)
    return lines, len(still)


FORMAL = re.compile(r"(ினாள்|ினான்|ினார்|கிறாள்|கிறான்|கிறார்|கிறது|ார்கள்|உள்ளது|வில்லை|மிகவும்|"
                    r"பின்னர்|கொண்டாள்|கொண்டான்|தவறினாள்|விட்டாள்|விட்டான்|போகிறாள்|வேண்டும்)(?=[\s,.!?…\"']|$)")


def spoken_polish(lines, complete):
    """Rewrite bookish lines (…கிறாள், …ினான்) into the casual spoken style of the rest."""
    lines = list(lines)
    idx = [i for i, s in enumerate(lines) if FORMAL.search(s)]
    for k in range(0, len(idx), 50):
        chunk = idx[k:k + 50]
        numbered = "\n".join(f"{n + 1}. {lines[i]}" for n, i in enumerate(chunk))
        try:
            out = complete(
                f"Rewrite these {len(chunk)} Tamil narration lines from bookish written Tamil into casual "
                "SPOKEN Tamil Nadu Tamil (light Tanglish), like a friend telling a story: "
                "பார்த்தாள்→பார்த்தா, போகிறான்→போறான், இல்லை→இல்ல, மிகவும்→ரொம்ப, பின்னர்→அப்புறம், "
                "கொண்டிருந்தாள்→கிட்டு இருந்தா. Same meaning, similar length, never merge or split lines.\n"
                f'Return JSON {{"lines": [exactly {len(chunk)} strings without numbers]}}.\n\n' + numbered,
                want_json=True, max_tokens=8000)
            new = [re.sub(r"^\d+\s*[.)]\s*", "", str(x)).strip().rstrip(SENTENCE_SEP) for x in out.get("lines", [])]
            if len(new) == len(chunk) and all(new) and not any(foreign(x) for x in new):
                for i, s in zip(chunk, new):
                    lines[i] = s
        except Exception as e:
            log.warning("Spoken polish failed: %s", str(e)[:150])
    return lines, len(idx)


def drop_bad(lines):
    """Last resort for 1-2 stubborn lines: remove the foreign letters' words."""
    out = []
    for s in lines:
        if foreign(s):
            s = " ".join(w for w in s.split() if not foreign(w))
        out.append(s)
    return out


def repair_fields(fields, context, complete):
    """fields: {name: text}. Returns the dict with foreign letters fixed."""
    bad = {k: v for k, v in fields.items() if foreign(v)}
    if not bad:
        return fields
    try:
        out = complete(
            f"Fix these Tamil YouTube texts ({context}). Some contain words in other scripts or broken "
            "words; rewrite them as correct, catchy casual Tamil with the same meaning and similar length. "
            "Return JSON with exactly the same keys.\n" + json.dumps(bad, ensure_ascii=False),
            want_json=True, max_tokens=3000)
        for k in bad:
            v = str(out.get(k, "")).strip()
            fields[k] = v if v and not foreign(v) else " ".join(w for w in bad[k].split() if not foreign(w))
    except Exception as e:
        log.warning("Field repair failed (%s); removing the broken words", str(e)[:150])
        for k in bad:
            fields[k] = " ".join(w for w in bad[k].split() if not foreign(w))
    return fields


def repair_row(row, complete):
    """Repair a stories.csv row in place. Returns True if anything changed."""
    from stories import split_sentences
    context = row.get("title_en", "")
    changed = False
    lines = split_sentences(row["script_ta"])
    if bad_lines(lines):
        n = len(bad_lines(lines))
        lines, still = repair_lines(lines, context, complete)
        if still:
            lines = drop_bad(lines)
        row["script_ta"] = " ".join(f"{i + 1}. {s}{SENTENCE_SEP}" for i, s in enumerate(lines))
        log.info("Row %s: repaired %d broken lines (%d needed word removal)", row["id"], n, still)
        changed = True
    try:
        thumb = json.loads(row.get("thumb_text") or "{}")
    except ValueError:
        thumb = {}
    fields = {k: row.get(k, "") for k in ("description_ta", "thumb_quote_ta", "thumb_hook_ta")}
    fields.update({f"thumb.{k}": v for k, v in thumb.items()})
    # the title's "| series - பகுதி N" part is fine; only the story part is checked
    head, sep, tail = (row.get("title_ta") or "").partition(" | ")
    fields["title"] = head
    if any(foreign(v) for v in fields.values()):
        fields = repair_fields(fields, context, complete)
        for k in ("description_ta", "thumb_quote_ta", "thumb_hook_ta"):
            row[k] = fields[k]
        row["thumb_text"] = json.dumps({k: fields[f"thumb.{k}"] for k in thumb}, ensure_ascii=False)
        row["title_ta"] = fields["title"] + sep + tail
        changed = True
    return changed


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from llm import complete as _complete
    from stories import load_rows, save_rows, split_sentences

    def complete(prompt, **kw):
        return _complete(prompt, providers=("gemini",), **kw)
    rows = load_rows()
    spoken = [x for x in os.environ.get("SPOKEN_ROWS", "").split(",") if x.strip()]
    for r in rows:
        if r["id"] in spoken:
            lines, n = spoken_polish(split_sentences(r["script_ta"]), complete)
            r["script_ta"] = " ".join(f"{i + 1}. {s}{SENTENCE_SEP}" for i, s in enumerate(lines))
            save_rows(rows)
            left = sum(bool(FORMAL.search(x)) for x in lines)
            log.info("Row %s: %d bookish lines rewritten in spoken style (%d still bookish)", r["id"], n, left)
    n = 0
    for r in rows:
        if r["status"] == "pending" and repair_row(r, complete):
            n += 1
            save_rows(rows)
    left = [r["id"] for r in rows if r["status"] == "pending" and
            (foreign(r["script_ta"]) or foreign(r["description_ta"]))]
    log.info("Repaired %d stories; still broken: %s", n, left or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
