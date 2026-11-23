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
    "thumb_quote_ta", "thumb_hook_ta", "thumb_prompt", "series_id", "part", "thumb_text",
    "end_lines", "quiz_q", "quiz_a", "quiz_winner",
]

# --- Story rules ---
SENTENCE_SEP = "।"
PROMPT_SEP = "|"
# Leda (1.08x) narrates ~118 Tamil words/min (measured: 1,892 words = 14.9 min at 1.15x), so ~2,600 words = 21-24 min
MIN_WORDS, MAX_WORDS = 1150, 1450   # 10-12 min parts: new viewers stay longer
MAX_WORDS_PER_SENTENCE = 15
MIN_SCENES, MAX_SCENES = 20, 25   # story beats in the plan (pictures follow the script)
MAX_PICTURES = 999   # no limit: quality first (never fewer pictures to save credits)
OLD_IMAGE_STYLE = ("cinematic semi-realistic digital painting like a Tamil TV serial still, "
                   "South Indian people and setting, dramatic natural lighting, detailed expressive faces, "
                   "vibrant colours, sharp focus, no text, no letters, no logos")
PHOTO_IMAGE_STYLE = ("photorealistic cinematic film still, South Indian people and setting, intriguing "
               "mysterious moment that makes you want to know what happens next, dramatic movie lighting "
               "with strong contrast and rim light, shallow depth of field, rich detail, expressive faces, "
               "natural skin, sharp focus, 35mm film look, no text, no letters, no logos")
# House look since 23 Nov: Gemini-like painted drama art with the "Nila face" design
IMAGE_STYLE = ("2D digital painting, semi-realistic illustrated Tamil drama art, smooth painterly shading, clean soft "
               "outlines, rich natural colours. NILA FACE DESIGN: soft oval face, high rounded cheekbones, large "
               "expressive deep-brown almond eyes with a bright catch-light, thick defined eyebrows, straight nose with "
               "a softly rounded tip, full lips, warm brown skin; realistic adult proportions for adults, every "
               "character looks exactly their stated age, never childlike unless a child. Signature lighting: cool "
               "blue moonlight on one side and warm orange lamp glow on the other. Every character wears a clearly "
               "visible small silver crescent-moon pendant. Every person's whole head and face fully inside the frame, natural "
               "anatomy, correct number of people. Detailed Tamil Nadu background, no text, no letters, no logos")
# every earlier picture style: stored prompts are switched to the current style, saved pictures still match
PREVIOUS_IMAGE_STYLES = [
    "warm watercolor illustration, South Indian home, soft natural light, no text, no logos",
    OLD_IMAGE_STYLE,
    PHOTO_IMAGE_STYLE,
]
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
IMAGE_RETRIES = 3
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
HARD_MIN, HARD_MAX = 8.0, 16.0   # fail outside; warn outside the soft range
SOFT_MIN, SOFT_MAX = 9.5, 14.0
# Weekend Doomsday serial (12 PM Sat/Sun): shorter parts, so two videos a day fit Leda's free limit
DOOM_MIN_WORDS, DOOM_MAX_WORDS = 1150, 1450
DOOM_HARD = (8.0, 16.0)
DOOM_SOFT = (9.5, 14.0)
DOOM_HOUR = 11
# 7 PM-slot story time by weekday (Mon=0 ... Sun=6), IST. Published ~1 hour before India's
# evening viewing peak (7-10 PM) so YouTube has time to start recommending it.
PUBLISH_HOURS = {0: 18, 1: 20, 2: 18, 3: 18, 4: 19, 5: 19, 6: 17}
MAX_AV_DRIFT = 1.0

# --- Scheduling / YouTube ---
TIMEZONE = "Asia/Kolkata"
PUBLISH_HOUR = 19
MIN_PENDING = 10
YT_CATEGORY_ID = "22"   # People & Blogs
HASHTAGS = "#TamilStory #TamilFamilyStory #TamilEmotionalStory"
DISCLOSURE_LINE = "இது ஒரு கற்பனை கதை (fictional story) | Original Tamil story | Narration by AI"

# --- Branding ---
CHANNEL_NAME_TA = "நிலா கதைகள்"
CHANNEL_NAME_EN = "Nila Kathaigal"
TTS_RATE = "+8%"            # natural conversational pace (slow speech sounded robotic)
MUSIC_FILE = ROOT / "assets" / "music.mp3"   # optional soft background music (royalty-free)
MUSIC_VOLUME = 0.07
THUMB_FONT = "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf"

# Intro / outro lines rotate by story id so videos don't all sound the same.
# {title} is replaced with the story title. Keep every sentence short.
# Title card after the cold open: one short line (about 3 seconds), no long welcome
INTRO_LINES = [
    "நிலா கதைகள் வழங்கும், {title}",
    "{title}",
    "நிலா கதைகள், {title}",
    "{title}, நிலா கதைகள்ல",
    "இது நிலா கதைகள், {title}",
]
OUTRO_LINES = [
    "கதை பிடிச்சிருந்தா லைக் பண்ணுங்க। நிலா கதைகளை சப்ஸ்க்ரைப் பண்ணுங்க। நாளைக்கு இன்னொரு கதையோட சந்திப்போம்",
    "இந்த கதை உங்க மனசை தொட்டிருந்தா, கமெண்ட்ல சொல்லுங்க। சப்ஸ்க்ரைப் பண்ண மறந்துடாதீங்க",
    "உங்களுக்கு பிடிச்ச பகுதி எது? கமெண்ட்ல எழுதுங்க। தினமும் ஒரு கதைக்கு நிலா கதைகளை சப்ஸ்க்ரைப் பண்ணுங்க",
    "இந்த கதையை உங்க குடும்பத்தோட பகிர்ந்துக்கோங்க। பெல் ஐகானை அழுத்துங்க, நாளைக்கு சந்திப்போம்",
    "நன்றி நண்பர்களே! நிலா கதைகளை சப்ஸ்க்ரைப் பண்ணுங்க। நாளைக்கு இன்னொரு புது கதையோட வர்றோம்",
]

# --- Gemini voice (main narrator) ---
TTS_ENGINE = "gemini"          # "gemini" (Leda) or "edge" (Pallavi). Never mixed within a video.
GEMINI_VOICE = "Leda"
GEMINI_STYLE = ("Read this Tamil story aloud like a warm, emotional storyteller from Tamil Nadu. "
                "Natural, slightly brisk conversational pace; short pauses between sentences; "
                "expressive: rising on questions, softer on sad lines, lively on dialogue. "
                "Speak ONLY in Tamil, read the text exactly as written, never translate or add English sentences")
GEMINI_TEMPO = 1.08            # gentle speed-up after synthesis (pitch unchanged); close to the reference voice
GEMINI_CHUNK_CHARS = 4000      # long passages = few requests (free daily limit is small)
TTS_CACHE = ROOT / "cache" / "tts"   # voiced chunks survive between runs (quota pauses)
