# 10 Reports

The core chart (posts per day with and without flagged accounts), anonymous account IDs, and an export function that refuses to leak identities.

Needs: `duckdb`, `pandas`, `plotly`, and `ANON_SALT` set in `.env`.

## Chart, anonymous IDs and safe export

```python
import hashlib, hmac, os
import pandas as pd
import plotly.express as px

SALT = os.environ["ANON_SALT"].encode()
FORBIDDEN = {"did", "handle", "display_name", "uri", "text", "description"}

def anon_id(did: str) -> str:
    return "acct_" + hmac.new(SALT, did.encode(), hashlib.sha256).hexdigest()[:12]

def export_public(df: pd.DataFrame, path: str, count_col: str, min_cell: int = 10):
    """The only way data leaves the project. Refuses identifying columns, hides small cells."""
    bad = FORBIDDEN & set(df.columns)
    if bad:
        raise ValueError(f"refusing to export identifying columns: {sorted(bad)}")
    df = df[df[count_col] >= min_cell]
    df.to_csv(path, index=False)
    return df

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

def mentions_chart(con, leader: str, start: str, end: str):
    df = con.execute(CHART_SQL, [leader, start, end]).df()
    fig = px.line(df, x="day", y=["all_accounts", "excluding_flagged", "self_declared_bots"],
                  title=f"Critical posts mentioning {leader.title()}, per day",
                  labels={"value": "posts", "variable": ""})
    fig.add_vline(x=pd.Timestamp("2026-11-03"), line_dash="dot")   # election day
    return df, fig
```

## Using it in a notebook

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

## Rendering a notebook as a report

Tag the first cell of a notebook `parameters` and give it `leader`, `start` and `end` variables. Then:

```bash
papermill reports/leadership_mentions.ipynb out/schumer-2026-11.ipynb -p leader schumer -p start 2026-09-01 -p end 2026-11-30
```

```bash
jupyter nbconvert --to html --no-input out/schumer-2026-11.ipynb
```

These two commands were not run during testing; everything else on this page was.

## Good to know

- **`ANON_SALT`** is a long random string you create once. Add it to `.env`. If you lose it, old and new anonymous IDs no longer match; if it leaks, the IDs can be reversed.
- **`export_public` is the only door out.** It refuses frames containing `did`, `handle`, `display_name`, `uri`, `text` or `description`, and drops rows whose count is under 10. Post text is blocked because it can be searched to find the author.
- **Label the series honestly.** Until accounts are reviewed, call the middle line "excluding accounts with two or more behavioral signals (unreviewed)".
- **If the lines nearly coincide, that is the finding.** Report it as readily as a gap.
- **Mark which days came from search backfill** and which from live capture; they are not equally complete.
- The dotted line marks election day, 2026-11-03.
