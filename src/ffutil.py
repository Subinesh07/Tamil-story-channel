"""Small ffmpeg/ffprobe helpers."""
import json
import logging
import subprocess

log = logging.getLogger(__name__)


def run(cmd, check=True):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if check and p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"Command failed ({cmd[0]}):\n{tail}")
    return p


def ffprobe_duration(path, stream=None):
    cmd = ["ffprobe", "-v", "error"]
    if stream:
        cmd += ["-select_streams", stream, "-show_entries", "stream=duration"]
    else:
        cmd += ["-show_entries", "format=duration"]
    cmd += ["-of", "json", str(path)]
    data = json.loads(run(cmd).stdout)
    if stream:
        return float(data["streams"][0]["duration"])
    return float(data["format"]["duration"])


def ffprobe_streams(path):
    out = run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)]).stdout
    return json.loads(out)["streams"]
