"""Map scene images onto sentence boundaries (about one image per 40-60 s).

With intro/outro, the first and last sentences get their own title-card scenes.
"""
import logging

from config import SECONDS_PER_IMAGE_MAX, SECONDS_PER_IMAGE_MIN

log = logging.getLogger(__name__)


def _cut_time(sents, i):
    """Middle of the pause before sentence i."""
    return (sents[i - 1]["end"] + sents[i]["start"]) / 2


def plan_scenes(timings, n_prompts, n_scenes=None, intro=0, outro=0, marks=None, min_secs=8.0):
    """Return dicts: kind (intro/story/outro), prompt_index, first, last, start, end, duration."""
    sents, total = timings["sentences"], timings["total"]
    # intro / outro = how many leading / trailing sentences are the intro / outro
    lo = intro if len(sents) - intro - outro >= 1 else 0
    hi = len(sents) - (outro if len(sents) - lo - outro >= 1 else 0)   # story = sents[lo:hi]
    story_start = 0.0 if lo == 0 else _cut_time(sents, lo)
    story_end = total if hi == len(sents) else _cut_time(sents, hi)
    story_len = story_end - story_start

    if marks:
        # picture changes chosen from the story itself: marks[k] = story-sentence index
        cuts, prompt_ids = [], []
        for k, m in enumerate(marks):
            idx = lo + m
            if idx >= hi or (cuts and idx <= cuts[-1]):
                continue
            if cuts and sents[idx]["start"] - sents[cuts[-1]]["start"] < min_secs:
                continue  # too short to show: keep the previous picture
            cuts.append(idx)
            prompt_ids.append(k)
        if not cuts or cuts[0] != lo:
            cuts, prompt_ids = [lo] + cuts, [0] + prompt_ids
        n_scenes = len(cuts)
        return _assemble(sents, total, lo, hi, story_start, story_end, cuts, prompt_ids)
    if n_scenes is None:
        n_scenes = round(story_len / ((SECONDS_PER_IMAGE_MIN + SECONDS_PER_IMAGE_MAX) / 2))
    n_scenes = max(1, min(n_scenes, n_prompts, hi - lo))
    per = story_len / n_scenes
    if not SECONDS_PER_IMAGE_MIN <= per <= SECONDS_PER_IMAGE_MAX and n_scenes == n_prompts:
        log.warning("Each image covers %.0f s (target %d-%d s)", per,
                    SECONDS_PER_IMAGE_MIN, SECONDS_PER_IMAGE_MAX)

    cuts = [lo]
    for k in range(1, n_scenes):
        ideal = story_start + k * per
        best = min(range(cuts[-1] + 1, hi - (n_scenes - k) + 1),
                   key=lambda i: abs(sents[i]["start"] - ideal))
        cuts.append(best)
    prompt_ids = ([0] if n_scenes == 1 else
                  [round(k * (n_prompts - 1) / (n_scenes - 1)) for k in range(n_scenes)])

    return _assemble(sents, total, lo, hi, story_start, story_end, cuts, prompt_ids)


def _assemble(sents, total, lo, hi, story_start, story_end, cuts, prompt_ids):
    scenes = []
    if lo:
        scenes.append({"kind": "intro", "prompt_index": prompt_ids[0], "first": 0,
                       "last": lo - 1, "start": 0.0})
    for k, first in enumerate(cuts):
        last = (cuts[k + 1] - 1) if k + 1 < len(cuts) else hi - 1
        start = story_start if k == 0 else _cut_time(sents, first)
        scenes.append({"kind": "story", "prompt_index": prompt_ids[k], "first": first,
                       "last": last, "start": start})
    if hi < len(sents):
        scenes.append({"kind": "outro", "prompt_index": prompt_ids[-1], "first": hi,
                       "last": len(sents) - 1, "start": story_end})
    for k, s in enumerate(scenes):
        s["end"] = scenes[k + 1]["start"] if k + 1 < len(scenes) else total
        s["duration"] = round(s["end"] - s["start"], 3)
    return scenes
