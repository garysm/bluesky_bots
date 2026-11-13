# 04 Backfill

Fetch history from the Bluesky AppView: one account's past posts, search results for any query, profiles and account creation dates.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/backfill/` |
| Reads | the AppView HTTP API and the PLC directory |
| Writes | nothing itself. Its functions return posts; its command turns them into rows and hands them to storage. |
| Command | `python -m bluesky_bots.backfill posts --topic NAME --start YYYY-MM-DD` and `... accounts` |
| Must not know | any subject. Queries and accounts come from a topic file. |

Needs: `httpx`. No login was used for anything on this page.

Read first:

- [API Hosts and Auth](https://bsky.network/docs/api-directory) in the Bluesky docs: which host answers what, and what needs a login
- [Viewing feeds](https://bsky.network/docs/bluesky-api/viewing-feeds): author feeds and paging with a cursor
- [Timestamps](https://bsky.network/docs/about-bluesky-content/timestamps): `createdAt`, `indexedAt` and `sortAt`. Step 3 is built on it.
- The [HTTP reference](https://endpoints.bsky.app). Search it for an endpoint's name, for example `searchPosts`, to see every parameter and the response shape.

## What you are building

All of these go in `bluesky_bots/backfill/appview.py`:

| Function | Gives you |
| --- | --- |
| `paged(client, method, params, key)` | every item from an endpoint that pages with a cursor |
| `parse_ts(value)`, `sort_time(post)` | the one timestamp to trust for a post |
| `author_history(client, actor, start)` | an account's posts and reposts back to a date |
| `search_posts(client, query, start, end)` | every post search can find for a query in a time range |
| `post_to_row(post, source)` | a row for the `posts` table from an AppView post |
| `resolve_did(client, handle)`, `account_created(client, did)` | an account's DID and its creation date |

You are done when `pytest tests/test_backfill.py` passes and you can fetch a day of results for one of a topic's searches with no duplicate URIs and no gap in the per-day counts.

This is the do-it-yourself route, through the same public API the app uses. Bluesky's own route to bulk history is [Network Replay](https://bsky.network/docs/jetstream-replay), which replays the archive in the same shape as the live stream. It needs an API key and has not been tried here.

## Step 1: Make one request by hand

**Concept.** Bluesky's HTTP API is [XRPC](https://atproto.com/specs/xrpc): every call is `https://<host>/xrpc/<method name>`, with parameters in the query string for reads. The method names are the same dotted names you saw as collections in [03](03-stream.md), such as `app.bsky.actor.getProfile`.

Public reads of `app.bsky.*` need no login. The Bluesky docs point you to `public.api.bsky.app` for them. On this PC that host answered search with a 403, so this page uses `api.bsky.app`, which the same docs list as the Bluesky App service.

**Your task.** In a scratch script, with `httpx`, fetch the profile of `bsky.app` and print the response's keys. Use one `httpx.Client` for all your requests, opened with `with`, so connections are reused and closed.

**Hints.**

- `client.get(url, params={...})` builds the query string for you.
- `r.json()` is the decoded body. `r.status_code` tells you whether to trust it.
- The parameter is called `actor` and accepts a handle or a DID.

**Check.** The response includes `did`, `handle`, `createdAt` and `description`, and the `did` is `did:plc:z72i7hdynmk6r22z27h6tvur`.

## Step 2: Follow a cursor

**Concept.** An endpoint that returns a list gives you one page at a time. Each response carries a `cursor`; send it back and you get the next page. When the response has no cursor, you have reached the end. Nearly every list endpoint works this way, so write the loop once.

Two more things belong in that loop:

- **Rate limits.** When you ask too fast the server answers with status 429 ([Rate Limits](https://bsky.network/docs/rate-limits)). The right response is to wait and ask again, not to fail.
- **Manners.** A short pause between pages keeps you well inside the limits.

**Your task.** Write a generator:

```python
def paged(client, method, params, key, max_pages=500, sleep=time.sleep):
```

It yields the items found under `key` in each page (`"feed"` for an author feed), following the cursor until there is none or `max_pages` is reached.

**Hints.**

- A generator lets the caller stop early without you fetching pages nobody will read. `yield from` passes a whole list along.
- Do not add the cursor to the caller's `params` dict. Build a new one for each request.
- On a 429, wait and go round again without advancing. Ask yourself whether that attempt should count against `max_pages`.
- `r.raise_for_status()` turns any other failure into an exception, which is what you want. Silently yielding nothing would look like "no posts".
- Why is `sleep` a parameter? So that a test can pass a function that does not wait. The tests replace the AppView itself too, with [`httpx.MockTransport`](https://www.python-httpx.org/advanced/transports/#mock-transports), so they run offline and in milliseconds.

**Check.** `pytest tests/test_backfill.py -k paged`. Then against the real API: feed it `app.bsky.feed.getAuthorFeed` with `{"actor": "bsky.app", "limit": 100}`, key `"feed"` and `max_pages=3`. You should get close to 300 items (a page can come back a few short of its limit; 298 arrived when this was checked), and no item should appear twice.

## Step 3: Decide which time a post has

**Concept.** A post has two timestamps and neither is fully trustworthy. Read [Timestamps](https://bsky.network/docs/about-bluesky-content/timestamps) for the detail:

- `createdAt` is written by the author's app. It can be wrong, in the future, or not a date at all.
- `indexedAt` is when Bluesky's server first saw the record. It is reliable, but for an imported post it is the import time.
- `sortAt` is what Bluesky sorts by: the earlier of the two. The search parameters `since` and `until` filter on it.

The API does not return `sortAt`, so you compute it. In a search result or feed item the two inputs are at `post["indexedAt"]` and `post["record"]["createdAt"]`.

**Your task.** Write `parse_ts(value) -> datetime` and `sort_time(post) -> datetime`. `sort_time` returns the earlier of the two timestamps, and falls back to `indexedAt` when `createdAt` is missing or unreadable.

**Hints.**

- `datetime.fromisoformat` reads the `Z` suffix.
- A timestamp with no time zone cannot be compared with one that has it. Decide what a zone-less value means (the example treats it as UTC) and make every value you return zone-aware.
- Two different exceptions can come out of a bad `createdAt`: one when the key is missing, one when the text is not a date.

**Check.** `pytest tests/test_backfill.py -k sort_time`, which covers this table:

| `indexedAt` | `createdAt` | `sort_time` returns |
| --- | --- | --- |
| `2026-11-05T00:00:10.000Z` | `2026-11-05T00:00:00.000Z` | 00:00:00, the earlier one |
| `2026-11-05T00:00:10.000Z` | `2030-01-01T00:00:00.000Z` | 00:00:10, because the future date loses |
| `2026-11-05T00:00:10.000Z` | `not a date` | 00:00:10 |
| `2026-11-05T00:00:10.000Z` | `2026-11-05T00:00:00` | 00:00:00 UTC, zone-aware |

## Step 4: One account's history

**Concept.** `app.bsky.feed.getAuthorFeed` returns an account's posts and reposts, newest first, and pages with a cursor, so `paged` does the fetching. The [lexicon](https://github.com/bluesky-social/bsky/blob/main/lexicons/app/bsky/feed/getAuthorFeed.json) lists the parameters; the ones that matter here are `actor`, `limit` (up to 100) and `filter`.

Each item wraps the post: the post is `item["post"]`. When the item is a repost, it also has a `reason`, and the post inside is the *original*, with the original's date.

**Your task.** Write a generator `author_history(client, actor, start)` that yields items newest first and stops once it has gone back past `start`.

**Hints.**

- Which `filter` value includes replies? You want them.
- The feed is ordered by when the account posted or reposted. A repost of a three-year-old post sits near the top with a three-year-old date inside it. Decide which items are allowed to end the walk.
- Stopping is a `return` from the generator, which also stops `paged` from fetching further pages.

**Check.** Ask for `bsky.app` back to thirty days ago. Among the items with no `reason`, the oldest should be no older than your `start`. If your walk stops after a handful of items, a repost ended it.

## Step 5: Search without a cursor

**Concept.** `app.bsky.feed.searchPosts` finds posts by text. The [lexicon](https://github.com/bluesky-social/bsky/blob/main/lexicons/app/bsky/feed/searchPosts.json) lists the parameters. You need `q`, `sort` (`latest`), `limit` (up to 100), `since` and `until`.

Search has a cursor too, and this is where the plan from step 2 breaks. The reference says of search that it "may require authentication" and that its cursor "may not necessarily allow scrolling through entire result set". Here is what was seen on this PC without a login:

- The first page works.
- Any request that carries `cursor` gets `403 Forbidden`.

So you page by time instead. Ask for the newest 100 posts before a moment `until`. Take the time of the oldest post you got, make that the new `until`, and ask again. Repeat until you reach `start`.

The details that make this harder than it sounds:

- **`until` is matched in whole seconds.** The reference describes it as not inclusive. In testing here, posts from the `until` second itself came back. Write the walker so that it is correct either way.
- **So pages overlap.** The post you took the new `until` from, and any others in that same second, can come back again. Remember which URIs you have seen and skip them.
- **So the walk can stall.** If a page contains nothing new, moving `until` to its oldest post changes nothing and you loop forever. In that case, step back one second.
- **A blind spot remains.** If more than 100 matching posts share one second, the extras cannot be reached.

**Your task.** Write a generator `search_posts(client, query, start, end)` that yields each matching post once, walking back from `end` to `start` without ever sending a cursor. When it finishes, have it print how many posts it found for each day.

**Hints.**

- `since` stays fixed at `start`. Only `until` moves.
- Handle 429 as in step 2.
- Use `sort_time` for a post's time, both for the per-day counts and for the next `until`. Drop the microseconds before using it as `until`.
- An empty page means you are finished.
- The per-day counts are your gap detector. A day with far fewer posts than its neighbours is the first sign that something was missed.
- The function takes any query. Which queries to run for a topic is the topic file's `search` list, and feeding them in is the command's job, not this function's.

**Check.**

- No URI is yielded twice. Collect them in a list and compare its length with the length of a set.
- A 20-minute window ending 2026-11-05 00:00 UTC returned 390 unique posts for "Schumer" when this was first run, and a 3-minute window on 2026-11-13 returned 40. Yours will differ.
- Start small. A full day is several hundred requests per query; plan for hours.

## Step 6: From an AppView post to a row

**Concept.** Storage takes rows: plain dicts with the columns of the `posts` table ([05](05-storage.md) lists them). A post from the AppView has a different shape from a stream event, so it needs its own conversion:

| Row column | Comes from |
| --- | --- |
| `uri` | `post["uri"]`, ready-made |
| `did` | `post["author"]["did"]` |
| `created_at` | `sort_time(post)` |
| `text`, `lang` | `record.text`; the first entry of `record.langs`, if any |
| `reply_parent`, `reply_root` | `record.reply.parent.uri`, `record.reply.root.uri`, if it is a reply |
| `quote_of` | the quoted post's URI, if it is a quote |
| `source` | a label you pass in, such as `backfill_search` or `backfill_feed` |

The record inside is the same as in a stream event, so `quoted_uri` from [02](02-topics.md) carries over.

**Your task.** Write `post_to_row(post, source)`.

**Hints.**

- A field the record does not have becomes `None` in the row; `text` becomes `""`.
- For an author-feed item, pass `item["post"]`. Items with a `reason` are reposts of someone else's post; the command leaves those out.

**Check.** `pytest tests/test_backfill.py -k post_to_row`

## Step 7: Accounts: DID and creation date

**Concept.** Topic files may list accounts as handles, but everything else in this project uses [DIDs](https://atproto.com/specs/did), the permanent account identifiers. [Resolving identities](https://bsky.network/docs/resolving-identities) covers the general case. For this project the profile endpoint from step 1 is enough, because the profile includes the DID.

Account age is one of the signals in [10](10-signals.md), so you also need each account's creation date. Where it comes from depends on the kind of DID:

- **`did:plc:...`** (nearly all accounts). The [PLC directory](https://web.plc.directory/) keeps the history of each identity, and `https://plc.directory/<did>/log/audit` returns it as a list, oldest entry first. The first entry's `createdAt` is when the account came into being. The method is specified in [did:plc](https://atproto.com/specs/did-plc).
- **`did:web:...`** has no such log. Fall back to the profile's `createdAt`.

**Your task.** Write `resolve_did(client, handle) -> str` and `account_created(client, did) -> str | None`.

**Hints.**

- `resolve_did` is step 1 with one field picked out.
- For many accounts at once, `app.bsky.actor.getProfiles` takes repeated `actors` parameters, 25 at most per call.

**Check.** `resolve_did(client, "bsky.app")` returns `did:plc:z72i7hdynmk6r22z27h6tvur`, and `account_created` for that DID gives the same moment as the profile's `createdAt`. From now on topic files can list handles ([02](02-topics.md) step 9).

## Step 8: Run it for a topic

**Concept.** The command in `bluesky_bots/backfill/__main__.py` is already written, and it is where a topic meets these functions. `posts` runs every query in the topic's `search` list and walks the feed of every account the topic names, hands the rows to storage, and recomputes the topic's membership. `accounts` fetches creation dates for accounts that have posts stored but no date yet.

```bash
python -m bluesky_bots.backfill posts --topic dem-leadership --start 2026-11-01
```

```bash
python -m bluesky_bots.backfill accounts --limit 200
```

**Check.** `python -m bluesky_bots.storage info` shows more posts than before, and running the same backfill again adds none.

## Good to know

- **Use `api.bsky.app`.** `public.api.bsky.app` answered search with a 403.
- **Search refuses cursors without a login.** The first page works; any request carrying `cursor` gets "403 Forbidden". `search_posts` avoids cursors by moving `until` backwards instead. `getAuthorFeed` paging with a cursor works normally.
- **`until` works in whole seconds** and includes that second. That is why the walker steps in seconds and skips posts it has already seen.
- **Blind spot.** If more than 100 matching posts share one second, the extras are missed.
- **Search is not guaranteed complete, and deleted posts never appear.** Compare search counts with your live capture for the same days to see how much is missing.
- **Result shape differs from Jetstream.** The record is under `post["record"]`, the author under `post["author"]`. Author feed items wrap the post as `item["post"]`, and reposts carry a `reason`.
- **A post the stream already stored keeps its `jetstream` source.** Storage skips a row whose URI it already has.
- **`createdAt` is supplied by the author's app** and can be wrong or malformed. `sort_time` takes the earlier of it and the server's `indexedAt`.
- **Account age.** The PLC audit log is the identity record itself; for `bsky.app` it matched the profile's `createdAt`.
- **If anonymous search stops working**, log in with the `atproto` package (already installed) and an app password kept in `.env`.

## Example solution

This is the code that was run on this PC. `tests/test_backfill.py` passes against it. On 2026-11-13 `resolve_did`, `account_created`, `search_posts` and `post_to_row` were also run against the live AppView for a three-minute window; `author_history` was last run in its earlier form on 2026-11-11.

<details>
<summary>Show example: step 2, following a cursor</summary>

```python
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator

import httpx

from ..aturi import quoted_uri


APPVIEW = "https://api.bsky.app/xrpc"


def paged(client: httpx.Client, method: str, params: dict, key: str, max_pages: int = 500,
          sleep: Callable[[float], None] = time.sleep) -> Iterator[dict]:
    """Yield every item under `key` from an endpoint that pages with a cursor.

    Waits and asks again on a 429. `sleep` is a parameter so a test can pass
    one that does not wait.
    """
    cursor = None
    for _ in range(max_pages):
        q = dict(params, cursor=cursor) if cursor else params
        r = client.get(f"{APPVIEW}/{method}", params=q)
        if r.status_code == 429:
            sleep(30)
            continue
        r.raise_for_status()
        data = r.json()
        yield from data[key]
        cursor = data.get("cursor")
        if not cursor:
            return
        sleep(0.3)
```

</details>

<details>
<summary>Show example: step 3, the time of a post</summary>

```python
def parse_ts(value: str) -> datetime:
    """A timezone-aware datetime from an ISO string; a value with no zone is taken to be UTC."""
    ts = datetime.fromisoformat(value)
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def sort_time(post: dict) -> datetime:
    """The one timestamp to trust for an AppView post: the earlier of indexedAt and createdAt.

    Falls back to indexedAt when createdAt is missing or is not a date.
    """
    times = [parse_ts(post["indexedAt"])]
    try:
        times.append(parse_ts(post["record"]["createdAt"]))
    except (KeyError, ValueError):
        pass                               # createdAt is client-supplied and can be malformed
    return min(times)
```

</details>

<details>
<summary>Show example: step 4, one account's history</summary>

```python
def author_history(client: httpx.Client, actor: str, start: datetime) -> Iterator[dict]:
    """Feed items (posts and reposts) by one account, newest first, back to `start`."""
    params = {"actor": actor, "limit": 100, "filter": "posts_with_replies"}
    for item in paged(client, "app.bsky.feed.getAuthorFeed", params, "feed"):
        if "reason" not in item and sort_time(item["post"]) < start:   # reposts carry a "reason"
            return
        yield item
```

</details>

<details>
<summary>Show example: step 5, search without a cursor</summary>

```python
def search_posts(client: httpx.Client, query: str, start: datetime, end: datetime,
                 sleep: Callable[[float], None] = time.sleep) -> Iterator[dict]:
    """Every post search can find for `query` between `start` and `end`, each yielded once.

    Walks backwards from `end` by moving `until`, never sending a cursor.
    Prints how many posts it found for each day when it finishes.
    """
    until, seen, counts = end, set(), {}
    while until > start:
        params = {"q": query, "sort": "latest", "limit": 100,
                  "since": start.isoformat(), "until": until.isoformat()}
        r = client.get(f"{APPVIEW}/app.bsky.feed.searchPosts", params=params)
        if r.status_code == 429:
            sleep(30)
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
        sleep(0.3)
    for day in sorted(counts):
        print(day, query, counts[day])     # per-day counts; a sudden dip means a gap
```

</details>

<details>
<summary>Show example: step 6, from an AppView post to a row</summary>

```python
def post_to_row(post: dict, source: str) -> dict:
    """A `posts` table row from an AppView post (a search result, or the "post" of a feed item).

    `source` says where it came from, for example 'backfill_search' or 'backfill_feed'.
    """
    rec = post["record"]
    reply = rec.get("reply") or {}
    return {"uri": post["uri"], "did": post["author"]["did"], "created_at": sort_time(post),
            "text": rec.get("text", ""), "lang": (rec.get("langs") or [None])[0],
            "reply_parent": (reply.get("parent") or {}).get("uri"),
            "reply_root": (reply.get("root") or {}).get("uri"),
            "quote_of": quoted_uri(rec), "source": source}
```

</details>

<details>
<summary>Show example: step 7, DID and creation date</summary>

```python
def resolve_did(client: httpx.Client, handle: str) -> str:
    """The DID of the account with this handle."""
    r = client.get(f"{APPVIEW}/app.bsky.actor.getProfile", params={"actor": handle})
    r.raise_for_status()
    return r.json()["did"]


def account_created(client: httpx.Client, did: str) -> str | None:
    """When an account was created, as an ISO string, from the PLC directory or the profile."""
    if did.startswith("did:plc:"):
        log = client.get(f"https://plc.directory/{did}/log/audit").json()
        return log[0]["createdAt"]         # the first entry is the account's creation
    prof = client.get(f"{APPVIEW}/app.bsky.actor.getProfile", params={"actor": did}).json()
    return prof.get("createdAt")
```

</details>
