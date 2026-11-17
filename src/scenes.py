"""Map scene images onto sentence boundaries (about one image per 40-60 s)."""
import logging

from config import SECONDS_PER_IMAGE_MAX, SECONDS_PER_IMAGE_MIN

log = logging.getLogger(__name__)


def plan_scenes(timings, n_prompts, n_scenes=None):
    """Return a list of dicts: prompt_index, first, last (sentence idx), start, end (seconds)."""
    sents, total = timings["sentences"], timings["total"]
    if n_scenes is None:
        target = (SECONDS_PER_IMAGE_MIN + SECONDS_PER_IMAGE_MAX) / 2
        n_scenes = round(total / target)
    n_scenes = max(1, min(n_scenes, n_prompts, len(sents)))
    per = total / n_scenes
    if not SECONDS_PER_IMAGE_MIN <= per <= SECONDS_PER_IMAGE_MAX and n_scenes == n_prompts:
        log.warning("Each image covers %.0f s (target %d-%d s)", per,
                    SECONDS_PER_IMAGE_MIN, SECONDS_PER_IMAGE_MAX)

    # choose the sentence whose start is closest to each ideal cut time
    cuts = [0]
    for k in range(1, n_scenes):
        ideal = k * per
        best = min(range(cuts[-1] + 1, len(sents) - (n_scenes - k) + 1),
                   key=lambda i: abs(sents[i]["start"] - ideal))
        cuts.append(best)

    # pick evenly spaced prompts if there are more prompts than scenes
    prompt_ids = [round(k * (n_prompts - 1) / max(1, n_scenes - 1)) for k in range(n_scenes)]
    if n_scenes == 1:
        prompt_ids = [0]

    scenes = []
    for k, first in enumerate(cuts):
        last = (cuts[k + 1] - 1) if k + 1 < len(cuts) else len(sents) - 1
        # cut in the middle of the pause before the scene's first sentence
        start = 0.0 if k == 0 else (sents[first - 1]["end"] + sents[first]["start"]) / 2
        scenes.append({"prompt_index": prompt_ids[k], "first": first, "last": last, "start": start})
    for k, s in enumerate(scenes):
        s["end"] = scenes[k + 1]["start"] if k + 1 < len(scenes) else total
        s["duration"] = round(s["end"] - s["start"], 3)
    return scenes
