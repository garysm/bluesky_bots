# 02 Live stream

Listen to Bluesky in real time through Jetstream and keep only the posts connected to your watch list or mentioning a leader.

Needs: `websockets`. No login, no model.

## The stream

- Endpoint: `wss://jetstream.us-east.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents`
- Subprotocol: `xrpc.v1.json`
- Query parameters: `collections` (repeatable), `dids` (repeatable, up to 10,000), `kinds`, `cursor`

Each message has the event under `payload`:

```
payload: did, collection, rkey, operation ("create" | "update" | "delete"),
         seq, time, cid, rev, record
record (post):   text, createdAt, langs, reply?{parent{uri,cid}, root{uri,cid}}, embed?
record (repost): createdAt, subject{uri, cid}
```

A delete has no `record`. A post's address is `at://{did}/{collection}/{rkey}`.

## Consumer with reconnect

```python
import asyncio, json
from urllib.parse import urlencode
import websockets

HOST = "wss://jetstream.us-east.bsky.network"
PATH = "/xrpc/network.bsky.jetstream.subscribeEvents"

def build_url(collections, dids=(), cursor=None):
    q = [("collections", c) for c in collections]
    q += [("dids", d) for d in dids]
    q.append(("kinds", "commit"))
    if cursor is not None:
        q.append(("cursor", str(cursor)))
    return f"{HOST}{PATH}?{urlencode(q)}"

async def consume(collections, handle, dids=(), cursor=None):
    """Call handle(event) for every commit; reconnect from the last seq on failure."""
    backoff = 1
    while True:
        try:
            url = build_url(collections, dids, cursor)
            async with websockets.connect(url, subprotocols=["xrpc.v1.json"]) as ws:
                backoff = 1
                async for frame in ws:
                    event = json.loads(frame)["payload"]
                    await handle(event)
                    cursor = event["seq"]
        except (websockets.ConnectionClosed, OSError):
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
```

## Keep only relevant events

```python
def did_of(at_uri: str) -> str:
    return at_uri.split("/")[2]

def is_relevant(event, watch: set[str], leader_rx) -> bool:
    if event["operation"] == "delete":
        return True                      # always keep deletes so they can be honored
    rec = event.get("record") or {}
    if event["did"] in watch:
        return True
    if event["collection"] == "app.bsky.feed.repost":
        return did_of(rec["subject"]["uri"]) in watch
    if leader_rx.search(rec.get("text", "")):
        return True
    reply = rec.get("reply")
    if reply and {did_of(reply["parent"]["uri"]), did_of(reply["root"]["uri"])} & watch:
        return True
    quoted = (rec.get("embed") or {}).get("record") or {}
    quoted = quoted.get("record", quoted)    # quote-with-media nests one level deeper
    return "uri" in quoted and did_of(quoted["uri"]) in watch
```

`watch` is the set of DIDs on your watch list. `leader_rx` is a compiled regex of leader names.

## Write kept events to hourly files

```python
import re
from datetime import datetime, timezone
from pathlib import Path

RAW = Path("data/raw")
RAW.mkdir(parents=True, exist_ok=True)
WATCH = {"did:plc:z72i7hdynmk6r22z27h6tvur"}          # DIDs from your watch list
LEADER_RX = re.compile(r"\b(schumer|jeffries)\b", re.I)

async def handle(event):
    if not is_relevant(event, WATCH, LEADER_RX):
        return
    hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    with open(RAW / f"{hour}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
```

Run it (in a script, not a notebook):

```python
asyncio.run(consume(["app.bsky.feed.post", "app.bsky.feed.repost"], handle))
```

Each line of `data/raw/<hour>.jsonl` is one event. [04 Storage](04-storage.md) loads those files into DuckDB.

## Good to know

- **Volume.** Posts plus reposts arrived at roughly 60 events per second in testing. The filter keeps a small fraction.
- **Subscribe without `dids`.** Replies, quotes and reposts of watch-list posts come from anyone, so take the whole stream and filter locally.
- **Resume.** `cursor` is the last `seq` you processed. Save it to a file every few seconds and pass it back on restart. It is inclusive, so one event repeats; the database's primary keys absorb that.
- **Deletes are always kept** so the loader can remove the post from your database.
- **Surname matching catches other people** with the same name. Keep the regex simple and let the labeling step decide who is meant.
- **Run it as its own process.** Notebook kernels restart; capture should not.
- Your existing `test.py` reads `event["record"]["text"]`. Reposts have no `text`, so use `.get` once you add them.
