"""Approve a video that was held for review: schedule it (and its Shorts) at their planned times.
python src/approve.py ROW_ID"""
import csv
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from competitors import client  # noqa: E402
from shorts import extra_when  # noqa: E402
from stories import update_row  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
rid = sys.argv[1]
row = next(r for r in csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")) if r["id"] == rid)
yt = client()
pub = datetime.fromisoformat(row["publish_at"])
soon = datetime.now(timezone.utc) + timedelta(minutes=15)
plan = [(row["video_id"], max(pub, soon))]
fr = row.get("fail_reason") or ""
m = re.search(r"short:([\w-]{11})", fr)
if m:
    plan.append((m.group(1), max(pub + timedelta(minutes=30), soon)))
m = re.search(r"shorts:([\w-]{11}(?:,[\w-]{11})*)", fr)
if m:
    for k, sid in enumerate(m.group(1).split(","), 1):
        plan.append((sid, max(extra_when(row["publish_at"], k).astimezone(timezone.utc), soon)))
for vid, when in plan:
    yt.videos().update(part="status", body={"id": vid, "status": {
        "privacyStatus": "private", "publishAt": when.isoformat().replace("+00:00", "Z"),
        "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}).execute()
    print(f"{vid}: scheduled for {when.astimezone().isoformat()}")
update_row(rid, fail_reason=fr.replace(" hold", "").replace("hold", "").strip())
