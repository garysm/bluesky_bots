# 05 Storage

Everything the project saves goes through one interface. On this page you learn that interface, write the code that turns stream events into rows, and build the DuckDB backend behind it.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/storage/` |
| Reads | the stream's landing files in `data/raw` |
| Writes | every table. It is the only service that does, and the one place a delete is honored. |
| Command | `python -m bluesky_bots.storage init`, `load`, `info` and `copy` |
| Must not know | what a topic means, or how a label was produced. It stores rows. |

Needs: `duckdb`. The files written by [03 Stream](03-stream.md) for step 4.

Read first:

- "DuckDB in ten minutes" in [17 Choosing storage](17-choosing-storage.md), if DuckDB is new to you
- `bluesky_bots/storage/base.py`, which defines the interface and the tables, and `sqlite_store.py`, a finished backend
- [`INSERT ... ON CONFLICT`](https://duckdb.org/docs/stable/sql/statements/insert): the clause that makes loading twice safe
- [AT URIs](https://atproto.com/specs/at-uri-scheme), which are the primary keys here

## What you are building

| Piece | File | Does |
| --- | --- | --- |
| `event_to_row(event)` | `records.py` | flattens one Jetstream event into a table row |
| `load_events(store, events)` | `records.py` | stores events, and removes what a delete event names |
| `load_raw_files(store, raw_dir)` | `records.py` | feeds the stream's hourly files through `load_events`, then removes them |
| `DuckDBStore` | `duckdb_store.py` | the default backend: one DuckDB file |

The first three do not care which database is underneath, so you can write and test them today against the finished SQLite backend. `DuckDBStore` is the larger piece. You build the part of it that data collection needs here, and each later service page adds the one to four methods its service needs.

You are done with this page when both of these pass:

```bash
pytest tests/test_storage_records.py
```

```bash
pytest tests/test_store_contract.py -m page05 -k duckdb
```

The contract tests are marked with the page that builds what they need (`page05`, `page07`, and so on), and each runs once per backend.

## Step 1: The interface and the tables

**Concept.** A **store** is an object that saves and fetches the project's rows. Other services never write SQL to save something; they call a method:

```python
from bluesky_bots.storage import open_store

store = open_store()                 # backend and location come from STORAGE_URL in .env
store.add_posts(rows)                # rows are plain dicts keyed by column name
store.delete_record(uri)
```

The methods are listed in the `Store` class in `base.py`. Any class that provides them is a backend. Two exist: `SQLiteStore`, finished, and `DuckDBStore`, yours. `STORAGE_URL` picks one by its first word, the same way a model string picks a provider:

```
duckdb:///data/narrative.duckdb      a path relative to the project root
sqlite:///E:/big/narrative.sqlite    an absolute path
sqlite://:memory:                    nothing on disk, for tests
```

Why an interface at all? So that the database can be changed without touching the ten services that use it, and so that there is exactly one place where a delete has to be right. [17](17-choosing-storage.md) covers when you would change it and to what.

The interface is deliberately narrow. It covers *records*: saving rows and fetching them by key, topic or time. It does not try to cover *analysis*. Signal queries, chart queries and the agent's tools are written as DuckDB SQL against `store.analytics()`, which hands back a DuckDB connection with every table visible, whichever backend holds the rows. Step 9 builds that.

These are the tables, the same in every backend:

| Table | One row per |
| --- | --- |
| `posts` | post, with links to the post it replies to or quotes |
| `reposts` | repost |
| `accounts` | account: creation date, watch-list flag, self-declared bot flag |
| `post_topic` | post and topic it belongs to, with the rule that matched ([02](02-topics.md)) |
| `labels` | post, topic, scheme version, model, target and dimension ([07](07-classify.md)) |
| `embeddings` | post and embedding model ([09](09-narratives.md)) |
| `post_narrative`, `narratives` | post-to-narrative assignment and narrative names, per topic and run |
| `signals` | account, signal and window, with the evidence as JSON ([10](10-signals.md)) |
| `reviews`, `review_queue` | a reviewer's decision; what is waiting for one ([11](11-review.md)) |

The primary key of `posts` and `reposts` is the record's AT URI. It names exactly one record on the network, and both of your sources (the stream and the AppView) can give it to you. That one choice is what lets the stream send an event twice, and the stream and the backfill overlap, without leaving duplicates.

Values cross the interface in one form, whatever the database does underneath: timestamps as timezone-aware `datetime` in UTC (ISO strings are accepted on the way in), booleans as `bool`, vectors as NumPy arrays.

**Your task.** Before you look at the table definitions, sketch `posts` and `reposts` on paper: which columns, which types, which key. For `posts` you need the URI, the author's DID, the creation time, the text, the language, the URI of the post it replies to, the URI of the thread's root, the URI of the post it quotes, and which source it came from. Then compare with what the project uses:

```python
from bluesky_bots.storage import create_tables_sql
print(create_tables_sql("duckdb"))
print(create_tables_sql("sqlite"))
```

**Hints.**

- Timestamps that come with a time zone belong in `TIMESTAMPTZ` in DuckDB. SQLite has no timestamp type; look at what it gets instead.
- `labels` has a six-part primary key. Work out from its "one row per" line what that allows when you change a prompt, add a model, or label a post about two entities.
- `IF NOT EXISTS` makes the whole thing safe to run at every start-up.

**Check.** In a notebook, open an in-memory SQLite store, add one row, and read it back:

```python
store = open_store("sqlite://:memory:")
store.add_posts([{"uri": "at://did:plc:a/app.bsky.feed.post/1", "did": "did:plc:a",
                  "created_at": "2026-11-05T00:00:00Z", "text": "hello"}])
list(store.iter_posts())
```

The `created_at` you get back is a `datetime` in UTC, not the string you put in, and the columns you left out are `None`.

## Step 2: Turn an event into a row

**Concept.** A Jetstream event (the shape is in step 2 of [03](03-stream.md)) has to be flattened into one row. Most fields are optional, and your code must cope with every combination.

| Column | Comes from |
| --- | --- |
| `uri` | `at://{did}/{collection}/{rkey}` |
| `did` | `did` |
| `created_at` | `record.createdAt` |
| `text` | `record.text` |
| `lang` | the first entry of `record.langs`, if any |
| `reply_parent`, `reply_root` | `record.reply.parent.uri`, `record.reply.root.uri`, if it is a reply |
| `quote_of` | the quoted post's URI, if it is a quote |
| `source` | the text `jetstream` |

A repost is simpler: its URI, `did`, `record.subject.uri` and `record.createdAt`.

**Your task.** In `bluesky_bots/storage/records.py`, write `event_to_row(event)`. It returns two things: the table name, `"posts"` or `"reposts"`, and the row as a dict.

**Hints.**

- `at_uri` and `quoted_uri` from [02](02-topics.md) step 3 do two of the columns for you.
- A missing `reply` or `embed` should become `None` in the row. `(x or {}).get(...)` is a compact way to get there.
- `createdAt` is written by the author's app and can be anything. `to_utc` in `base.py` turns a readable value into a UTC `datetime` and an unreadable one into `None`. A post with a broken date is still a post.

**Check.** `pytest tests/test_storage_records.py -k "plain or reply or repost or malformed"`

## Step 3: Load events and honor deletes

**Concept.** When someone deletes a post, the stream sends a delete event with no record, only the parts of the URI. A project that studies people's posts has to stop holding a post its author removed. That is one of this project's rules ([14 Guardrails](14-guardrails.md)) and one of Bluesky's [developer guidelines](https://bsky.network/docs/developer-guidelines).

A delete has to reach everything derived from the post as well as the post itself: its topic membership, its labels, its vector, its narrative assignment, its place in the review queue. That is the store's job, and it is one call: `store.delete_record(uri)`. Your job here is to make that call at the right moment.

Order matters. Events arrive in the order things happened, and a post can be created and deleted minutes apart, in the same file. If you save up rows to insert them in batches, which is much faster than one at a time, a delete must not overtake the insert it refers to.

**Your task.** Write `load_events(store, events)`. For a create or update it converts the event and stores the row; for a delete it removes the record. It returns how many posts, reposts and deletes it saw.

**Hints.**

- You do not know which table a deleted URI is in, and you do not need to. `delete_record` tries them all, and deleting a row that is not there is not an error.
- Handle the delete before anything that reads `event["record"]`.
- Collect rows in two lists and store them when a list is long enough, at the end, and before every delete.

**Check.** `pytest tests/test_storage_records.py -k "twice or one_batch"`

## Step 4: Load the stream's files

**Concept.** The stream in [03](03-stream.md) leaves hourly `.jsonl` files in `data/raw`. The loader reads those files, stores their events, and removes each file once it is loaded.

Two rules:

- **Leave the newest file alone.** The stream is still appending to it.
- **The files are a buffer, not an archive.** If they stayed on disk, so would every deleted post.

**Your task.** Write `load_raw_files(store, raw_dir, keep_newest=True)`. It returns how many files it loaded.

**Hints.**

- The file names sort in time order, which is why they were named that way.
- Pass `load_events` a generator that decodes one line at a time, so a large file is never held in memory whole.
- Delete a file only after its events are stored. Think through what happens if the PC loses power between the two, and why loading a file twice is harmless.

**Check.** `pytest tests/test_storage_records.py -k raw_files`. Then, with `STORAGE_URL` pointing at SQLite in `.env` and a few files in `data/raw`:

```bash
python -m bluesky_bots.storage load
```

```bash
python -m bluesky_bots.storage info
```

All but the newest file are gone, and `posts` has rows. Running `load` again at once changes nothing. You now have a working pipeline from the network to a database. The rest of this page replaces the database.

## Step 5: The DuckDB backend: open and create

**Concept.** DuckDB is a database that runs inside your Python process and keeps everything in one file. There is no server to start. [17](17-choosing-storage.md) has a ten-minute tour; do it now if you have not.

A backend is a class. `open_store` creates one from the path in `STORAGE_URL`, and calls `init_schema()` on it when it was opened for writing.

**Your task.** In `bluesky_bots/storage/duckdb_store.py`, write three methods of `DuckDBStore`:

- `__init__(path, read_only=False)` opens the file, or `":memory:"`, and keeps the connection as `self.con`. It also sets `self.path`, `self.read_only` and `self.url`.
- `init_schema()` creates the tables and the two analysis views.
- `close()` closes the connection.

**Hints.**

- `duckdb.connect(path, read_only=...)`. Opening for writing creates the file but not its folder.
- DuckDB hands timestamps back in the session's time zone, which defaults to the PC's. `SET TimeZone = 'UTC'` right after connecting makes every per-day count in the project agree.
- A query too big for memory spills to a temporary folder. `SET temp_directory = '...'` puts it under `config.DATA_DIR`, on the data drive, instead of wherever the process happens to run.
- `create_tables_sql("duckdb")` is the schema. `views.create_views(con)` creates `labels_final` and `flagged`, which later pages explain.

**Check.** `python -m bluesky_bots.storage init` with the default `STORAGE_URL` (remove the SQLite line from `.env`, or put `duckdb:///data/narrative.duckdb`). It prints where the tables are, and running it twice is not an error.

## Step 6: Two helpers and two conversions

**Concept.** Almost every method does one of two things: insert rows into a table, or run a query and return rows. Writing those once keeps the other twenty methods to a few lines each.

Rows arrive as dicts in the interface's value forms and have to become what DuckDB takes, and the other way round. DuckDB has real types for most of them, so there is little to do:

| Kind (from `TABLES[...].columns`) | Into DuckDB | Out of DuckDB |
| --- | --- | --- |
| `timestamp` | `to_utc(value)`, which also accepts ISO text | `.astimezone(timezone.utc)` |
| `date` | `to_date(value)` | as is |
| `json` | text; `json.dumps` a dict | as is (text) |
| `vector` | a list of floats | `np.asarray(value, dtype=np.float32)` |
| everything else | as is | as is |

**Your task.** Write the module-level functions `_encode(kind, value)` and `_decode(kind, value)`, and the methods `_insert(table, rows, on_conflict="DO NOTHING")` and `_rows(table, sql, params=())`.

**Hints.**

- Pass values as `?` parameters: `con.execute("INSERT ... VALUES (?,?,...)", [values])`. Never build SQL by pasting post text into a string. Post text contains quotes, and worse.
- `TABLES["posts"].columns` is a dict of column name to kind, in table order. `TABLES["posts"].key` is the primary key.
- `ON CONFLICT DO NOTHING` skips a row whose primary key is already there. Only add the clause for tables that have a key.
- `con.executemany(sql, list_of_parameter_lists)` inserts many rows. It refuses an empty list, so return early.
- Wrap a batch in `con.begin()` and `con.commit()`: one transaction is far faster than one per row. Roll back and re-raise if anything fails.
- After `cur = con.execute(...)`, `cur.description` holds the column names and `cur.fetchall()` the rows.
- Compare with `_encode` and `_decode` in `sqlite_store.py`, which have much more to do.

## Step 7: Ingest, delete, read back

**Your task.** With the helpers in place, write:

- `add_posts(rows)` and `add_reposts(rows)`
- `upsert_accounts(rows)`: create the account if it is new, then update only the columns the row actually gives
- `delete_record(uri)`: remove the URI from every table in `URI_TABLES`, and from `review_queue` where it is queued as a post
- `iter_posts()`: every stored post, as dicts

**Hints.**

- The first two are one line each.
- For `upsert_accounts`, "insert the bare `did`, do nothing on conflict, then one `UPDATE` per column that is not `None`" is simple and correct. A background fetch that knows only the creation date must not wipe the handle.
- `URI_TABLES` is in `base.py` so that a table added later is added in one place.

**Check.** `pytest tests/test_store_contract.py -m page05 -k "duckdb and (twice or promised or malformed or upsert)"`. The delete test needs step 8 as well.

## Step 8: Topic membership

**Your task.** Write the two methods the topics service uses ([02](02-topics.md) step 8), plus the classifier's and clusterer's way of asking for a topic's posts:

- `set_post_topics(topic, rows)`: replace that topic's membership
- `posts_in_topic(topic, since=None, until=None)`: the topic's posts, oldest first, each with `parent_text`, the text of the post it replies to when that post is stored

**Hints.**

- "Replace" is a `DELETE` for the topic followed by an insert.
- `parent_text` is a `LEFT JOIN` of `posts` to itself on `reply_parent`. A reply means little without what it answers, and a model is shown both.
- The example puts the shared query in a small private method, `_topic_posts`, because [07](07-classify.md) adds a second method that needs the same join.

**Check.** `pytest tests/test_store_contract.py -m page05 -k "duckdb and (membership or delete)"`

## Step 9: Moving data and analysing it

**Concept.** Two last pieces make the backend a full member.

**Portability.** `export_table(name)` yields every row of a table in the interface's value forms, and `import_table(name, rows)` inserts such rows. With those two, `copy_store` in `base.py` copies everything from any backend to any other. Changing your mind about storage costs one command.

**Analysis.** `analytics()` returns a DuckDB connection for reading. For this backend the data is already in DuckDB, so it is a second cursor on the same database. For the SQLite backend, DuckDB attaches the SQLite file and reads it in place (see `views.py`). Either way, the code that asks a question writes the same SQL.

**Your task.** Write `export_table`, `import_table` and `analytics`.

**Hints.**

- Both of the first two are one line on top of your helpers.
- `self.con.cursor()` gives an independent cursor. Set its time zone too.

**Check.** `pytest tests/test_store_contract.py -m page05 -k duckdb` now passes in full. Then copy what you collected in SQLite into DuckDB:

```bash
python -m bluesky_bots.storage copy --from sqlite:///data/narrative.sqlite --to duckdb:///data/narrative.duckdb
```

## Step 10: Read from a notebook

**Concept.** Everything that is not a batch command opens the store read-only: notebooks, the agent's tools in [12](12-agent.md), the reports in [13](13-reports.md).

```python
import bluesky_bots
from bluesky_bots.storage import open_store

store = open_store(read_only=True)
con = store.analytics()
con.sql("SELECT source, count(*) FROM posts GROUP BY 1").df()
```

**Your task.** Run that, then show the number of posts per topic from `post_topic`.

**Check.** Run `SELECT max(created_at) FROM posts`. It is in UTC. A post made late in the evening, US Eastern, belongs to the next day in UTC, which is why the time zone is fixed in one place and not left to each notebook.

Close the store (`store.close()`) or shut the kernel down when you are finished. The next section says why.

## Good to know

- **DuckDB locks the whole file.** Tested on this PC with DuckDB 2.0.0: while one process has the file open for writing, no other process can open it at all. While any process has it open read-only, others can read but nothing can write. So an open notebook blocks the loader, with an error that the file is in use. Close the notebook's store first. The SQLite backend does not have this limit ([17](17-choosing-storage.md)).
- **Run batch commands one at a time.** For the same reason. The stream is not affected: it writes files.
- **Deletes are honored in one place.** `delete_record` removes the URI from every table in `URI_TABLES` and from the review queue.
- **Loading twice is safe.** Primary keys plus `ON CONFLICT DO NOTHING` drop repeats.
- **Landing files are a buffer.** `load_raw_files` removes each file after loading so deleted posts do not linger on disk.
- **A backend is finished when the contract tests pass for it.** `tests/test_store_contract.py` runs every test once per backend. To add a third backend, write the class, add it to `_backend` in `storage/__init__.py` and to the `store` fixture in `tests/conftest.py`.
- **Keyless tables append.** `signals` and `reviews` have no primary key, so importing them twice doubles them. Copy into an empty store.
- Row-at-a-time inserts are fine for a filtered stream. If loading gets slow, DuckDB can read whole files with [`read_json_auto`](https://duckdb.org/docs/stable/data/json/overview).

## Example solution

This is the code that was run on this PC on 2026-11-13. `tests/test_storage_records.py` and every test in `tests/test_store_contract.py` pass against it, for both backends. The commands were also run end to end on made-up landing files: load, assign, info, and a copy from DuckDB to SQLite with the same row counts on both sides.

<details>
<summary>Show example: step 2, an event into a row (bluesky_bots/storage/records.py)</summary>

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..aturi import at_uri, quoted_uri
from .base import to_utc


REPOST = "app.bsky.feed.repost"


def event_to_row(event: dict) -> tuple[str, dict]:
    """Flatten a Jetstream create or update event into ("posts" or "reposts", row).

    A field the record does not have becomes None in the row.
    """
    uri, rec = at_uri(event), event.get("record") or {}
    if event["collection"] == REPOST:
        return "reposts", {"uri": uri, "did": event["did"],
                           "subject_uri": (rec.get("subject") or {}).get("uri"),
                           "created_at": to_utc(rec.get("createdAt"))}
    reply = rec.get("reply") or {}
    return "posts", {"uri": uri, "did": event["did"], "created_at": to_utc(rec.get("createdAt")),
                     "text": rec.get("text", ""), "lang": (rec.get("langs") or [None])[0],
                     "reply_parent": (reply.get("parent") or {}).get("uri"),
                     "reply_root": (reply.get("root") or {}).get("uri"),
                     "quote_of": quoted_uri(rec), "source": "jetstream"}
```

</details>

<details>
<summary>Show example: step 3, loading events and honoring deletes</summary>

```python
def load_events(store, events: Iterable[dict], batch: int = 500) -> dict[str, int]:
    """Store Jetstream events, and remove what a delete event names.

    Events are applied in order, so a post created and then deleted in the
    same file ends up gone. Returns how many posts, reposts and deletes it saw.
    """
    pending = {"posts": [], "reposts": []}
    counts = {"posts": 0, "reposts": 0, "deletes": 0}

    def flush():
        if pending["posts"]:
            store.add_posts(pending["posts"])
        if pending["reposts"]:
            store.add_reposts(pending["reposts"])
        pending["posts"], pending["reposts"] = [], []

    for event in events:
        if event["operation"] == "delete":
            flush()                         # anything waiting must be stored before it can be removed
            store.delete_record(at_uri(event))
            counts["deletes"] += 1
            continue
        table, row = event_to_row(event)
        pending[table].append(row)
        counts[table] += 1
        if len(pending[table]) >= batch:
            flush()
    flush()
    return counts
```

</details>

<details>
<summary>Show example: step 4, loading the stream's files</summary>

```python
def load_raw_files(store, raw_dir: str | Path, keep_newest: bool = True) -> int:
    """Feed the stream's hourly files through load_events, removing each file once it is stored.

    The newest file is left alone when keep_newest is true, because the
    stream is still appending to it. Returns how many files were loaded.
    """
    files = sorted(Path(raw_dir).glob("*.jsonl"))
    if keep_newest:
        files = files[:-1]
    for path in files:
        with open(path, encoding="utf-8") as f:
            load_events(store, (json.loads(line) for line in f))
        path.unlink()                       # landing files are a buffer, not an archive
    return len(files)
```

</details>

<details>
<summary>Show example: step 5, opening the database (bluesky_bots/storage/duckdb_store.py)</summary>

```python
from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path
from typing import Iterable, Iterator

import duckdb
import numpy as np

from .. import config
from . import views
from .base import TABLES, URI_TABLES, create_tables_sql, now_utc, to_date, to_utc


class DuckDBStore:
    ...

    def __init__(self, path: str, read_only: bool = False):
        """Open the database file (or ':memory:'), creating its folder when opening for writing."""
        self.path, self.read_only = str(path), read_only
        self.url = "duckdb://:memory:" if self.path == ":memory:" else "duckdb:///" + Path(path).as_posix()
        if self.path != ":memory:" and not read_only:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(self.path, read_only=read_only)
        self.con.execute("SET TimeZone = 'UTC'")
        # Queries too big for memory spill to disk; keep that on the data drive.
        self.con.execute("SET temp_directory = '" + (config.DATA_DIR / "tmp").as_posix() + "'")

    def init_schema(self) -> None:
        """Create the tables and the analysis views if they are missing."""
        self.con.execute(create_tables_sql("duckdb"))
        views.create_views(self.con)

    def close(self) -> None:
        """Close the connection."""
        self.con.close()
```

</details>

<details>
<summary>Show example: step 6, conversions and helpers</summary>

```python
def _encode(kind: str, value):
    """A Python value in the form DuckDB takes for a column of this kind."""
    if value is None:
        return None
    if kind == "timestamp":
        return to_utc(value)
    if kind == "date":
        return to_date(value)
    if kind == "json":
        return value if isinstance(value, str) else json.dumps(value)
    if kind == "vector":
        return np.asarray(value, dtype=np.float32).tolist()
    return value


def _decode(kind: str, value):
    """A value DuckDB returned, in the form the Store interface promises."""
    if value is None:
        return None
    if kind == "timestamp":
        return value.astimezone(timezone.utc)
    if kind == "vector":
        return np.asarray(value, dtype=np.float32)
    return value


class DuckDBStore:
    ...

    # --- helpers ----------------------------------------------------------
    def _insert(self, table: str, rows: Iterable[dict], on_conflict: str = "DO NOTHING") -> None:
        """Insert rows into a table in one transaction; columns a row leaves out are stored as NULL."""
        spec = TABLES[table]
        names = list(spec.columns)
        data = [[_encode(spec.columns[n], row.get(n)) for n in names] for row in rows]
        if not data:
            return                          # executemany refuses an empty list
        sql = (f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})"
               + (f" ON CONFLICT {on_conflict}" if spec.key else ""))
        self.con.begin()
        try:
            self.con.executemany(sql, data)
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise

    def _rows(self, table: str, sql: str, params=()) -> list[dict]:
        """Run a query and return dicts, decoding each column by its type in `table`."""
        kinds = TABLES[table].columns
        cur = self.con.execute(sql, params)
        names = [d[0] for d in cur.description]
        return [{n: _decode(kinds.get(n, "text"), v) for n, v in zip(names, row)}
                for row in cur.fetchall()]
```

</details>

<details>
<summary>Show example: step 7, ingest, delete, read back</summary>

```python
class DuckDBStore:
    ...

    # --- ingest -----------------------------------------------------------
    def add_posts(self, rows: Iterable[dict]) -> None:
        """Insert posts. A row whose uri is already stored is skipped."""
        self._insert("posts", rows)

    def add_reposts(self, rows: Iterable[dict]) -> None:
        """Insert reposts. A row whose uri is already stored is skipped."""
        self._insert("reposts", rows)

    def upsert_accounts(self, rows: Iterable[dict]) -> None:
        """Create accounts or update them. A column that is missing or None keeps its stored value."""
        kinds = TABLES["accounts"].columns
        for row in rows:
            self.con.execute("INSERT INTO accounts (did) VALUES (?) ON CONFLICT DO NOTHING", [row["did"]])
            for name, kind in kinds.items():
                if name != "did" and row.get(name) is not None:
                    self.con.execute(f"UPDATE accounts SET {name} = ? WHERE did = ?",
                                     [_encode(kind, row[name]), row["did"]])

    def delete_record(self, uri: str) -> None:
        """Remove a record its author deleted from every table in URI_TABLES and from the review queue."""
        for table in URI_TABLES:
            self.con.execute(f"DELETE FROM {table} WHERE uri = ?", [uri])
        self.con.execute("DELETE FROM review_queue WHERE item_type = 'post' AND item_id = ?", [uri])

    # --- fetch ------------------------------------------------------------
    def iter_posts(self) -> Iterator[dict]:
        """Every stored post."""
        yield from self._rows("posts", "SELECT * FROM posts ORDER BY created_at, uri")
```

</details>

<details>
<summary>Show example: step 8, topic membership</summary>

```python
class DuckDBStore:
    ...

    # --- derived data -----------------------------------------------------
    def set_post_topics(self, topic: str, rows: Iterable[dict]) -> None:
        """Replace a topic's membership with `rows` (each has uri and matched_by)."""
        now = now_utc()
        self.con.execute("DELETE FROM post_topic WHERE topic = ?", [topic])
        self._insert("post_topic", ({"uri": r["uri"], "topic": topic, "matched_by": r.get("matched_by"),
                                     "assigned_at": now} for r in rows))

    def _topic_posts(self, topic: str, extra: str = "", params: list | None = None,
                     limit: int | None = None) -> list[dict]:
        """A topic's posts with parent_text, oldest first; `extra` adds conditions to the WHERE."""
        sql = f"""
            SELECT p.*, parent.text AS parent_text
            FROM post_topic t JOIN posts p ON p.uri = t.uri
            LEFT JOIN posts parent ON parent.uri = p.reply_parent
            WHERE t.topic = ? {extra}
            ORDER BY p.created_at, p.uri""" + (f" LIMIT {int(limit)}" if limit else "")
        return self._rows("posts", sql, [topic] + (params or []))

    def posts_in_topic(self, topic, since=None, until=None) -> list[dict]:
        """Posts assigned to a topic, oldest first, each with `parent_text`."""
        extra, params = "", []
        if since is not None:
            extra += " AND p.created_at >= ?"
            params.append(to_utc(since))
        if until is not None:
            extra += " AND p.created_at < ?"
            params.append(to_utc(until))
        return self._topic_posts(topic, extra, params)
```

</details>

<details>
<summary>Show example: step 9, moving data and analysing it</summary>

```python
class DuckDBStore:
    ...

    # --- portability ------------------------------------------------------
    def export_table(self, table: str) -> Iterator[dict]:
        """Every row of a table, in the value forms the Store interface promises."""
        yield from self._rows(table, f"SELECT * FROM {TABLES[table].name}")

    def import_table(self, table: str, rows: Iterable[dict]) -> None:
        """Insert rows produced by export_table. Rows whose key is already stored are skipped."""
        self._insert(table, rows)

    # --- analysis ---------------------------------------------------------
    def analytics(self):
        """A DuckDB connection for reading: a second cursor on this same database."""
        cur = self.con.cursor()
        cur.execute("SET TimeZone = 'UTC'")
        return cur
```

</details>
