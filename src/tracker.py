"""Daily progress tracker for YouTube + Facebook -> status/TRACKER.md (open it on GitHub, phone friendly).

Runs with the daily analytics job. Keeps one row per day in status/tracker.csv so the page shows the trend.
Every source is optional: if one API refuses, the rest still update.
"""
import csv
import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
STATUS = ROOT / "status"
CSV = STATUS / "tracker.csv"
PAGE = STATUS / "TRACKER.md"
FIELDS = ["date", "yt_subs", "yt_views_total", "yt_views_day", "yt_watch_hours_total", "yt_avg_view_sec",
          "yt_subs_gained_day", "fb_followers", "fb_reels", "fb_reel_plays_total"]
GOAL_SUBS, GOAL_HOURS = 1000, 4000
log = logging.getLogger("tracker")


def youtube():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"].strip(),
                        client_id=os.environ["YT_CLIENT_ID"].strip(),
                        client_secret=os.environ["YT_CLIENT_SECRET"].strip(),
                        token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    out = {}
    st = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
    out["yt_subs"], out["yt_views_total"] = int(st.get("subscriberCount", 0)), int(st.get("viewCount", 0))
    end = date.today()
    tot = ya.reports().query(ids="channel==MINE", startDate="2026-01-01", endDate=str(end),
                             metrics="estimatedMinutesWatched,averageViewDuration").execute().get("rows", [[0, 0]])[0]
    out["yt_watch_hours_total"] = round(tot[0] / 60, 1)
    out["yt_avg_view_sec"] = int(tot[1])
    # YouTube Analytics lags 1-2 days: take the latest day that has data
    days = ya.reports().query(ids="channel==MINE", startDate=str(end - timedelta(days=5)), endDate=str(end),
                              dimensions="day", metrics="views,subscribersGained").execute().get("rows", [])
    if days:
        out["yt_views_day"], out["yt_subs_gained_day"] = int(days[-1][1]), int(days[-1][2])
    return out


def studio_numbers():
    """The Studio numbers that matter, for the status page (status/analytics.json)."""
    import re
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"].strip(),
                        client_id=os.environ["YT_CLIENT_ID"].strip(),
                        client_secret=os.environ["YT_CLIENT_SECRET"].strip(),
                        token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    end = date.today()

    def q(start, **k):
        return ya.reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end), **k).execute()
    out = {"updated": str(end)}
    d = q(end - timedelta(days=30), dimensions="day",
          metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained").get("rows", [])
    out["daily"] = [{"date": r[0], "views": int(r[1]), "watch_min": int(r[2]), "avg_sec": int(r[3]),
                     "subs": int(r[4])} for r in d]
    v = q(date(2026, 1, 1), dimensions="video", sort="-views", maxResults=60,
          metrics="views,averageViewDuration,averageViewPercentage,subscribersGained,likes,comments").get("rows", [])
    info = {}
    ids = [r[0] for r in v]
    for k in range(0, len(ids), 50):
        for it in yt.videos().list(part="snippet,contentDetails", id=",".join(ids[k:k + 50])).execute().get("items", []):
            m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", it["contentDetails"]["duration"])
            secs = sum(int(x or 0) * f for x, f in zip(m.groups(), (3600, 60, 1)))
            info[it["id"]] = (it["snippet"]["title"], it["snippet"]["publishedAt"][:10], secs)
    out["videos"] = sorted([{"id": r[0], "title": info.get(r[0], ("", "", 0))[0], "published": info.get(r[0], ("", "", 0))[1],
                             "length_sec": info.get(r[0], ("", "", 0))[2], "views": int(r[1]), "avg_sec": int(r[2]),
                             "pct": round(float(r[3]), 1), "subs": int(r[4]), "likes": int(r[5]), "comments": int(r[6])}
                            for r in v if r[0] in info], key=lambda x: x["published"], reverse=True)
    t = q(end - timedelta(days=28), dimensions="insightTrafficSourceType", metrics="views,averageViewDuration").get("rows", [])
    out["traffic"] = [{"source": r[0], "views": int(r[1]), "avg_sec": int(r[2])} for r in sorted(t, key=lambda r: -r[1])]
    try:
        a = q(end - timedelta(days=90), dimensions="ageGroup,gender", metrics="viewerPercentage").get("rows", [])
        out["audience"] = [{"age": r[0], "gender": r[1], "pct": round(float(r[2]), 1)} for r in a]
    except Exception as e:
        log.info("Audience numbers unavailable: %s", str(e)[:80])
    try:
        out["retention"] = json.loads((STATUS / "retention.json").read_text())
    except Exception:
        pass
    (STATUS / "analytics.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return {}


def facebook():
    tok = os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not tok:
        return {}
    api = "https://graph.facebook.com/v21.0"
    me = requests.get(f"{api}/me", params={"access_token": tok, "fields": "id,followers_count,fan_count"},
                      timeout=30).json()
    out = {"fb_followers": me.get("followers_count", me.get("fan_count", ""))}
    reels = requests.get(f"{api}/{me['id']}/video_reels", params={"access_token": tok, "limit": 100,
                                                                  "fields": "id,created_time"}, timeout=30).json()
    plays, n = 0, 0
    for r in reels.get("data", []):
        n += 1
        ins = requests.get(f"{api}/{r['id']}/video_insights", params={"access_token": tok,
                           "metric": "blue_reels_play_count"}, timeout=30).json()
        if "error" in ins:
            log.warning("Reel insights refused: %s", str(ins["error"].get("message"))[:150])
        for m in ins.get("data", []):
            plays += int((m.get("values") or [{}])[0].get("value") or 0)
    out["fb_reels"], out["fb_reel_plays_total"] = n, plays
    return out


def bar(v, goal):
    try:
        p = min(1.0, float(v) / goal)
    except (TypeError, ValueError):
        return ""
    return "▓" * round(p * 20) + "░" * (20 - round(p * 20)) + f" {p * 100:.1f}%"


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    STATUS.mkdir(exist_ok=True)
    row = {"date": str(date.today())}
    for name, fn in (("YouTube", youtube), ("Facebook", facebook), ("Studio page", studio_numbers)):
        try:
            row.update(fn())
        except Exception as e:
            log.warning("%s numbers unavailable: %s", name, str(e)[:150])
    rows = list(csv.DictReader(open(CSV, encoding="utf-8"))) if CSV.exists() else []
    rows = [r for r in rows if r["date"] != row["date"]] + [{k: row.get(k, "") for k in FIELDS}]
    with open(CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    def delta(key, back):
        try:
            old = next(r for r in reversed(rows[:-back]) if r.get(key))
            return f"{float(rows[-1][key]) - float(old[key]):+g}"
        except (StopIteration, ValueError, KeyError, IndexError):
            return "–"
    last = rows[-1]
    exp = (STATUS / "experiment.md").read_text(encoding="utf-8") if (STATUS / "experiment.md").exists() else ""
    lines = [f"# 📈 Nila Kathaigal – progress tracker", f"_Updated {row['date']} (every day automatically)_", "",
             "## 💰 Monetisation goal (YouTube Partner Programme)",
             f"- Subscribers: **{last['yt_subs']} / {GOAL_SUBS}**  `{bar(last['yt_subs'], GOAL_SUBS)}`",
             f"- Watch hours: **{last['yt_watch_hours_total']} / {GOAL_HOURS}**  "
             f"`{bar(last['yt_watch_hours_total'], GOAL_HOURS)}`  (YouTube counts long videos only; this includes Shorts)",
             "", "## 🔁 Change", "| | last 7 days | last 28 days |", "|---|---|---|",
             f"| YouTube subscribers | {delta('yt_subs', 7)} | {delta('yt_subs', 28)} |",
             f"| YouTube total views | {delta('yt_views_total', 7)} | {delta('yt_views_total', 28)} |",
             f"| YouTube watch hours | {delta('yt_watch_hours_total', 7)} | {delta('yt_watch_hours_total', 28)} |",
             f"| Facebook followers | {delta('fb_followers', 7)} | {delta('fb_followers', 28)} |",
             f"| Facebook reel plays | {delta('fb_reel_plays_total', 7)} | {delta('fb_reel_plays_total', 28)} |",
             "", "## 📅 Day by day (latest first)",
             "| Date | YT subs | YT views that day | YT watch hrs (total) | FB followers | FB reel plays (total) |",
             "|---|---|---|---|---|---|"]
    for r in reversed(rows[-30:]):
        lines.append(f"| {r['date']} | {r['yt_subs']} | {r['yt_views_day']} | {r['yt_watch_hours_total']} | "
                     f"{r['fb_followers']} | {r['fb_reel_plays_total']} |")
    if exp:
        lines += ["", "## 🧪 Did the 26 Nov changes work?", "```", exp.strip(), "```"]
    lines += ["", "_‘YT views that day’ is YouTube’s latest finished day (Analytics runs 1–2 days behind)._"]
    PAGE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
