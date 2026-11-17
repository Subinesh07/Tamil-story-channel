"""Central settings for the Tamil story pipeline. Change values here, not in code."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORIES_CSV = ROOT / "stories.csv"
STORY_INDEX = ROOT / "story_index.md"
SCHEDULE_MD = ROOT / "SCHEDULE.md"
WORK_DIR = ROOT / "work"          # per-run scratch (git-ignored)
OUTPUT_DIR = ROOT / "output"      # final mp4 / timings / logs (git-ignored)

CSV_COLUMNS = [
    "id", "genre", "title_ta", "title_en", "script_ta", "scene_prompts",
    "publish_at", "status", "video_id", "fail_reason",
]

# --- Story rules ---
SENTENCE_SEP = "।"
PROMPT_SEP = "|"
MIN_WORDS, MAX_WORDS = 3500, 4000
MAX_WORDS_PER_SENTENCE = 15
MIN_SCENES, MAX_SCENES = 20, 25
IMAGE_STYLE = ("warm watercolor illustration, South Indian home, soft natural light, "
               "no text, no logos")
GENRE_MIX = {  # used by generate_stories.py for each new batch of 30
    "family emotional": 12,
    "moral or life-lesson": 8,
    "suspense or mystery": 5,
    "friendship or romance": 5,
}
OPENING_STYLES = ["in the middle of the action", "a letter", "a flashback",
                  "a mystery", "a dialogue", "a small everyday moment that turns strange"]

# --- Voice ---
VOICE_PRIMARY = "ta-IN-PallaviNeural"
VOICE_FALLBACK = "ta-IN-ValluvarNeural"
SENTENCE_PAUSE = 0.25        # seconds between sentences
TTS_RETRIES = 3
TTS_RETRY_WAIT = 5

# --- Images ---
WIDTH, HEIGHT = 1280, 720
IMAGE_RETRIES = 2
SECONDS_PER_IMAGE_MIN, SECONDS_PER_IMAGE_MAX = 40, 60

# --- Video ---
FPS = 25
ZOOM_AMOUNT = 0.08
XFADE = 0.4
FADE_IN = 1.0
FADE_OUT = 2.0
FONT_NAME = "Noto Sans Tamil"
FONT_SIZE = 44
X264_PRESET = "veryfast"
X264_CRF = 21

# --- Quality gate (minutes) ---
HARD_MIN, HARD_MAX = 19.0, 26.0
SOFT_MIN, SOFT_MAX = 20.0, 25.0
MAX_AV_DRIFT = 1.0

# --- Scheduling / YouTube ---
TIMEZONE = "Asia/Kolkata"
PUBLISH_HOUR = 19
MIN_PENDING = 10
YT_CATEGORY_ID = "22"   # People & Blogs
HASHTAGS = "#TamilStory #TamilFamilyStory #TamilEmotionalStory"
DISCLOSURE_LINE = "Original Tamil story | Narration by AI"
