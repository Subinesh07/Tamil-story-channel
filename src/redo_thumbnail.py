"""Make the curiosity thumbnail again for an uploaded story and set it on YouTube.

python src/redo_thumbnail.py 5      # row id
Uses a fresh AI picture when the free allowance allows, otherwise the story's own saved pictures.
"""
import logging
import sys

from config import ROOT, WORK_DIR
from image_provider import get_provider
from make_video import drama_thumbnail
from stories import load_rows
from youtube_upload import set_thumbnail

log = logging.getLogger("redo_thumbnail")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    rid = sys.argv[1]
    row = next(r for r in load_rows() if r["id"] == rid)
    if not row.get("video_id"):
        raise SystemExit(f"Row {rid} has no video on YouTube yet")
    work = (WORK_DIR / f"thumb_{rid}").resolve()
    (work / "images").mkdir(parents=True, exist_ok=True)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    path = drama_thumbnail(row, get_provider(), work, out / f"story_{rid}_thumbnail.jpg", int(rid))
    set_thumbnail(row["video_id"], path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
