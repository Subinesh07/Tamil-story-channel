# Nila Kathaigal (நிலா கதைகள்) — automated Tamil story channel

## 🎛️ Control panel (works without Claude)

Everything runs **by itself on GitHub** every 6 hours: stories are written about a week ahead and
videos are made and scheduled up to 3 days before their slot. You never need to press anything.
Use these buttons only if you want something to happen **now**. Open the link, press
**Run workflow** (top right; in the GitHub phone app: ⋯ → Run workflow), then the green button.

**👉 [Open the status page](https://subinesh07.github.io/Tamil-story-channel/status.html)** – shows every video's progress, any problem and what to press to fix it.

| Button | What it does | Time |
|---|---|---|
| [▶️ Make the next video now](https://github.com/Subinesh07/Tamil-story-channel/actions/workflows/produce.yml) | Voices (Leda), pictures, renders, checks and schedules the next story | 20–40 min |
| [✍️ Write stories now](https://github.com/Subinesh07/Tamil-story-channel/actions/workflows/generate.yml) | Writes the next story parts (quality-checked) | 10–30 min |
| [🔑 Check all keys](https://github.com/Subinesh07/Tamil-story-channel/actions/workflows/check-keys.yml) | Confirms Gemini, Leda, Cloudflare, YouTube work | 1 min |
| [🖼️ Redo a thumbnail](https://github.com/Subinesh07/Tamil-story-channel/actions/workflows/redo-thumbnail.yml) | Makes the thumbnail of an uploaded story again (enter its id) | 2 min |
| [📅 Schedule](https://github.com/Subinesh07/Tamil-story-channel/blob/main/SCHEDULE.md) | What goes out when | – |
| [🛡️ Problems & fixes log](https://github.com/Subinesh07/Tamil-story-channel/blob/main/docs/PROBLEMS_AND_FIXES.md) | Every problem found and the check that now prevents it | – |

If a run fails, GitHub emails the repository owner. Nothing ever costs money: when a free limit is
used up, the run waits and continues after the daily reset.

---

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


## Everyday use: one tap from your phone
Install the **GitHub** app (Play Store or App Store), sign in, open **Tamil-story-channel → Actions**,
pick a workflow, then tap **Run workflow**.

| Workflow | When it runs by itself | What you get |
|---|---|---|
| **Generate stories** | every 6 hours | new stories in `stories.csv` and the schedule in `SCHEDULE.md` |
| **Produce video** | daily 11:00 IST | next story uploaded as private, scheduled for 19:00, plus a **community post issue** |
| **Competitor report** | Mondays 09:00 IST | `reports/competitors-DATE.md` plus a notification issue |
| **Test pipeline** | only when you run it | a short test video; tick *upload* to send it to YouTube as private |

**Community post and poll:** YouTube doesn't let apps publish these, so each day the automation
opens a GitHub issue with a ready-made post and poll. Copy it into **YouTube Studio → Create → Post**.
It takes about 30 seconds, and the human touch also helps against the "reused content" flag.

**Competitors:** list channel links or @handles in `competitors.txt` (one per line). The token
must include the `youtube.readonly` permission.

**Background music (optional):** put a royalty-free track at `assets/music.mp3` (for example from
YouTube Studio → Audio Library). It's mixed in quietly under the narration.

**Branding:** logo and banner are in `assets/brand/` (made with `python src/brand_assets.py`).
Upload them in YouTube Studio → Customisation → Branding.

## Weekly series plan
**Now:** the series already running finish in full on their old days
(Mon adventure, Tue horror, Wed + Sat family serial, Thu real lives, Fri family moral, Sun adventure;
Doomsday Sat + Sun 11 AM).

**As each one ends, its day switches to the niche plan:**
| Day | Video |
|---|---|
| Mon, Wed, Fri, Sat | Horror story in 4 parts (no gore) |
| Tue, Thu, Sun | Family emotional story in 3 parts |
| Sat, Sun 11 AM | Weekend special: Doomsday-type serial, later experiments |

`src/series.py` (OLD_WEEKLY, LEGACY_SERIES, WEEKLY) holds the plan.

`series.json` holds each series' characters, planned arc and story so far, so every part continues
the last one: a recap at the start, a cliffhanger at the end, and the final part wraps it all up.
Titles end with "| series name - பகுதி N", thumbnails get a பகுதி sticker, and each description
links the previous part. When a series ends, a new one of the same genre starts automatically.

## What every video contains
Intro title card (the channel name and story title, plus a spoken welcome; 5 rotating versions),
the narrated story with Tamil subtitles, an outro card with a spoken subscribe request (5 rotating
versions), chapters in the description, an auto thumbnail (3 rotating layouts), and a unique Tamil
description. Every picture is checked by a vision model and redrawn if broken.

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
| `src/make_video.py` | Runs phases 2–6 for one story: intro, outro, chapters, thumbnail, community post |
| `src/image_check.py` | Vision checker that rejects broken or wrong images |
| `src/thumbnail.py` | Auto thumbnail with the Tamil title |
| `src/community.py` | Daily community post and poll draft |
| `src/competitors.py` | Weekly competitor report |
| `src/brand_assets.py` | Draws the logo and banner |
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

**Free backup story writers (recommended).** The story writer tries each free service in turn and
moves on when one is busy or out of free quota. Add as many as you like:

| Secret | Free key from |
|---|---|
| `OPENROUTER_API_KEY` | https://openrouter.ai/settings/keys → **Create key** (no card needed) |
| `GROQ_API_KEY` | https://console.groq.com/keys → **Create API key** (no card needed) |
| `ANTHROPIC_API_KEY` | Optional, paid. Used last |

Optional variables: `LLM_ORDER` (for example `openrouter,gemini,groq`), `STORIES_PER_RUN` (default 5).

### 2. YouTube access (one time, works on a phone)
Sign in everywhere with **the Google account that owns the channel**.

1. **Project:** open https://console.cloud.google.com/projectcreate, name it `tamil-story`, then tap **Create**.
2. **Enable YouTube:** open https://console.cloud.google.com/apis/library/youtube.googleapis.com, then tap **Enable**.
3. **Login screen:** open https://console.cloud.google.com/auth/overview and tap **Get started**. Enter app name `Tamil Story Uploader` and your email, choose **External**, then tap **Create**.
   Then open https://console.cloud.google.com/auth/audience and tap **Publish app**. If you skip this, the token **expires after 7 days**.
4. **Client:** open https://console.cloud.google.com/auth/clients/create and choose **Web application**.
   Under **Authorized redirect URIs**, add `https://developers.google.com/oauthplayground`, then tap **Create**.
   Save the Client ID as secret `YT_CLIENT_ID` and the Client secret as `YT_CLIENT_SECRET`.
5. **Refresh token:** open https://developers.google.com/oauthplayground (use "Desktop site" on a phone).
   - Tap the **⚙️ gear** and tick **Use your own OAuth credentials**. Paste the Client ID and Client secret.
   - In **Input your own scopes**, paste `https://www.googleapis.com/auth/youtube.upload`, then tap **Authorize APIs**.
   - Sign in. On "Google hasn't verified this app", tap **Advanced → Go to Tamil Story Uploader → Continue**.
   - Tap **Exchange authorization code for tokens**. Copy the **Refresh token** (starts with `1//`) into secret `YT_REFRESH_TOKEN`.

(Laptop alternative: create a **Desktop app** client instead, download it as `client_secret.json`, and run `python get_refresh_token.py`.)

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
