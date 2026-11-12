# 04 Storage

One DuckDB file holds everything. On this page you design the tables, write a loader for Jetstream events and a loader for search and feed results, and read the result from a notebook.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed.

Needs: `duckdb`. The files written by [02 Live stream](02-live-stream.md), and the functions from [03 Backfill](03-backfill.md) for step 5.

Read first:

- [DuckDB's Python API](https://duckdb.org/docs/stable/clients/python/overview): connecting, `execute`, and `?` parameters
- [Concurrency in DuckDB](https://duckdb.org/docs/stable/connect/concurrency): why only one process may write
- [`INSERT ... ON CONFLICT`](https://duckdb.org/docs/stable/sql/statements/insert): the clause that makes loading twice safe
- [AT URIs](https://atproto.com/specs/at-uri-scheme), which are the primary keys here

## What you are building

A database file, `data/narrative.duckdb`, and three functions:

| Function | Does |
| --- | --- |
| `load_events(con, events)` | stores Jetstream events, and removes what a delete event names |
| `load_raw_files()` | feeds the consumer's hourly files through `load_events`, then removes them |
| `load_appview_posts(con, posts, source)` | stores posts returned by search and author feeds |

You are done when loading the same file twice leaves the row counts unchanged, and a delete event removes its post from every table.

## Step 1: Design the tables

**Concept.** Decide what one row means in each table before writing any SQL. These are the tables the rest of the pages use:

| Table | One row per |
| --- | --- |
| `posts` | post, with links to the post it replies to or quotes |
| `reposts` | repost |
| `accounts` | account: creation date, watch-list flag, self-declared bot flag |
| `labels` | post, model and prompt version |
| `post_narrative`, `narratives` | post-to-narrative assignment, and narrative names |
| `signals` | account, signal type and time window, with the evidence as JSON |
| `reviews` | a reviewer's decision about an account |
| `stream_state` | saved stream cursor |

The primary key of `posts` and `reposts` is the record's AT URI. It names exactly one record on the network, and both of your sources (the stream and the AppView) can give it to you. That one choice is what lets the stream send an event twice, and the stream and the backfill overlap, without leaving duplicates.

**Your task.** Write the `CREATE TABLE IF NOT EXISTS` statements for `posts` and `reposts` as one SQL string called `SCHEMA`. For `posts` you need: the URI, the author's DID, the creation time, the text, the language, the URI of the post it replies to, the URI of the thread's root, the URI of the post it quotes, and which source it came from. For `reposts`: its own URI, who reposted, the URI of the post that was reposted, and when.

Then open the example and compare. Take the remaining tables from it as they are. Later pages insert into them by position, so the column order has to match.

**Hints.**

- Timestamps that come with a time zone belong in `TIMESTAMPTZ`.
- `labels` has a three-part primary key. Work out from its "one row per" line what the three parts are, and what that allows when you change a prompt.
- `IF NOT EXISTS` makes the whole string safe to run at every start-up.

**Check.** `con.execute(SCHEMA)` runs twice without an error, and `con.sql("SHOW TABLES")` lists nine tables.

## Step 2: Turn an event into a row

**Concept.** A Jetstream event (the shape is in step 2 of [02](02-live-stream.md)) has to be flattened into one row. Most fields are optional, and your loader must cope with every combination.

| Column | Comes from |
| --- | --- |
| `uri` | `at://{did}/{collection}/{rkey}` |
| `did` | `did` |
| `created_at` | `record.createdAt` |
| `text` | `record.text` |
| `lang` | the first entry of `record.langs`, if any |
| `reply_parent`, `reply_root` | `record.reply.parent.uri`, `record.reply.root.uri`, if it is a reply |
| `quote_of` | the quoted post's URI, if it is a quote (both shapes from step 5 of [02](02-live-stream.md)) |
| `source` | the text `jetstream` |

A repost is simpler: its URI, `did`, `record.subject.uri` and `record.createdAt`.

**Your task.** Write `at_uri(event)` and the part of `load_events(con, events)` that handles creates: reposts go to `reposts`, everything else to `posts`.

**Hints.**

- Pass values as `?` parameters: `con.execute("INSERT ... VALUES (?,?,...)", [values])`. Never build SQL by pasting post text into a string. Post text contains quotes, and worse.
- `ON CONFLICT DO NOTHING` skips a row whose primary key is already there.
- A missing `reply` or `embed` should become `NULL` in the row. In Python that is `None`, and `(x or {}).get(...)` is a compact way to get there.
- You have already solved "find the quoted URI in either shape" in `is_relevant`.

**Check.** Build three events by hand (a plain post, a reply, a repost) and load them into a database opened with `duckdb.connect(":memory:")`. `posts` has two rows, `reposts` has one, and the plain post's `reply_parent` is `NULL`. Load the same three again; the counts do not change.

## Step 3: Honor deletes

**Concept.** When someone deletes a post, the stream sends a delete event with no record, only the parts of the URI. A project that studies people's posts has to stop holding a post its author removed. That is one of this project's rules ([11 Guardrails](11-guardrails.md)) and one of Bluesky's [developer guidelines](https://bsky.network/docs/developer-guidelines).

A delete has to reach everything derived from the post as well as the post itself: its label and its narrative assignment.

**Your task.** Extend `load_events` so that a delete event removes the URI from `posts`, `reposts`, `labels` and `post_narrative`.

**Hints.**

- You do not know which table the URI is in, and you do not need to. Deleting a row that is not there is not an error.
- Handle the delete before anything that reads `event["record"]`.

**Check.** Load a post, then load a delete event for the same `did`, `collection` and `rkey`. `SELECT count(*) FROM posts` is back to where it started.

## Step 4: Load the consumer's files

**Concept.** The consumer in [02](02-live-stream.md) leaves hourly `.jsonl` files in `data/raw`. The loader is the one process that writes to the database. It reads those files, stores their events, and removes each file once it is loaded.

Two rules:

- **Leave the newest file alone.** The consumer is still appending to it.
- **The files are a buffer, not an archive.** If they stayed on disk, so would every deleted post.

**Your task.** Write `load_raw_files(db="data/narrative.duckdb", raw="data/raw", keep_newest=True)`.

**Hints.**

- The file names sort in time order, which is why they were named that way.
- Pass `load_events` a generator that decodes one line at a time, so a large file is never held in memory whole.
- Delete a file only after its events are stored. Think through what happens if the PC loses power between the two, and why step 2 makes that harmless.

**Check.** With a few files in `data/raw`, run it. All but the newest file are gone, and `posts` has rows with `source = 'jetstream'`. Running it again at once changes nothing.

## Step 5: Load search and feed results

**Concept.** Posts from [03 Backfill](03-backfill.md) arrive in a different shape from stream events, because they come from the AppView:

| | Jetstream event | AppView post |
| --- | --- | --- |
| URI | assembled from `did`, `collection`, `rkey` | `post["uri"]`, ready-made |
| Author | `event["did"]` | `post["author"]["did"]` |
| Record | `event["record"]` | `post["record"]` |
| Time | `record.createdAt` | `sort_time(post)` from 03 |

The record inside is the same, so everything you worked out for replies and quotes carries over.

**Your task.** Write `load_appview_posts(con, posts, source)`, where `source` is a label such as `backfill_search` or `backfill_feed`. Then use it for both kinds of backfill.

**Hints.**

- Author-feed items wrap the post as `item["post"]`. Items with a `reason` are reposts of someone else's post; leave those out here.
- `ON CONFLICT DO NOTHING` means a post that the stream already stored keeps its `jetstream` source. Decide whether that is what you want.

**Check.** After a small search backfill, `SELECT source, count(*) FROM posts GROUP BY 1` shows your new label next to `jetstream`.

## Step 6: Read from a notebook

**Concept.** Because only one process may write, everything that is not the loader opens the file read-only. Notebooks, the agent's tools in [07](07-gemma-tools.md) and the reports in [10](10-reports.md) all do.

DuckDB returns `TIMESTAMPTZ` values in the session's time zone, which defaults to the PC's. That matters more than it sounds: a post made late in the evening, US Eastern, belongs to the next day in UTC. Every per-day count in this project depends on choosing one zone and using it everywhere.

**Your task.** In a notebook, open the database read-only, set the session time zone to UTC, and show the number of posts per source as a DataFrame.

**Hints.**

- `duckdb.connect(path, read_only=True)`
- `SET TimeZone = '...'`; see [time zones](https://duckdb.org/docs/stable/sql/data_types/timestamp) in the DuckDB docs.
- `con.sql("...").df()` gives a pandas DataFrame.

**Check.** Run `SELECT max(created_at) FROM posts` before and after setting the time zone and see the displayed value change.

## Good to know

- **One writer at a time.** DuckDB lets a single process write. Let the loader be that process and open the file `read_only=True` everywhere else. This is why the consumer writes files instead of writing to the database directly.
- **Deletes are honored.** A delete event removes the post from `posts`, `reposts`, `labels` and `post_narrative`.
- **Loading twice is safe.** Primary keys plus `ON CONFLICT DO NOTHING` drop repeats.
- **Set the time zone.** Timestamps come back in the PC's local zone (US Eastern here) unless you run `SET TimeZone = 'UTC'`, which changes which day a late-evening post is counted in.
- **Landing files are a buffer.** `load_raw_files` removes each file after loading so deleted posts do not linger on disk.
- **`labels` is keyed by model and prompt version**, so results from a changed prompt sit beside the old ones and are never mixed.
- Row-at-a-time inserts are fine for a filtered stream. If loading gets slow, use DuckDB's [`read_json_auto`](https://duckdb.org/docs/stable/data/json/overview) on whole files.

## Example solution

This is the code that was run on this PC.

<details>
<summary>Show example: step 1, the tables</summary>

```python
import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
  uri TEXT PRIMARY KEY, did TEXT NOT NULL, created_at TIMESTAMPTZ, text TEXT, lang TEXT,
  reply_parent TEXT, reply_root TEXT, quote_of TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS reposts (
  uri TEXT PRIMARY KEY, did TEXT NOT NULL, subject_uri TEXT, created_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS accounts (
  did TEXT PRIMARY KEY, handle TEXT, created_at TIMESTAMPTZ, description TEXT,
  is_watchlist BOOLEAN DEFAULT FALSE, self_declared_bot BOOLEAN DEFAULT FALSE,
  fetched_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS labels (
  uri TEXT, model TEXT, prompt_version TEXT, leaders TEXT[], stance TEXT, tone TEXT,
  confidence DOUBLE, labeled_at TIMESTAMPTZ, PRIMARY KEY (uri, model, prompt_version));
CREATE TABLE IF NOT EXISTS post_narrative (uri TEXT, run_date DATE, narrative_id INTEGER);
CREATE TABLE IF NOT EXISTS narratives (
  narrative_id INTEGER, run_date DATE, name TEXT, summary TEXT, n_posts INTEGER);
CREATE TABLE IF NOT EXISTS signals (
  did TEXT, signal TEXT, window_start TIMESTAMPTZ, value DOUBLE, evidence JSON,
  computed_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS reviews (
  did TEXT, reviewer TEXT, decision TEXT, notes TEXT, reviewed_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS stream_state (name TEXT PRIMARY KEY, cursor BIGINT);
"""
```

</details>

<details>
<summary>Show example: steps 2 and 3, loading events and honoring deletes</summary>

```python
def at_uri(e):
    return f"at://{e['did']}/{e['collection']}/{e['rkey']}"

def load_events(con, events):
    for e in events:
        uri = at_uri(e)
        if e["operation"] == "delete":
            for table in ("posts", "reposts", "labels", "post_narrative"):
                con.execute(f"DELETE FROM {table} WHERE uri = ?", [uri])
            continue
        rec = e["record"]
        if e["collection"] == "app.bsky.feed.repost":
            con.execute("INSERT INTO reposts VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                        [uri, e["did"], rec["subject"]["uri"], rec["createdAt"]])
            continue
        reply = rec.get("reply") or {}
        quoted = (rec.get("embed") or {}).get("record") or {}
        quoted = quoted.get("record", quoted)
        con.execute(
            "INSERT INTO posts VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            [uri, e["did"], rec["createdAt"], rec.get("text", ""),
             (rec.get("langs") or [None])[0],
             (reply.get("parent") or {}).get("uri"), (reply.get("root") or {}).get("uri"),
             quoted.get("uri"), "jetstream"])

# con = duckdb.connect("data/narrative.duckdb"); con.execute(SCHEMA)
# notebooks: duckdb.connect("data/narrative.duckdb", read_only=True)
```

</details>

<details>
<summary>Show example: step 4, loading the hourly files</summary>

```python
import json
from pathlib import Path

def load_raw_files(db="data/narrative.duckdb", raw="data/raw", keep_newest=True):
    con = duckdb.connect(db)
    con.execute(SCHEMA)
    files = sorted(Path(raw).glob("*.jsonl"))
    if keep_newest:
        files = files[:-1]                       # the newest file is still being written
    for path in files:
        with open(path, encoding="utf-8") as f:
            load_events(con, (json.loads(line) for line in f))
        path.unlink()                            # landing files are a buffer, not an archive
    con.close()
```

</details>

<details>
<summary>Show example: step 5, loading search and author-feed results</summary>

```python
def load_appview_posts(con, posts, source: str):
    """Store posts returned by searchPosts or getAuthorFeed (the item's "post")."""
    for p in posts:
        rec = p["record"]
        reply = rec.get("reply") or {}
        quoted = (rec.get("embed") or {}).get("record") or {}
        quoted = quoted.get("record", quoted)
        con.execute(
            "INSERT INTO posts VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            [p["uri"], p["author"]["did"], sort_time(p), rec.get("text", ""),
             (rec.get("langs") or [None])[0],
             (reply.get("parent") or {}).get("uri"), (reply.get("root") or {}).get("uri"),
             quoted.get("uri"), source])
```

```python
with httpx.Client(timeout=30) as client:
    found = leader_mentions(client, "Schumer", start, end)
    load_appview_posts(con, found, "backfill_search")

    feed = author_history(client, "bsky.app", start)
    load_appview_posts(con, (item["post"] for item in feed if "reason" not in item),
                       "backfill_feed")
```

`leader_mentions`, `author_history` and `sort_time` are on [03 Backfill](03-backfill.md).

</details>

<details>
<summary>Show example: step 6, reading from a notebook</summary>

```python
import duckdb
con = duckdb.connect("data/narrative.duckdb", read_only=True)
con.execute("SET TimeZone = 'UTC'")
con.sql("SELECT source, count(*) FROM posts GROUP BY 1").df()
```

</details>
