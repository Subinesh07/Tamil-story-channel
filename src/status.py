"""Progress log for the status page (docs/status.html).

Every step writes what happened to status/progress.json, which the workflows commit:
  stages[row]  - script / checks / voice / pictures / video / upload / short, each with a short note
  events       - the last 80 things that happened (newest first)
  limits       - when each free service last refused and last worked (real reset times)
Never raises: the status page must never break a video.
"""
import json
from datetime import datetime, timezone

from config import ROOT

PATH = ROOT / "status" / "progress.json"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load():
    try:
        return json.loads(PATH.read_text())
    except Exception:
        return {"stages": {}, "events": [], "limits": {}}


def _save(d):
    try:
        PATH.parent.mkdir(exist_ok=True)
        PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    except Exception:
        pass


def stage(row_id, name, state, note=""):
    """state: done | waiting | failed | working"""
    try:
        d = _load()
        d["stages"].setdefault(str(row_id), {})[name] = {"state": state, "note": note[:200], "at": _now()}
        _save(d)
    except Exception:
        pass


def event(msg, row_id=None, level="info"):
    """level: info | warn | error"""
    try:
        d = _load()
        d["events"].insert(0, {"at": _now(), "row": str(row_id or ""), "level": level, "msg": msg[:240]})
        d["events"] = d["events"][:80]
        _save(d)
    except Exception:
        pass


def limit(service, ok, note=""):
    """Record when a free service refused (ok=False) or worked (ok=True)."""
    try:
        d = _load()
        s = d["limits"].setdefault(service, {})
        key = "worked_at" if ok else "blocked_at"
        if ok and s.get("blocked_at") and (not s.get("worked_at") or s["worked_at"] < s["blocked_at"]):
            s["last_reset_seen"] = _now()
        s[key] = _now()
        if note:
            s["note"] = note[:160]
        _save(d)
    except Exception:
        pass


def community(row_id, post, poll_q, options):
    """Post and poll texts for the status page checklist."""
    try:
        d = _load()
        d.setdefault("community", {})[str(row_id)] = {"post": post, "poll": poll_q, "options": options, "at": _now()}
        _save(d)
    except Exception:
        pass
