# 17 Choosing storage

A ten-minute tour of DuckDB, how big this project's data gets, and what to move to when it outgrows one file. The code on the other pages does not care which database is underneath: it talks to a store, and `STORAGE_URL` in `.env` says which one ([05](05-storage.md)).

Everything in "DuckDB in ten minutes" and every number marked *measured* was run on this PC on 2026-11-13 with DuckDB 2.0.0 and SQLite 3.54.1. The options beyond DuckDB and SQLite are described from their documentation and have not been run here.

## Where storage is set

| Key | Default | Meaning |
| --- | --- | --- |
| `STORAGE_URL` | `duckdb:///data/narrative.duckdb` | The backend (the word before `://`) and where it is |
| `DATA_DIR` | `data` | Landing files, the default database, trained classifiers, DuckDB's temporary files |

```bash
STORAGE_URL=duckdb:///data/narrative.duckdb
STORAGE_URL=sqlite:///data/narrative.sqlite
STORAGE_URL=duckdb:///E:/bluesky-data/narrative.duckdb
```

Two backends exist. To move everything from one to the other:

```bash
python -m bluesky_bots.storage copy --from sqlite:///data/narrative.sqlite --to duckdb:///data/narrative.duckdb
```

## DuckDB in ten minutes

DuckDB is a database that runs inside your Python process. There is no server to install or start: `import duckdb`, open a file, and write SQL. The whole database is that one file. It is built for analysis, which means it is fast at "count, group and join millions of rows" and less suited to many small updates from many programs at once.

Run these in a notebook, in order.

**Open a file, make a table, put rows in.**

```python
import duckdb

con = duckdb.connect("tour.duckdb")          # creates the file if it is not there
con.execute("CREATE TABLE posts (uri TEXT PRIMARY KEY, did TEXT, created_at TIMESTAMPTZ, text TEXT)")
con.execute("INSERT INTO posts VALUES (?, ?, ?, ?)",
            ["at://did:plc:a/app.bsky.feed.post/1", "did:plc:a", "2026-11-05T23:30:00Z", "hello"])
```

The `?` marks are filled from the list. Always pass values this way. Never paste text into the SQL string yourself: the second row below contains both kinds of quote, and it goes in without trouble.

```python
con.executemany("INSERT INTO posts VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING", [
    ["at://did:plc:a/app.bsky.feed.post/1", "did:plc:a", "2026-11-05T23:30:00Z", "hello again"],
    ["at://did:plc:b/app.bsky.feed.post/1", "did:plc:b", "2026-11-06T01:00:00Z", "it's \"quoted\""],
])
con.execute("SELECT count(*) FROM posts").fetchall()
```

```
[(2,)]
```

Two rows, not three. The first row of the batch has a `uri` that is already there, and `ON CONFLICT DO NOTHING` skipped it. That clause is why loading the same data twice is safe everywhere in this project.

**Get results out.** `fetchall()` gives a list of tuples. `.df()` gives a pandas DataFrame, which is what you want in a notebook.

```python
con.sql("SELECT did, count(*) AS n FROM posts GROUP BY 1 ORDER BY 1").df()
```

```
         did  n
0  did:plc:a  1
1  did:plc:b  1
```

Prefer `fetchall()` to `fetchone()`. In DuckDB 2.0 a result you have only partly read stays open, and the next query on the same connection can fail with "connection has an unfinished result".

**Look around.**

```python
con.sql("SHOW TABLES").fetchall()        # [('posts',)]
con.sql("DESCRIBE posts").df()           # column names and types
con.sql("SUMMARIZE posts").df()          # min, max, distinct count and more, per column
```

**Time zones.** A `TIMESTAMPTZ` is stored as a moment in time and shown in the session's time zone, which starts as the PC's:

```python
con.execute("SELECT created_at FROM posts ORDER BY 1 LIMIT 1").fetchall()[0][0]
```

```
2026-11-05 18:30:00-05:00
```

```python
con.execute("SET TimeZone = 'UTC'")
con.execute("SELECT created_at FROM posts ORDER BY 1 LIMIT 1").fetchall()[0][0]
```

```
2026-11-05 23:30:00+00:00
```

Same moment, shown two ways. It matters when you count per day: a post made at 20:00 Eastern on the 5th is on the 6th in UTC. The project's DuckDB backend sets UTC when it connects, so every count agrees.

**Query a file without loading it.** DuckDB reads JSON Lines, CSV and Parquet files in place. A stream landing file is JSON Lines:

```python
con.sql("SELECT did, record.text AS text FROM 'data/raw/2026-11-13T05.jsonl' LIMIT 3").fetchall()
```

`record.text` reaches inside the nested record. This is the quickest way to look at what the stream is keeping.

**Write and read Parquet.** Parquet is a compact column-by-column file format that many tools read.

```python
con.execute("COPY posts TO 'posts.parquet' (FORMAT parquet)")
con.sql("SELECT count(*) FROM 'posts.parquet'").fetchall()        # [(2,)]

con.execute("""COPY (SELECT *, CAST(created_at AS DATE) AS day FROM posts)
               TO 'by_day' (FORMAT parquet, PARTITION_BY (day))""")
```

The second command writes one folder per day: `by_day/day=2026-11-05/data_0.parquet`, `by_day/day=2026-11-06/data_0.parquet`. Read them back as one table, and DuckDB opens only the folders a query needs:

```python
con.sql("""SELECT day, count(*) FROM read_parquet('by_day/*/*.parquet', hive_partitioning = true)
           GROUP BY 1 ORDER BY 1""").fetchall()
```

**Back up.** Either copy the database file while nothing has it open, or:

```python
con.execute("EXPORT DATABASE 'backup' (FORMAT parquet)")   # schema.sql, load.sql and one Parquet file per table
con.close()
```

**The one rule to remember: one writer, or many readers, never both.** Tested on this PC:

| Another process has the file open | You open it read-only | You open it for writing |
| --- | --- | --- |
| read-only (a notebook, say) | works | fails: the file is in use |
| for writing (a batch command) | fails | fails |

`duckdb.connect(path, read_only=True)` is the read-only form; the project's `open_store(read_only=True)` uses it. This rule is why the stream writes files instead of rows, why batch commands run one at a time, and why you close a notebook's store before loading. The [concurrency page](https://duckdb.org/docs/stable/connect/concurrency) has the detail.

There is also a command-line program; see the [DuckDB documentation](https://duckdb.org/docs/stable/). In this project you will mostly use `open_store(read_only=True).analytics()`, which gives you a connection like `con` above with every table and view ready.

## How big will it get

Three things take the space, in rising order.

| What | Size | Basis |
| --- | --- | --- |
| A post's row (uri, author, time, about 190 characters of text) | about 200 bytes in DuckDB, 350 in SQLite, 65 in compressed Parquet | *measured* on 100,000 made-up posts. Real text repeats more than random words and should compress somewhat better. |
| Labels, topic membership, signals | tens of bytes per row, a few rows per post | estimate |
| A post's embedding (768 numbers) | about 2,800 bytes in DuckDB; 3,072 raw | *measured* on 20,000 vectors. Random numbers do not compress; neither do real embeddings, much. |

So an embedding is more than ten times the size of the post it came from. If storage becomes a problem, it will be because of vectors.

How many posts depends on your topics. Two reference points:

| Capture | Posts per day | Rows | Vectors, if every post is embedded |
| --- | --- | --- | --- |
| The example topic | about 36,000 (5 kept in a 12-second run on 2026-11-13; a rough figure from a tiny sample) | about 7 MB a day | about 100 MB a day |
| Everything (`stream --all`) | up to about 5 million events (60 a second, *measured* earlier; reposts included) | about 1 GB a day | about 14 GB a day |

At the example topic's rate, a year of rows is a few gigabytes and fits in one DuckDB file with room to spare on drive E:. Capturing everything is a different project: a month of rows is 30 GB, and embedding it all is not practical on this PC.

**Measure your own** once the stream has run for a day:

```python
from pathlib import Path
from bluesky_bots import config
from bluesky_bots.storage import open_store

files = sorted(config.RAW_DIR.glob("*.jsonl"))[:-1]            # finished hours
events = sum(1 for f in files for _ in open(f, encoding="utf-8"))
print("events per hour:", events // max(len(files), 1))
print("bytes per event in landing files:", sum(f.stat().st_size for f in files) // max(events, 1))

con = open_store(read_only=True).analytics()
print(con.sql("SELECT count(*) AS posts FROM posts").fetchall())
print(con.sql("CALL pragma_database_size()").df())            # DuckDB backend only
```

**Keeping vectors small**, cheapest first:

- Embed only what you cluster or classify: one topic's rolling window, not everything stored. The narratives service already works this way.
- Ask the embedding model for fewer dimensions. Several models, EmbeddingGemma and Gemini's among them, are trained so that a shortened vector still works; check the model's documentation for the supported sizes. A quarter of the dimensions is a quarter of the space. All vectors under one model name must be the same length, so treat a new size as a new model.
- Delete vectors older than your clustering window. They can be recomputed.

## Options, smallest step first

| Option | What it is | When it fits | What it takes here |
| --- | --- | --- | --- |
| **One DuckDB file** (default) | Everything in `data/narrative.duckdb` | Topic-filtered capture; one person; analysis on this PC. Comfortable into the tens of gigabytes. | Built on [05](05-storage.md). |
| **SQLite** (provided) | One file, built into Python | You want to read in a notebook while a batch command writes, or you have not built the DuckDB backend yet. Slower than DuckDB at large aggregations. | Nothing: set `STORAGE_URL`. Analysis still runs in DuckDB, which reads the SQLite file in place. |
| **DuckDB plus Parquet for old data** | Recent days in the DuckDB file; older days exported to Parquet folders by day, queried with the same SQL | The file is getting large and old data is rarely touched | A step in `DuckDBStore`: export days past a cutoff, delete them from the tables, and make `analytics()` expose a view over both. Deletes then have to reach the Parquet files too (see below). |
| **[DuckLake](https://ducklake.select/)** | A lakehouse format from the DuckDB team: data as Parquet files, with a small catalog database tracking them. Requires DuckDB 2.0 or later, which this PC has. | Data too big for one file, still on one machine or a shared disk. With SQLite or PostgreSQL as the catalog, more than one process can write. | A new backend, close to the DuckDB one. One real difference: DuckLake has no primary keys, so "skip a row that is already there" must be written as a query instead of `ON CONFLICT`. |
| **[MotherDuck](https://motherduck.com/docs/)** | DuckDB hosted as a service | You want the data off this PC or shared with someone, and to keep writing DuckDB SQL | Close to a one-line change in how the DuckDB backend connects, plus an account. Post text then lives with a third party; read their terms. |
| **PostgreSQL**, with [pgvector](https://github.com/pgvector/pgvector) for embeddings | A database server | Several programs or people writing at once; a long-lived shared installation | A new backend with the `psycopg` driver. Its SQL is close to the SQLite backend's. You install and look after a server. DuckDB can attach PostgreSQL, so analysis SQL keeps working. |
| **[ClickHouse](https://clickhouse.com/docs)** | A column-store server built for billions of rows | Capturing everything, for months | A new backend, and the analysis SQL has to be ported: DuckDB does not read ClickHouse in place. The most upkeep of anything here. |
| **[BigQuery](https://cloud.google.com/bigquery/docs)** | Google's serverless warehouse; pay per query | The project moves to Google Cloud ([15](15-google-cloud.md)) | A new backend, and ported analysis SQL. No server, but a bill that depends on how much each query reads. |

A sensible path: stay on one DuckDB file until something specific hurts. If what hurts is "I cannot read while it writes", try SQLite. If it is size, move old data to Parquet or to DuckLake. If it is more than one person, PostgreSQL or MotherDuck.

## What moves and what does not

The project splits storage work in two, and they move differently.

**Records** are what the pipeline saves and fetches: posts, labels, vectors, queue items. They go through the `Store` interface, so a new database means one new class, and nothing else changes. `tests/test_store_contract.py` tells you when the class is right, and `storage copy` moves the data.

**Analysis** is the signal queries, the chart query, the agent's tools and the training-set query. They are DuckDB SQL, run on the connection `store.analytics()` returns. For any store DuckDB can read (its own files, Parquet, DuckLake, SQLite, PostgreSQL, MotherDuck), `analytics()` hands back DuckDB looking at that store, and not one query changes. For a store DuckDB cannot read in place, these are the pieces to translate:

| DuckDB | Used in | What to look for elsewhere |
| --- | --- | --- |
| `time_bucket(INTERVAL '10 minutes', t)` | burst signal | a date-truncation or interval-bucketing function |
| `date_diff('day', a, b)` | age and sync signals | date subtraction; argument order differs between databases |
| `QUALIFY row_number() OVER (...) = 1` | `labels_final` | a subquery around the window function |
| `count(...) FILTER (WHERE ...)` | chart and agent tool | `count(CASE WHEN ... END)`, where `FILTER` is missing |
| `unnest(?)` with a list parameter | vector lookup (a record operation, DuckDB backend only) | an `IN` list or an array parameter |
| `evidence->>'$.posts'` | reading signal evidence | that database's JSON functions |

## Deletes at scale

Honoring a delete means the post is gone, not just hidden. `store.delete_record` removes the rows. Whether the *bytes* leave the disk depends on the database, and it is worth knowing before you promise anything.

| Option | After `delete_record` | To remove the bytes |
| --- | --- | --- |
| DuckDB file | The row is gone from every query. *Measured*: after deleting every row and running `CHECKPOINT`, the file shrank from 20.5 MB to 0.3 MB, but the deleted text could still be found in the file's bytes. `VACUUM` did not change that, which matches the [documentation](https://duckdb.org/docs/stable/operations_manual/footprint_of_duckdb/reclaiming_space). | Copy into a fresh file: attach a new database and run `COPY FROM DATABASE old TO new`. *Measured*: the text was not in the new file. `storage copy` to a new `STORAGE_URL` does the same. |
| SQLite file | The row is gone from every query. *Measured*: the file did not shrink and the text was still in it. | `VACUUM` (*measured*: file shrank, text gone), or turn on `PRAGMA secure_delete`, which overwrites deleted content as it goes. |
| Landing files | A delete event sits in a later file than the post it deletes | Nothing to do: `load_raw_files` removes each file once loaded. |
| Parquet archive | Parquet files are not edited in place. The row stays until the file is rewritten. | Keep a list of deleted URIs, leave them out when reading, and rewrite the affected day's file on a schedule. This is the hard part of the Parquet option. |
| DuckLake | A delete is recorded in a separate delete file; the original data file is unchanged | Its maintenance operations rewrite files with deletes and clean up old ones. Read its [documentation](https://ducklake.select/docs/stable/) for the current commands and schedule them. |
| PostgreSQL | The row is gone from queries; its space is reused later | PostgreSQL's own vacuuming reclaims the space over time. |
| Backups and exports | A backup made before the delete still holds the post | Keep backups for a short, stated time, and never publish row-level exports ([13](13-reports.md)). |

For a single-file store, a monthly compaction (copy into a fresh file, replace the old one) is a simple way to make deletes final.

## Resources

- [DuckDB documentation](https://duckdb.org/docs/stable/): the [Python client](https://duckdb.org/docs/stable/clients/python/overview), [concurrency](https://duckdb.org/docs/stable/connect/concurrency), [Parquet](https://duckdb.org/docs/stable/data/parquet/overview), [reclaiming space](https://duckdb.org/docs/stable/operations_manual/footprint_of_duckdb/reclaiming_space)
- [DuckLake](https://ducklake.select/), including [choosing a catalog database](https://ducklake.select/docs/stable/duckdb/usage/choosing_a_catalog_database)
- [SQLite: write-ahead logging](https://www.sqlite.org/wal.html), the mode the SQLite backend uses so readers and a writer can overlap
- [MotherDuck documentation](https://motherduck.com/docs/)
- [PostgreSQL documentation](https://www.postgresql.org/docs/) and [pgvector](https://github.com/pgvector/pgvector)
- [ClickHouse documentation](https://clickhouse.com/docs) and [BigQuery documentation](https://cloud.google.com/bigquery/docs)
- [Apache Parquet](https://parquet.apache.org/docs/), the file format
