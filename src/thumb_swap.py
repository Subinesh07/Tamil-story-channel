"""Automatic thumbnail swap (free): a long video 2-7 days old with clearly fewer views than our
average gets ONE new thumbnail - a different story picture and a different layout. No AI pictures.

python src/thumb_swap.py            # check and swap
python src/thumb_swap.py --dry-run  # only report
"""
import csv
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import ROOT  # noqa: E402

log = logging.getLogger("thumb_swap")
WORK = ROOT / "output" / "swap"
RATIO = 0.5          # "clearly below": under half the average
MIN_AGE, MAX_AGE = timedelta(hours=48), timedelta(days=7)


def pictures(rid):
    """Story pictures: kept copies in the 'videos' release, else the restored picture cache."""
    WORK.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gh", "release", "download", "videos", "-p", f"row{rid}_pic*.png", "-D", str(WORK),
                    "--clobber"], capture_output=True)
    pics = sorted(WORK.glob(f"row{rid}_pic*.png"))
    return pics or sorted((ROOT / "cache" / "images" / f"row_{rid}").glob("*.png"))


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    dry = "--dry-run" in sys.argv
    rows = list(csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")))
    now = datetime.now(timezone.utc)
    longs = [r for r in rows if r.get("status") == "done" and r.get("video_id") and r.get("publish_at")
             and now - datetime.fromisoformat(r["publish_at"]) >= MIN_AGE]
    if len(longs) < 3:
        log.info("Not enough videos older than 2 days to compare yet")
        return 0
    from competitors import client
    yt = client()
    views = {}
    ids = [r["video_id"] for r in longs]
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="statistics", id=",".join(ids[i:i + 50])).execute().get("items", []):
            views[v["id"]] = int(v["statistics"].get("viewCount", 0))
    for r in longs:
        age = now - datetime.fromisoformat(r["publish_at"])
        if age > MAX_AGE or "thumbswap" in (r.get("fail_reason") or "") or r["video_id"] not in views:
            continue
        others = [views[x["video_id"]] for x in longs if x is not r and x["video_id"] in views]
        avg = sum(others) / len(others)
        mine = views[r["video_id"]]
        log.info("Row %s: %d views vs average %.0f", r["id"], mine, avg)
        if mine >= RATIO * avg:
            continue
        pics = pictures(r["id"])
        if not pics:
            log.warning("Row %s: no saved story pictures, cannot swap", r["id"])
            continue
        if dry:
            log.info("Row %s would get a new thumbnail", r["id"])
            continue
        import thumb_v2
        from youtube_upload import set_thumbnail
        try:
            texts = json.loads(r.get("thumb_text") or "{}")
        except ValueError:
            texts = {}
        if not texts.get("line1"):
            texts = {"line1": r.get("thumb_quote_ta", ""), "line2": r.get("thumb_hook_ta", "")}
        n = int(r["id"])
        pic = pics[(len(pics) // 2 + 1) % len(pics)] if len(pics) > 1 else pics[0]   # not the original middle one
        out = WORK / f"story_{r['id']}_thumb_b.jpg"
        thumb_v2.make(pic, texts, out, genre=r.get("genre", ""), variant=n + 1, part=r.get("part") or "")
        set_thumbnail(r["video_id"], out)
        from stories import update_row
        update_row(r["id"], fail_reason=f"{r.get('fail_reason', '')} thumbswap".strip())
        try:
            import status as ST
            ST.event(f"Row {r['id']}: new thumbnail tried ({mine} views vs average {avg:.0f})")
        except Exception:
            pass
        log.info("Row %s: new thumbnail set", r["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
