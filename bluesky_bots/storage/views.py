"""Views used by analysis, and the DuckDB sessions they are created in.

The views are DuckDB SQL. Every backend's `analytics()` ends up here, so a
chart or a signal query reads the same names whichever backend holds the rows.
"""
from __future__ import annotations

import duckdb

from .base import SCHEMA, create_tables_sql

# One final label per post, topic, scheme version, target and dimension:
# the row from the highest tier. A person's label has the highest tier of all.
LABELS_FINAL = """
CREATE OR REPLACE VIEW labels_final AS
SELECT * FROM labels
QUALIFY row_number() OVER (
    PARTITION BY uri, topic, scheme_version, target, dimension
    ORDER BY tier DESC, labeled_at DESC) = 1
"""

# Accounts in the review queue: two or more different signal types in the last
# 14 days, not a self-declared bot, not named in a topic file, and not already
# cleared by a reviewer. Label values appear nowhere in this view.
FLAGGED = """
CREATE OR REPLACE VIEW flagged AS
SELECT did FROM signals
WHERE computed_at >= now() - INTERVAL 14 DAY
  AND did NOT IN (SELECT did FROM accounts WHERE self_declared_bot OR is_watchlist)
  AND did NOT IN (SELECT did FROM reviews WHERE decision = 'not_coordinated')
GROUP BY did HAVING count(DISTINCT signal) >= 2
"""

VIEWS = (LABELS_FINAL, FLAGGED)


def create_views(con) -> None:
    for statement in VIEWS:
        con.execute(statement)


# How a SQLite column is read as its real type through DuckDB.
_SQLITE_CASTS = {"timestamp": "TIMESTAMPTZ", "date": "DATE", "bool": "BOOLEAN", "json": "JSON"}


def session_over_sqlite(path: str):
    """A DuckDB session that reads a SQLite file in place.

    Needs DuckDB's sqlite extension, which is downloaded once on first use.
    """
    con = duckdb.connect(":memory:")
    con.execute("SET TimeZone = 'UTC'")
    con.execute("INSTALL sqlite")
    con.execute("LOAD sqlite")
    con.execute("ATTACH '" + path.replace("'", "''") + "' AS store (TYPE sqlite, READ_ONLY)")
    for table in SCHEMA:
        cols = [f"CAST({name} AS {_SQLITE_CASTS[kind]}) AS {name}" if kind in _SQLITE_CASTS else name
                for name, kind in table.columns.items()]
        con.execute(f"CREATE VIEW {table.name} AS SELECT {', '.join(cols)} FROM store.{table.name}")
    create_views(con)
    return con


def session_by_copy(store):
    """A DuckDB session holding a copy of every table, read through `export_table`.

    Works for any backend and needs no extension. The copy is taken once, so
    it suits tests and small stores, not large ones.
    """
    con = duckdb.connect(":memory:")
    con.execute("SET TimeZone = 'UTC'")
    con.execute(create_tables_sql("duckdb"))
    for table in SCHEMA:
        names = list(table.columns)
        marks = ", ".join("?" for _ in names)
        for row in store.export_table(table.name):
            values = [row[n].tolist() if table.columns[n] == "vector" and row[n] is not None else row[n]
                      for n in names]
            con.execute(f"INSERT INTO {table.name} VALUES ({marks})", values)
    create_views(con)
    return con
