"""Daily YouTube community post + poll DRAFT (the YouTube API cannot publish these).

The draft is saved to output/community_post.md and the workflow opens it as a GitHub issue,
so Subinesh gets a notification and can paste it into YouTube Studio -> Create -> Post.
"""
import logging

from config import CHANNEL_NAME_TA

log = logging.getLogger(__name__)

FALLBACK_POLLS = [
    ("இன்னைக்கு கதையில உங்களுக்கு பிடிச்ச பகுதி எது?", ["ஆரம்பம்", "திருப்புமுனை", "முடிவு", "எல்லாமே!"]),
    ("அடுத்த கதை எந்த மாதிரி இருக்கணும்?", ["குடும்ப கதை", "மர்ம கதை", "நட்பு கதை", "நீதிக் கதை"]),
    ("நீங்க எப்போ கதை கேட்பீங்க?", ["சாயங்காலம்", "ராத்திரி தூங்கும் முன்", "பயணத்துல", "வேலை செய்யும்போது"]),
    ("இந்த கதையோட முடிவு உங்களுக்கு எப்படி இருந்துச்சு?", ["அருமை!", "கண்ணீர் வந்துச்சு", "எதிர்பார்க்கல", "வேற முடிவு வேணும்"]),
]


POLL_TYPES = [
    ("prediction", "what will happen in the next part (2-4 possible outcomes)",
     ("அடுத்த பகுதியில என்ன நடக்கும்னு நினைக்கிறீங்க?", ["உண்மை வெளிவரும்", "பெரிய ஆபத்து வரும்", "யாரோ துரோகம் பண்ணுவாங்க", "எதிர்பாராத திருப்பம்"])),
    ("character", "which character the viewer likes or suspects most (use the real character names)",
     ("இந்த கதையில உங்களுக்கு பிடிச்ச கேரக்டர் யாரு?", ["ஹீரோ", "ஹீரோயின்", "வில்லன்", "குட்டி பையன்"])),
    ("your choice", "what would YOU do in the main character's situation",
     ("நீங்க அந்த இடத்துல இருந்தா என்ன பண்ணுவீங்க?", ["தைரியமா எதிர்ப்பேன்", "யாருக்காவது சொல்வேன்", "அமைதியா இருப்பேன்", "தப்பிச்சு ஓடுவேன்"])),
    ("guess", "guess the secret / who is behind the mystery",
     ("இந்த ரகசியத்துக்கு பின்னாடி யாரு இருப்பாங்க?", ["குடும்பத்துல ஒருத்தர்", "ஒரு அந்நியர்", "நண்பர்", "யாருமே எதிர்பார்க்காதவர்"])),
    ("rating", "how the viewer felt about this part's twist",
     ("இந்த பகுதியோட திருப்பம் எப்படி இருந்துச்சு?", ["செம்ம! 🔥", "எதிர்பார்க்கல 😱", "கண்ணீர் வந்துச்சு 😢", "இன்னும் வேணும்!"])),
]
EMOJI = {"doomsday": "😱", "horror": "👻", "adventure": "🗺️", "family serial": "🏠", "real lives": "⭐",
         "family moral": "🌳"}


def draft(row, video_id):
    """Same look every time (fixed layout), different words every time (new hook, teaser and a
    rotating kind of poll question)."""
    from datetime import datetime
    title = row["title_ta"].split(" | ")[0]
    series = (row["title_ta"].split(" | ") + [""])[1]
    link = f"https://youtu.be/{video_id}" if video_id else "(link)"
    try:
        h = datetime.fromisoformat(row["publish_at"]).hour
        when = f"{'காலை' if h < 12 else 'மதியம்' if h < 16 else 'சாயங்காலம்'} {h if h <= 12 else h - 12} மணிக்கு"
    except (KeyError, ValueError):
        when = "இன்னைக்கு"
    kind, ask, (fb_q, fb_opts) = POLL_TYPES[(int(row["id"]) if str(row["id"]).isdigit() else 0) % len(POLL_TYPES)]
    hook = teaser = poll_q = None
    options = []
    try:
        from llm import complete
        data = complete(
            "You write YouTube community posts in casual spoken Tamil (light Tanglish) for the story channel "
            f"'{CHANNEL_NAME_TA}'. Story: '{title}' ({row['title_en']}). "
            f"Teaser: {row.get('description_ta', '')[:400]}\n"
            "Return JSON: {\"hook\": \"ONE gripping question or line, max 12 words, no spoilers\", "
            "\"teaser\": \"2 short lines that make people curious, no spoilers\", "
            f"\"poll_question\": \"a poll question about {ask}\", "
            "\"poll_options\": [\"exactly 4 short options, max 5 words each\"]}",
            want_json=True, max_tokens=1500, rounds=1)
        hook, teaser = data["hook"].strip(), data["teaser"].strip()
        poll_q, options = data["poll_question"].strip(), [str(o).strip() for o in data["poll_options"]][:4]
    except Exception as e:  # AI busy: the same layout with a template
        log.warning("Community post AI draft failed (%s); using template", str(e)[:120])
    if not hook:
        hook = f"\"{title}\" – அடுத்து என்ன நடக்கும்?"
        teaser = "குடும்பத்தோட உட்கார்ந்து பாருங்க.\nஉங்க கருத்தை கமெண்ட்ல சொல்லுங்க! ❤️"
    if not poll_q or len(options) < 2:
        poll_q, options = fb_q, fb_opts
    head = f"{EMOJI.get(row.get('genre'), '🌙')} {series or title}"
    post = (f"{head}\n\n{hook}\n{teaser}\n\n▶️ {link}\n⏰ {when} – நிலா கதைகள்\n"
            f"#நிலாகதைகள் #TamilStory")
    poll_q = f"🗳️ {poll_q}"
    opts = "\n".join(f"- {o}" for o in options)
    try:
        import status as ST
        ST.community(row["id"], post, poll_q, list(options))
    except Exception:
        pass
    return f"""## Today's community post — {title}

Paste this in **YouTube Studio → Create → Post** (or the YouTube app → **+** → **Post**).

### Post text
{post}

### Poll (choose "Poll" when creating the post)
**{poll_q}**
{opts}
"""
