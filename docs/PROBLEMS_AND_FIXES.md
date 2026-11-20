# Problems found and how they are prevented

Every problem that reached (or almost reached) a video is listed here, with the automatic check that
now stops it. Newest first. Keep adding to this file whenever something new goes wrong.

| # | Date | Problem seen | Cause | Automatic prevention now |
|---|------|--------------|-------|--------------------------|
| 14 | 20 Nov | Viewer reported ~1 minute of English speech in a video | The scripts contain no English (checked), so the Leda voice itself drifted into English / instructions | **Listening check**: after every voiced passage, Gemini listens to the audio and compares it with the script; a complete English sentence (> 3 s; Tanglish words are fine), skipped/added/translated lines or spoken instructions → the passage is voiced again (up to 3 times), otherwise the video waits. Leda is also told to speak only Tamil and never translate |
| 13 | 20 Nov | English words written in A-Z letters in a script (Leda may say them the English way) | Model output | Tanglish is kept: English words in A-Z letters are automatically rewritten in Tamil letters (office → ஆபீஸ்). Nothing is rejected for Tanglish |
| 12 | 20 Nov | Doomsday Part 1 showed a purple grid with a yellow circle (test pattern) | The first attempt failed on every picture (Cloudflare rejected a setting). The code fell back to the offline **test pattern** for picture 1, saved it in the picture cache, and the next run reused it | Real videos can **never** use the test pattern or repeat a picture: a failed picture stops the video (it waits for the next run). Cached test patterns are detected and thrown away. A final **picture check** before rendering rejects test patterns, blank pictures and duplicates |
| 11 | 20 Nov | "Doomsday" word missing from title / thumbnail | Title came from the AI, series name was only at the end in Tamil | Doomsday parts always start with **"டூம்ஸ்டே 😱"** (Tamil), thumbnail title is **டூம்ஸ்டே**, and search tags include doomsday / doomsday tamil |
| 10 | 20 Nov | 7 PM thumbnail plain (no picture) | Free picture allowance ran out before the thumbnail | Thumbnail falls back to the story's most dramatic picture, never to plain; `Redo thumbnail` workflow fixes an uploaded one |
| 9 | 20 Nov | Picture allowance ran out after ~75 pictures | Cloudflare free daily limit | Pauses instead of degrading; continues after the reset (5:30 AM IST); videos are made up to 3 days ahead to spread the load |
| 8 | 20 Nov | Cloudflare rejected every picture request | We sent a `seed` setting the model does not accept | Removed; the run paused correctly instead of uploading |
| 7 | 20 Nov | Same story could be uploaded twice | A run uploaded but could not save its status (git conflict) | Before upload, recent channel uploads are checked for the same title; the status commit retries |
| 6 | 20 Nov | Script rewrite rejected every story | Our sentence separator "।" was wrongly flagged as a foreign letter; the copy check rejected ordinary genre tropes | Checker allows "।"; copy check only rejects stories that copy a specific work's plot and characters |
| 5 | 20 Nov | Scripts too bookish, flowery, slow ("hair waving in the wind…") | Weak free models wrote some scripts; style rules too loose | Only Gemini writes stories; new spoken-Tanglish rules with a style sample; every script is **scored** (spoken / pace / clear, start, middle and end) and rewritten if any score is below 7; bookish lines are converted to spoken style |
| 4 | 20 Nov | Hindi, Malayalam, Korean letters mixed into Tamil scripts | Free fallback models glitched | Foreign-letter check when a story is written (repair or reject) and again before voicing |
| 3 | 20 Nov | Doomsday Part 1 uploaded with the broken old script | It was rendered before the text was repaired | Same as #4; plus a remake waits until the old upload is deleted (`replaces:` check) |
| 2 | 20 Nov | Pollinations stopped giving free pictures | Pollinations changed to a paid balance | Free Cloudflare is the main picture source; providers are chained; quota = pause, never pay |
| 1 | 19 Nov | Thumbnail text cut off / boxes instead of English letters | Text sizing and font fallback | Text fits or shrinks; Latin font for English words |

## Checks every video passes before upload
1. Script: Gemini only, English words converted to Tamil letters (Tanglish kept), style score ≥ 7 (start, middle, end), no foreign letters, length in range, ending resolves (final parts), not a copy of a specific work.
2. Voice: Leda only (extra key first, main key second); every passage passes the **listening check** (clean Tamil, matches the script); quota = wait, never another voice.
3. Pictures: every picture real and different (no test pattern, blank or duplicate); any failure = wait.
4. Video: duration in range, subtitles match sentences, audio/video in sync, H.264/AAC format, Tamil letters render.
5. Upload: not already on YouTube (same title); a remake waits until the old video is deleted.
6. Thumbnail: curiosity layout with picture (story picture if the allowance is out).
