"""Phase 2: one edge-tts clip per sentence, exact timings, one narration track."""
import asyncio
import json
import logging

from config import (SENTENCE_PAUSE, TTS_RATE, TTS_RETRIES, TTS_RETRY_WAIT, VOICE_FALLBACK,
                    VOICE_PRIMARY)
from ffutil import ffprobe_duration, run

log = logging.getLogger(__name__)
CONCURRENCY = 4


class TTSError(RuntimeError):
    pass


async def _synth_one(text, voice, out_path):
    import edge_tts  # imported lazily so tests run without it
    last = None
    for attempt in range(1, TTS_RETRIES + 1):
        try:
            await edge_tts.Communicate(text, voice, rate=TTS_RATE).save(str(out_path))
            if out_path.exists() and out_path.stat().st_size > 1000:
                return
            last = "empty audio"
        except Exception as e:  # network / service errors
            last = repr(e)
        log.warning("TTS attempt %d/%d failed for '%s…': %s", attempt, TTS_RETRIES, text[:20], last)
        if attempt < TTS_RETRIES:
            await asyncio.sleep(TTS_RETRY_WAIT)
    raise TTSError(f"TTS failed after {TTS_RETRIES} tries: {last}")


async def _synth_all(sentences, voice, clip_dir):
    sem = asyncio.Semaphore(CONCURRENCY)
    async def job(i, s):
        async with sem:
            await _synth_one(s, voice, clip_dir / f"s{i:04d}.mp3")
    await asyncio.gather(*(job(i, s) for i, s in enumerate(sentences)))


def pick_voice(sentences, clip_dir):
    """Use the female voice; switch the whole story to the fallback only if it is unavailable."""
    for voice in (VOICE_PRIMARY, VOICE_FALLBACK):
        try:
            asyncio.run(_synth_one(sentences[0], voice, clip_dir / "s0000.mp3"))
            return voice
        except TTSError as e:
            log.warning("Voice %s unavailable: %s", voice, e)
    raise TTSError("Both Tamil voices failed")


def synthesize(sentences, clip_dir):
    clip_dir.mkdir(parents=True, exist_ok=True)
    voice = pick_voice(sentences, clip_dir)
    log.info("Using voice %s for %d sentences", voice, len(sentences))
    asyncio.run(_synth_all(sentences, voice, clip_dir))
    return [clip_dir / f"s{i:04d}.mp3" for i in range(len(sentences))], voice


def build_narration(clips, sentences, work_dir, lead_in=0.5):
    """Convert clips to WAV, measure them, join with 0.25 s pauses, write timings.json."""
    wav_dir = work_dir / "wav"
    wav_dir.mkdir(parents=True, exist_ok=True)
    silence = wav_dir / "pause.wav"
    lead = wav_dir / "lead.wav"
    for path, secs in ((silence, SENTENCE_PAUSE), (lead, lead_in)):
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", f"{secs}", "-c:a", "pcm_s16le", str(path)])

    timings, t = [], lead_in
    concat_lines = [f"file '{lead.name}'"]
    for i, (clip, text) in enumerate(zip(clips, sentences)):
        wav = wav_dir / f"s{i:04d}.wav"
        run(["ffmpeg", "-y", "-i", str(clip), "-ar", "44100", "-ac", "2",
             "-c:a", "pcm_s16le", str(wav)])
        d = ffprobe_duration(wav)
        timings.append({"index": i, "start": round(t, 3), "end": round(t + d, 3), "text": text})
        t += d
        concat_lines.append(f"file '{wav.name}'")
        if i < len(clips) - 1:
            concat_lines.append(f"file '{silence.name}'")
            t += SENTENCE_PAUSE
    # tail so the fade-out never cuts the last word
    concat_lines.append(f"file '{lead.name}'")
    concat_lines.append(f"file '{lead.name}'")
    t += 2 * lead_in

    lst = wav_dir / "concat.txt"
    lst.write_text("\n".join(concat_lines), encoding="utf-8")
    narration = work_dir / "narration.wav"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(narration)])
    total = ffprobe_duration(narration)
    data = {"total": round(total, 3), "pause": SENTENCE_PAUSE, "sentences": timings}
    (work_dir / "timings.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    return narration, data
