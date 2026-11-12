# 02 Live stream

Listen to Bluesky in real time through Jetstream and keep only the posts connected to your watch list or mentioning a leader.

This page is a guide, not a listing. Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed. Open it when you are stuck or want to compare.

Needs: `websockets`. No login, no model.

Read first:

- [Jetstream](https://bsky.network/docs/jetstream) in the Bluesky docs. It is the reference for everything in steps 1 to 4: hosts, filters, the event shape and resuming.
- [15 Async Python](15-async-python.md), if `async def`, `await`, `async with` and `async for` are new to you. The consumer is one coroutine.
- [Posts in-depth](https://bsky.network/docs/about-bluesky-content/posts) in the Bluesky docs, for what replies and quote posts look like inside a record. You need it in step 5.

## What you are building

One script that runs for days:

1. It opens a websocket to Jetstream and receives every new post and repost on the network.
2. It checks each event against your watch list and your leader names.
3. It appends the events it keeps to `data/raw/<hour>.jsonl`, one JSON object per line.
4. When the connection drops, it reconnects and carries on from where it stopped.

You are done when the script has run for an hour, there is one file per hour in `data/raw`, every line in them passes the rules in step 5, and switching your network off for a minute loses nothing.

## Step 1: Connect and look at the stream

**Concept.** Jetstream is Bluesky's JSON view of the network's firehose. You open one websocket and each frame you receive is one event, already decoded. The live stream needs no account and no key.

| Part | Value |
| --- | --- |
| Host | `jetstream.us-west.bsky.network` or `jetstream.us-east.bsky.network` |
| Path | `/xrpc/network.bsky.jetstream.subscribeEvents` |
| Subprotocol | `xrpc.v1.json` |

You say what you want with query parameters. Each of these is covered under "Filtering" on the [Jetstream page](https://bsky.network/docs/jetstream):

| Parameter | Meaning |
| --- | --- |
| `collections` | Record types to receive, as [NSIDs](https://atproto.com/specs/nsid) such as `app.bsky.feed.post`. Repeat the parameter for each one; up to 100. |
| `dids` | Only these accounts. Repeatable, up to 10,000. You will not use it; step 5 explains why. |
| `kinds` | `commit`, `identity`, `account` or `sync`. The `collections` filter applies to commits only, so ask for `kinds=commit` or the other kinds arrive too. |
| `cursor` | Where to resume from. Step 4. |

**Your task.** Write two things:

- `build_url(collections, dids=(), cursor=None) -> str`, which returns the full `wss://` address for a list of collections.
- A small coroutine that connects to that address and prints the first ten frames exactly as they arrive.

**Hints.**

- A repeated parameter is one `(name, value)` pair per value. [`urllib.parse.urlencode`](https://docs.python.org/3/library/urllib.parse.html#urllib.parse.urlencode) accepts a list of pairs.
- `websockets.connect(url, subprotocols=[...])` is used with `async with`, and the connection it gives you is read with `async for`. See the [websockets client reference](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html).
- `test.py` in the project root already does the smallest possible version of this for posts. Read it, then extend it.

**Check.** `build_url(["app.bsky.feed.post", "app.bsky.feed.repost"])` should return exactly:

```
wss://jetstream.us-east.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents?collections=app.bsky.feed.post&collections=app.bsky.feed.repost&kinds=commit
```

When you connect, frames arrive faster than you can read them. Posts plus reposts came at roughly 60 a second in testing.

> Older tutorials, and the [HTTP reference](https://endpoints.bsky.app/#jetstream), show a `/subscribe` path with `wantedCollections` and `wantedDids`. That is the earlier interface, and its events have a different shape (fields nested under `commit`). The same hosts still serve it. This page uses the newer `subscribeEvents` path throughout.

## Step 2: Read one event

**Concept.** Every frame is an envelope with the event under `payload`. For the commits you asked for:

```
payload: did, collection, rkey, operation ("create" | "update" | "delete"),
         seq, time, cid, rev, record
record (post):   text, createdAt, langs, reply?{parent{uri,cid}, root{uri,cid}}, embed?
record (repost): createdAt, subject{uri, cid}
```

Three facts decide how your code has to be written:

- **A delete has no `record`.** It carries only `did`, `collection` and `rkey`, which is enough to say which record is gone.
- **A repost has no `text`.** Its record points at another post through `subject`.
- **A record's address is its [AT URI](https://atproto.com/specs/at-uri-scheme):** `at://{did}/{collection}/{rkey}`. The event gives you the three parts, not the assembled address.

The full field lists are in the lexicons for [posts](https://github.com/bluesky-social/bsky/blob/main/lexicons/app/bsky/feed/post.json) and [reposts](https://github.com/bluesky-social/bsky/blob/main/lexicons/app/bsky/feed/repost.json).

**Your task.** Change your coroutine so that for each event it prints the `seq`, the operation, the AT URI, and the first 60 characters of the text when there is any. It must not crash on deletes or reposts.

**Hints.**

- `test.py` reads `event["record"]["text"]`. That raises `KeyError` on the first repost and on the first delete. `dict.get` with a default is the tool.
- Decide what "no record" should become in your code, so the lines after it do not each need their own check.

**Check.**

- It runs for a full minute without an exception.
- `seq` only ever goes up.
- Take one AT URI from your output and open `https://bsky.app/profile/<did>/post/<rkey>` in a browser. You should see the post you printed.
- Before moving on, find one reply and one quote post in your output and print their whole `record`. Compare them with [Posts in-depth](https://bsky.network/docs/about-bluesky-content/posts#replies-quote-posts-and-embeds). You will need to know where the other post's URI sits in each.

## Step 3: The consumer loop

**Concept.** Separate receiving events from deciding what to do with them. The receiving half is a coroutine, `consume`, that knows about websockets and nothing else. The deciding half is a function you pass in, `handle`, that takes one event. That way the filter and the file writing in steps 5 and 6 can change without touching the connection code, and you can test `consume` with a `handle` that only prints.

`handle` is itself a coroutine, so `consume` calls it with `await`. Nothing in this page needs `handle` to wait for anything, but a later version might (a queue, a network call), and the cost of allowing it is one keyword.

`consume` also has to remember how far it got. Every event carries a `seq`, a number that only increases. After `handle` returns, keep that event's `seq`; step 4 uses it.

**Your task.** Write:

```python
async def consume(collections, handle, dids=(), cursor=None):
    """Call handle(event) for every commit."""
```

For now it connects once and stops when the connection ends.

**Hints.**

- The event you pass to `handle` is the `payload`, not the envelope.
- Update your saved `seq` after `handle` returns, not before. Ask yourself what would be lost if `handle` raised an exception and the order were the other way round.

**Check.** Pass a `handle` that prints `event["seq"]` and run it with [`asyncio.run`](https://docs.python.org/3/library/asyncio-runner.html#asyncio.run). The numbers should scroll past, increasing.

## Step 4: Survive disconnects

**Concept.** A connection that is meant to stay open for days will drop: the server restarts, your Wi-Fi blinks, the PC sleeps. Jetstream lets you carry on from where you were. Read "Resuming where you left off" on the [Jetstream page](https://bsky.network/docs/jetstream); the short version is:

- Reconnect with `cursor=<last seq you handled>`.
- **The cursor is inclusive.** The event with that `seq` is sent again.
- **Delivery is at-least-once.** Duplicates can happen across reconnects, so whatever stores the events must be safe to run twice on the same event. In this project the database's primary keys take care of it ([04 Storage](04-storage.md)).
- **Replay only reaches back so far.** The [replay page](https://bsky.network/docs/jetstream-replay) gives 36 hours for Bluesky's own hosts. If the script is down longer than that, there is a gap, and [03 Backfill](03-backfill.md) is how you fill it.

Reconnecting at once, in a tight loop, hammers a server that may be down. Wait before each retry, and wait longer each time: one second, then two, four, and so on up to a ceiling. This is called exponential backoff.

**Your task.** Make `consume` run forever. When the connection fails, it waits, reconnects from the last `seq`, and continues.

**Hints.**

- The address has to be rebuilt on every attempt, because the cursor has changed.
- Two kinds of failure are worth catching: the connection closing (`websockets.ConnectionClosed`) and the network not being there at all (`OSError`, which covers refused connections and failed name lookups).
- Do not catch `Exception`. Think about what happens to a bug inside `handle` if you do.
- Decide where the wait goes back to one second. After a successful connect? After the first event? What does each choice do when the server accepts connections and then drops them at once?
- The wait must be `await asyncio.sleep(...)`, not `time.sleep(...)`. [15 Async Python](15-async-python.md) explains the difference.

**Check.** Run it with a `handle` that prints `seq`. Turn your network off for twenty seconds, then on again. The first `seq` printed after the reconnect should be the same as the last one printed before the drop (the cursor is inclusive), and the numbers should continue from there. Ctrl+C should still stop the script.

## Step 5: Decide what is relevant

**Concept.** You might expect to pass your watch list in `dids` and let the server filter. That would give you only what those accounts post. The replies to them, the quotes of them and the reposts of them come from anyone, so you take the whole stream and filter on your side.

The filter is one function:

```python
def is_relevant(event, watch: set[str], leader_rx) -> bool:
```

`watch` is the set of DIDs on your watch list. `leader_rx` is a compiled regular expression of leader names. These are the rules:

| The event is | Keep it? | Where to look |
| --- | --- | --- |
| a delete | always | `operation` |
| by a watch-list account | yes | `did` |
| a repost of a watch-list account's post | yes | the DID inside `record.subject.uri` |
| a repost of anyone else's post | no | |
| a post whose text matches a leader name | yes | `record.text` |
| a reply whose parent or thread root is by a watch-list account | yes | the DIDs inside `record.reply.parent.uri` and `record.reply.root.uri` |
| a quote of a watch-list account's post | yes | the DID inside `record.embed.record.uri` |
| a quote of a watch-list post that also has images or video | yes | the DID inside `record.embed.record.record.uri` |
| anything else | no | |

Why deletes are always kept: a delete event does not say what the post was, so the consumer cannot tell whether you stored it. Keeping every delete lets the loader in [04](04-storage.md) remove the post if it is there. Removing content its author deleted is one of this project's rules ([11 Guardrails](11-guardrails.md)) and one of Bluesky's [developer guidelines](https://bsky.network/docs/developer-guidelines).

**Your task.** Write `is_relevant`, and a helper `did_of(at_uri) -> str` that pulls the DID out of an AT URI.

**Hints.**

- An AT URI is `at://<did>/<collection>/<rkey>`. Split it on `/` and count which piece the DID is.
- Order matters. A delete has no record, and a repost has no text, reply or embed. Deal with those two before the checks that assume a post.
- A quote post's embed has type `app.bsky.embed.record`. A quote with media has type [`app.bsky.embed.recordWithMedia`](https://github.com/bluesky-social/bsky/blob/main/lexicons/app/bsky/embed/recordWithMedia.json), which wraps the same reference one level deeper. Both end in a dict with a `uri`. Look for a way to reduce the two shapes to one before you test it.
- Other embeds (images alone, link cards) have no `record` at all, so every lookup on the way down needs a default.
- For names, `\b` matches a word boundary and `re.I` ignores case. A surname catches other people with the same name. Keep the pattern simple and let the labeling step ([06](06-gemma-labels.md)) decide who is meant.

**Check.** These made-up events cover each row of the table. All of the assertions should pass with your function:

```python
import re

W = {"did:plc:watch"}
RX = re.compile(r"\b(schumer|jeffries)\b", re.I)
POST, REPOST = "app.bsky.feed.post", "app.bsky.feed.repost"
THEIRS = {"uri": "at://did:plc:watch/app.bsky.feed.post/abc"}       # a watch-list post
OTHER = {"uri": "at://did:plc:nobody/app.bsky.feed.post/xyz"}       # someone else's post

def ev(did, collection=POST, operation="create", **record):
    e = {"did": did, "collection": collection, "rkey": "1", "operation": operation}
    if operation != "delete":
        e["record"] = record
    return e

cases = [
    (ev("did:plc:stranger", operation="delete"), True),
    (ev("did:plc:watch", text="good morning"), True),
    (ev("did:plc:stranger", text="good morning"), False),
    (ev("did:plc:stranger", text="What is SCHUMER doing?"), True),
    (ev("did:plc:stranger", text="schumerism is not a word"), False),
    (ev("did:plc:stranger", REPOST, subject=THEIRS), True),
    (ev("did:plc:stranger", REPOST, subject=OTHER), False),
    (ev("did:plc:stranger", text="agreed", reply={"parent": OTHER, "root": THEIRS}), True),
    (ev("did:plc:stranger", text="agreed", reply={"parent": OTHER, "root": OTHER}), False),
    (ev("did:plc:stranger", text="look", embed={"record": THEIRS}), True),
    (ev("did:plc:stranger", text="look", embed={"record": {"record": THEIRS}, "media": {}}), True),
    (ev("did:plc:stranger", text="look", embed={"record": OTHER}), False),
    (ev("did:plc:stranger", text="a photo", embed={"images": []}), False),
]
for event, expected in cases:
    assert is_relevant(event, W, RX) is expected, event
print("all", len(cases), "cases pass")
```

## Step 6: Write kept events to hourly files

**Concept.** The consumer does not write to the database. DuckDB allows one writing process at a time ([04](04-storage.md)), and a stream that must never fall behind should not be the one waiting for it. So the consumer appends to plain files, and a separate loader moves them into the database later.

The format is [JSON Lines](https://jsonlines.org/): one event per line, each line a complete JSON object. A new file starts every hour, named for the hour in UTC, for example `data/raw/2026-11-12T16.jsonl`. Hourly files give the loader a simple rule: every file except the newest is finished.

**Your task.** Write the `handle` coroutine that `consume` will call. It drops events that are not relevant and appends the rest to the current hour's file. Then run the whole thing for posts and reposts.

**Hints.**

- `datetime.now(timezone.utc)` and `strftime` give you the hour. Use UTC so the file names do not jump when the clocks change.
- `Path.mkdir(parents=True, exist_ok=True)` creates `data/raw` once, at start-up.
- Open the file in append mode with `encoding="utf-8"`. Posts contain every script and emoji there is, and the Windows default encoding cannot write them.
- Writing a line to a file is a blocking call inside a coroutine. Here that is fine, because it takes microseconds. [15 Async Python](15-async-python.md) explains when it would not be.
- Your watch list needs DIDs, not handles. `resolve_did` in [03 Backfill](03-backfill.md) turns one into the other. To start, `did:plc:z72i7hdynmk6r22z27h6tvur` is the `bsky.app` account.
- Run it from a script in a terminal, not from a notebook. Notebook kernels restart; capture should not.

**Check.** After a few minutes:

- `data/raw` has a file named for the current UTC hour.
- Every line in it loads with `json.loads`.
- Every loaded event passes `is_relevant`.
- The file grows slowly compared with the stream. The filter keeps a small fraction of what arrives.

## Step 7 (stretch): Resume after a restart

Step 4 survives a dropped connection, because the last `seq` is still in memory. It does not survive the script being stopped and started. No example is given for this step; it has not been built on this PC.

- Save the last `seq` to a small file every few seconds, and read it at start-up to pass as `cursor`.
- Save the `seq` of the last event *received*, not the last event *kept*. Most events are dropped by the filter, and you do not want to replay them.
- Because the cursor is inclusive, one event repeats after a restart. The database's primary keys absorb it.
- Think about what the file contains if the PC loses power halfway through writing it, and how writing to a temporary file and renaming it avoids that.
- "Every few seconds, alongside the consumer" is a second task. [15 Async Python](15-async-python.md) shows the pattern.

## Good to know

- **Volume.** Posts plus reposts arrived at roughly 60 events per second in testing. The filter keeps a small fraction.
- **Subscribe without `dids`.** Replies, quotes and reposts of watch-list posts come from anyone, so take the whole stream and filter locally.
- **Resume.** `cursor` is the last `seq` you processed. It is inclusive, so one event repeats; the database's primary keys absorb that.
- **Deletes are always kept** so the loader can remove the post from your database.
- **Surname matching catches other people** with the same name. Keep the regex simple and let the labeling step decide who is meant.
- **Run it as its own process.** Notebook kernels restart; capture should not.
- **Which host.** Bluesky's page lists `us-west` as the recommended host. The code here was run against `us-east`. Either works; pick the closer one.
- Each line of `data/raw/<hour>.jsonl` is one event. [04 Storage](04-storage.md) loads those files into DuckDB.

## Example solution

This is the code that was run on this PC. Read top to bottom, the blocks make one script.

<details>
<summary>Show example: step 1, building the address</summary>

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
```

</details>

<details>
<summary>Show example: steps 3 and 4, the consumer with reconnect</summary>

```python
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

</details>

<details>
<summary>Show example: step 5, keeping only relevant events</summary>

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

</details>

<details>
<summary>Show example: step 6, writing hourly files and running it</summary>

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

</details>
