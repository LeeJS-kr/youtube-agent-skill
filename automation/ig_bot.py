#!/usr/bin/env python3
"""Misstery Files: publish queued Instagram Reels at their slot time, then post the question comment.

Runs on GitHub Actions (.github/workflows/yt-comments.yml). Reads automation/ig_queue.json:
  [{slug, publish_at, caption, video_url, cover_url, comment}]
For each entry whose publish time has passed (and is less than 6 hours old) it checks the account's
recent posts; if no post starts with the same caption yet, it publishes the reel from video_url
(Meta downloads it), then comments the question. Safe to run many times.
Secrets: IG_USER_ID, IG_ACCESS_TOKEN
"""
import datetime, json, os, sys, time, urllib.error, urllib.parse, urllib.request

G = "https://graph.facebook.com/v23.0"
QUEUE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ig_queue.json")


def secret(k):
    v = os.environ.get(k, "").strip().strip('"').strip("'")
    if v.startswith(k + "="): v = v[len(k) + 1:].strip().strip('"').strip("'")
    if not v: sys.exit(f"secret {k} is empty")
    return v


def req(method, path, params):
    params = dict(params, access_token=secret("IG_ACCESS_TOKEN"))
    data = urllib.parse.urlencode(params).encode()
    url = f"{G}/{path}" + ("?" + data.decode() if method == "GET" else "")
    r = urllib.request.Request(url, data=None if method == "GET" else data, method=method)
    try:
        return json.load(urllib.request.urlopen(r, timeout=120))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {path}: {e.read().decode()[:400]}")


def key(text):
    return " ".join((text or "").split())[:120]


def main():
    queue = json.load(open(QUEUE, encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc)
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    due = [q for q in queue if datetime.datetime.fromisoformat(q["publish_at"]) <= now
           <= datetime.datetime.fromisoformat(q["publish_at"]) + datetime.timedelta(hours=6)]
    if not due and not manual:
        print("ig: nothing due"); return
    ig = secret("IG_USER_ID")
    me = req("GET", ig, {"fields": "username"}); print("ig: signed in as", me.get("username"))
    if not due:
        print("ig: keys OK, nothing due"); return
    recent = req("GET", f"{ig}/media", {"fields": "id,caption,permalink", "limit": "30"}).get("data", [])
    posted = {key(m.get("caption")): m for m in recent}
    failed = 0
    for q in due:
        if key(q["caption"]) in posted:
            print(f"ig {q['slug']}: already posted {posted[key(q['caption'])].get('permalink')}"); continue
        try:
            p = {"media_type": "REELS", "video_url": q["video_url"], "caption": q["caption"], "share_to_feed": "true"}
            if q.get("cover_url"): p["cover_url"] = q["cover_url"]
            for k in range(3):
                try: cid = req("POST", f"{ig}/media", p)["id"]; break
                except RuntimeError as e:
                    if k == 2 or "2207003" not in str(e): raise
                    time.sleep(20)
            for _ in range(60):
                st = req("GET", cid, {"fields": "status_code,status"})
                if st.get("status_code") == "FINISHED": break
                if st.get("status_code") in ("ERROR", "EXPIRED"): raise RuntimeError(f"processing {st}")
                time.sleep(10)
            else:
                raise RuntimeError("processing took over 10 minutes")
            mid = req("POST", f"{ig}/media_publish", {"creation_id": cid})["id"]
            link = req("GET", mid, {"fields": "permalink"}).get("permalink")
            print(f"ig {q['slug']}: posted {link}")
            if q.get("comment"):
                req("POST", f"{mid}/comments", {"message": q["comment"]}); print(f"ig {q['slug']}: comment posted")
        except Exception as e:
            failed += 1; print(f"ig {q['slug']}: FAILED {e}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
