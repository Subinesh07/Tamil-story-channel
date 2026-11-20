"""Quick health check of every key (tiny requests only; writes no stories or videos)."""
import os
import sys

import requests


def ok(name, msg):
    print(f"✅ {name}: {msg}")


def bad(name, msg):
    print(f"❌ {name}: {msg}")


def main():
    # Gemini: listing models costs no quota
    k = os.environ.get("LLM_API_KEY", "").strip()
    if not k:
        bad("Gemini", "LLM_API_KEY not set")
    else:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         headers={"x-goog-api-key": k}, params={"pageSize": 200}, timeout=30)
        names = [m["name"] for m in r.json().get("models", [])] if r.ok else []
        (ok if r.ok else bad)("Gemini", f"{len(names)} models, voice model "
                              f"{'found' if any('tts' in n for n in names) else 'NOT found'}" if r.ok
                              else f"HTTP {r.status_code}")
    # Extra Leda voice key(s)
    for name in ("VOICE_API_KEY", "VOICE_API_KEY_2"):
        v = os.environ.get(name, "").strip()
        if not v:
            if name == "VOICE_API_KEY":
                bad("Leda extra key", "VOICE_API_KEY not set")
            continue
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         headers={"x-goog-api-key": v}, params={"pageSize": 200}, timeout=30)
        names = [m["name"] for m in r.json().get("models", [])] if r.ok else []
        good = r.ok and any("tts" in n for n in names)
        (ok if good else bad)(f"Leda extra key ({name})",
                              "works, Leda voice model found" if good else f"HTTP {r.status_code} / no voice model")
    # Recent uploads and their status (what is scheduled on the channel right now)
    if os.environ.get("YT_REFRESH_TOKEN"):
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from competitors import client
            yt = client()
            pl = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0][
                "contentDetails"]["relatedPlaylists"]["uploads"]
            ids = [i["contentDetails"]["videoId"] for i in yt.playlistItems().list(
                part="contentDetails", playlistId=pl, maxResults=10).execute().get("items", [])]
            ch = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
            print(f"📊 CHANNEL | subscribers {ch.get('subscriberCount')} | views {ch.get('viewCount')} | "
                  f"videos {ch.get('videoCount')}")
            for v in yt.videos().list(part="snippet,status,statistics,contentDetails",
                                      id=",".join(ids)).execute().get("items", []):
                st, stat = v["status"], v.get("statistics", {})
                when = st.get("publishAt", "")[:16] or v["snippet"]["publishedAt"][:16]
                print(f"📺 {v['id']} | {st['privacyStatus']} | {when} | views {stat.get('viewCount', 0)} | "
                      f"likes {stat.get('likeCount', 0)} | comments {stat.get('commentCount', 0)} | "
                      f"{v['contentDetails']['duration']} | {v['snippet']['title'][:60]}")
        except Exception as e:
            bad("Upload list", str(e)[:120])
    # Is the broken early Doomsday upload deleted?
    if os.environ.get("YT_REFRESH_TOKEN"):
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from competitors import client
            items = client().videos().list(part="status", id="6kWHO7Obyek").execute().get("items", [])
            (bad if items else ok)("Broken Doomsday upload",
                                   "still on YouTube - delete it in Studio" if items else "deleted")
        except Exception as e:
            bad("Broken Doomsday upload", str(e)[:120])
    # OpenRouter: one tiny request to a free model
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        bad("OpenRouter", "OPENROUTER_API_KEY not set")
    else:
        sys.path.insert(0, os.path.dirname(__file__))
        from llm import openrouter_models
        models = openrouter_models(k)
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          headers={"Authorization": f"Bearer {k}"},
                          json={"model": models[0], "max_tokens": 20,
                                "messages": [{"role": "user", "content": "Say வணக்கம் in one word."}]},
                          timeout=90) if models else None
        if r is not None and r.ok:
            ok("OpenRouter", f"free model {models[0]} answered: "
               f"{r.json()['choices'][0]['message']['content'][:40]!r}")
        else:
            bad("OpenRouter", f"{len(models)} free models; test call: "
                f"{'HTTP ' + str(r.status_code) + ' ' + r.text[:120] if r is not None else 'no model'}")
        kr = requests.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {k}"}, timeout=30)
        if kr.ok:
            d = kr.json().get("data", {})
            print(f"   OpenRouter key: free tier={d.get('is_free_tier')}, usage=${d.get('usage', 0)}, "
                  f"limit={d.get('limit')}")
    # Groq
    k = os.environ.get("GROQ_API_KEY", "").strip()
    if not k:
        print("⚪ Groq: GROQ_API_KEY not set (optional)")
    else:
        r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {k}"}, timeout=30)
        (ok if r.ok else bad)("Groq", f"{len(r.json().get('data', []))} models" if r.ok else f"HTTP {r.status_code}")
    # YouTube token: upload + readonly
    try:
        from competitors import client
        ch = client().channels().list(part="snippet,statistics", mine=True).execute()["items"][0]
        ok("YouTube", f"token works for '{ch['snippet']['title']}' "
           f"({ch['statistics'].get('subscriberCount', '?')} subscribers, "
           f"{ch['statistics'].get('videoCount', '?')} videos)")
    except Exception as e:
        bad("YouTube", str(e)[:200])
    # Cloudflare (free pictures)
    a, t = os.environ.get("CF_ACCOUNT_ID", "").strip(), os.environ.get("CF_API_TOKEN", "").strip()
    if a and t:
        try:
            r = requests.get(f"https://api.cloudflare.com/client/v4/accounts/{a}/ai/models/search?per_page=1",
                             headers={"Authorization": f"Bearer {t}"}, timeout=30)
            (ok if r.status_code == 200 else bad)("Cloudflare pictures",
                                                  "works (free 10,000 units/day)" if r.status_code == 200
                                                  else f"HTTP {r.status_code}: check the token has Workers AI permission")
        except Exception as e:
            bad("Cloudflare pictures", str(e)[:120])
    else:
        bad("Cloudflare pictures", "CF_ACCOUNT_ID / CF_API_TOKEN not set")
    # Pollinations
    k = os.environ.get("IMAGE_API_KEY", "").strip()
    (ok if k else bad)("Pollinations", "IMAGE_API_KEY set" if k else "IMAGE_API_KEY not set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
