# Tamil Story Channel — automated pipeline

Writes original Tamil family/emotional stories, narrates them with a female Tamil voice,
illustrates 20–25 scenes, renders a 20–25 minute video with Tamil subtitles, checks it, and
uploads it to YouTube as a private video scheduled for 19:00 IST. Everything runs on GitHub
Actions; nothing runs on your laptop after setup.

```
Generate stories (twice daily)          Produce video (daily 11:00 IST, or "Run workflow")
  LLM writes story ─► self-check          next pending story
  ─► stories.csv + story_index.md         ─► edge-tts, one clip per sentence ─► timings.json
  ─► publish date ─► SCHEDULE.md          ─► Pollinations images (1 per ~50 s)
                                          ─► FFmpeg: zoom in/out, 0.4 s crossfades, ASS subtitles
                                          ─► quality gate ─► YouTube (private + publishAt)
                                          ─► stories.csv status "done" + video id
```

## Files

| Path | What it does |
|---|---|
| `src/generate_stories.py` | Phase 1. Plans and writes each story, splits long sentences, checks length, ending and originality, and builds the scene prompts |
| `src/llm.py` | Text model used for stories: Gemini (free) or Claude API |
| `src/tts.py` | Phase 2. edge-tts `ta-IN-PallaviNeural` (falls back to `ta-IN-ValluvarNeural`), with 3 retries 5 s apart, 0.25 s pauses and `timings.json` |
| `src/image_provider.py` | Phase 3. Pluggable `generate(prompt) -> PNG bytes`. Includes a Pollinations provider and an offline placeholder |
| `src/scenes.py` | Places scene changes on sentence boundaries, about one image per 40–60 s |
| `src/subtitles.py` | ASS subtitles in Noto Sans Tamil (yellow, black outline, 44 pt), plus the Tamil glyph check |
| `src/render.py` | Phase 4. zoompan clips, xfade chain, fade in and out, H.264 High yuv420p, AAC 44.1 kHz stereo, faststart |
| `src/quality.py` | Phase 5 gate |
| `src/youtube_upload.py` | Phase 6 upload |
| `src/schedule.py` | Phase 8. Assigns publish dates and writes `SCHEDULE.md` |
| `src/make_video.py` | Runs phases 2–6 for one story |
| `tests/test_sample.py` | Offline 10-second render test. Runs before every production job |
| `get_refresh_token.py` | One-time YouTube login helper |

`stories.csv` columns: `id, genre, title_ta, title_en, script_ta, scene_prompts, publish_at, status, video_id, fail_reason`.
Status flow: `pending → processing → done`, or `failed` with the reason.

## Setup: what to click

### 1. Secrets
Add each secret at **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Where to get it |
|---|---|
| `IMAGE_API_KEY` | Go to https://enter.pollinations.ai, sign in, then **Create key** and choose a **Secret** key (starts with `sk_`) |
| `LLM_API_KEY` | **Gemini (free):** https://aistudio.google.com → **Get API key** → **Create API key**. **Or Claude (paid):** https://console.anthropic.com → **API keys** |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | Step 2 below |

If you use Claude instead of Gemini, go to the **Variables** tab and add `LLM_PROVIDER` = `anthropic`.
Optional variables: `LLM_MODEL` (override the model), `STORIES_PER_RUN` (default 5).

### 2. YouTube access (one time)
1. Go to https://console.cloud.google.com and create a new project.
2. Open **APIs & Services → Library**, search **YouTube Data API v3**, and click **Enable**.
3. Open **APIs & Services → OAuth consent screen** (shown as "Google Auth Platform"):
   - Choose **External** and fill in the app name and your email.
   - Under **Audience**, click **Publish app** so the status is **In production**.
     If you skip this, the refresh token **expires after 7 days** and uploads stop.
4. Open **Clients → Create client → Desktop app → Create → Download JSON**. Rename the file to `client_secret.json`.
5. On your laptop, run:
   ```
   pip install google-auth-oauthlib
   python get_refresh_token.py
   ```
   Sign in with **the Google account that owns the channel**. On the "Google hasn't verified this app" screen, click **Advanced → Go to (app)**. Then copy the three printed values into GitHub secrets.

### 3. YouTube channel requirements
- **Verify the channel** at https://www.youtube.com/verify. Without this, uploads longer than 15 minutes are rejected.
- **API audit.** Videos uploaded through an unaudited Google Cloud project are locked to **private**, and the scheduled publish **will not make them public**. To lift this, submit the *YouTube API Services – Audit and Quota Extension* form: https://support.google.com/youtube/contact/yt_api_form
  Until it's approved, open each uploaded video in YouTube Studio at publish time and set it to Public or Scheduled.

### 4. First run
1. Open **Actions → Generate stories → Run workflow**. Set `start_date` (for example `2026-12-01`) and leave count at `0`.
   It writes stories, then continues on its own twice a day until 30 exist.
2. Open **Actions → Produce video → Run workflow**. Untick *Upload* the first time and check the video in the run's **Artifacts**.
3. Once that looks right, leave everything alone. **Produce video** runs every day at 11:00 IST and uploads that day's story for 19:00.

## Free-tier limits (as of Nov 2026; check your dashboards)

| Service | Limit | What one item uses |
|---|---|---|
| **Pollinations** (images, chosen provider) | Free daily "pollen" credits on the secret key. The amount depends on your tier (shown at enter.pollinations.ai). Anonymous use is about one request per 15 s, which is why a key is used | about 24 images per video |
| **Gemini API free tier** (stories) | Set per project and shown in AI Studio. In 2026 it has been reported anywhere from **20 to 250 requests a day** for `gemini-2.5-flash` | 5–7 requests per story, so about 3–30 stories a day. The job stops cleanly at the quota and resumes on the next run |
| **YouTube Data API** | 10,000 units a day. One upload costs about 1,600 | about 6 uploads a day at most |
| **edge-tts** | No key. Unofficial Microsoft Edge voice service and may change | about 300 sentences per video |
| **GitHub Actions** | Free and unlimited for **public** repos. Private repos get 2,000 min/month | about 25–35 min per video, so 30 videos ≈ 1,000 min |

To switch image providers, add a class with `generate(prompt) -> bytes` in `src/image_provider.py` and register it in `get_provider()`.

## Reminder list
- When `SCHEDULE.md` shows **fewer than 10 pending** stories, *Generate stories* refills to 20 automatically. If it isn't keeping up (quota), run it manually with a count, or use 15–20 over a few days.
- If a row is `failed`, read `fail_reason` in `stories.csv`. Fix it, set the status back to `pending`, then **Run workflow** with that `row_id`.
- Each week, skim one finished video's `*_subtitle_frame.png` artifact to confirm the Tamil subtitles still look right.
- Every 30 stories, read `story_index.md` and delete any premise you don't want repeated in style.

## Local test
```
sudo apt install ffmpeg fonts-noto-core
pip install -r requirements.txt
python tests/test_sample.py
```
