# 10 Reports

The core chart (posts per day with and without flagged accounts), anonymous account IDs, and an export function that refuses to leak identities.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed.

Needs: `duckdb`, `pandas`, `plotly`, and `ANON_SALT` set in `.env`. The `flagged` view from [09](09-signals.md) and labels from [06](06-gemma-labels.md).

Read first:

- [11 Guardrails](11-guardrails.md): "anonymization", "no harassment pathways" and "test the hypothesis" are what this page turns into code
- Bluesky's [developer guidelines](https://bsky.network/docs/developer-guidelines), before anything leaves this PC
- Python's [`hmac`](https://docs.python.org/3/library/hmac.html) module, for step 1
- [Line charts in Plotly](https://plotly.com/python/line-charts/), for step 4

## What you are building

| Piece | Does |
| --- | --- |
| `anon_id(did)` | turns a DID into a stable label that cannot be turned back |
| `export_public(df, path, count_col)` | the only way data leaves the project; refuses identifying columns and hides small counts |
| `mentions_chart(con, leader, start, end)` | the with/without chart and the numbers behind it |

You are done when the chart shows three lines for one leader, and `export_public` raises an error when you hand it a frame with a `did` column.

## Step 1: Anonymous IDs

**Concept.** Reviewers and reports need to refer to an account ("the same account did this on three days") without knowing who it is. You need a label that is the same every time for the same DID, and that nobody can reverse.

A plain hash is not enough. DIDs are public, so anyone can hash every DID on the network and look yours up. Mixing in a secret that only you hold, the salt, defeats that. HMAC is the standard way to combine a secret with a value.

**Your task.** Write `anon_id(did) -> str`, returning something like `acct_3f9a1c0b77de`. The secret comes from `ANON_SALT` in the environment.

**Hints.**

- `hmac.new(key, message, hashlib.sha256).hexdigest()`. Both arguments are bytes.
- Twelve hex characters is plenty to tell accounts apart and short enough to read.
- Create the salt once, as a long random string, and put it in `.env`. `python -c "import secrets; print(secrets.token_hex(32))"` makes one.

**Check.** The same DID gives the same ID twice. Change the salt and the ID changes. Nothing in the ID resembles the DID.

## Step 2: One door out

**Concept.** A rule that says "never export identities" is only reliable when code enforces it. So every export goes through one function, and that function refuses.

Two ways a table can identify someone:

- **A column that names them.** `did` and `handle`, obviously. Also `uri` (it contains the DID) and `text` (paste a post into search and you have its author).
- **A small count.** "One account posted this on Tuesday" singles someone out even with no name attached. Rows whose count is below a minimum are dropped.

**Your task.** Write `export_public(df, path, count_col, min_cell=10)`. It raises `ValueError` if the frame contains any forbidden column, drops rows whose count is under `min_cell`, writes a CSV, and returns what it wrote.

**Hints.**

- Keep the forbidden names in a set. Set intersection with `df.columns` finds offenders in one expression.
- Name the offending columns in the error message. The person who triggers it will want to know which.
- `df.to_csv(path, index=False)`

**Check.** A frame with a `did` column raises. A frame of daily counts writes a file, and no row in it has a count under 10.

## Step 3: The query behind the chart

**Concept.** The project's question is whether criticism of a leader looks different once accounts showing coordinated behavior are set aside. So the chart needs the same daily count twice, once for everyone and once without flagged accounts. If the two lines nearly coincide, that is the finding, and it is reported as readily as a gap.

A third line shows self-declared bots separately, since they are neither hidden nor accused.

**Your task.** Write `CHART_SQL`: per day, the number of critical posts mentioning a leader from all accounts, from accounts not in `flagged`, and from self-declared bots. It takes three parameters: the leader, the start and the end.

**Hints.**

- `count(*) FILTER (WHERE ...)` gives each series from one pass ([DuckDB `FILTER`](https://duckdb.org/docs/stable/sql/query_syntax/filter)).
- Join `posts` to `labels`; `list_contains(l.leaders, ?)` picks the leader.
- Cast `created_at` to a date for the day. Which day a late-evening post falls in depends on the session time zone ([04](04-storage.md)).

**Check.** On any day, `excluding_flagged` is no larger than `all_accounts`.

## Step 4: The chart

**Your task.** Write `mentions_chart(con, leader, start, end)`, which runs the query and returns both the DataFrame and a Plotly line chart with one line per series, a title naming the leader, and a dotted vertical line on election day, 2026-11-03.

**Hints.**

- `px.line(df, x="day", y=[...three column names...])` draws one line per column.
- [`fig.add_vline`](https://plotly.com/python/horizontal-vertical-shapes/) adds the marker.
- Return the frame as well as the figure. The numbers behind a chart are what you export.

**Check.** Three lines, a readable title, and the marker on the right day.

## Step 5: Use it in a notebook

**Your task.** In a notebook: load `.env`, open the database read-only, set the time zone to UTC, draw the chart for one leader, and export the daily numbers through `export_public`.

**Hints.**

- `load_dotenv()` has to run before the cell that reads `ANON_SALT`.
- Create the output folder first.

**Check.** The CSV exists and holds only days whose count is 10 or more.

## Step 6: Render a notebook as a report

**Concept.** A notebook becomes a repeatable report when its inputs are parameters. [papermill](https://papermill.readthedocs.io/en/latest/usage-parameterize.html) runs a notebook with values you pass on the command line, and [nbconvert](https://nbconvert.readthedocs.io/en/latest/usage.html) turns the result into HTML without the code.

**Your task.** Tag the first cell of a notebook `parameters` and give it `leader`, `start` and `end` variables. Then:

```bash
papermill reports/leadership_mentions.ipynb out/schumer-2026-11.ipynb -p leader schumer -p start 2026-09-01 -p end 2026-11-30
```

```bash
jupyter nbconvert --to html --no-input out/schumer-2026-11.ipynb
```

These two commands were not run during testing; everything else on this page was.

**Check.** The HTML file opens in a browser and shows the chart and text with no code cells.

## Good to know

- **`ANON_SALT`** is a long random string you create once. Add it to `.env`. If you lose it, old and new anonymous IDs no longer match; if it leaks, the IDs can be reversed.
- **`export_public` is the only door out.** It refuses frames containing `did`, `handle`, `display_name`, `uri`, `text` or `description`, and drops rows whose count is under 10. Post text is blocked because it can be searched to find the author.
- **Label the series honestly.** Until accounts are reviewed, call the middle line "excluding accounts with two or more behavioral signals (unreviewed)".
- **If the lines nearly coincide, that is the finding.** Report it as readily as a gap.
- **Mark which days came from search backfill** and which from live capture; they are not equally complete.
- The dotted line marks election day, 2026-11-03.

## Example solution

This is the code that was run on this PC. Read top to bottom, the first four blocks make one module.

<details>
<summary>Show example: step 1, anonymous IDs</summary>

```python
import hashlib, hmac, os
import pandas as pd
import plotly.express as px

SALT = os.environ["ANON_SALT"].encode()
FORBIDDEN = {"did", "handle", "display_name", "uri", "text", "description"}

def anon_id(did: str) -> str:
    return "acct_" + hmac.new(SALT, did.encode(), hashlib.sha256).hexdigest()[:12]
```

</details>

<details>
<summary>Show example: step 2, one door out</summary>

```python
def export_public(df: pd.DataFrame, path: str, count_col: str, min_cell: int = 10):
    """The only way data leaves the project. Refuses identifying columns, hides small cells."""
    bad = FORBIDDEN & set(df.columns)
    if bad:
        raise ValueError(f"refusing to export identifying columns: {sorted(bad)}")
    df = df[df[count_col] >= min_cell]
    df.to_csv(path, index=False)
    return df
```

</details>

<details>
<summary>Show example: step 3, the query</summary>

```python
CHART_SQL = """
SELECT CAST(p.created_at AS DATE) AS day,
       count(*) AS all_accounts,
       count(*) FILTER (WHERE p.did NOT IN (SELECT did FROM flagged)) AS excluding_flagged,
       count(*) FILTER (WHERE p.did IN (SELECT did FROM accounts WHERE self_declared_bot))
           AS self_declared_bots
FROM posts p JOIN labels l USING (uri)
WHERE l.stance = 'critical' AND list_contains(l.leaders, ?)
  AND p.created_at BETWEEN ? AND ?
GROUP BY 1 ORDER BY 1
"""
```

</details>

<details>
<summary>Show example: step 4, the chart</summary>

```python
def mentions_chart(con, leader: str, start: str, end: str):
    df = con.execute(CHART_SQL, [leader, start, end]).df()
    fig = px.line(df, x="day", y=["all_accounts", "excluding_flagged", "self_declared_bots"],
                  title=f"Critical posts mentioning {leader.title()}, per day",
                  labels={"value": "posts", "variable": ""})
    fig.add_vline(x=pd.Timestamp("2026-11-03"), line_dash="dot")   # election day
    return df, fig
```

</details>

<details>
<summary>Show example: step 5, using it in a notebook</summary>

```python
from dotenv import load_dotenv
load_dotenv()                                   # before the code above, so ANON_SALT is set

import duckdb
con = duckdb.connect("data/narrative.duckdb", read_only=True)
con.execute("SET TimeZone = 'UTC'")

df, fig = mentions_chart(con, "schumer", "2026-09-01", "2026-11-30")
fig.show()

from pathlib import Path
Path("out").mkdir(exist_ok=True)
export_public(df, "out/schumer_daily.csv", count_col="all_accounts")
```

</details>
