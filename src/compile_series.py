"""Full-series compilation: when every part of a series is public, join all parts into one long
"full story" video, upload it (scheduled 3 PM IST) and add it to the series playlist.
Uses the finished part videos kept in the GitHub release "videos" - no voice or picture credits.

python src/compile_series.py            # compile every finished series not yet compiled
python src/compile_series.py --dry-run  # only list what would be compiled
"""
import csv
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from config import ROOT  # noqa: E402

log = logging.getLogger("compile")
IST = ZoneInfo("Asia/Kolkata")
WORK = ROOT / "output" / "compile"
RELEASE = "videos"


def gh(*args, check=True):
    return subprocess.run(["gh", *args], check=check, capture_output=True, text=True)


def ffprobe_dur(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", str(p)], capture_output=True, text=True).stdout
    return float(out.strip())


def stamp(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def ready_series():
    data = json.loads((ROOT / "series.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(open(ROOT / "stories.csv", encoding="utf-8")))
    now = datetime.now(timezone.utc)
    out = []
    for s in data["series"]:
        if s["genre"] == "family emotional" or s.get("compilation_id") or s["parts_total"] < 2:
            continue
        parts = {}
        for r in rows:
            if r.get("series_id") == s["id"] and r.get("status") == "done" and r.get("video_id") \
                    and (r.get("part") or "").isdigit():
                parts[int(r["part"])] = r
        if sorted(parts) != list(range(1, s["parts_total"] + 1)):
            continue
        last = parts[s["parts_total"]]
        if datetime.fromisoformat(last["publish_at"]) > now:
            continue   # final part not public yet
        out.append((s, [parts[k] for k in sorted(parts)]))
    return data, out


def build(s, parts):
    WORK.mkdir(parents=True, exist_ok=True)
    files = []
    for r in parts:
        name = f"story_{r['id']}.mp4"
        dest = WORK / name
        if not dest.exists():
            res = gh("release", "download", RELEASE, "-p", name, "-D", str(WORK), "--clobber", check=False)
            if res.returncode or not dest.exists():
                raise FileNotFoundError(f"{name} is not kept in the '{RELEASE}' release")
        files.append(dest)
    lst = WORK / f"{s['id']}.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in files), encoding="utf-8")
    out = WORK / f"{s['id']}_full.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                        "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    total = sum(ffprobe_dur(f) for f in files)
    if r.returncode or abs(ffprobe_dur(out) - total) > 5:
        log.info("Fast join failed; re-encoding")
        ins, graph = [], ""
        for i, f in enumerate(files):
            ins += ["-i", str(f)]
            graph += f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}];[{i}:a]aresample=48000[a{i}];"
        graph += "".join(f"[v{i}][a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=1:a=1[v][a]"
        subprocess.run(["ffmpeg", "-y", *ins, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-b:a", "160k",
                        "-movflags", "+faststart", str(out)], check=True)
    chapters, t = [], 0.0
    for k, (f, r) in enumerate(zip(files, parts), 1):
        head = r["title_ta"].split(" | ")[0].replace("டூம்ஸ்டே 😱", "").strip()
        chapters.append(f"{stamp(t)} பகுதி {k} – {head[:60]}")
        t += ffprobe_dur(f)
    return out, "\n".join(chapters), t


def thumbnail(s, parts):
    covers = {"doomsday-1": "doomsday.jpg", "family-1": "nizhal_nijamanal.jpg"}
    p = ROOT / "previews" / "covers" / covers.get(s["id"], f"{s['id']}.jpg")
    if p.exists():
        return p
    name = f"story_{parts[0]['id']}_thumbnail.jpg"
    if gh("release", "download", RELEASE, "-p", name, "-D", str(WORK), "--clobber", check=False).returncode == 0:
        return WORK / name
    return None


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    dry = "--dry-run" in sys.argv
    data, todo = ready_series()
    if not todo:
        log.info("No finished series waiting for a compilation")
        return
    for s, parts in todo:
        log.info("Compiling %s (%d parts)%s", s["title_en"], len(parts), " [dry run]" if dry else "")
        if dry:
            continue
        try:
            video, chapters, total = build(s, parts)
        except Exception as e:
            log.warning("Compilation of %s skipped: %s", s["id"], str(e)[:200])
            continue
        last = datetime.fromisoformat(parts[-1]["publish_at"]).astimezone(IST)
        when = (last + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
        when = max(when, datetime.now(IST) + timedelta(hours=1))
        mins = int(total // 60)
        name = s["title_ta"]
        title = f"{name} – முழு கதை | எல்லா {len(parts)} பகுதிகளும் ஒரே வீடியோவில் 🎬"
        if len(title) > 100:
            title = f"{name[:60]} – முழு கதை (எல்லா பகுதிகளும்) 🎬"[:100]
        desc = (f"🎬 {name} – முழு கதை, ஆரம்பம் முதல் முடிவு வரை ({mins} நிமிடங்கள்).\n"
                f"எல்லா {len(parts)} பகுதிகளும் ஒரே வீடியோவில் – நிம்மதியா உட்கார்ந்து பாருங்க!\n\n"
                f"{s.get('premise_ta') or ''}".strip())
        row = {"title_ta": title, "description_ta": desc, "script_ta": "", "chapters": chapters,
               "publish_at": when.isoformat(), "genre": s["genre"], "series_id": s["id"]}
        from youtube_upload import set_thumbnail, upload
        vid = upload(video, row)
        th = thumbnail(s, parts)
        if th:
            set_thumbnail(vid, th)
        from channel_tools import add_to_playlist, post_comment
        add_to_playlist(row, vid)
        post_comment({"series_id": ""}, vid, f"இந்த கதையில உங்களுக்கு பிடிச்ச பகுதி எது? ({len(parts)} பகுதிகள்)")
        s["compilation_id"] = vid
        import series as S
        S.save(data)
        try:
            import status as ST
            ST.event(f"Full-story compilation of {s['title_en']} uploaded: {vid} (public {when:%d %b %I:%M %p})")
        except Exception:
            pass
        log.info("Compilation uploaded: %s (public %s)", vid, when.isoformat())


if __name__ == "__main__":
    main()
