# 13 Reports

The core chart (posts per day with and without flagged accounts) for any topic, anonymous account IDs, and an export function that refuses to leak identities.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/reports/`, plus `bluesky_bots/privacy.py` |
| Reads | `posts`, `labels_final`, `accounts` and `flagged`, through a read-only store; a topic's markers |
| Writes | files in `out/`, and only through `export_public` |
| Command | `python -m bluesky_bots.reports --topic NAME --dimension NAME --value VALUE --start ... --end ...` |
| Must not know | any subject. What is charted comes from its arguments and the topic file. |

Needs: `duckdb`, `pandas`, `plotly`, and `ANON_SALT` set in `.env`. The `flagged` view from [10](10-signals.md) and labels from [07](07-classify.md).

Read first:

- [14 Guardrails](14-guardrails.md): "anonymization", "no harassment pathways" and "test the hypothesis" are what this page turns into code
- Bluesky's [developer guidelines](https://bsky.network/docs/developer-guidelines), before anything leaves this PC
- Python's [`hmac`](https://docs.python.org/3/library/hmac.html) module, for step 1
- [Line charts in Plotly](https://plotly.com/python/line-charts/), for step 4

## What you are building

| Piece | File | Does |
| --- | --- | --- |
| `anon_id(did)` | `privacy.py` | turns a DID into a stable label that cannot be turned back |
| `export_public(df, path, count_col)` | `reports/export.py` | the only way data leaves the project; refuses identifying columns and hides small counts |
| `label_counts_by_day(con, topic, ...)` | `reports/charts.py` | the numbers behind the chart |
| `label_chart(con, topic, ...)` | `reports/charts.py` | those numbers and a chart of them |

You are done when `pytest tests/test_review_reports_agent.py -k "anon_id or export or label_counts_by_day or chart"` passes, the chart shows three lines for one value of one dimension, and `export_public` raises an error when you hand it a frame with a `did` column.

## Step 1: Anonymous IDs

**Concept.** Reviewers and reports need to refer to an account ("the same account did this on three days") without knowing who it is. You need a label that is the same every time for the same DID, and that nobody can reverse.

A plain hash is not enough. DIDs are public, so anyone can hash every DID on the network and look yours up. Mixing in a secret that only you hold, the salt, defeats that. HMAC is the standard way to combine a secret with a value.

**Your task.** In `bluesky_bots/privacy.py`, write `anon_id(did, salt=None) -> str`, returning something like `acct_3f9a1c0b77de`. The secret is `salt`, or `ANON_SALT` from the environment.

**Hints.**

- `hmac.new(key, message, hashlib.sha256).hexdigest()`. Both arguments are bytes.
- Twelve hex characters is plenty to tell accounts apart and short enough to read.
- Create the salt once, as a long random string, and put it in `.env`. `python -c "import secrets; print(secrets.token_hex(32))"` makes one.
- With no salt anywhere, raise an error that says what is missing. An ID made with an empty secret would look fine and protect nobody.

**Check.** `pytest tests/test_review_reports_agent.py -k anon_id`. The same DID gives the same ID twice. Change the salt and the ID changes. Nothing in the ID resembles the DID.

## Step 2: One door out

**Concept.** A rule that says "never export identities" is only reliable when code enforces it. So every export goes through one function, and that function refuses.

Two ways a table can identify someone:

- **A column that names them.** `did` and `handle`, obviously. Also `uri` (it contains the DID) and `text` (paste a post into search and you have its author).
- **A small count.** "One account posted this on Tuesday" singles someone out even with no name attached. Rows whose count is below a minimum are dropped.

**Your task.** In `bluesky_bots/reports/export.py`, write `export_public(df, path, count_col, min_cell=10)`. It raises `ValueError` if the frame contains any column in `FORBIDDEN`, drops rows whose count is under `min_cell`, writes a CSV, and returns what it wrote.

**Hints.**

- `FORBIDDEN` is a set. Set intersection with `df.columns` finds offenders in one expression.
- Name the offending columns in the error message. The person who triggers it will want to know which.
- `df.to_csv(path, index=False)`

**Check.** `pytest tests/test_review_reports_agent.py -k export`

## Step 3: The query behind the chart

**Concept.** The question behind this project is whether a conversation looks different once accounts showing coordinated behavior are set aside. So the chart needs the same daily count twice, once for everyone and once without flagged accounts. If the two lines nearly coincide, that is the finding, and it is reported as readily as a gap.

A third line shows self-declared bots separately, since they are neither hidden nor accused.

What is counted is "posts with this value on this dimension": for the example topic, `stance` = `critical`, optionally about one entity. The function does not know those words. They are arguments.

**Your task.** In `bluesky_bots/reports/charts.py`, write `label_counts_by_day(con, topic, dimension, value, start, end, target=None)`. It returns a DataFrame with one row per day and the columns `day`, `all_accounts`, `excluding_flagged` and `self_declared_bots`.

**Hints.**

- `con` is the connection from `store.analytics()`.
- Join `posts` to `labels_final`, and filter on the topic's name and its current `labels.version`. Reading `labels_final` and not `labels` is what counts each post once across tiers.
- `count(DISTINCT p.uri) FILTER (WHERE ...)` gives each series from one pass ([DuckDB `FILTER`](https://duckdb.org/docs/stable/sql/query_syntax/filter)), and counts a post about two entities once.
- `(? IS NULL OR l.target = ?)` makes the entity optional.
- Cast `created_at` to a date for the day. Which day a late-evening post falls in depends on the session time zone, which `analytics()` sets to UTC.
- `start` and `end` are days, both included. "Before the day after `end`" is the safe way to include all of the last day.

**Check.** `pytest tests/test_review_reports_agent.py -k label_counts_by_day`. On any day, `excluding_flagged` is no larger than `all_accounts`.

## Step 4: The chart

**Your task.** Write `label_chart(con, topic, dimension, value, start, end, target=None)`, which returns both the DataFrame and a Plotly line chart with one line per series, a title that says what is counted, and a dotted vertical line for each of the topic's `markers`.

**Hints.**

- `px.line(df, x="day", y=[...three column names...])` draws one line per column.
- [`fig.add_vline`](https://plotly.com/python/horizontal-vertical-shapes/) adds a marker; `fig.add_annotation` labels it.
- Markers are dates with labels in the topic file, such as an election day. The chart function has no dates of its own.
- Return the frame as well as the figure. The numbers behind a chart are what you export.

**Check.** `pytest tests/test_review_reports_agent.py -k chart`: three lines, a title naming the topic, and one marker per entry in the topic file.

## Step 5: Use it

From a terminal:

```bash
python -m bluesky_bots.reports --topic dem-leadership --dimension stance --value critical --target schumer --start 2026-09-01 --end 2026-11-30
```

It writes an HTML chart and, through `export_public`, the daily numbers as CSV, both in `out/`.

In a notebook:

```python
import bluesky_bots
from bluesky_bots.storage import open_store
from bluesky_bots.topics import get_topic
from bluesky_bots.reports import label_chart

store = open_store(read_only=True)
df, fig = label_chart(store.analytics(), get_topic("dem-leadership"), "stance", "critical",
                      "2026-09-01", "2026-11-30", target="schumer")
fig.show()
store.close()
```

**Check.** The CSV exists and holds only days whose count is 10 or more.

## Step 6: Render a notebook as a report

**Concept.** A notebook becomes a repeatable report when its inputs are parameters. [papermill](https://papermill.readthedocs.io/en/latest/usage-parameterize.html) runs a notebook with values you pass on the command line, and [nbconvert](https://nbconvert.readthedocs.io/en/latest/usage.html) turns the result into HTML without the code.

**Your task.** Tag the first cell of a notebook `parameters` and give it `topic`, `dimension`, `value`, `start` and `end` variables. Then:

```bash
papermill reports/topic_report.ipynb out/dem-leadership-2026-11.ipynb -p topic dem-leadership -p dimension stance -p value critical -p start 2026-09-01 -p end 2026-11-30
```

```bash
jupyter nbconvert --to html --no-input out/dem-leadership-2026-11.ipynb
```

These two commands have not been run on this PC.

**Check.** The HTML file opens in a browser and shows the chart and text with no code cells.

## Good to know

- **`ANON_SALT`** is a long random string you create once. Add it to `.env`. If you lose it, old and new anonymous IDs no longer match; if it leaks, the IDs can be reversed.
- **`export_public` is the only door out.** It refuses frames containing `did`, `handle`, `display_name`, `uri`, `text` or `description`, and drops rows whose count is under 10. Post text is blocked because it can be searched to find the author.
- **Label the series honestly.** Until accounts are reviewed on [11](11-review.md), call the middle line "excluding accounts with two or more behavioral signals (unreviewed)".
- **If the lines nearly coincide, that is the finding.** Report it as readily as a gap.
- **Mark which days came from search backfill** and which from live capture; they are not equally complete. `posts.source` records it.
- **Close the store when the notebook is done.** With the DuckDB backend an open read-only store blocks the loader ([05](05-storage.md)).

## Example solution

`tests/test_review_reports_agent.py` passes against this code (run on 2026-11-13), and the command was run on a store with no labels, where it wrote an empty chart and CSV.

<details>
<summary>Show example: step 1, anonymous IDs (bluesky_bots/privacy.py)</summary>

```python
from __future__ import annotations

import hashlib
import hmac
import os

from . import config  # noqa: F401  (importing it loads .env, where ANON_SALT lives)


def anon_id(did: str, salt: str | None = None) -> str:
    """A stable label for an account, such as acct_3f9a1c0b77de, that cannot be turned back into the DID.

    The same DID always gives the same label. The secret comes from `salt`,
    or from ANON_SALT in .env.
    """
    salt = salt or os.environ.get("ANON_SALT")
    if not salt:
        raise RuntimeError("ANON_SALT is not set in .env; see docs/13-reports.md")
    return "acct_" + hmac.new(salt.encode(), did.encode(), hashlib.sha256).hexdigest()[:12]
```

</details>

<details>
<summary>Show example: step 2, one door out (bluesky_bots/reports/export.py)</summary>

```python
import pandas as pd


# Columns that name a person, or that can be searched to find one.
FORBIDDEN = {"did", "handle", "display_name", "uri", "text", "description"}


def export_public(df: pd.DataFrame, path: str, count_col: str, min_cell: int = 10) -> pd.DataFrame:
    """Write a frame to CSV, refusing identifying columns and hiding small counts.

    Raises ValueError if the frame has any column in FORBIDDEN. Rows whose
    `count_col` is under `min_cell` are dropped. Returns what was written.
    """
    bad = FORBIDDEN & set(df.columns)
    if bad:
        raise ValueError(f"refusing to export identifying columns: {sorted(bad)}")
    df = df[df[count_col] >= min_cell]
    df.to_csv(path, index=False)
    return df
```

</details>

<details>
<summary>Show example: steps 3 and 4, the query and the chart (bluesky_bots/reports/charts.py)</summary>

```python
import pandas as pd
import plotly.express as px

from ..topics import Topic


SERIES = ["all_accounts", "excluding_flagged", "self_declared_bots"]


def label_counts_by_day(con, topic: Topic, dimension: str, value: str, start: str, end: str,
                        target: str | None = None) -> pd.DataFrame:
    """Per day, how many of a topic's posts carry `value` on `dimension`, as three series.

    all_accounts, excluding_flagged (accounts in the `flagged` view left out)
    and self_declared_bots. start and end are dates as YYYY-MM-DD, both
    included. target limits the count to labels about one entity.
    """
    return con.execute("""
        SELECT CAST(p.created_at AS DATE) AS day,
               count(DISTINCT p.uri) AS all_accounts,
               count(DISTINCT p.uri) FILTER (WHERE p.did NOT IN (SELECT did FROM flagged))
                   AS excluding_flagged,
               count(DISTINCT p.uri) FILTER (WHERE p.did IN
                   (SELECT did FROM accounts WHERE self_declared_bot)) AS self_declared_bots
        FROM posts p JOIN labels_final l USING (uri)
        WHERE l.topic = ? AND l.scheme_version = ? AND l.dimension = ? AND l.value = ?
          AND (? IS NULL OR l.target = ?)
          AND p.created_at >= CAST(? AS DATE) AND p.created_at < CAST(? AS DATE) + 1
        GROUP BY 1 ORDER BY 1""",
        [topic.name, topic.labels.version, dimension, value, target, target, start, end]).df()


def label_chart(con, topic: Topic, dimension: str, value: str, start: str, end: str,
                target: str | None = None):
    """The numbers from label_counts_by_day and a line chart of them.

    Returns (DataFrame, figure). The topic's markers are drawn as dotted
    vertical lines.
    """
    df = label_counts_by_day(con, topic, dimension, value, start, end, target)
    about = f" about {target}" if target else ""
    fig = px.line(df, x="day", y=SERIES,
                  title=f"{topic.title or topic.name}: posts per day with {dimension} = {value}{about}",
                  labels={"value": "posts", "variable": ""})
    for marker in topic.markers:
        fig.add_vline(x=pd.Timestamp(marker.date), line_dash="dot")
        fig.add_annotation(x=pd.Timestamp(marker.date), y=1, yref="paper", text=marker.label,
                           showarrow=False, yanchor="bottom")
    return df, fig
```

</details>
