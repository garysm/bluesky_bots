# 04 Storage

One DuckDB file holds everything. This page has the tables, a loader for Jetstream events, a loader for search and feed results, and how to read from a notebook.

Needs: `duckdb`.

## Tables and the Jetstream loader

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

## Load the hourly files from the consumer

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

## Load search and author-feed results

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

## Read from a notebook

```python
import duckdb
con = duckdb.connect("data/narrative.duckdb", read_only=True)
con.execute("SET TimeZone = 'UTC'")
con.sql("SELECT source, count(*) FROM posts GROUP BY 1").df()
```

## Good to know

- **One writer at a time.** DuckDB lets a single process write. Let the loader be that process and open the file `read_only=True` everywhere else. This is why the consumer writes files instead of writing to the database directly.
- **Deletes are honored.** A delete event removes the post from `posts`, `reposts`, `labels` and `post_narrative`.
- **Loading twice is safe.** Primary keys plus `ON CONFLICT DO NOTHING` drop repeats.
- **Set the time zone.** Timestamps come back in the PC's local zone (US Eastern here) unless you run `SET TimeZone = 'UTC'`, which changes which day a late-evening post is counted in.
- **Landing files are a buffer.** `load_raw_files` removes each file after loading so deleted posts do not linger on disk.
- **`labels` is keyed by model and prompt version**, so results from a changed prompt sit beside the old ones and are never mixed.
- Row-at-a-time inserts are fine for a filtered stream. If loading gets slow, use DuckDB's `read_json_auto` on whole files.
