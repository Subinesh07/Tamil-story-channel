"""python src/fb_backfill.py ROW_ID - post that story's Shorts (output/story_<id>_short*.mp4) as Facebook Reels."""
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import facebook  # noqa: E402
from shorts import EXTRA, extra_when  # noqa: E402

logging.basicConfig(level=logging.INFO)
ROOT = Path(__file__).resolve().parent.parent
rid = sys.argv[1]
row = next(r for r in csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")) if r["id"] == rid)
pub = datetime.fromisoformat(row["publish_at"])
from datetime import timedelta  # noqa: E402
plan = [(ROOT / "output" / f"story_{rid}_short.mp4", "", pub + timedelta(minutes=30)),
        (ROOT / "output" / f"story_{rid}_short2.mp4", EXTRA[1][0], extra_when(row["publish_at"], 1))]
for path, ending, when in plan:
    if path.exists():
        print(path.name, facebook.post_reel(path, facebook.caption_for(row, ending), when))
    else:
        print(path.name, "not in the saved files")
