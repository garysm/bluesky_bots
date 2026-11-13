"""A complete storage backend on SQLite, which ships with Python.

It has three jobs: to show that the Store interface does not depend on
DuckDB, to be a worked example of a backend, and to let the pipeline and the
tests run before the DuckDB backend is built (docs/05-storage.md).

SQLite has no timestamp, boolean or list type, so this class converts on the
way in (`_encode`) and on the way out (`_decode`). Timestamps are stored as
ISO text in UTC, which sorts in time order.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np

from . import views
from .base import TABLES, URI_TABLES, create_tables_sql, now_utc, to_date, to_utc


def _encode(kind: str, value):
    if value is None:
        return None
    if kind == "timestamp":
        ts = to_utc(value)
        return ts.isoformat(timespec="microseconds") if ts else None
    if kind == "date":
        return to_date(value).isoformat()
    if kind == "bool":
        return int(bool(value))
    if kind == "json":
        return value if isinstance(value, str) else json.dumps(value)
    if kind == "vector":
        return np.asarray(value, dtype=np.float32).tobytes()
    return value


def _decode(kind: str, value):
    if value is None:
        return None
    if kind == "timestamp":
        return datetime.fromisoformat(value)
    if kind == "date":
        return date.fromisoformat(value)
    if kind == "bool":
        return bool(value)
    if kind == "vector":
        return np.frombuffer(value, dtype=np.float32).copy()
    return value


class SQLiteStore:
    dialect = "sqlite"

    def __init__(self, path: str, read_only: bool = False):
        # check_same_thread=False: ADK may run a workflow node on a worker thread. The store is
        # still used by one caller at a time.
        self.path, self.read_only = str(path), read_only
        self.url = "sqlite://:memory:" if self.path == ":memory:" else "sqlite:///" + Path(path).as_posix()
        if self.path == ":memory:":
            self.con = sqlite3.connect(":memory:", check_same_thread=False)
        elif read_only:
            self.con = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True,
                                       check_same_thread=False)
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.con = sqlite3.connect(self.path, check_same_thread=False)
            # Write-ahead logging lets other processes read while this one writes.
            self.con.execute("PRAGMA journal_mode = WAL")
        self.con.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self.con.executescript(create_tables_sql("sqlite"))

    def close(self) -> None:
        self.con.close()

    # --- helpers ----------------------------------------------------------
    def _insert(self, table: str, rows: Iterable[dict], on_conflict: str = "DO NOTHING") -> None:
        """Insert rows into a table; columns a row leaves out are stored as NULL."""
        spec = TABLES[table]
        names = list(spec.columns)
        sql = (f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})"
               + (f" ON CONFLICT {on_conflict}" if spec.key else ""))
        with self.con:      # one transaction for the whole batch
            self.con.executemany(sql, ([_encode(spec.columns[n], row.get(n)) for n in names]
                                       for row in rows))

    def _rows(self, table: str, sql: str, params=()) -> list[dict]:
        """Run a query and decode each column by its type in `table`."""
        kinds = TABLES[table].columns
        return [{k: _decode(kinds.get(k, "text"), row[k]) for k in row.keys()}
                for row in self.con.execute(sql, params)]

    # --- ingest -----------------------------------------------------------
    def add_posts(self, rows: Iterable[dict]) -> None:
        self._insert("posts", rows)

    def add_reposts(self, rows: Iterable[dict]) -> None:
        self._insert("reposts", rows)

    def upsert_accounts(self, rows: Iterable[dict]) -> None:
        kinds = TABLES["accounts"].columns
        with self.con:
            for row in rows:
                self.con.execute("INSERT INTO accounts (did) VALUES (?) ON CONFLICT DO NOTHING",
                                 [row["did"]])
                for name, kind in kinds.items():
                    if name != "did" and row.get(name) is not None:
                        self.con.execute(f"UPDATE accounts SET {name} = ? WHERE did = ?",
                                         [_encode(kind, row[name]), row["did"]])

    def delete_record(self, uri: str) -> None:
        with self.con:
            for table in URI_TABLES:
                self.con.execute(f"DELETE FROM {table} WHERE uri = ?", [uri])
            self.con.execute("DELETE FROM review_queue WHERE item_type = 'post' AND item_id = ?", [uri])

    # --- fetch ------------------------------------------------------------
    def iter_posts(self) -> Iterator[dict]:
        yield from self._rows("posts", "SELECT * FROM posts ORDER BY created_at, uri")

    def _topic_posts(self, topic: str, extra: str = "", params: list | None = None,
                     limit: int | None = None) -> list[dict]:
        sql = f"""
            SELECT p.*, parent.text AS parent_text
            FROM post_topic t JOIN posts p ON p.uri = t.uri
            LEFT JOIN posts parent ON parent.uri = p.reply_parent
            WHERE t.topic = ? {extra}
            ORDER BY p.created_at, p.uri""" + (f" LIMIT {int(limit)}" if limit else "")
        return self._rows("posts", sql, [topic] + (params or []))

    def posts_in_topic(self, topic, since=None, until=None) -> list[dict]:
        extra, params = "", []
        if since is not None:
            extra += " AND p.created_at >= ?"
            params.append(_encode("timestamp", since))
        if until is not None:
            extra += " AND p.created_at < ?"
            params.append(_encode("timestamp", until))
        return self._topic_posts(topic, extra, params)

    def unlabeled_posts(self, topic, scheme_version, model=None, limit=None) -> list[dict]:
        extra = """ AND NOT EXISTS (
            SELECT 1 FROM labels l
            WHERE l.uri = p.uri AND l.topic = t.topic AND l.scheme_version = ?"""
        params = [scheme_version]
        if model is not None:
            extra += " AND l.model = ?"
            params.append(model)
        return self._topic_posts(topic, extra + ")", params, limit)

    # --- derived data -----------------------------------------------------
    def set_post_topics(self, topic: str, rows: Iterable[dict]) -> None:
        now = now_utc()
        with self.con:
            self.con.execute("DELETE FROM post_topic WHERE topic = ?", [topic])
        self._insert("post_topic", ({"uri": r["uri"], "topic": topic, "matched_by": r.get("matched_by"),
                                     "assigned_at": now} for r in rows))

    def save_labels(self, rows: Iterable[dict]) -> None:
        now = now_utc()
        key = ", ".join(TABLES["labels"].key)
        self._insert("labels", ({"target": "", "labeled_at": now, **r} for r in rows),
                     on_conflict=f"({key}) DO UPDATE SET value = excluded.value, "
                                 "confidence = excluded.confidence, tier = excluded.tier, "
                                 "labeled_at = excluded.labeled_at")

    def save_vectors(self, model: str, vectors: dict[str, np.ndarray]) -> None:
        self._insert("embeddings", ({"uri": uri, "model": model, "vector": v}
                                    for uri, v in vectors.items()),
                     on_conflict="(uri, model) DO UPDATE SET vector = excluded.vector")

    def load_vectors(self, model: str, uris=None) -> dict[str, np.ndarray]:
        if uris is None:
            rows = self._rows("embeddings", "SELECT uri, vector FROM embeddings WHERE model = ?", [model])
            return {r["uri"]: r["vector"] for r in rows}
        out, uris = {}, list(uris)
        for i in range(0, len(uris), 500):          # SQLite limits how many ? one statement may hold
            chunk = uris[i:i + 500]
            marks = ", ".join("?" for _ in chunk)
            for r in self._rows("embeddings", f"SELECT uri, vector FROM embeddings "
                                              f"WHERE model = ? AND uri IN ({marks})", [model, *chunk]):
                out[r["uri"]] = r["vector"]
        return out

    def save_narratives(self, topic, run_date, narratives, assignments) -> None:
        day = _encode("date", run_date)
        with self.con:
            self.con.execute("DELETE FROM narratives WHERE topic = ? AND run_date = ?", [topic, day])
            self.con.execute("DELETE FROM post_narrative WHERE topic = ? AND run_date = ?", [topic, day])
        self._insert("narratives", ({**n, "topic": topic, "run_date": run_date} for n in narratives))
        self._insert("post_narrative", ({**a, "topic": topic, "run_date": run_date} for a in assignments))

    def narrative_run(self, topic, before=None) -> dict | None:
        sql, params = "SELECT max(run_date) AS d FROM narratives WHERE topic = ?", [topic]
        if before is not None:
            sql += " AND run_date < ?"
            params.append(_encode("date", before))
        day = self.con.execute(sql, params).fetchone()["d"]
        if day is None:
            return None
        return {
            "run_date": date.fromisoformat(day),
            "narratives": self._rows("narratives", "SELECT narrative_id, name, summary, n_posts "
                                     "FROM narratives WHERE topic = ? AND run_date = ? "
                                     "ORDER BY narrative_id", [topic, day]),
            "assignments": self._rows("post_narrative", "SELECT uri, narrative_id FROM post_narrative "
                                      "WHERE topic = ? AND run_date = ?", [topic, day]),
        }

    def save_signals(self, rows: Iterable[dict]) -> None:
        now = now_utc()
        self._insert("signals", ({"window_start": now, "computed_at": now, **r} for r in rows))

    def enqueue_review(self, rows: Iterable[dict]) -> None:
        now = now_utc()
        self._insert("review_queue", ({"topic": "", "queued_at": now, **r} for r in rows))

    def pending_reviews(self, item_type=None, topic=None) -> list[dict]:
        sql, params = "SELECT * FROM review_queue WHERE 1 = 1", []
        if item_type is not None:
            sql += " AND item_type = ?"
            params.append(item_type)
        if topic is not None:
            sql += " AND topic = ?"
            params.append(topic)
        return self._rows("review_queue", sql + " ORDER BY queued_at, item_id", params)

    def resolve_review(self, item_type: str, item_id: str, topic: str = "") -> None:
        with self.con:
            self.con.execute("DELETE FROM review_queue WHERE item_type = ? AND item_id = ? AND topic = ?",
                             [item_type, item_id, topic])

    def save_review(self, row: dict) -> None:
        self._insert("reviews", [{"reviewed_at": now_utc(), **row}])

    # --- portability ------------------------------------------------------
    def export_table(self, table: str) -> Iterator[dict]:
        yield from self._rows(table, f"SELECT * FROM {TABLES[table].name}")

    def import_table(self, table: str, rows: Iterable[dict]) -> None:
        self._insert(table, rows)

    # --- analysis ---------------------------------------------------------
    def analytics(self):
        if self.path == ":memory:":
            return views.session_by_copy(self)      # another engine cannot open an in-memory database
        self.con.commit()
        return views.session_over_sqlite(self.path)
