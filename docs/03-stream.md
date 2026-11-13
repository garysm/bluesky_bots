# 03 Stream

Listen to Bluesky in real time through Jetstream and keep the events a `keep` function accepts.

This page is a guide, not a listing. Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed. Open it when you are stuck or want to compare.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/stream/` |
| Reads | Jetstream, over one websocket |
| Writes | `data/raw/<hour>.jsonl`, one kept event per line; `data/state/cursor.json` |
| Command | `python -m bluesky_bots.stream` |
| Must not know | what a topic is, or that a database exists. It is handed a `keep` function and writes files. |

Needs: `websockets`. No login, no model.

Read first:

- [Jetstream](https://bsky.network/docs/jetstream) in the Bluesky docs. It is the reference for everything in steps 1 to 4: hosts, filters, the event shape and resuming.
- [18 Async Python](18-async-python.md), if `async def`, `await`, `async with` and `async for` are new to you. The consumer is one coroutine.
- [02 Topics](02-topics.md) step 6, which builds the `keep` function this service is given.

## What you are building

One command that runs for days:

1. It opens a websocket to Jetstream and receives every new post and repost on the network.
2. It asks `keep(event)` about each one.
3. It appends the events that are kept to `data/raw/<hour>.jsonl`, one JSON object per line.
4. When the connection drops, it reconnects and carries on from where it stopped. When the command itself is restarted, it does the same from a saved position.

You are done when `pytest tests/test_stream.py` passes, the command has run for an hour, there is one file per hour in `data/raw`, and switching your network off for a minute loses nothing.

`test.py` in the project root is your earlier work on steps 1 to 4. Move `build_url` and `consume` from it into `bluesky_bots/stream/consumer.py`, replacing the stubs there, then carry on from step 5.

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

**Your task.** In `bluesky_bots/stream/consumer.py`, write `build_url(collections, dids=(), cursor=None)`, which returns the full `wss://` address. Then, in a scratch script, connect to that address and print the first ten frames exactly as they arrive.

**Hints.**

- A repeated parameter is one `(name, value)` pair per value. [`urllib.parse.urlencode`](https://docs.python.org/3/library/urllib.parse.html#urllib.parse.urlencode) accepts a list of pairs.
- `websockets.connect(url, subprotocols=[...])` is used with `async with`, and the connection it gives you is read with `async for`. See the [websockets client reference](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html).

**Check.** `pytest tests/test_stream.py -k build_url`. The address for posts and reposts should be exactly:

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

Three facts decide how the rest of the project has to be written:

- **A delete has no `record`.** It carries only `did`, `collection` and `rkey`, which is enough to say which record is gone.
- **A repost has no `text`.** Its record points at another post through `subject`.
- **A record's address is its [AT URI](https://atproto.com/specs/at-uri-scheme):** `at://{did}/{collection}/{rkey}`. The event gives you the three parts, not the assembled address. `at_uri` from [02](02-topics.md) step 3 puts them together.

The full field lists are in the lexicons for [posts](https://github.com/bluesky-social/bsky/blob/main/lexicons/app/bsky/feed/post.json) and [reposts](https://github.com/bluesky-social/bsky/blob/main/lexicons/app/bsky/feed/repost.json).

**Your task.** Change your scratch script so that for each event it prints the `seq`, the operation, the AT URI, and the first 60 characters of the text when there is any. It must not crash on deletes or reposts.

**Hints.**

- Reading `event["record"]["text"]` raises `KeyError` on the first repost and on the first delete. `dict.get` with a default is the tool.
- Decide what "no record" should become in your code, so the lines after it do not each need their own check.

**Check.**

- It runs for a full minute without an exception.
- `seq` only ever goes up.
- Take one AT URI from your output and open `https://bsky.app/profile/<did>/post/<rkey>` in a browser. You should see the post you printed.
- Find one reply and one quote post in your output and print their whole `record`. Compare them with [Posts in-depth](https://bsky.network/docs/about-bluesky-content/posts#replies-quote-posts-and-embeds), and with what `event_fields` from [02](02-topics.md) pulls out of them.

## Step 3: The consumer loop

**Concept.** Separate receiving events from deciding what to do with them. The receiving half is a coroutine, `consume`, that knows about websockets and nothing else. The deciding half is a function you pass in, `handle`, that takes one event. That way what is kept and where it is written can change without touching the connection code, and you can test `consume` with a `handle` that only prints.

`handle` is itself a coroutine, so `consume` calls it with `await`. Nothing on this page needs `handle` to wait for anything, but a later version might (a queue, a network call), and the cost of allowing it is one keyword.

`consume` also has to remember how far it got. Every event carries a `seq`, a number that only increases. After `handle` returns, keep that event's `seq`; step 4 uses it.

**Your task.** In `consumer.py`, write:

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
- **Delivery is at-least-once.** Duplicates can happen across reconnects, so whatever stores the events must be safe to run twice on the same event. In this project storage takes care of it ([05 Storage](05-storage.md)).
- **Replay only reaches back so far.** The [replay page](https://bsky.network/docs/jetstream-replay) gives 36 hours for Bluesky's own hosts. If the command is down longer than that, there is a gap, and [04 Backfill](04-backfill.md) is how you fill it.

Reconnecting at once, in a tight loop, hammers a server that may be down. Wait before each retry, and wait longer each time: one second, then two, four, and so on up to a ceiling. This is called exponential backoff.

**Your task.** Make `consume` run forever. When the connection fails, it waits, reconnects from the last `seq`, and continues.

**Hints.**

- The address has to be rebuilt on every attempt, because the cursor has changed.
- Two kinds of failure are worth catching: the connection closing (`websockets.ConnectionClosed`) and the network not being there at all (`OSError`, which covers refused connections and failed name lookups).
- Do not catch `Exception`. Think about what happens to a bug inside `handle` if you do.
- Decide where the wait goes back to one second. After a successful connect? After the first event? What does each choice do when the server accepts connections and then drops them at once?
- The wait must be `await asyncio.sleep(...)`, not `time.sleep(...)`. [18 Async Python](18-async-python.md) explains the difference.

**Check.** Run it with a `handle` that prints `seq`. Turn your network off for twenty seconds, then on again. The first `seq` printed after the reconnect should be the same as the last one printed before the drop (the cursor is inclusive), and the numbers should continue from there. Ctrl+C should still stop the script.

## Step 5: Keep what `keep` accepts, in hourly files

**Concept.** You might expect to pass a topic's accounts in `dids` and let the server filter. That would give you only what those accounts post. The replies to them, the quotes of them and the reposts of them come from anyone, and so does every post that mentions a keyword. So you take the whole stream and filter on your side.

The stream service does not make that decision. It is handed a function, `keep(event)`, that answers yes or no. [02](02-topics.md) step 6 builds the usual one from your active topics. Because it is a parameter, the stream can be tested with `lambda e: True`, pointed at one topic, or switched to keeping everything, without a change to this code.

What is kept goes to files, not to the database. DuckDB allows one writing process at a time ([17](17-choosing-storage.md)), and a stream that must never fall behind should not be the one waiting for it. A separate loader moves the files into storage later ([05](05-storage.md)).

The format is [JSON Lines](https://jsonlines.org/): one event per line, each line a complete JSON object. A new file starts every hour, named for the hour in UTC, for example `data/raw/2026-11-12T16.jsonl`. Hourly files give the loader a simple rule: every file except the newest is finished.

**Your task.** In `bluesky_bots/stream/landing.py`, write `hour_file(raw_dir, now=None)` and `make_handler(keep, raw_dir, state=None)`. `make_handler` returns the `handle` coroutine that `consume` will call: it drops events `keep` refuses and appends the rest to the current hour's file. If `state` is given, it also records the `seq` of every event it sees under `state["cursor"]`; step 6 uses that.

**Hints.**

- `datetime.now(timezone.utc)` and `strftime` give you the hour. Use UTC so the file names do not jump when the clocks change.
- `Path.mkdir(parents=True, exist_ok=True)` creates the folder once, when the handler is made.
- Open the file in append mode with `encoding="utf-8"`. Posts contain every script and emoji there is, and the Windows default encoding cannot write them.
- Writing a line to a file is a blocking call inside a coroutine. Here that is fine, because it takes microseconds. [18 Async Python](18-async-python.md) explains when it would not be.
- Record the `seq` of the last event *received*, not the last one *kept*. Most events are dropped, and you do not want to replay them after a restart.

**Check.** `pytest tests/test_stream.py -k "hour_file or handler"`

## Step 6: Resume after a restart

**Concept.** Step 4 survives a dropped connection, because the last `seq` is still in memory. It does not survive the command being stopped and started. For that the position has to be on disk.

Two details:

- **Save it every few seconds, not on every event.** That is a second task running beside the consumer; [18 Async Python](18-async-python.md) section 8 shows the pattern.
- **Never leave a half-written file.** If the PC loses power halfway through a write, the file is garbage and the next start fails. Write to a temporary file, then rename it over the real one. A rename either happens completely or not at all.

The position lives in a file and not in the database for the same reason as the events: this service does not open the database.

**Your task.** In `landing.py`, write `save_cursor(path, seq)`, `load_cursor(path)` (which returns `None` when there is no file yet) and `every(seconds, fn)`, a coroutine that calls `fn()` every few seconds, forever.

**Hints.**

- `os.replace(tmp, path)` is the rename, and it overwrites.
- Because the cursor is inclusive, one event repeats after a restart. Storage absorbs it.

**Check.** `pytest tests/test_stream.py -k cursor`

## Step 7: Run it

**Concept.** The command in `bluesky_bots/stream/__main__.py` is already written. Read it: it is the only place the pieces meet. It loads the active topics, builds `keep` from them, makes the handler, and runs `consume` and the cursor-saving task side by side in a [`TaskGroup`](https://docs.python.org/3/library/asyncio-task.html#task-groups).

**Your task.** Run it in a terminal, not a notebook. Notebook kernels restart; capture should not.

```bash
python -m bluesky_bots.stream
```

**Check.** After a few minutes:

- `data/raw` has a file named for the current UTC hour, and `data/state/cursor.json` holds a number that grows.
- Every line of the file loads with `json.loads`, and every loaded event passes your `keep`.
- The file grows slowly compared with the stream.
- Stop it with Ctrl+C and start it again. It resumes from the saved position.

## Good to know

- **Volume.** Posts plus reposts arrived at roughly 60 events per second in testing. The filter keeps a small fraction.
- **Most of what is kept is deletes.** In a 12-second run on 2026-11-13 with the example topic, 55 events were kept and 50 of them were deletes. That is expected: every delete is kept so storage can honor it, whichever post it was for.
- **Subscribe without `dids`.** Replies, quotes and reposts of a topic's accounts come from anyone, so take the whole stream and filter locally.
- **Resume.** `cursor` is the last `seq` you processed. It is inclusive, so one event repeats; storage absorbs that. After Ctrl+C the position is saved on the way out. After a hard kill it can be up to five seconds old, which only means a few more repeats.
- **Changing a topic file** takes effect in capture when the stream is restarted.
- **`--all` keeps every event.** It replaces `keep` with a function that always says yes. Read "How big will it get" in [17](17-choosing-storage.md) before using it.
- **Run it as its own process.** Notebook kernels restart; capture should not.
- **Which host.** Bluesky's page lists `us-west` as the recommended host. The code here was run against `us-east`. Either works; pick the closer one.
- Each line of `data/raw/<hour>.jsonl` is one event. [05 Storage](05-storage.md) loads those files.

## Example solution

This is the code that was run on this PC. `tests/test_stream.py` passes against it, and on 2026-11-13 the whole command ran against Jetstream for 12 seconds: every kept event passed the filter, `seq` only increased, and the cursor file was written.

<details>
<summary>Show example: step 1, building the address</summary>

```python
from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable, Iterable
from urllib.parse import urlencode

import websockets


HOST = "wss://jetstream.us-east.bsky.network"
PATH = "/xrpc/network.bsky.jetstream.subscribeEvents"


def build_url(collections: Iterable[str], dids: Iterable[str] = (), cursor: int | None = None) -> str:
    """The full wss:// address for a subscription to these collections (commits only)."""
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
async def consume(collections: Iterable[str], handle: Callable[[dict], Awaitable[None]],
                  dids: Iterable[str] = (), cursor: int | None = None) -> None:
    """Call handle(event) for every commit, forever; reconnect from the last seq on failure."""
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
<summary>Show example: step 5, keeping events in hourly files (bluesky_bots/stream/landing.py)</summary>

```python
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable


def hour_file(raw_dir: str | Path, now: datetime | None = None) -> Path:
    """The landing file for the current hour in UTC, for example data/raw/2026-11-12T16.jsonl."""
    now = now or datetime.now(timezone.utc)
    return Path(raw_dir) / (now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H") + ".jsonl")


def make_handler(keep: Callable[[dict], bool], raw_dir: str | Path,
                 state: dict | None = None) -> Callable[[dict], Awaitable[None]]:
    """The coroutine `consume` calls for each event.

    It appends the events that `keep` accepts to the current hour's file, one
    JSON object per line. If `state` is given, it records the seq of every
    event received (kept or not) under state["cursor"].
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    async def handle(event: dict) -> None:
        if state is not None:
            state["cursor"] = event["seq"]
        if not keep(event):
            return
        with open(hour_file(raw_dir), "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    return handle
```

</details>

<details>
<summary>Show example: step 6, saving the position</summary>

```python
def save_cursor(path: str | Path, seq: int) -> None:
    """Save the stream position so that a crash half-way through cannot leave a broken file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"cursor": seq}), encoding="utf-8")
    os.replace(tmp, path)          # a rename either happens completely or not at all


def load_cursor(path: str | Path) -> int | None:
    """The saved stream position, or None if there is none yet."""
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["cursor"]


async def every(seconds: float, fn: Callable[[], None]) -> None:
    """Call fn() every few seconds, forever. Run it as a task beside the consumer."""
    while True:
        await asyncio.sleep(seconds)
        fn()
```

</details>
