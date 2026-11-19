"""Weekly competitor analysis for Nila Kathaigal.

Looks at similar Tamil story channels (the ones listed in competitors.txt plus channels found
by search), compares them with our channel, and writes reports/competitors-YYYY-MM-DD.md with
practical suggestions. Needs the YouTube token to include the youtube.readonly permission.

python src/competitors.py
"""
import logging
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config import ROOT, TIMEZONE

log = logging.getLogger("competitors")
SEARCHES = ["tamil story", "tamil family story", "தமிழ் கதைகள்", "tamil kathaigal audio story"]
LIST_FILE = ROOT / "competitors.txt"
REPORT_DIR = ROOT / "reports"
IST = ZoneInfo(TIMEZONE)


def client():
    import os

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"].strip(),
                        client_id=os.environ["YT_CLIENT_ID"].strip(),
                        client_secret=os.environ["YT_CLIENT_SECRET"].strip(),
                        token_uri="https://oauth2.googleapis.com/token")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def iso_minutes(d):
    m = re.fullmatch(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0.0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 60 + mi + s / 60


def resolve(yt, entry):
    """Accept a channel ID, @handle, or a youtube.com URL containing either."""
    entry = entry.strip()
    m = re.search(r"(UC[\w-]{22})", entry)
    if m:
        return m.group(1)
    m = re.search(r"@([\w.\-]+)", entry)
    handle = m.group(1) if m else entry.lstrip("@")
    r = yt.channels().list(part="id", forHandle=handle).execute()
    items = r.get("items", [])
    return items[0]["id"] if items else None


def discover(yt, limit=8):
    found = Counter()
    for q in SEARCHES:
        r = yt.search().list(part="snippet", q=q, type="channel", regionCode="IN",
                             relevanceLanguage="ta", maxResults=10).execute()
        for it in r.get("items", []):
            found[it["snippet"]["channelId"]] += 1
    return [c for c, _ in found.most_common(limit * 2)]


def channel_report(yt, cid, n_videos=15):
    ch = yt.channels().list(part="snippet,statistics,contentDetails", id=cid).execute()["items"]
    if not ch:
        return None
    ch = ch[0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt.playlistItems().list(part="contentDetails", playlistId=uploads,
                                    maxResults=n_videos).execute().get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in items]
    vids = yt.videos().list(part="snippet,statistics,contentDetails",
                            id=",".join(ids)).execute().get("items", []) if ids else []
    now = datetime.now(timezone.utc)
    rows = []
    for v in vids:
        pub = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
        views = int(v["statistics"].get("viewCount", 0))
        days = max(1.0, (now - pub).total_seconds() / 86400)
        rows.append({"title": v["snippet"]["title"], "views": views, "per_day": views / days,
                     "minutes": iso_minutes(v["contentDetails"]["duration"]),
                     "hour": pub.astimezone(IST).hour, "pub": pub,
                     "likes": int(v["statistics"].get("likeCount", 0)),
                     "comments": int(v["statistics"].get("commentCount", 0)), "id": v["id"]})
    span_days = ((max(r["pub"] for r in rows) - min(r["pub"] for r in rows)).days or 1) if len(rows) > 1 else 7
    return {
        "id": cid, "name": ch["snippet"]["title"],
        "subs": int(ch["statistics"].get("subscriberCount", 0) or 0),
        "total_views": int(ch["statistics"].get("viewCount", 0)),
        "videos": rows,
        "median_views": statistics.median([r["views"] for r in rows]) if rows else 0,
        "per_week": round(len(rows) / span_days * 7, 1) if rows else 0,
        "avg_minutes": round(statistics.mean([r["minutes"] for r in rows]), 1) if rows else 0,
        "top_hour": Counter(r["hour"] for r in rows).most_common(1)[0][0] if rows else None,
        "engagement": round(100 * sum(r["likes"] + r["comments"] for r in rows) /
                            max(1, sum(r["views"] for r in rows)), 2),
    }


def suggestions(ours, others):
    tips = []
    if not others:
        return ["No competitor data yet."]
    hours = Counter(o["top_hour"] for o in others if o["top_hour"] is not None)
    if hours:
        h = hours.most_common(1)[0][0]
        tips.append(f"Most competitors publish around **{h}:00 IST**; we publish at 19:00. "
                    + ("Keep it." if abs(h - 19) <= 1 else "Consider testing their slot for a week."))
    mins = statistics.median(o["avg_minutes"] for o in others)
    tips.append(f"Typical competitor video length is **{mins:.0f} min**; ours target 20-25 min.")
    freq = statistics.median(o["per_week"] for o in others)
    tips.append(f"Competitors post about **{freq:.1f} videos/week**; we post 7.")
    best = sorted((v for o in others for v in o["videos"]), key=lambda v: -v["per_day"])[:10]
    words = Counter(w for v in best for w in re.findall(r"[஀-௿]{3,}|[A-Za-z]{4,}", v["title"].lower()))
    common = [w for w, _ in words.most_common(12) if w not in {"story", "tamil", "stories"}][:8]
    if common:
        tips.append("Words that keep appearing in their best-performing titles: " + ", ".join(common)
                    + ". Use the themes as inspiration only. Never copy titles or stories.")
    if ours and ours["videos"]:
        if ours["engagement"] < statistics.median(o["engagement"] for o in others):
            tips.append("Our likes+comments per view are below the competitor median: ask a question "
                        "in the outro and pin a comment with a poll-style question.")
    return tips


def write_report(ours, others):
    REPORT_DIR.mkdir(exist_ok=True)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    lines = [f"# Competitor report — {today}", "",
             "| Channel | Subscribers | Median views (last 15) | Videos/week | Avg length | Usual hour (IST) | Engagement % |",
             "|---|---|---|---|---|---|---|"]
    for c in ([ours] if ours else []) + others:
        tag = " **(us)**" if ours and c is ours else ""
        lines.append(f"| [{c['name']}](https://youtube.com/channel/{c['id']}){tag} | {c['subs']:,} | "
                     f"{c['median_views']:,.0f} | {c['per_week']} | {c['avg_minutes']} min | "
                     f"{c['top_hour']}:00 | {c['engagement']} |")
    lines += ["", "## Their best recent videos (views per day)", ""]
    best = sorted(((o["name"], v) for o in others for v in o["videos"]), key=lambda x: -x[1]["per_day"])[:10]
    for name, v in best:
        lines.append(f"- {v['title']} — *{name}* — {v['per_day']:,.0f} views/day, {v['minutes']:.0f} min "
                     f"([watch](https://youtu.be/{v['id']}))")
    lines += ["", "## Suggestions", ""] + [f"- {t}" for t in suggestions(ours, others)]
    lines += ["", "_Generated automatically every Monday. Use competitors for themes and timing "
              "ideas only: never copy their stories, titles or thumbnails (reused-content risk)._"]
    path = REPORT_DIR / f"competitors-{today}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    yt = client()
    ours = None
    try:
        mine = yt.channels().list(part="id", mine=True).execute().get("items", [])
        if mine:
            ours = channel_report(yt, mine[0]["id"])
    except Exception as e:
        log.warning("Could not read our channel: %s", str(e)[:200])

    ids = []
    if LIST_FILE.exists():
        for line in LIST_FILE.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()   # allow trailing comments
            if line:
                cid = resolve(yt, line)
                if cid:
                    ids.append(cid)
                else:
                    log.warning("Could not find channel: %s", line)
    if len(ids) < 5:
        ids += [c for c in discover(yt) if c not in ids]
    ours_id = ours["id"] if ours else None
    others = []
    for cid in ids:
        if cid == ours_id or len(others) >= 8:
            continue
        try:
            rep = channel_report(yt, cid)
            if rep and rep["videos"] and rep["avg_minutes"] >= 5:  # story channels, not shorts-only
                others.append(rep)
        except Exception as e:
            log.warning("Skipping %s: %s", cid, str(e)[:150])
    path = write_report(ours, others)
    log.info("Report written: %s (%d competitors)", path, len(others))
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
