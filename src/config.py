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
# Painted look tried on 23-24 Nov (dropped: the free model drew it badly)
PAINTED_IMAGE_STYLE = ("2D digital painting, semi-realistic illustrated Tamil drama art, smooth painterly shading, clean soft "
               "outlines, rich natural colours. NILA FACE DESIGN: soft oval face, high rounded cheekbones, large "
               "expressive deep-brown almond eyes with a bright catch-light, thick defined eyebrows, straight nose with "
               "a softly rounded tip, full lips, warm brown skin; realistic adult proportions for adults, every "
               "character looks exactly their stated age, never childlike unless a child. Signature lighting: cool "
               "blue moonlight on one side and warm orange lamp glow on the other. Every character wears a clearly "
               "visible small silver crescent-moon pendant. Every person's whole head and face fully inside the frame, natural "
               "anatomy, correct number of people. Detailed Tamil Nadu background, no text, no letters, no logos")
# House look (back to the proven photorealistic cinematic style, 24 Nov)
IMAGE_STYLE = PHOTO_IMAGE_STYLE.replace("no text, no letters, no logos",
    "every person's whole head and face fully inside the frame, natural anatomy, correct number of people, "
    "no text, no letters, no logos")
# Short style that goes FIRST in every drawn prompt: the free picture model reads only about the first
# 250 words, so a style sentence at the end of a long description can be cut off (photo instead of painting)
STYLE_PREFIX = "photorealistic cinematic film still, South Indian people and setting, dramatic movie lighting: "
# every earlier picture style: stored prompts are switched to the current style, saved pictures still match
PREVIOUS_IMAGE_STYLES = [
    "warm watercolor illustration, South Indian home, soft natural light, no text, no logos",
    OLD_IMAGE_STYLE,
    PHOTO_IMAGE_STYLE,
    PAINTED_IMAGE_STYLE,
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
IMAGE_RETRIES = 5
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
# Experiment from 26 Nov 2026 (competitor report): longer horror, Tamil+English titles, face thumbnails
EXPERIMENT_START = "2026-11-26"
HORROR_MIN_WORDS, HORROR_MAX_WORDS = 1850, 2250   # 15-18 min (top Tamil horror channels run 15-40 min)
HORROR_HARD = (12.0, 22.0)
HORROR_SOFT = (14.0, 20.0)
EN_TAGS = {"horror": "Tamil Horror Story", "doomsday": "Tamil Story", "family serial": "Tamil Family Story",
           "family moral": "Tamil Family Story", "family emotional": "Tamil Family Story",
           "real lives": "Tamil Real Story", "adventure": "Tamil Adventure Story"}
# 7 PM-slot story time by weekday (Mon=0 ... Sun=6), IST. Published ~1 hour before India's
# evening viewing peak (7-10 PM) so YouTube has time to start recommending it.
# 26 Nov 2026: India-wide data says publish 4-5 PM on weekdays (indexed before the 7-10 PM peak) and
# 10-11 AM at weekends (viewing runs all day). Our viewers are mostly 55+ women: they watch YouTube in the
# afternoon and TV serials from ~6:30 PM, so 5 PM catches them first. Studio has no hourly data for us yet.
PUBLISH_HOURS = {0: 17, 1: 17, 2: 17, 3: 17, 4: 17, 5: 11, 6: 11}
SECOND_SLOT_HOURS = {0: 19, 1: 19, 2: 19, 3: 19, 4: 19, 5: 18, 6: 18}   # after the 2nd Cloudflare account refills   # when a day has two long videos
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
# 27 Nov: the long English instruction was read ALOUD by Leda (Whisper caught it). Keep it to a few words -
# Google's own guidance for speech style is a short lead-in like "Say warmly:". Retries send the Tamil text alone.
GEMINI_STYLE = "Say warmly, like a Tamil storyteller"
GEMINI_TEMPO = 1.08            # gentle speed-up after synthesis (pitch unchanged); close to the reference voice
GEMINI_CHUNK_CHARS = 4000      # long passages = few requests (free daily limit is small)
TTS_CACHE = ROOT / "cache" / "tts"   # voiced chunks survive between runs (quota pauses)

# 25 Nov 2026 (owner): no picture checker for videos - the "failed" pictures were fine; what viewers notice is a
# character's dress colour or face changing, which fixed character cards now handle. Set PICTURE_CHECK=1 to re-enable.
import os as _os
PICTURE_CHECK = bool(_os.environ.get("PICTURE_CHECK"))

# 26 Nov 2026: family-only channel. No weekend Doomsday/survival serial while this is True.
FAMILY_ONLY = True
SERIAL_HOUR = 17   # special serials use the day's main slot (PUBLISH_HOURS); kept for reference
