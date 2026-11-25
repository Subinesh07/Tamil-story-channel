"""Character cards for picture prompts: the same age, gender, face and facial hair in every picture.

Picture models ignore a bare number like "(30, ...)" and draw a child, or add a beard in one picture
and not the next. A card spells it out: "Karthik: a 30-year-old adult man in his thirties, ...,
short beard" / "clean-shaven, no beard, no moustache".
"""
import re

MALE = re.compile(r"\b(man|boy|male|gentleman|husband|father|grandfather|son|king|he|his|uncle|brother)\b", re.I)
FEMALE = re.compile(r"\b(woman|girl|female|lady|wife|mother|grandmother|daughter|queen|she|her|aunt|sister|paati)\b", re.I)


def gender(c):
    g = str(c.get("gender", "")).lower()
    if g.startswith(("m", "boy")):
        return "m"
    if g.startswith(("f", "w", "girl")):
        return "f"
    for text in (c.get("appearance_en", ""), c.get("role", "")):   # the look decides first
        m, f = len(MALE.findall(text)), len(FEMALE.findall(text))
        if m != f:
            return "m" if m > f else "f"
    return ""


def age_words(age, g):
    try:
        a = int(re.search(r"\d+", str(age)).group())
    except (AttributeError, ValueError):
        return ""
    who = {"m": ("boy", "teenage boy", "man"), "f": ("girl", "teenage girl", "woman")}.get(g, ("child", "teenager", "adult"))
    if a <= 12:
        return f"a {a}-year-old young {who[0]} (a small child, not an adult)"
    if a <= 19:
        return f"a {a}-year-old {who[1]}"
    decade = {2: "twenties", 3: "thirties", 4: "forties", 5: "fifties", 6: "sixties", 7: "seventies"}.get(a // 10, "old age")
    grown = ("adult " if a < 60 else "elderly ") + who[2]
    pron = {"m": "his", "f": "her"}.get(g, "their")
    return f"a {a}-year-old {grown} in {pron} {decade}"


def facial_hair(c, g, age):
    if g != "m":
        return ""
    try:
        if int(re.search(r"\d+", str(age)).group()) < 16:
            return ""
    except (AttributeError, ValueError):
        pass
    look = c.get("appearance_en", "").lower()
    beard = "beard" in look and not re.search(r"no beard|beardless", look)
    tache = re.search(r"moustache|mustache", look) and not re.search(r"no (moustache|mustache)", look)
    if beard:
        return "always with the same beard"
    if re.search(r"clean[- ]shaven|shaved face", look):
        return ""   # the look already says clean-shaven: never contradict it
    if tache:
        return "a thick moustache, smooth shaved chin"
    # the free picture model draws most adult Tamil men with a beard and fails "clean-shaven" again and
    # again, so every other adult man gets the same short trimmed beard in every picture (consistent)
    return "a short neatly trimmed black beard and moustache"


def card(c, age_override=None):
    """One consistent description of a character for every picture."""
    g = gender(c)
    age = age_override if age_override not in (None, "") else c.get("age", "")
    if age_override in (None, ""):
        look = c.get("appearance_en", "")
    else:   # flashback / years later: same person at another age, no grown-up details
        look = "same family face as the grown-up character, age-appropriate simple clothes"
    parts = [p for p in (age_words(age, g), look, facial_hair(c, g, age)) if p]
    return f"{c['name']} ({'; '.join(parts)})"


# ---- Fixed look per story (25 Nov): the audience reads a new dress colour as a new person ----
COLOURS = ["sky-blue", "maroon", "mustard-yellow", "bottle-green", "dark grey", "purple", "orange", "cream-white"]


COLOURED = re.compile(r"\b(red|blue|teal|green|yellow|grey|gray|maroon|cream|white|navy|orange|purple|black|brown|"
                      r"gold|golden|crimson|beige|khaki|pink|olive|violet|silver)\b[^,;.]{0,40}\b(saree|sari|kurta|"
                      r"shirt|t-shirt|vest|dhoti|veshti|lungi|robe|robes|chiton|armou?r|dress|jeans|trousers|shorts|"
                      r"blouse|shawl|uniform|jacket|skirt|pavadai|frock|rash guard|bandana)", re.I)


def garment(c, g):
    look = c.get("appearance_en", "").lower()
    if "saree" in look or "sari" in look:
        return "silk saree"
    try:
        child = int(re.search(r"\d+", str(c.get("age", ""))).group()) <= 12
    except (AttributeError, ValueError):
        child = False
    if child and g == "f" and not re.search(r"saree|sari", look):
        return "pavadai long skirt with a matching short blouse"
    if re.search(r"salwar|kurta|churidar|kurti", look):
        return "knee-length kurta top with matching loose trousers and a dupatta scarf"
    if "polo" in look:
        return "polo t-shirt with dark jeans"
    if "t-shirt" in look or "tshirt" in look:
        return "t-shirt with dark jeans"
    if re.search(r"veshti|dhoti|lungi", look):
        return "half-sleeve shirt with a white veshti"
    if "shirt" in look:
        return "half-sleeve formal shirt with dark trousers"
    return None   # history / fantasy costume: keep the story's own clothing words


def face_only(c):
    """The appearance text without any clothing words (clothes are fixed separately)."""
    look = c.get("appearance_en", "")
    look = re.split(r",?\s*\b(?:always |usually |often )?(?:wears|wearing|dressed|in a|in an)\b", look, flags=re.I)[0]
    return look.strip(" ,.")


def fixed_cards(chars):
    """name -> short card with face, age, facial hair and ONE outfit colour kept for the whole story."""
    cards = {}
    for k, c in enumerate(chars or []):
        if not c.get("name"):
            continue
        g = gender(c)
        age = c.get("age", "")
        look = c.get("appearance_en", "")
        if COLOURED.search(look):   # the story already fixed the clothes and their colours: keep them exactly
            bits = [age_words(age, g), look.strip(" ."), facial_hair(c, g, age), "ALWAYS exactly this outfit"]
        else:
            wear = garment(c, g)
            clothes = look[len(face_only(c)):].strip(" ,.")
            outfit = (f"ALWAYS the same plain {COLOURS[k % len(COLOURS)]} {wear}" if wear else
                      f"ALWAYS the same outfit: {clothes}" if clothes else "the same clothes in every picture")
            bits = [age_words(age, g), face_only(c), facial_hair(c, g, age), outfit]
        card = "; ".join(b for b in bits if b)
        words = card.split()
        if len(words) > 55:   # FLUX reads ~250 words in all: keep each card short, outfit line kept
            card = " ".join(words[:47]).rstrip(",;") + "; " + bits[-1]
        cards[c["name"]] = card
    return cards


def story_prompt(scene, cards, genre=""):
    """What Cloudflare gets: who the characters are and the rules FIRST, then the scene.
    Only characters named in the scene are listed (FLUX reads ~250 words)."""
    def names(n):   # "வானதி (Vaanathi)" -> ["வானதி (Vaanathi)", "வானதி", "Vaanathi"]
        return [n] + [x.strip(" '\"") for x in re.split(r"[()]", n) if x.strip(" '\"")]
    present = [n for n in cards if any(re.search(rf"(?<!\w){re.escape(a)}(?!\w)", scene) for a in names(n))]
    kind = {"horror": "Tamil horror story", "doomsday": "Tamil survival story", "adventure": "Tamil adventure story",
            "real lives": "Tamil history story"}.get(genre, "Tamil family drama")
    head = f"One picture for a YouTube {kind} video. Same characters, same faces and same clothes in every picture. "
    if present:
        def label(n):   # the picture model cannot read Tamil letters: use the English name
            return next((a for a in names(n)[1:] if re.fullmatch(r"[A-Za-z .'\-]+", a)), n)
        head += "Characters: " + " | ".join(f"{label(n)} = {cards[n]}" for n in present) + ". "
    rules = ("Rules: only the named people, every head fully inside the frame with space above, "
             "five fingers on each hand, natural bodies, no text or letters. ")
    return head + rules + "Scene: " + scene
