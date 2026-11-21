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
    if tache:
        return "moustache only, NO beard, chin shaved"
    return "clean-shaven, no beard, no moustache"


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
