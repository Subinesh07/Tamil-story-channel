"""Central settings for the Tamil story pipeline. Change values here, not in code."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORIES_CSV = Path(os.environ.get("STORIES_CSV", ROOT / "stories.csv"))
STORY_INDEX = ROOT / "story_index.md"
SCHEDULE_MD = ROOT / "SCHEDULE.md"
WORK_DIR = ROOT / "work"          # per-run scratch (git-ignored)
OUTPUT_DIR = ROOT / "output"      # final mp4 / timings / logs (git-ignored)

CSV_COLUMNS = [
    "id", "genre", "title_ta", "title_en", "script_ta", "scene_prompts",
    "publish_at", "status", "video_id", "fail_reason", "description_ta",
    "thumb_quote_ta", "thumb_hook_ta", "thumb_prompt", "series_id", "part",
]

# --- Story rules ---
SENTENCE_SEP = "।"
PROMPT_SEP = "|"
# Leda (1.08x) narrates ~118 Tamil words/min (measured: 1,892 words = 14.9 min at 1.15x), so ~2,600 words = 21-24 min
MIN_WORDS, MAX_WORDS = 2450, 2850
MAX_WORDS_PER_SENTENCE = 15
MIN_SCENES, MAX_SCENES = 20, 25   # story beats in the plan (pictures follow the script)
IMAGE_STYLE = ("cinematic semi-realistic digital painting like a Tamil TV serial still, "
               "South Indian people and setting, dramatic natural lighting, detailed expressive faces, "
               "vibrant colours, sharp focus, no text, no letters, no logos")
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
SENTENCE_PAUSE = 0.15        # seconds between separately voiced sentences (fallback only)
TTS_RETRIES = 3
TTS_RETRY_WAIT = 5

# --- Images ---
WIDTH, HEIGHT = 1280, 720
IMAGE_RETRIES = 2
SECONDS_PER_IMAGE_MIN, SECONDS_PER_IMAGE_MAX = 25, 40   # fallback when a story has no scene marks

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
HARD_MIN, HARD_MAX = 12.0, 30.0   # fail outside; warn outside the soft range
SOFT_MIN, SOFT_MAX = 18.0, 26.0
MAX_AV_DRIFT = 1.0

# --- Scheduling / YouTube ---
TIMEZONE = "Asia/Kolkata"
PUBLISH_HOUR = 19
MIN_PENDING = 10
YT_CATEGORY_ID = "22"   # People & Blogs
HASHTAGS = "#TamilStory #TamilFamilyStory #TamilEmotionalStory"
DISCLOSURE_LINE = "Original Tamil story | Narration by AI"

# --- Branding ---
CHANNEL_NAME_TA = "நிலா கதைகள்"
CHANNEL_NAME_EN = "Nila Kathaigal"
TTS_RATE = "+8%"            # natural conversational pace (slow speech sounded robotic)
MUSIC_FILE = ROOT / "assets" / "music.mp3"   # optional soft background music (royalty-free)
MUSIC_VOLUME = 0.07
THUMB_FONT = "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf"

# Intro / outro lines rotate by story id so videos don't all sound the same.
# {title} is replaced with the story title. Keep every sentence short.
INTRO_LINES = [
    "வணக்கம்! நிலா கதைகளுக்கு உங்களை அன்போட வரவேற்கிறோம்। இன்னைக்கு கதை, {title}",
    "நிலா கதைகள்ல இன்னைக்கு ஒரு புது கதை। கதையோட பேரு, {title}",
    "வாங்க, ஒரு கதை கேட்கலாம்। நிலா கதைகள் வழங்கும், {title}",
    "இன்னைக்கு சாயங்காலம் நிலா கதைகள்ல, {title}। வாங்க கேட்கலாம்",
    "வணக்கம் நண்பர்களே! இது நிலா கதைகள்। இன்னைக்கு நம்ம கதை, {title}",
]
OUTRO_LINES = [
    "கதை பிடிச்சிருந்தா லைக் பண்ணுங்க। நிலா கதைகளை சப்ஸ்க்ரைப் பண்ணுங்க। நாளைக்கு இன்னொரு கதையோட சந்திப்போம்",
    "இந்த கதை உங்க மனசை தொட்டிருந்தா, கமெண்ட்ல சொல்லுங்க। சப்ஸ்க்ரைப் பண்ண மறந்துடாதீங்க",
    "உங்களுக்கு பிடிச்ச பகுதி எது? கமெண்ட்ல எழுதுங்க। தினமும் ஒரு கதைக்கு நிலா கதைகளை சப்ஸ்க்ரைப் பண்ணுங்க",
    "இந்த கதையை உங்க குடும்பத்தோட பகிர்ந்துக்கோங்க। பெல் ஐகானை அழுத்துங்க, நாளைக்கு சந்திப்போம்",
    "நன்றி நண்பர்களே! நிலா கதைகளை சப்ஸ்க்ரைப் பண்ணுங்க। நாளை சாயங்காலம் ஏழு மணிக்கு புது கதை",
]

# --- Gemini voice (main narrator) ---
TTS_ENGINE = "gemini"          # "gemini" (Leda) or "edge" (Pallavi). Never mixed within a video.
GEMINI_VOICE = "Leda"
GEMINI_STYLE = ("Read this Tamil story aloud like a warm, emotional storyteller from Tamil Nadu. "
                "Natural, slightly brisk conversational pace; short pauses between sentences; "
                "expressive: rising on questions, softer on sad lines, lively on dialogue")
GEMINI_TEMPO = 1.08            # gentle speed-up after synthesis (pitch unchanged); close to the reference voice
GEMINI_CHUNK_CHARS = 4000      # long passages = few requests (free daily limit is small)
TTS_CACHE = ROOT / "cache" / "tts"   # voiced chunks survive between runs (quota pauses)
