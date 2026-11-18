"""Phase 6: upload as a private video with a scheduled publish time."""
import logging
import os
from datetime import datetime, timezone

from config import DISCLOSURE_LINE, HASHTAGS, YT_CATEGORY_ID

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
    script = row["script_ta"].replace("।", ". ").replace("  ", " ").strip()
    description = f"{script[:200].rstrip()}…\n\n{DISCLOSURE_LINE}\n\n{HASHTAGS}"
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
