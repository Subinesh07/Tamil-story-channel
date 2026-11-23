"""Art-style previews: the same 2 scenes in 3 candidate house styles -> previews/styles/."""
import logging
from pathlib import Path

from image_provider import get_provider

logging.basicConfig(level=logging.INFO)
OUT = Path(__file__).resolve().parent.parent / "previews" / "styles"
OUT.mkdir(parents=True, exist_ok=True)

SCENES = {
    "pair": ("a 55-year-old South Indian mother (grey hair in a bun, maroon cotton saree) and her 25-year-old son "
             "(short black hair, thin moustache only, clean-shaven chin, plain white shirt), talking in their "
             "small Tamil Nadu village house at night"),
    "girl": ("a 19-year-old Tamil college girl (long single braid, mustard churidar) looking worried, "
             "standing near a village temple wall at dusk"),
}
STYLES = {
    "P_painted": '2D digital painting, semi-realistic illustrated Tamil drama art, smooth painterly shading, clean soft outlines, rich but natural colours. NILA FACE DESIGN for every character: soft oval face, high rounded cheekbones, large expressive deep-brown almond eyes with a bright catch-light, thick defined eyebrows, straight nose with a softly rounded tip, full lips, warm brown skin. Signature lighting: cool blue moonlight from a window on one side and warm orange lantern glow on the other. Every character wears a clearly visible small silver crescent-moon pendant on a thin chain. Detailed Tamil Nadu home or street background. no text, no letters, no watermark',
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
