"""Make sample thumbnails with real AI pictures into previews/ (to judge the style)."""
import sys

import thumb_v2
from config import ROOT
from image_provider import get_provider
from thumbnail import THUMB_STYLE

OUT = ROOT / "previews"
SAMPLES = [
    ("family serial", "2", "Split composition: LEFT half: an elderly Tamil mother in a simple cotton saree sitting alone and crying on her suitcase inside a big airport; RIGHT half: the same mother now smiling proudly in a rich silk saree with gold jewellery beside a black luxury car, her shocked son in the background",
     {"line1": "அம்மாவை தனியாக ஏர்போர்ட்டில் விட்ட மகன்…", "line2": "கடைசியில் நடந்தது என்ன?", "ribbon": "கோடீஸ்வரியாக திரும்பி வந்த அம்மா!"}),
    ("horror", "1", "Night, misty Tamil Nadu ghat road: close-up of a terrified bus conductor in khaki uniform holding a ticket machine in the foreground, behind him an old government town bus with dim lights, a pale woman in a white saree sitting alone at the last window seat, eerie blue and red lighting",
     {"title": "கடைசி பேருந்து", "tagline": "14 பயணிகள்… 15 டிக்கெட் யாருக்கு?"}),
    ("family serial", "", "Split composition: LEFT half: a young Tamil woman in a simple churidar laughing with a car driver in uniform beside a taxi; RIGHT half: the same man in an expensive suit stepping out of a mansion with bodyguards, the woman staring at him in shock",
     {"line1": "டிரைவர் என்று காதலித்தாள்…", "line2": "அவன் யார் என்று தெரிந்ததும்..!"}),
    ("adventure", "3", "A young Tamil man and a girl with a torch standing small at the entrance of a gigantic ancient temple cave, huge stone statue eyes glowing gold in the darkness above them, dramatic light rays, sense of discovery and danger",
     {"line1": "மலைக்கோயிலுக்குள் ஒளிந்திருந்த ரகசியம்…", "line2": "உள்ளே என்ன இருந்தது?"}),
]


DOOMSDAY = [
    ("horror", "1", "Chennai Marina beach at night, the whole sky blood red and violet with a gigantic glowing solar storm swirling above the sea, city buildings going dark one by one, close-up in the foreground of a terrified young Tamil woman scientist with glasses holding a tablet and her scared little brother clutching her arm, epic disaster movie scale",
     {"title": "டூம்ஸ்டே", "tagline": "சென்னைக்கு இன்னும் 7 நாள் தான்!"}),
    ("family serial", "", "Split composition: LEFT half: a normal busy Chennai street in bright daylight with buses and people; RIGHT half: the same street at night completely dark and empty, a red sky, one Tamil family with torches standing together in fear",
     {"line1": "உலகம் இருட்டாக 7 நாள்…", "line2": "யாருக்கும் தெரியாத ரகசியம்!", "ribbon": "டூம்ஸ்டே தொடர் ஆரம்பம்!"}),
]


def main():
    OUT.mkdir(exist_ok=True)
    prov = get_provider()
    import os
    samples = DOOMSDAY if os.environ.get("SAMPLE") == "doomsday" else SAMPLES
    for i, (genre, part, scene, texts) in enumerate(samples):
        bg = OUT / f"bg_{i}.png"
        bg.write_bytes(prov.generate(f"{scene}. South Indian setting. {THUMB_STYLE}", seed=4242 + i))
        prefix = "doomsday" if samples is DOOMSDAY else "thumb"
        path, layout = thumb_v2.make(bg, texts, OUT / f"{prefix}_{i}.jpg", genre, i, part)
        bg.unlink()
        print("made", path, layout)
    return 0


def layout_name(genre, i):
    c = thumb_v2.GENRE_LAYOUTS.get(genre, list(thumb_v2.LAYOUTS))
    return c[i % len(c)]


if __name__ == "__main__":
    sys.exit(main())
