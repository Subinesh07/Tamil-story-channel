"""Channel helpers that need the full YouTube permission:
- add a new video to its series playlist (creates the playlist the first time)
- post the story comment (YouTube does not allow pinning by API - pin it by hand)
- daily analytics report (watch hours, retention, progress to 4,000 hours)

Every function here is safe: errors are logged, never fail a video.
"""
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
log = logging.getLogger(__name__)
PLAYLIST_FILE = ROOT / "playlists.json"
GENRE_PLAYLIST = {"family emotional": "தமிழ் குடும்ப கதைகள்", "family moral": "தமிழ் குடும்ப கதைகள்"}


def _yt():
    from competitors import client
    return client()


def _load():
    try:
        return json.loads(PLAYLIST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _playlist_name(row):
    if row.get("series_id"):
        try:
            data = json.loads((ROOT / "series.json").read_text(encoding="utf-8"))
            for s in data["series"]:
                if s["id"] == row["series_id"]:
                    return s["title_ta"]
        except Exception:
            pass
    return GENRE_PLAYLIST.get(row.get("genre"), "நிலா கதைகள்")


def _find_or_create(yt, name, known):
    if name in known:
        return known[name]
    req = yt.playlists().list(part="snippet", mine=True, maxResults=50)
    while req:
        res = req.execute()
        for p in res.get("items", []):
            if p["snippet"]["title"].strip() == name.strip():
                known[name] = p["id"]
                return p["id"]
        req = yt.playlists().list_next(req, res)
    p = yt.playlists().insert(part="snippet,status", body={
        "snippet": {"title": name[:150], "description": f"{name} – நிலா கதைகள். எல்லா பகுதிகளும் வரிசையா."},
        "status": {"privacyStatus": "public"}}).execute()
    log.info("Created playlist %s (%s)", name, p["id"])
    known[name] = p["id"]
    return p["id"]


def add_to_playlist(row, video_id):
    try:
        yt, known = _yt(), _load()
        name = _playlist_name(row)
        import time
        fresh = name not in known
        pid = _find_or_create(yt, name, known)
        if not fresh:
            try:
                items = yt.playlistItems().list(part="contentDetails", playlistId=pid, maxResults=50).execute()
                if any(i["contentDetails"]["videoId"] == video_id for i in items.get("items", [])):
                    return pid
            except Exception:
                pass
        for attempt in range(4):   # a brand-new playlist needs a few seconds before it can be used
            try:
                yt.playlistItems().insert(part="snippet", body={"snippet": {
                    "playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(15)
        PLAYLIST_FILE.write_text(json.dumps(known, ensure_ascii=False, indent=1), encoding="utf-8")
        log.info("Added %s to playlist %s", video_id, name)
        return pid
    except Exception as e:
        log.warning("Playlist add failed: %s", str(e)[:200])


def next_part_line(row):
    """'Next part tomorrow 8:30 PM' when it is already planned; never 'coming soon' for a finished story."""
    import csv
    from datetime import datetime
    if not row.get("series_id"):
        return "தினமும் ஒரு புது கதை – Subscribe பண்ணி 🔔 அழுத்துங்க!"
    try:
        rows = list(csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")))
        later = sorted((r for r in rows if r.get("series_id") == row["series_id"]
                        and r.get("publish_at", "") > row.get("publish_at", "")
                        and r.get("status") not in ("parked",)), key=lambda r: r["publish_at"])
        if later:
            t = datetime.fromisoformat(later[0]["publish_at"])
            days = (t.date() - datetime.fromisoformat(row["publish_at"]).date()).days
            when = "நாளைக்கு" if days == 1 else t.strftime("%d/%m")
            hm = t.strftime("%I:%M").lstrip("0").replace(":00", "")
            part_of_day = ("காலை" if t.hour < 12 else "மதியம்" if t.hour < 16 else "மாலை" if t.hour < 19 else "இரவு")
            return f"⏰ பகுதி {later[0].get('part', '')} – {when} {part_of_day} {hm} மணிக்கு! Subscribe பண்ணி 🔔 அழுத்துங்க"
        import series as S
        ser = next((x for x in S.load()["series"] if x["id"] == row["series_id"]), {})
        if str(row.get("part")) == str(ser.get("parts_total")):
            return "🙏 இது தான் கடைசி பகுதி – முழு கதை பிடிச்சிருந்தா Share பண்ணுங்க!"
    except Exception as e:
        log.info("Next-part line: %s", str(e)[:100])
    return "அடுத்த பகுதி சீக்கிரம் வருது – Subscribe பண்ணி 🔔 அழுத்துங்க!"


def post_comment(row, video_id, poll_q=None):
    """Top comment with a question to start discussion. Pin it by hand (API cannot pin)."""
    try:
        q = (poll_q or "").replace("🗳️", "").strip() or "இந்த கதையில உங்களுக்கு பிடிச்ச இடம் எது?"
        nxt = next_part_line(row)
        text = f"💬 {q}\nகமெண்ட்ல சொல்லுங்க 👇\n\n{nxt}\n🌙 நிலா கதைகள்"
        c = _yt().commentThreads().insert(part="snippet", body={"snippet": {
            "videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}}).execute()
        log.info("Posted comment %s on %s", c["id"], video_id)
        return c["id"]
    except Exception as e:
        log.warning("Comment post failed: %s", str(e)[:200])
        if "403" in str(e) or "insufficient" in str(e).lower():   # video still private: retry after it goes public
            pend = _pending()
            pend[video_id] = {"row": row.get("id"), "poll": poll_q}
            _save_pending(pend)
            log.info("Comment queued until %s is public", video_id)


PENDING = ROOT / "status" / "pending_comments.json"


def _pending():
    try:
        return json.loads(PENDING.read_text())
    except Exception:
        return {}


def _save_pending(d):
    PENDING.parent.mkdir(exist_ok=True)
    PENDING.write_text(json.dumps(d, ensure_ascii=False, indent=1))


def retry_pending_comments(rows=None):
    """Post comments that failed while the video was private (runs hourly with produce + daily analytics)."""
    pend = _pending()
    if not pend:
        return
    try:
        import csv
        rows = rows or list(csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")))
        st = {i["id"]: i["status"]["privacyStatus"] for i in
              _yt().videos().list(part="status", id=",".join(pend)).execute().get("items", [])}
    except Exception as e:
        log.warning("Pending comments check failed: %s", str(e)[:120])
        return
    for vid in list(pend):
        if vid not in st:          # video deleted: drop it
            pend.pop(vid)
        elif st[vid] == "public":
            item = pend.pop(vid)
            _save_pending(pend)   # saved first, so a second failure can't loop forever
            row = next((r for r in rows if r["id"] == str(item["row"])), {"id": item["row"]})
            post_comment(row, vid, item.get("poll"))
    _save_pending(pend)


def analytics_report(days=28):
    """Prints and returns a short report. Needs the yt-analytics.readonly permission."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    import os
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"].strip(),
                        client_id=os.environ["YT_CLIENT_ID"].strip(),
                        client_secret=os.environ["YT_CLIENT_SECRET"].strip(),
                        token_uri="https://oauth2.googleapis.com/token")
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    end, start = date.today(), date(2026, 1, 1)
    q = lambda **k: ya.reports().query(ids="channel==MINE", startDate=str(k.pop("s", start)),
                                       endDate=str(end), **k).execute()
    tot = q(metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost")
    v, mins, avd, sg, sl = (tot.get("rows") or [[0, 0, 0, 0, 0]])[0]
    hours = mins / 60
    recent = q(s=end - timedelta(days=days), metrics="estimatedMinutesWatched")
    r_hours = ((recent.get("rows") or [[0]])[0][0]) / 60
    lines = [f"⏱️ Watch hours (all time): {hours:.1f} / 4000  ({hours / 40:.1f}%)",
             f"⏱️ Watch hours (last {days} days, what YouTube counts): {r_hours:.1f}",
             f"👀 Views: {v} | average view time {int(avd) // 60}:{int(avd) % 60:02d}",
             f"👥 Subscribers gained {sg}, lost {sl}"]
    per = q(dimensions="video", metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
            sort="-views", maxResults=15)
    ids = [r[0] for r in per.get("rows", [])]
    titles = {}
    if ids:
        for it in _yt().videos().list(part="snippet", id=",".join(ids)).execute().get("items", []):
            titles[it["id"]] = it["snippet"]["title"][:45]
    lines.append("\n📺 Per video: views | watch h | avg view | % watched")
    for vid, vv, m, a, p in per.get("rows", []):
        lines.append(f"  {titles.get(vid, vid)} | {vv} | {m / 60:.1f}h | {int(a) // 60}:{int(a) % 60:02d} | {p:.0f}%")
    # where viewers leave, for the 3 most viewed long videos
    lines.append("\n📉 Viewers still watching at 10% / 25% / 50% / 75% of the video:")
    curve = []
    for vid in ids[:3]:
        try:
            rr = q(dimensions="elapsedVideoTimeRatio", metrics="audienceWatchRatio",
                   filters=f"video=={vid}").get("rows", [])
            pts = {round(x, 2): y for x, y in rr}
            pick = [pts.get(k) for k in (0.1, 0.25, 0.5, 0.75)]
            if all(y is not None for y in pick):
                curve.append(pick)
            lines.append(f"  {titles.get(vid, vid)}: " + " / ".join(f"{y * 100:.0f}%" if y is not None else "-" for y in pick))
        except Exception as e:
            lines.append(f"  {vid}: retention not available yet ({str(e)[:60]})")
    if curve:   # saved for the story writer: it adapts the opening / middle to where viewers leave
        avg = [sum(c[k] for c in curve) / len(curve) for k in range(4)]
        (ROOT / "status").mkdir(exist_ok=True)
        (ROOT / "status" / "retention.json").write_text(json.dumps(
            {"date": str(end), "at_10": avg[0], "at_25": avg[1], "at_50": avg[2], "at_75": avg[3]}), encoding="utf-8")
    src = q(s=end - timedelta(days=days), dimensions="insightTrafficSourceType", metrics="views", sort="-views")
    lines.append("\n🚦 Where views come from (last %d days): " % days +
                 ", ".join(f"{a} {b}" for a, b in (src.get("rows") or [])[:6]))
    try:
        lines.append(experiment_check(q))
    except Exception as e:
        lines.append(f"\n🧪 Experiment check not available yet ({str(e)[:80]})")
    report = "\n".join(lines)
    print(report)
    try:
        (ROOT / "status").mkdir(exist_ok=True)
        (ROOT / "status" / "analytics.txt").write_text(f"Updated {end}\n\n{report}\n", encoding="utf-8")
    except Exception:
        pass
    return report


def experiment_check(q):
    """Did the 26 Nov changes work? (longer horror, Tamil+English titles, face thumbnails)
    Compares long videos published before vs after EXPERIMENT_START, each judged on its first days.
    Saves status/experiment.md."""
    import re as _re
    from datetime import datetime as _dt
    from config import EXPERIMENT_START
    rows = q(s=date(2026, 1, 1), dimensions="video", sort="-views", maxResults=200,
             metrics="views,averageViewDuration,averageViewPercentage,subscribersGained").get("rows", [])
    stats = {r[0]: r[1:] for r in rows}
    yt, info = _yt(), {}
    ids = list(stats)
    for k in range(0, len(ids), 50):
        for it in yt.videos().list(part="snippet,contentDetails", id=",".join(ids[k:k + 50])).execute().get("items", []):
            m = _re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", it["contentDetails"]["duration"])
            secs = sum(int(x or 0) * f for x, f in zip(m.groups(), (3600, 60, 1)))
            info[it["id"]] = (it["snippet"]["publishedAt"][:10], secs)
    today = str(date.today())
    groups = {"before": [], "after": []}
    for vid, (pub, secs) in info.items():
        if secs < 180 or (date.fromisoformat(today) - date.fromisoformat(pub)).days < 2:
            continue   # Shorts, and videos younger than 2 days, are not compared
        groups["after" if pub >= EXPERIMENT_START else "before"].append(stats[vid])
    def avg(g, i):
        return sum(x[i] for x in g) / len(g) if g else 0
    out = [f"\n🧪 Experiment since {EXPERIMENT_START} (longer horror, Tamil+English titles, face thumbnails)",
           "   long videos | avg views | avg view time | % watched | subs gained per video"]
    for name, g in groups.items():
        out.append(f"   {name:6} {len(g):3} | {avg(g, 0):7.0f} | {int(avg(g, 1)) // 60}:{int(avg(g, 1)) % 60:02d} | "
                   f"{avg(g, 2):4.0f}% | {avg(g, 3):.1f}")
    b, a = groups["before"], groups["after"]
    if len(a) < 4:
        out.append(f"   Verdict: waiting ({len(a)}/4 new videos old enough to judge).")
    else:
        # recent 'before' videos only: older ones had months to collect views
        b = b[-10:] if b else b
        better = [n for n, i in (("views", 0), ("view time", 1), ("subs", 3)) if avg(a, i) > avg(b, i) * 1.15]
        worse = [n for n, i in (("views", 0), ("view time", 1), ("subs", 3)) if avg(a, i) < avg(b, i) * 0.85]
        out.append("   Verdict: " + ("✅ WORKING: better " + ", ".join(better) if better and not worse else
                                     "❌ NOT WORKING: worse " + ", ".join(worse) if worse and not better else
                                     "➖ mixed/no clear change: better " + (", ".join(better) or "nothing") +
                                     "; worse " + (", ".join(worse) or "nothing")))
    text = "\n".join(out)
    (ROOT / "status").mkdir(exist_ok=True)
    (ROOT / "status" / "experiment.md").write_text(f"Updated {today}\n{text}\n", encoding="utf-8")
    return text


def review_before_apply(subs_goal=800, hours_goal=3000):
    """Once the channel nears monetization: list weak videos to consider making private before applying.
    Writes status/apply_review.md once (the workflow turns it into a GitHub issue)."""
    import os
    flag = ROOT / "status" / "apply_review_sent"
    if flag.exists():
        return
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"].strip(),
                        client_id=os.environ["YT_CLIENT_ID"].strip(),
                        client_secret=os.environ["YT_CLIENT_SECRET"].strip(),
                        token_uri="https://oauth2.googleapis.com/token")
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    end = date.today()
    subs = int(_yt().channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]["subscriberCount"])
    tot = ya.reports().query(ids="channel==MINE", startDate=str(end - timedelta(days=365)), endDate=str(end),
                             metrics="estimatedMinutesWatched").execute()
    hours = ((tot.get("rows") or [[0]])[0][0]) / 60
    if subs < subs_goal and hours < hours_goal:
        return
    per = ya.reports().query(ids="channel==MINE", startDate=str(end - timedelta(days=365)), endDate=str(end),
                             dimensions="video", metrics="views,estimatedMinutesWatched,averageViewPercentage",
                             sort="averageViewPercentage", maxResults=50).execute().get("rows", [])
    weak = [r for r in per if r[3] < 15]
    titles = {}
    for i in range(0, len(weak), 50):
        ids = ",".join(r[0] for r in weak[i:i + 50])
        if ids:
            for it in _yt().videos().list(part="snippet", id=ids).execute().get("items", []):
                titles[it["id"]] = it["snippet"]["title"][:60]
    lines = [f"The channel is close to monetization ({subs} subscribers, {hours:.0f} public watch hours).",
             "Before you apply, consider making these weak videos **private** (Studio → Content → Visibility).",
             "",
             "⚠️ Only PUBLIC videos' watch hours count. Making a video private removes its hours - "
             "only hide a video if you still have enough hours without it.", "",
             "| Video | Views | Watch hours | % watched |", "|---|---|---|---|"]
    for vid, v, m, p in weak:
        lines.append(f"| [{titles.get(vid, vid)}](https://studio.youtube.com/video/{vid}/edit) | {v} | {m / 60:.1f} | {p:.0f}% |")
    if not weak:
        lines.append("| (no weak videos – nothing needs hiding) | | | |")
    (ROOT / "status").mkdir(exist_ok=True)
    (ROOT / "status" / "apply_review.md").write_text("\n".join(lines), encoding="utf-8")
    flag.write_text(str(end), encoding="utf-8")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    retry_pending_comments()
    if len(sys.argv) > 2 and sys.argv[1] == "fixnext":   # refresh the "next part" line in a video's description
        import csv
        rid = sys.argv[2]
        row = next(r for r in csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")) if r["id"] == rid)
        yt = _yt()
        it = yt.videos().list(part="snippet", id=row["video_id"]).execute()["items"][0]
        sn = it["snippet"]
        lines = [x for x in sn["description"].split("\n") if not x.startswith("⏰ பகுதி")]
        i = next((k for k, x in enumerate(lines) if "WhatsApp" in x), 0)
        lines.insert(i + 1, next_part_line(row))
        sn["description"] = "\n".join(lines)
        yt.videos().update(part="snippet", body={"id": row["video_id"], "snippet": {
            k: sn[k] for k in ("title", "description", "categoryId", "tags", "defaultLanguage") if k in sn}}).execute()
        print("FIXED", row["video_id"], next_part_line(row))
        sys.exit(0)
    if len(sys.argv) > 3 and sys.argv[1] == "postponevid":
        _yt().videos().update(part="status", body={"id": sys.argv[2], "status": {
            "privacyStatus": "private", "publishAt": sys.argv[3], "selfDeclaredMadeForKids": False}}).execute()
        print("POSTPONED", sys.argv[2], sys.argv[3])
        sys.exit(0)
    if len(sys.argv) > 3 and sys.argv[1] == "postpone":   # move a scheduled (private) video to a later time
        import csv
        row = next(r for r in csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")) if r["id"] == sys.argv[2])
        _yt().videos().update(part="status", body={"id": row["video_id"], "status": {
            "privacyStatus": "private", "publishAt": sys.argv[3], "selfDeclaredMadeForKids": False}}).execute()
        print("POSTPONED", row["video_id"], sys.argv[3])
        sys.exit(0)
    if len(sys.argv) > 2 and sys.argv[1] == "setthumb":   # put assets/thumbs/row_<id>.jpg on that row's video
        import csv
        from googleapiclient.http import MediaFileUpload
        rid = sys.argv[2]
        row = next(r for r in csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")) if r["id"] == rid)
        f = ROOT / "assets" / "thumbs" / f"row_{rid}.jpg"
        _yt().thumbnails().set(videoId=row["video_id"], media_body=MediaFileUpload(str(f), mimetype="image/jpeg")).execute()
        print("THUMB SET", row["video_id"], f.name)
        sys.exit(0)
    if len(sys.argv) > 2 and sys.argv[1] == "stats":   # quick live numbers for given video ids
        for it in _yt().videos().list(part="statistics,snippet,contentDetails", id=sys.argv[2]).execute()["items"]:
            st = it["statistics"]
            print(f"STATS {it['id']} | {it['contentDetails']['duration']} | views {st.get('viewCount')} | "
                  f"likes {st.get('likeCount')} | comments {st.get('commentCount')} | {it['snippet']['title'][:60]}")
        sys.exit(0)
    if len(sys.argv) > 2 and sys.argv[1] == "comment":
        import csv
        for row in csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")):
            if row["id"] in sys.argv[2].split(",") and row.get("video_id"):
                print("comment:", post_comment(row, row["video_id"], row.get("quiz_q") or None))
    elif len(sys.argv) > 2 and sys.argv[1] == "add":
        import csv
        for row in csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")):
            if row["id"] in sys.argv[2].split(",") and row.get("video_id"):
                add_to_playlist(row, row["video_id"])
    elif len(sys.argv) > 1 and sys.argv[1] == "backfill":
        # add every uploaded long video to its playlist
        import csv
        for row in csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")):
            if row.get("video_id") and row.get("status") == "done":
                add_to_playlist(row, row["video_id"])
    else:
        analytics_report()
        try:
            review_before_apply()
        except Exception as e:
            log.warning("Apply review skipped: %s", str(e)[:150])
