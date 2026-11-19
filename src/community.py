"""Daily YouTube community post + poll DRAFT (the YouTube API cannot publish these).

The draft is saved to output/community_post.md and the workflow opens it as a GitHub issue,
so Subinesh gets a notification and can paste it into YouTube Studio -> Create -> Post.
"""
import logging
import random

from config import CHANNEL_NAME_TA

log = logging.getLogger(__name__)

FALLBACK_POLLS = [
    ("இன்னைக்கு கதையில உங்களுக்கு பிடிச்ச பகுதி எது?", ["ஆரம்பம்", "திருப்புமுனை", "முடிவு", "எல்லாமே!"]),
    ("அடுத்த கதை எந்த மாதிரி இருக்கணும்?", ["குடும்ப கதை", "மர்ம கதை", "நட்பு கதை", "நீதிக் கதை"]),
    ("நீங்க எப்போ கதை கேட்பீங்க?", ["சாயங்காலம்", "ராத்திரி தூங்கும் முன்", "பயணத்துல", "வேலை செய்யும்போது"]),
    ("இந்த கதையோட முடிவு உங்களுக்கு எப்படி இருந்துச்சு?", ["அருமை!", "கண்ணீர் வந்துச்சு", "எதிர்பார்க்கல", "வேற முடிவு வேணும்"]),
]


def draft(row, video_id):
    title = row["title_ta"]
    link = f"https://youtu.be/{video_id}" if video_id else "(link)"
    post = poll_q = None
    options = []
    try:
        from llm import complete
        data = complete(
            "Write a YouTube community post in natural spoken Tamil for a story channel called "
            f"'{CHANNEL_NAME_TA}'. Today's story: '{title}' ({row['title_en']}). "
            f"Teaser: {row.get('description_ta', '')[:300]}\n"
            "Return JSON: {\"post\": \"2-3 short warm lines inviting people to watch tonight at 7 PM, "
            "no spoilers, 1-2 emojis\", \"poll_question\": \"a fun question about the story theme\", "
            "\"poll_options\": [\"2 to 4 short options\"]}",
            want_json=True, max_tokens=1500, rounds=1)
        post, poll_q, options = data["post"], data["poll_question"], data["poll_options"][:4]
    except Exception as e:  # AI busy: use a rotating template
        log.warning("Community post AI draft failed (%s); using template", str(e)[:120])
    if not post:
        post = (f"🌙 இன்னைக்கு சாயங்காலம் 7 மணிக்கு புது கதை: \"{title}\"\n"
                "குடும்பத்தோட உட்கார்ந்து கேளுங்க. உங்க கருத்தை கமெண்ட்ல சொல்லுங்க! ❤️")
    if not poll_q:
        poll_q, options = random.Random(row["id"]).choice(FALLBACK_POLLS)
    opts = "\n".join(f"- {o}" for o in options)
    return f"""## Today's community post — {title}

Paste this in **YouTube Studio → Create → Post** (or the YouTube app → **+** → **Post**).

### Post text
{post}

▶️ {link}

### Poll (choose "Poll" when creating the post)
**{poll_q}**
{opts}
"""
