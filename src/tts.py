"""Phase 2: natural narration with exact sentence timings.

Sentences are voiced a PARAGRAPH at a time (up to CHUNK_SENTENCES), so the intonation flows
from one sentence to the next like a real storyteller. edge-tts reports where every sentence
starts and ends inside the paragraph audio, which keeps the subtitles exact. If those
boundaries don't line up for a paragraph, that paragraph falls back to one clip per sentence.
"""
import asyncio
import json
import logging
import re

from config import (SENTENCE_PAUSE, TTS_RATE, TTS_RETRIES, TTS_RETRY_WAIT, VOICE_FALLBACK,
                    VOICE_PRIMARY)
from ffutil import ffprobe_duration, run

log = logging.getLogger(__name__)
CONCURRENCY = 4
CHUNK_SENTENCES = 6
CHUNK_CHARS = 600
PARAGRAPH_PAUSE = 0.35   # breath between paragraphs (sentences inside one flow naturally)


class TTSError(RuntimeError):
    pass


def _end_punct(s):
    s = s.strip()
    return s if re.search(r"[.!?…]$", s) else s + "."


async def _synth(text, voice, out_path, want_boundaries=False):
    """Save audio for text; return [(offset_s, duration_s, text)] sentence boundaries."""
    import edge_tts  # imported lazily so tests run without it
    last = None
    for attempt in range(1, TTS_RETRIES + 1):
        try:
            bounds = []
            with open(out_path, "wb") as f:
                comm = edge_tts.Communicate(text, voice, rate=TTS_RATE, boundary="SentenceBoundary")
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "SentenceBoundary":
                        bounds.append((chunk["offset"] / 1e7, chunk["duration"] / 1e7, chunk.get("text", "")))
            if out_path.stat().st_size > 1000:
                return bounds
            last = "empty audio"
        except Exception as e:  # network / service errors
            last = repr(e)
        log.warning("TTS attempt %d/%d failed for '%s…': %s", attempt, TTS_RETRIES, text[:20], last)
        if attempt < TTS_RETRIES:
            await asyncio.sleep(TTS_RETRY_WAIT)
    raise TTSError(f"TTS failed after {TTS_RETRIES} tries: {last}")


def make_chunks(sentences):
    """Group consecutive sentence indexes into paragraphs."""
    chunks, cur, chars = [], [], 0
    for i, s in enumerate(sentences):
        if cur and (len(cur) >= CHUNK_SENTENCES or chars + len(s) > CHUNK_CHARS):
            chunks.append(cur)
            cur, chars = [], 0
        cur.append(i)
        chars += len(s)
    if cur:
        chunks.append(cur)
    return chunks


async def _voice_chunk(k, idxs, sentences, voice, clip_dir):
    """Returns a list of pieces: (audio_path, [(sentence_idx, rel_start, rel_end_or_None)])."""
    path = clip_dir / f"c{k:04d}.mp3"
    text = " ".join(_end_punct(sentences[i]) for i in idxs)
    bounds = await _synth(text, voice, path)
    if len(bounds) == len(idxs):
        return [(path, [(i, off, off + dur) for i, (off, dur, _) in zip(idxs, bounds)])]
    log.info("Paragraph %d: %d boundaries for %d sentences; voicing sentences one by one",
             k, len(bounds), len(idxs))
    pieces = []
    for i in idxs:
        p = clip_dir / f"s{i:04d}.mp3"
        await _synth(_end_punct(sentences[i]), voice, p)
        pieces.append((p, [(i, 0.0, None)]))
    return pieces


async def _voice_all(sentences, voice, clip_dir):
    sem = asyncio.Semaphore(CONCURRENCY)
    chunks = make_chunks(sentences)

    async def job(k, idxs):
        async with sem:
            return await _voice_chunk(k, idxs, sentences, voice, clip_dir)
    results = await asyncio.gather(*(job(k, c) for k, c in enumerate(chunks)))
    return [piece for r in results for piece in r]


def pick_voice(sentences, clip_dir):
    """Use the female voice; switch the whole story to the fallback only if it is unavailable."""
    for voice in (VOICE_PRIMARY, VOICE_FALLBACK):
        try:
            asyncio.run(_synth(_end_punct(sentences[0]), voice, clip_dir / "probe.mp3"))
            return voice
        except TTSError as e:
            log.warning("Voice %s unavailable: %s", voice, e)
    raise TTSError("Both Tamil voices failed")


def synthesize(sentences, clip_dir):
    clip_dir.mkdir(parents=True, exist_ok=True)
    voice = pick_voice(sentences, clip_dir)
    log.info("Using voice %s (rate %s) for %d sentences in paragraphs", voice, TTS_RATE, len(sentences))
    pieces = asyncio.run(_voice_all(sentences, voice, clip_dir))
    return pieces, voice


def build_narration(pieces, sentences, work_dir, lead_in=0.5):
    """Join the audio pieces, convert to timeline timings, write timings.json.

    pieces: list of (audio_path, [(sentence_idx, rel_start, rel_end_or_None)]), or a plain list
    of per-sentence audio files (one per sentence, used by the tests)."""
    if pieces and not isinstance(pieces[0], tuple):
        pieces = [(p, [(i, 0.0, None)]) for i, p in enumerate(pieces)]
    wav_dir = work_dir / "wav"
    wav_dir.mkdir(parents=True, exist_ok=True)
    lead = wav_dir / "lead.wav"
    gaps = {}
    for secs in {SENTENCE_PAUSE, PARAGRAPH_PAUSE}:
        g = wav_dir / f"gap_{int(secs * 1000)}.wav"
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{secs}",
             "-c:a", "pcm_s16le", str(g)])
        gaps[secs] = g
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{lead_in}",
         "-c:a", "pcm_s16le", str(lead)])

    found = {}
    t = lead_in
    concat = [f"file '{lead.name}'"]
    for n, (audio, marks) in enumerate(pieces):
        wav = wav_dir / f"p{n:04d}.wav"
        run(["ffmpeg", "-y", "-i", str(audio), "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(wav)])
        d = ffprobe_duration(wav)
        for i, rs, re_ in marks:
            end = d if re_ is None else min(d, re_)
            found[i] = (round(t + rs, 3), round(t + end, 3))
        t += d
        concat.append(f"file '{wav.name}'")
        if n < len(pieces) - 1:
            gap = PARAGRAPH_PAUSE if len(marks) > 1 else SENTENCE_PAUSE
            concat.append(f"file '{gaps[gap].name}'")
            t += gap
    concat += [f"file '{lead.name}'", f"file '{lead.name}'"]   # tail for the fade-out

    timings = [{"index": i, "start": found[i][0], "end": found[i][1], "text": s}
               for i, s in enumerate(sentences)]
    # subtitles stay up through the short gap to the next sentence (easier to read)
    for a, b in zip(timings, timings[1:]):
        if 0 < b["start"] - a["end"] < 0.6:
            a["end"] = round(b["start"] - 0.02, 3)

    lst = wav_dir / "concat.txt"
    lst.write_text("\n".join(concat), encoding="utf-8")
    narration = work_dir / "narration.wav"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(narration)])
    total = ffprobe_duration(narration)
    data = {"total": round(total, 3), "pause": SENTENCE_PAUSE, "sentences": timings}
    (work_dir / "timings.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return narration, data
