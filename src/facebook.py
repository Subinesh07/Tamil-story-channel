"""Post each YouTube Short as a Facebook Reel on the நிலா கதைகள் Page, at the same time it goes public on YouTube.

Needs the GitHub secret FB_PAGE_TOKEN (a Page key that never expires). The Page id is read from the key.
Never blocks a video: every error is logged and skipped.
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)
API = "https://graph.facebook.com/v21.0"


def _token():
    return os.environ.get("FB_PAGE_TOKEN", "").strip()


def available():
    return bool(_token())


def post_reel(path, caption, when=None):
    """Upload a vertical video as a Reel. when: a datetime to schedule it (at least ~10 min ahead), else now.
    Returns the Facebook video id, or None."""
    tok = _token()
    if not tok:
        return None
    try:
        page = requests.get(f"{API}/me", params={"access_token": tok}, timeout=30).json()["id"]
        start = requests.post(f"{API}/{page}/video_reels",
                              data={"upload_phase": "start", "access_token": tok}, timeout=60).json()
        vid = start["video_id"]
        data = Path(path).read_bytes()
        up = requests.post(start.get("upload_url") or f"https://rupload.facebook.com/video-upload/v21.0/{vid}",
                           headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(len(data))},
                           data=data, timeout=600)
        if not up.ok:
            raise RuntimeError(f"upload: {up.text[:200]}")
        fin = {"upload_phase": "finish", "video_id": vid, "description": caption[:2000], "access_token": tok}
        soon = datetime.now(timezone.utc) + timedelta(minutes=12)
        if when and when > soon:
            fin.update(video_state="SCHEDULED", scheduled_publish_time=str(int(when.timestamp())))
        else:
            fin["video_state"] = "PUBLISHED"
        r = None
        for attempt in range(6):          # Facebook may still be processing the upload
            r = requests.post(f"{API}/{page}/video_reels", data=fin, timeout=60)
            if r.ok and r.json().get("success", True):
                break
            time.sleep(20)
        if not (r is not None and r.ok):
            raise RuntimeError(f"finish: {r.text[:300] if r is not None else ''}")
        log.info("Facebook Reel %s %s", vid, f"scheduled for {when.isoformat()}" if "scheduled_publish_time" in fin
                 else "published")
        return vid
    except Exception as e:
        log.warning("Facebook Reel failed: %s", str(e)[:300])
        return None


def caption_for(row, ending=""):
    head = row["title_ta"].split(" | ")[0].strip()
    return (f"{head}{ending}\n\nமுழு கதை YouTube-ல: நிலா கதைகள் 🌙\n"
            "#நிலாகதைகள் #TamilStory #தமிழ்கதைகள் #Reels")
