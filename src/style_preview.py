"""Art-style previews: the same 2 scenes in 3 candidate house styles -> previews/styles/."""
import logging
from pathlib import Path

from image_provider import get_provider

logging.basicConfig(level=logging.INFO)
OUT = Path(__file__).resolve().parent.parent / "previews" / "styles"
OUT.mkdir(parents=True, exist_ok=True)

SCENES = {
    "sample": ("a 55-year-old South Indian mother in a cotton saree with grey hair in a bun and her "
               "25-year-old son with a moustache, in their small Tamil Nadu village house at night"),
}
STYLES = {
    "B_tanjore": ("in the style of a modern Tanjore painting: rich flat jewel colours (deep red, emerald, "
                  "royal blue), bold dark outlines, embossed gold-leaf ornamental border and gold details, "
                  "flat decorative background, expressive faces, traditional Tamil art made modern, "
                  "no text, no letters, no watermark"),
    "C_shadow": ("in the style of Tholpavakoothu shadow-puppet cinema: characters as intricately cut translucent "
                 "leather puppets with coloured dye and perforated patterns, backlit by a warm lamp behind a "
                 "white cloth screen, dramatic silhouettes and glowing colours, deep shadows, theatrical, "
                 "no text, no letters, no watermark"),
    "D_papercut": ("as a moonlit layered paper-cut diorama: scene built from many layers of cut paper with "
                   "visible depth and soft shadows between layers, handcrafted paper texture, cool silver-blue "
                   "moonlight with warm lamp accents, a full moon visible somewhere in the scene, "
                   "storybook craft look, no text, no letters, no watermark"),
}

prov = get_provider()
for s_name, style in STYLES.items():
    for sc_name, scene in SCENES.items():
        out = OUT / f"{s_name}_{sc_name}.png"
        try:
            out.write_bytes(prov.generate(f"{scene}, {style}", seed=7))
            logging.info("made %s", out.name)
        except Exception as e:
            logging.warning("%s failed: %s", out.name, str(e)[:150])
