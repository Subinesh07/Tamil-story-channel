"""Phase 6: upload as a private video with a scheduled publish time."""
import logging
import os
import re
from datetime import datetime, timezone

from config import CHANNEL_NAME_EN, CHANNEL_NAME_TA, DISCLOSURE_LINE, HASHTAGS, YT_CATEGORY_ID

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def build_metadata(row):
    title = row["title_ta"].strip()[:100]
    script = re.sub(r"\d+\.\s*", "", row["script_ta"]).replace("।", ".").strip()
    intro = (row.get("description_ta") or "").strip() or f"{script[:200].rstrip()}…"
    description = (f"{intro}\n\n{CHANNEL_NAME_TA} ({CHANNEL_NAME_EN}) - தினமும் மாலை 7 மணிக்கு ஒரு புது கதை.\n"
                   f"{DISCLOSURE_LINE}\n\n{HASHTAGS}")
    publish = datetime.fromisoformat(row["publish_at"]) if row.get("publish_at") else None
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": True}
    if publish and publish > datetime.now(timezone.utc):
        status["publishAt"] = publish.isoformat()
    else:
        log.warning("No future publish_at (%s); uploading as private without a schedule",
                    row.get("publish_at") or "empty")
    return {
        "snippet": {"title": title, "description": description, "categoryId": YT_CATEGORY_ID,
                    "defaultLanguage": "ta", "defaultAudioLanguage": "ta",
                    "tags": ["Tamil story", "Tamil family story", "Tamil emotional story"]},
        "status": status,
    }


def upload(video_path, row):
    from googleapiclient.http import MediaFileUpload
    yt = _client()
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=16 * 1024 * 1024,
                            resumable=True)
    req = yt.videos().insert(part="snippet,status", body=build_metadata(row), media_body=media)
    response = None
    while response is None:
        status, response = req.next_chunk(num_retries=5)
        if status:
            log.info("Upload %d%%", int(status.progress() * 100))
    log.info("Uploaded video id %s", response["id"])
    return response["id"]


def set_thumbnail(video_id, jpg_path):
    """Custom thumbnails need a phone-verified channel; failure is only a warning."""
    from googleapiclient.http import MediaFileUpload
    try:
        _client().thumbnails().set(videoId=video_id,
                                   media_body=MediaFileUpload(str(jpg_path), mimetype="image/jpeg")
                                   ).execute()
        log.info("Thumbnail set")
    except Exception as e:
        log.warning("Thumbnail not set (verify the channel at youtube.com/verify): %s", str(e)[:200])
