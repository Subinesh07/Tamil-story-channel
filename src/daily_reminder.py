"""7:05 PM IST: one checklist for today's videos (end screen, pin comment, Shorts related video).
Prints Markdown; the workflow opens it as a GitHub issue (phone notification)."""
import csv
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
IST = ZoneInfo("Asia/Kolkata")


def main():
    today = datetime.now(IST).date()
    rows = [r for r in csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8"))
            if r.get("video_id") and r.get("publish_at")
            and datetime.fromisoformat(r["publish_at"]).astimezone(IST).date() == today]
    if not rows:
        return 1
    out = [f"Today's videos – about 2 minutes in YouTube Studio. Tick each box when done.\n"]
    for r in sorted(rows, key=lambda r: r["publish_at"]):
        v = r["video_id"]
        t = datetime.fromisoformat(r["publish_at"]).astimezone(IST).strftime("%I:%M %p")
        title = r["title_ta"].split(" | ")[0]
        out.append(f"### {t} – {title}")
        out.append(f"- [ ] **End screen**: [open editor](https://studio.youtube.com/video/{v}/edit) → "
                   "End screen → Add element → **Video: Best for viewer** + **Subscribe** → Save")
        out.append(f"- [ ] **Pin the story comment**: [open video](https://youtu.be/{v}) → comments → ⋮ → Pin")
        fr = r.get("fail_reason") or ""
        shorts = [x for x in fr.replace("shorts:", "short:").replace(",", " short:").split() if x.startswith("short:")]
        for k, s in enumerate(shorts, 1):
            sid = s.split(":", 1)[1]
            if len(sid) == 11:
                out.append(f"- [ ] **Short {k} → Related video**: [open Short](https://studio.youtube.com/video/{sid}/edit) "
                           "→ Related video → pick the full video → Save")
        out.append("")
    out.append("Status page: https://subinesh07.github.io/Tamil-story-channel/status.html")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
