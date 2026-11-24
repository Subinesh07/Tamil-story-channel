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
    # YouTube Analytics permission
    if os.environ.get("YT_REFRESH_TOKEN"):
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from channel_tools import analytics_report
            analytics_report()
            ok("YouTube Analytics", "permission works")
        except Exception as e:
            bad("YouTube Analytics", str(e)[:150])
    # YouTube token: upload + readonly
    try:
        from competitors import client
        ch = client().channels().list(part="snippet,statistics", mine=True).execute()["items"][0]
        ok("YouTube", f"token works for '{ch['snippet']['title']}' "
           f"({ch['statistics'].get('subscriberCount', '?')} subscribers, "
           f"{ch['statistics'].get('videoCount', '?')} videos)")
    except Exception as e:
        bad("YouTube", str(e)[:200])
    # Cloudflare (free pictures): every account, with a 1-step test picture to show today's allowance
    for sfx in ("", "_2", "_3"):
        a, t = os.environ.get("CF_ACCOUNT_ID" + sfx, "").strip(), os.environ.get("CF_API_TOKEN" + sfx, "").strip()
        label = "Cloudflare pictures" + (f" (account {sfx[1:]})" if sfx else " (account 1)")
        if not (a and t):
            if not sfx:
                bad(label, "CF_ACCOUNT_ID / CF_API_TOKEN not set")
            continue
        try:
            r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{a}/ai/run/@cf/black-forest-labs/flux-1-schnell",
                              headers={"Authorization": f"Bearer {t}"}, json={"prompt": "a full moon", "steps": 1},
                              timeout=60)
            if r.status_code == 200:
                ok(label, "works, pictures available now")
            elif r.status_code == 429 or "daily free allocation" in r.text:
                ok(label, "key works, but today's free allowance is used up (comes back about 24 h after it ran out)")
            else:
                bad(label, f"HTTP {r.status_code}: {r.text[:120]} - check the account id and that the token has Workers AI permission")
        except Exception as e:
            bad(label, str(e)[:120])
    # Facebook Page (Reels)
    pid, ptok = os.environ.get("FB_PAGE_ID", "").strip(), os.environ.get("FB_PAGE_TOKEN", "").strip()
    if ptok:
        try:
            # the Page key knows its own Page: no need for a separate (easy to mistype) id
            pid = str(requests.get("https://graph.facebook.com/v21.0/me", params={"access_token": ptok}, timeout=30).json().get("id", pid))
            r = requests.get(f"https://graph.facebook.com/v21.0/{pid}", params={"fields": "name,fan_count", "access_token": ptok}, timeout=30)
            d = requests.get("https://graph.facebook.com/v21.0/debug_token", params={"input_token": ptok, "access_token": ptok}, timeout=30).json().get("data", {})
            if r.status_code == 200:
                exp = d.get("expires_at", 0)
                ok("Facebook Page", f"{r.json().get('name')} | key expires: {'never' if not exp else exp} | permissions: {', '.join(d.get('scopes', []))}")
            else:
                me = requests.get("https://graph.facebook.com/v21.0/me", params={"fields": "id,name", "access_token": ptok}, timeout=30).json()
                info = (f"key belongs to '{me.get('name')}' (type {d.get('type')}); "
                        f"page id in FB_PAGE_ID {'matches' if str(me.get('id')) == pid else 'does NOT match'} the key's own id")
                bad("Facebook Page", info)
        except Exception as e:
            bad("Facebook Page", str(e)[:150])
    # Pollinations
    k = os.environ.get("IMAGE_API_KEY", "").strip()
    (ok if k else bad)("Pollinations", "IMAGE_API_KEY set" if k else "IMAGE_API_KEY not set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
