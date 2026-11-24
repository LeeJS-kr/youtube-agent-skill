#!/usr/bin/env python3
"""Misstery Files: post each Short's question comment once the video is public.

Runs on GitHub Actions (see .github/workflows/yt-comments.yml). Reads
automation/comment_queue.json ([{video_id, slug, publish_at, comment}]) and, for every
entry whose publish time has passed and whose video is public, posts the comment
unless the channel already left that exact comment (safe to run many times).
Pinning is not possible through the API; pin in the YouTube app.

Secrets (GitHub repo > Settings > Secrets and variables > Actions):
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
"""
import datetime, json, os, sys, urllib.error, urllib.parse, urllib.request

API = "https://www.googleapis.com/youtube/v3"
QUEUE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comment_queue.json")


def token():
    env = {k: os.environ.get(k, "").strip().strip('"').strip("'") for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")}
    for k, v in env.items():
        if v.startswith(k + "="): env[k] = v = v[len(k) + 1:].strip().strip('"').strip("'")   # pasted as NAME=value
        if not v: sys.exit(f"secret {k} is empty")
    print("client id length", len(env["YT_CLIENT_ID"]), "| secret length", len(env["YT_CLIENT_SECRET"]),
          "| refresh token length", len(env["YT_REFRESH_TOKEN"]))
    body = urllib.parse.urlencode({
        "client_id": env["YT_CLIENT_ID"], "client_secret": env["YT_CLIENT_SECRET"],
        "refresh_token": env["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    try:
        return json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=30))["access_token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"token refresh failed HTTP {e.code}: {e.read().decode()[:300]}")


def call(tok, method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {url.split('?')[0]}: {e.read().decode()[:400]}")


def main():
    queue = json.load(open(QUEUE, encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc)
    due = [q for q in queue if q.get("comment") and
           datetime.datetime.fromisoformat(q["publish_at"]) <= now <= datetime.datetime.fromisoformat(q["publish_at"]) + datetime.timedelta(days=3)]
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if not due and not manual:
        print("nothing due"); return
    tok = token()
    ch = call(tok, "GET", f"{API}/channels?part=id,snippet&mine=true")["items"][0]
    me = ch["id"]; print("signed in as", ch["snippet"]["title"])
    if not due:
        print("keys OK, nothing due"); return
    ids = ",".join(q["video_id"] for q in due)
    status = {x["id"]: x["status"]["privacyStatus"] for x in call(tok, "GET", f"{API}/videos?part=status&id={ids}")["items"]}
    failed = 0
    for q in due:
        vid = q["video_id"]
        if status.get(vid) != "public":
            print(f"{q['slug']}: not public yet ({status.get(vid)})"); continue
        try:
            threads = call(tok, "GET", f"{API}/commentThreads?part=snippet&videoId={vid}&maxResults=100&order=time")["items"]
            mine = [t for t in threads if t["snippet"]["topLevelComment"]["snippet"].get("authorChannelId", {}).get("value") == me]
            if any(t["snippet"]["topLevelComment"]["snippet"]["textOriginal"].strip() == q["comment"].strip() for t in mine):
                print(f"{q['slug']}: already commented"); continue
            call(tok, "POST", f"{API}/commentThreads?part=snippet", {"snippet": {"videoId": vid,
                 "topLevelComment": {"snippet": {"textOriginal": q["comment"]}}}})
            print(f"{q['slug']}: comment posted")
        except Exception as e:
            failed += 1; print(f"{q['slug']}: FAILED {e}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
