# 03 Backfill

Fetch history from the Bluesky AppView: one account's past posts, search results for a leader's name, profiles and account creation dates.

Needs: `httpx`. No login was used for anything on this page.

## Author history and leader search

```python
import time
from datetime import datetime, timedelta, timezone
import httpx

APPVIEW = "https://api.bsky.app/xrpc"

def paged(client, method, params, key, max_pages=500):
    cursor = None
    for _ in range(max_pages):
        q = dict(params, cursor=cursor) if cursor else params
        r = client.get(f"{APPVIEW}/{method}", params=q)
        if r.status_code == 429:
            time.sleep(30)
            continue
        r.raise_for_status()
        data = r.json()
        yield from data[key]
        cursor = data.get("cursor")
        if not cursor:
            return
        time.sleep(0.3)

def parse_ts(value: str) -> datetime:
    ts = datetime.fromisoformat(value)
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

def sort_time(post) -> datetime:
    """Search orders by the earlier of indexedAt and the author-supplied createdAt."""
    times = [parse_ts(post["indexedAt"])]
    try:
        times.append(parse_ts(post["record"]["createdAt"]))
    except (KeyError, ValueError):
        pass                               # createdAt is client-supplied and can be malformed
    return min(times)

def author_history(client, actor, start: datetime):
    """Posts and reposts by one watch-list account, newest first, back to `start`."""
    params = {"actor": actor, "limit": 100, "filter": "posts_with_replies"}
    for item in paged(client, "app.bsky.feed.getAuthorFeed", params, "feed"):
        if "reason" not in item and sort_time(item["post"]) < start:   # reposts carry a "reason"
            return
        yield item

def leader_mentions(client, query, start: datetime, end: datetime):
    """Walk backwards from `end` to `start` by moving `until`, never using a cursor."""
    until, seen, counts = end, set(), {}
    while until > start:
        params = {"q": query, "sort": "latest", "limit": 100,
                  "since": start.isoformat(), "until": until.isoformat()}
        r = client.get(f"{APPVIEW}/app.bsky.feed.searchPosts", params=params)
        if r.status_code == 429:
            time.sleep(30)
            continue
        r.raise_for_status()
        posts = r.json()["posts"]
        if not posts:
            break
        fresh = [p for p in posts if p["uri"] not in seen]
        for post in fresh:
            seen.add(post["uri"])
            day = sort_time(post).date()
            counts[day] = counts.get(day, 0) + 1
            yield post
        # `until` is matched in whole seconds and includes that second, so step in seconds.
        oldest = sort_time(posts[-1]).replace(microsecond=0)
        until = oldest if fresh and oldest < until else until - timedelta(seconds=1)
        time.sleep(0.3)
    for day in sorted(counts):
        print(day, query, counts[day])     # log per-day counts; sudden dips mean a gap

# usage
# with httpx.Client(timeout=30) as client:
#     start = datetime(2026, 9, 1, tzinfo=timezone.utc)
#     for post in leader_mentions(client, "Schumer", start, datetime.now(timezone.utc)): ...
```

## Account creation date and handle lookup

```python
def account_created(client, did: str) -> str | None:
    if did.startswith("did:plc:"):
        log = client.get(f"https://plc.directory/{did}/log/audit").json()
        return log[0]["createdAt"]         # first entry is the account's creation
    prof = client.get(f"{APPVIEW}/app.bsky.actor.getProfile", params={"actor": did}).json()
    return prof.get("createdAt")
```

```python
def resolve_did(client, handle: str) -> str:
    r = client.get(f"{APPVIEW}/app.bsky.actor.getProfile", params={"actor": handle})
    return r.json()["did"]
```

For many accounts at once use `app.bsky.actor.getProfiles` with repeated `actors` parameters, 25 at most per call.

## Good to know

- **Use `api.bsky.app`.** `public.api.bsky.app` answered search with a 403.
- **Search refuses cursors without a login.** The first page works; any request carrying `cursor` gets "403 Forbidden". `leader_mentions` avoids cursors by moving `until` backwards instead. `getAuthorFeed` paging with a cursor works normally.
- **`until` works in whole seconds** and includes that second. That is why the walker steps in seconds and skips posts it has already seen.
- **What to expect.** A 20-minute window ending 2026-11-05 00:00 UTC returned 390 unique posts for "Schumer". A full day is several hundred requests per query; plan for hours.
- **Blind spot.** If more than 100 matching posts share one second, the extras are missed.
- **Search is not guaranteed complete, and deleted posts never appear.** Compare search counts with your live capture for the same days to see how much is missing.
- **Result shape differs from Jetstream.** The record is under `post["record"]`, the author under `post["author"]`. Author feed items wrap the post as `item["post"]`, and reposts carry a `reason`. [04 Storage](04-storage.md) has a loader for this shape.
- **`createdAt` is supplied by the author's app** and can be wrong or malformed. `sort_time` takes the earlier of it and the server's `indexedAt`.
- **Account age.** The PLC audit log is the identity record itself; for `bsky.app` it matched the profile's `createdAt`.
- **If anonymous search stops working**, log in with the `atproto` package (already installed) and an app password kept in `.env`.
