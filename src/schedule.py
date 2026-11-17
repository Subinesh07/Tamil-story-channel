"""Phase 8: give every story a publish date (one a day, 19:00 IST) and write SCHEDULE.md.

python src/schedule.py --start-date 2026-12-01   # first time (saved to channel.json)
python src/schedule.py                           # later runs: new stories get the next free days
"""
import argparse
import json
import logging
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from config import MIN_PENDING, PUBLISH_HOUR, ROOT, SCHEDULE_MD, TIMEZONE
from stories import load_rows, save_rows

log = logging.getLogger("schedule")
CHANNEL_JSON = ROOT / "channel.json"


def load_channel():
    return json.loads(CHANNEL_JSON.read_text()) if CHANNEL_JSON.exists() else {}


def assign_dates(rows, start):
    tz = ZoneInfo(TIMEZONE)
    taken = {datetime.fromisoformat(r["publish_at"]).date() for r in rows if r["publish_at"]}
    day = max(taken) + timedelta(days=1) if taken else start
    day = max(day, start)
    for r in rows:
        if not r["publish_at"] and r["status"] == "pending":
            r["publish_at"] = datetime.combine(day, time(PUBLISH_HOUR), tz).isoformat()
            day += timedelta(days=1)
    return rows


def write_schedule_md(rows):
    lines = ["# Publishing schedule", "",
             f"One video a day at {PUBLISH_HOUR}:00 {TIMEZONE}. Updated automatically.", "",
             "| Date | ID | Title | Status | Video |", "|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["publish_at"] or "9999"):
        d = r["publish_at"][:10] if r["publish_at"] else "unscheduled"
        vid = f"[{r['video_id']}](https://youtu.be/{r['video_id']})" if r.get("video_id") else ""
        lines.append(f"| {d} | {r['id']} | {r['title_en']} | {r['status']} | {vid} |")
    pending = sum(r["status"] == "pending" for r in rows)
    lines += ["", f"Pending stories: **{pending}**"
              + (" ⚠️ below 10, the Generate stories workflow will top this up." if pending < MIN_PENDING else "")]
    SCHEDULE_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-date", help="YYYY-MM-DD, first publish day")
    args = ap.parse_args()
    ch = load_channel()
    if args.start_date:
        ch["start_date"] = date.fromisoformat(args.start_date).isoformat()
        CHANNEL_JSON.write_text(json.dumps(ch, indent=2) + "\n")
    rows = load_rows()
    if ch.get("start_date"):
        rows = assign_dates(rows, date.fromisoformat(ch["start_date"]))
        save_rows(rows)
    else:
        log.warning("No start date yet: run with --start-date YYYY-MM-DD")
    write_schedule_md(rows)
    log.info("Schedule written for %d stories", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
