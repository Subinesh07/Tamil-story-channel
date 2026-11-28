"""Whole-channel research (lifetime): where viewers drop, per video and on average.

python src/research.py  ->  status/research.json + a printed summary.
Uses the YouTube Analytics API with the channel's own login (GitHub secrets).
"""
import json
import logging
import os
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("research")


def clients():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"].strip(),
                        client_id=os.environ["YT_CLIENT_ID"].strip(),
                        client_secret=os.environ["YT_CLIENT_SECRET"].strip(),
                        token_uri="https://oauth2.googleapis.com/token")
    return (build("youtube", "v3", credentials=creds, cache_discovery=False),
            build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False))


def secs(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 0


def main():
    yt, ya = clients()
    start, end = "2026-01-01", str(date.today())

    def q(**k):
        return ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, **k).execute()

    rows = q(dimensions="video", sort="-views", maxResults=200,
             metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                     "subscribersGained,likes,comments,shares").get("rows", [])
    ids = [r[0] for r in rows]
    meta = {}
    for i in range(0, len(ids), 50):
        for it in yt.videos().list(part="snippet,contentDetails", id=",".join(ids[i:i + 50])).execute()["items"]:
            meta[it["id"]] = {"title": it["snippet"]["title"], "published": it["snippet"]["publishedAt"][:16],
                              "len": secs(it["contentDetails"]["duration"])}
    ctr = {}
    try:
        for r in q(dimensions="video", maxResults=200,
                   metrics="videoThumbnailImpressions,videoThumbnailImpressionsClickRate").get("rows", []):
            ctr[r[0]] = (int(r[1]), round(float(r[2]), 2))
    except Exception as e:
        log.info("CTR not available from the API: %s", str(e)[:100])

    videos, curves = [], {}
    for r in rows:
        vid = r[0]
        m = meta.get(vid, {"title": "?", "published": "", "len": 0})
        v = {"id": vid, **m, "views": int(r[1]), "watch_min": int(r[2]), "avg_sec": int(r[3]),
             "avg_pct": round(float(r[4]), 1), "subs": int(r[5]), "likes": int(r[6]), "comments": int(r[7]),
             "shares": int(r[8]), "short": m["len"] <= 70,
             "impressions": ctr.get(vid, (None, None))[0], "ctr": ctr.get(vid, (None, None))[1]}
        if not v["short"] and v["views"] >= 10:
            try:
                c = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end,
                                       dimensions="elapsedVideoTimeRatio", filters=f"video=={vid}",
                                       metrics="audienceWatchRatio,relativeRetentionPerformance").execute()
                curves[vid] = [(float(x[0]), float(x[1]), float(x[2])) for x in c.get("rows", [])]
                pts = curves[vid]

                def at(sec):
                    if not pts or not m["len"]:
                        return None
                    ratio = sec / m["len"]
                    best = min(pts, key=lambda p: abs(p[0] - ratio))
                    return round(best[1] * 100)
                v["kept"] = {f"{s}s": at(s) for s in (10, 20, 30, 45, 60, 90, 120, 180, 300)}
                v["kept"]["end"] = round(pts[-1][1] * 100) if pts else None
                v["vs_similar"] = round(sum(p[2] for p in pts) / len(pts), 2) if pts else None
                drops = sorted(((pts[i - 1][1] - pts[i][1], pts[i][0]) for i in range(1, len(pts))), reverse=True)[:3]
                v["biggest_drops_at_sec"] = [round(r_ * m["len"]) for _, r_ in drops]
            except Exception as e:
                log.info("Retention failed for %s: %s", vid, str(e)[:100])
        try:
            t = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end,
                                   dimensions="insightTrafficSourceType", filters=f"video=={vid}",
                                   metrics="views").execute().get("rows", [])
            v["traffic"] = {x[0]: int(x[1]) for x in t}
        except Exception:
            pass
        videos.append(v)

    # channel-wide: view-weighted share still watching at fixed seconds (long videos)
    longs = [v for v in videos if v.get("kept")]
    tot = sum(v["views"] for v in longs) or 1
    avg = {}
    for k in ("10s", "20s", "30s", "45s", "60s", "90s", "120s", "180s", "300s", "end"):
        have = [(v["kept"][k], v["views"]) for v in longs if v["kept"].get(k) is not None]
        w = sum(n for _, n in have) or 1
        avg[k] = round(sum(p * n for p, n in have) / w)
    hours = q(dimensions="day", metrics="views").get("rows", [])
    weekday = {}
    for d, n in hours:
        wd = date.fromisoformat(d).strftime("%a")
        weekday[wd] = weekday.get(wd, 0) + int(n)
    out = {"updated": end, "videos": videos, "channel_kept": avg, "views_by_weekday": weekday,
           "long_views": tot}
    try:
        out["age_gender"] = q(dimensions="ageGroup,gender", metrics="viewerPercentage").get("rows", [])
        out["traffic"] = q(dimensions="insightTrafficSourceType", metrics="views,averageViewDuration").get("rows", [])
        out["devices"] = q(dimensions="deviceType", metrics="views,averageViewDuration").get("rows", [])
        out["subscribed"] = q(dimensions="subscribedStatus", metrics="views,averageViewDuration").get("rows", [])
    except Exception as e:
        log.info("Audience breakdown failed: %s", str(e)[:100])
    (ROOT / "status").mkdir(exist_ok=True)
    (ROOT / "status" / "research.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("CHANNEL KEPT (long videos, view-weighted):", avg)
    for v in videos:
        print("VID", json.dumps(v, ensure_ascii=False))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
