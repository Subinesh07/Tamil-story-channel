"""Art-style previews: the same 2 scenes in 3 candidate house styles -> previews/styles/."""
import logging
from pathlib import Path

from image_provider import get_provider

logging.basicConfig(level=logging.INFO)
OUT = Path(__file__).resolve().parent.parent / "previews" / "styles"
OUT.mkdir(parents=True, exist_ok=True)

from config import IMAGE_STYLE, STYLE_PREFIX
SCENE = ("Kavin, a 30-year-old Tamil man with short wavy black hair, round glasses, a thin moustache and a smooth "
         "shaved chin, navy jacket over a beige shirt, drives a car on a misty village road, seen from the front "
         "through the windshield; Oviya, a 27-year-old Tamil woman with long black hair and a green kurta, sits "
         "calmly in the passenger seat beside him looking ahead. Both faces fully in frame. ")
SCENES = {"car": SCENE}
STYLES = {"fixed": None}
prov = get_provider()
for s_name, style in STYLES.items():
    for sc_name, scene in SCENES.items():
      for k in range(3):
        out = OUT / f"{s_name}_{sc_name}_{k}.png"
        try:
            out.write_bytes(prov.generate(STYLE_PREFIX + scene + IMAGE_STYLE, seed=7 + k))
            logging.info("made %s", out.name)
        except Exception as e:
            logging.warning("%s failed: %s", out.name, str(e)[:150])
