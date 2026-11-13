# 10 Coordination signals

Behavioral flags computed from timing, account age and repeated text. No model is involved and no label is ever read.

Each step explains one signal, sets a task, and tells you how to check your work. The example code is at the bottom under [Example solution](#example-solution), collapsed.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/signals/` |
| Reads | `posts`, `reposts` and `accounts`, through `store.analytics()` |
| Writes | `signals`: one row per account and signal, with what was observed |
| Command | `python -m bluesky_bots.signals` |
| Must not know | what anyone said about anything. It never reads `labels`, and it does not know what a topic is about. |

Needs: `duckdb`, `datasketch`, and stored posts with `accounts` filled in (`python -m bluesky_bots.backfill accounts`, [04](04-backfill.md)).

Read first:

- [14 Guardrails](14-guardrails.md). "Behavior, not opinions" and "evidence over verdicts" are the two rules this page exists to implement.
- DuckDB's [date functions](https://duckdb.org/docs/stable/sql/functions/date) and [timestamp functions](https://duckdb.org/docs/stable/sql/functions/timestamptz), for `date_diff` and `time_bucket`
- [MinHash](https://ekzhu.com/datasketch/minhash.html) and [MinHash LSH](https://ekzhu.com/datasketch/lsh.html) in the datasketch docs, for step 5

## What you are building

Five signals. Each is a function that runs one query, or one pass over recent posts, and returns rows about accounts with something measurable about them:

| Signal | Function | Asks |
| --- | --- | --- |
| Account age | `account_age` | Was the account very new when it first posted in your data? |
| Burst | `bursts` | Did it post faster than a person plausibly types? |
| Synchronized reposting | `synchronized_reposts` | Does it keep reposting the same posts within seconds of another account? |
| Behavior shift | `behavior_shift` | Is it suddenly posting far more than its own normal? |
| Near-identical text | `near_duplicates` | Did many accounts post almost the same words? |

No signal is proof of anything. Real people post in bursts and repost quickly during big news. An account enters the review queue only when two or more *different* signals fire, and then a person looks at the evidence ([11](11-review.md)).

Each function returns rows ready for `store.save_signals`: `did`, `signal`, `value`, `evidence`, and where it applies `window_start`. **Evidence says what was observed, never a verdict.** `{"age_days_at_first_post": 3}` is evidence. `"suspicious"` is a verdict.

The queries are DuckDB SQL, run on the connection from `store.analytics()`. They work unchanged whichever backend holds the rows ([05](05-storage.md) step 9).

You are done when `pytest tests/test_signals.py` passes, the command runs on your data, and each row it saves can be explained by pointing at posts.

## Step 1: Account age

**Concept.** An account created days before it starts posting in your data is worth a second look. What matters is its age when it *first appeared in your data*, not its age today.

**Your task.** In `bluesky_bots/signals/queries.py`, write `account_age(con, max_days=30)`: each account whose youngest age at posting, in days, was under `max_days`.

**Hints.**

- Join `posts` to `accounts` on `did`. Both have a `created_at`; one is the post's and one is the account's.
- `date_diff('day', a, b)` counts days from `a` to `b`.
- You want the smallest age per account, and then only the small ones. A filter on an aggregate goes in `HAVING`.
- An account whose creation date has not been fetched has nothing to compare. Leave it out.
- `_dicts(cur)`, already in the file, turns a query result into a list of dicts.

**Check.** `pytest tests/test_signals.py -k account_age`. On your data, pick one returned account and confirm by hand that its creation date and its earliest post are less than 30 days apart.

## Step 2: Burst

**Concept.** Fifteen posts in ten minutes is one every forty seconds, sustained. Some people do that during a live event; scripts do it all the time.

**Your task.** Write `bursts(con, minutes=10, min_posts=15)`: each account and window in which it made `min_posts` or more posts.

**Hints.**

- `time_bucket(INTERVAL '10 minutes', created_at)` rounds a timestamp down to the start of its window.
- Group by account and window. The window's start goes in `window_start`.
- An interval cannot be a `?` parameter. Format the number into the SQL, through `int(...)` so it can only ever be a number.

**Check.** `pytest tests/test_signals.py -k bursts`. News outlets named in your topic files will probably appear. That is expected, and it is why accounts named in a topic file are left out of flagging.

## Step 3: Synchronized reposting

**Concept.** Two accounts reposting the same post within a minute happens by chance. The same two accounts doing it five times is a pattern. This is the only signal about *pairs*, and it needs a table joined to itself.

**Your task.** Write `synchronized_reposts(con, seconds=60, min_together=5)`. Find each pair of accounts that reposted the same post within `seconds` of each other at least `min_together` times, then return one row per *account* in such a pair.

**Hints.**

- Join `reposts` to itself on the reposted post's URI.
- Without a further condition every pair appears twice (A with B, B with A), and every account pairs with itself. One comparison between the two DIDs removes both problems.
- The time gap can be positive or negative. `abs` makes it one test.
- The evidence counts partners and the most reposts made together. It does not name the partner: a reviewer sees evidence, not identities.

**Check.** `pytest tests/test_signals.py -k synchronized`

## Step 4: Behavior shift

**Concept.** Compare an account with *itself*. Someone who posts fifty times a day every day is not unusual on a fifty-post day. Someone who posts twice a day and then forty times is.

The measure is a z-score: how many standard deviations the recent daily average sits above the account's own earlier average.

**Your task.** Write `behavior_shift(con, min_z=4, today=None)`. For each account with at least 20 active days in the 60-day period before last week, compare its average posts per day over the last 7 days with that baseline, and return the accounts whose z-score is `min_z` or more.

**Hints.**

- Build it in stages with `WITH`: first posts per account per day, then each account's baseline mean and standard deviation, then the comparison.
- `stddev_samp` is the sample standard deviation.
- An account that posts the same number every day has a standard deviation of zero. `nullif(sd, 0)` turns a division by zero into `NULL`, which then fails the filter.
- Keep the baseline period and the recent period from overlapping.
- `today` is a parameter so a test can fix the date. DuckDB accepts named parameters: `$today` in the SQL and `{"today": ...}` in Python.

**Check.** `pytest tests/test_signals.py -k behavior_shift`. The test plants an account that posts one to three times a day for two months and then forty times a day for a week. Then try an account that posts exactly twice a day before its sudden week. It is *not* returned, because its standard deviation is zero. Decide whether that blind spot matters to you.

## Step 5: Near-identical text across accounts

**Concept.** Copy-and-paste campaigns change a word or a hashtag between posts, so exact matching misses them. Comparing every post with every other post is far too slow. MinHash with LSH solves both: it reduces each text to a small sketch, and finds texts whose sketches agree, without comparing all pairs.

The method has three parts:

1. **Normalize** each text so that trivial differences disappear: case, links, mentions, runs of spaces.
2. **Shingle** it into overlapping five-character pieces, and feed those to a MinHash.
3. **Index** the sketches in an LSH, then ask the index, for each post, which others resemble it.

A group of similar posts only matters when it spans *many accounts*. One person repeating themselves is not coordination.

**Your task.** In `bluesky_bots/signals/neardup.py`, write:

- `normalize(text) -> str`
- `near_duplicate_groups(rows, threshold=0.8, min_accounts=5, min_chars=40)`: `rows` is an iterable of `(uri, did, text)`; the result is a list of groups, each a set of post URIs spanning at least `min_accounts` different accounts
- `near_duplicates(rows, **settings)`: signal rows, one per account in a group

**Hints.**

- Short texts match by accident ("lol", "this."). Skip anything under `min_chars` after normalizing.
- `MinHash(num_perm=128)`, then `m.update(piece.encode())` for each shingle. `MinHashLSH(threshold=..., num_perm=128)`, then `lsh.insert(key, m)` and `lsh.query(m)`.
- Each post's query returns its whole group, so you will meet every group once per member. Track which URIs you have already placed.
- Keep a dict from URI to DID so you can count the distinct accounts in a group.
- For the evidence, think about what a reviewer needs to see: the normalized text and the number of accounts and posts, not a list of names.

**Check.** `pytest tests/test_signals.py -k "normalize or near_duplicate"`. The test uses five accounts posting the same sentence of about 90 characters, each ending in a different link and mention, among twenty unrelated posts. Then change one word in each of the five and run it again. In testing here the group disappeared at a threshold of 0.8: a single changed word in a short post is a bigger difference than it looks. That is what tuning the threshold means.

## Step 6: Two different signals, then a person

**Concept.** This is where the page's caution is enforced in code. The `flagged` view lists an account only when:

- it has two or more *different* signal types,
- computed in the last 14 days,
- it is not a self-declared bot and not named in a topic file,
- and no reviewer has already decided it is not coordinated.

The view is in `bluesky_bots/storage/views.py`, already written, because charts and the agent's tools read it too.

**Your task.** Before you open the file, write the view yourself as `CREATE OR REPLACE VIEW flagged AS ...` over the `signals`, `accounts` and `reviews` tables. Then compare.

**Hints.**

- "Different signal types" is `count(DISTINCT signal)`.
- The exclusions are `NOT IN (SELECT ...)` conditions.
- No label appears in this view, or in any query on this page. Keep it that way.

**Check.** `pytest tests/test_store_contract.py -m page10`: one test account has two rows of the same signal, another has two different signals, a third is named in a topic file, and a fourth was cleared by a reviewer. Only the second is flagged.

## Step 7: Save what was observed

**Your task.** Two parts:

- In `DuckDBStore` ([05](05-storage.md)), write `save_signals(rows)`: append the rows, filling in `window_start` and `computed_at` with the current time where a row leaves them out. `evidence` arrives as a dict and is stored as JSON.
- In `bluesky_bots/signals/run.py`, write `compute_signals(store)`: run the four queries, run `near_duplicates` over the last day of posts, save everything, and return how many rows each signal produced.

**Check.** `pytest tests/test_signals.py -k compute` and `pytest tests/test_store_contract.py -m page10 -k duckdb`. Then:

```bash
python -m bluesky_bots.signals
```

It prints the row counts and how many accounts have two or more different signals. Open a few `evidence` values: each should read as a fact.

## Good to know

- **Two signals to flag.** One signal alone flags nothing, because real people also post in bursts and repost quickly during big news.
- **Every threshold is a guess**: 30 days, 15 posts in 10 minutes, 60 seconds, five co-reposts, z of 4, 0.8 similarity, five accounts. They are parameters with those defaults. Tune them against accounts you have reviewed by hand.
- **Tested on planted data only.** Each signal finds what `tests/test_signals.py` plants for it and nothing else. None has been checked against real accounts.
- **Signals are about accounts, not topics.** They are computed over everything stored. Because storage only holds what some topic captured, a signal is always relative to your topics: "fifteen posts in ten minutes" means fifteen *captured* posts.
- **Accounts named in a topic file are left out of `flagged`.** They are the named sources, and outlets post fast enough to trip the burst signal. Their signal rows are still written.
- **Self-declared bots are left out too** and should be shown as their own group. Set `accounts.self_declared_bot` from the profile text, then check matches by hand.
- **Reviewed accounts.** A decision of `not_coordinated` on [11](11-review.md) removes the account from `flagged`.
- **Each run appends.** Running the command twice writes the same observations twice. The view counts *different* signal types, so that changes nothing.

Common false alarms:

- Share-button text: many people posting an article's headline are not coordinating. Drop posts whose text equals the link title.
- Slogans and quotations: the 40-character floor helps; reading the largest groups helps more.
- New accounts after a wave of sign-ups: age alone means little.

## Example solution

`tests/test_signals.py` passes against this code (run on 2026-11-13), on planted data, through both storage backends.

<details>
<summary>Show example: steps 1 to 4, the four queries (bluesky_bots/signals/queries.py)</summary>

```python
from datetime import date


def _dicts(cur) -> list[dict]:
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def account_age(con, max_days: int = 30) -> list[dict]:
    """Accounts that were under `max_days` old when they first posted in the stored data."""
    rows = _dicts(con.execute("""
        SELECT p.did, min(date_diff('day', a.created_at, p.created_at)) AS age_days
        FROM posts p JOIN accounts a USING (did)
        WHERE a.created_at IS NOT NULL
        GROUP BY 1 HAVING age_days < ?""", [max_days]))
    return [{"did": r["did"], "signal": "account_age", "value": r["age_days"],
             "evidence": {"age_days_at_first_post": r["age_days"]}} for r in rows]


def bursts(con, minutes: int = 10, min_posts: int = 15) -> list[dict]:
    """Accounts that made `min_posts` or more posts inside one window of `minutes`."""
    rows = _dicts(con.execute(f"""
        SELECT did, time_bucket(INTERVAL '{int(minutes)} minutes', created_at) AS win, count(*) AS n
        FROM posts GROUP BY 1, 2 HAVING n >= ?""", [min_posts]))
    return [{"did": r["did"], "signal": "burst", "window_start": r["win"], "value": r["n"],
             "evidence": {"posts": r["n"], "window_minutes": minutes}} for r in rows]


def synchronized_reposts(con, seconds: int = 60, min_together: int = 5) -> list[dict]:
    """Accounts in a pair that reposted the same posts within `seconds` of each other, repeatedly.

    One row per account. The evidence counts partners; it does not name them.
    """
    rows = _dicts(con.execute("""
        WITH pairs AS (
          SELECT a.did AS did_a, b.did AS did_b, count(*) AS n_together
          FROM reposts a JOIN reposts b
            ON a.subject_uri = b.subject_uri AND a.did < b.did
           AND abs(date_diff('second', a.created_at, b.created_at)) <= ?
          GROUP BY 1, 2 HAVING n_together >= ?),
        both_ways AS (
          SELECT did_a AS did, n_together FROM pairs
          UNION ALL SELECT did_b, n_together FROM pairs)
        SELECT did, count(*) AS partners, max(n_together) AS most FROM both_ways GROUP BY 1""",
        [seconds, min_together]))
    return [{"did": r["did"], "signal": "synchronized_reposts", "value": r["most"],
             "evidence": {"partners": r["partners"], "most_reposts_together": r["most"],
                          "within_seconds": seconds}} for r in rows]


def behavior_shift(con, min_z: float = 4, today: date | None = None) -> list[dict]:
    """Accounts posting far more in the last 7 days than their own 60 days before that.

    The measure is a z-score against the account's own baseline; accounts
    with fewer than 20 active days in the baseline are left out.
    """
    today = today or date.today()
    rows = _dicts(con.execute("""
        WITH daily AS (
          SELECT did, CAST(created_at AS DATE) AS day, count(*) AS n FROM posts GROUP BY 1, 2),
        base AS (
          SELECT did, avg(n) AS mu, stddev_samp(n) AS sd FROM daily
          WHERE day BETWEEN CAST($today AS DATE) - 67 AND CAST($today AS DATE) - 8
          GROUP BY 1 HAVING count(*) >= 20)
        SELECT d.did, avg(d.n) AS recent, b.mu, (avg(d.n) - b.mu) / nullif(b.sd, 0) AS z
        FROM daily d JOIN base b USING (did)
        WHERE d.day >= CAST($today AS DATE) - 7
        GROUP BY d.did, b.mu, b.sd HAVING z >= $min_z""", {"today": today, "min_z": min_z}))
    return [{"did": r["did"], "signal": "behavior_shift", "value": r["z"],
             "evidence": {"posts_per_day_last_7": round(r["recent"], 1),
                          "posts_per_day_before": round(r["mu"], 1), "z": round(r["z"], 1)}}
            for r in rows]
```

</details>

<details>
<summary>Show example: step 5, near-identical text (bluesky_bots/signals/neardup.py)</summary>

```python
import re
from typing import Iterable

from datasketch import MinHash, MinHashLSH


def normalize(text: str) -> str:
    """Text with case, links, mentions and runs of spaces removed, so trivial differences disappear."""
    text = re.sub(r"https?://\S+|@[\w.\-]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def near_duplicate_groups(rows: Iterable[tuple], threshold: float = 0.8, min_accounts: int = 5,
                          min_chars: int = 40) -> list[set[str]]:
    """Groups of post uris with near-identical text, each spanning at least `min_accounts` accounts.

    rows: an iterable of (uri, did, text).
    """
    lsh, sketches, owner = MinHashLSH(threshold=threshold, num_perm=128), {}, {}
    for uri, did, text in rows:
        t = normalize(text)
        if len(t) < min_chars:
            continue
        m = MinHash(num_perm=128)
        for i in range(len(t) - 4):
            m.update(t[i:i + 5].encode())
        lsh.insert(uri, m)
        sketches[uri], owner[uri] = m, did
    seen, groups = set(), []
    for uri, m in sketches.items():
        if uri in seen:
            continue
        group = set(lsh.query(m))
        seen |= group
        if len({owner[u] for u in group}) >= min_accounts:
            groups.append(group)
    return groups


def near_duplicates(rows: Iterable[tuple], **settings) -> list[dict]:
    """Signal rows, one per account in a near-duplicate group.

    The evidence holds the shared text and the counts, not a list of accounts.
    """
    rows = list(rows)
    by_uri = {uri: (did, text) for uri, did, text in rows}
    out = []
    for group in near_duplicate_groups(rows, **settings):
        dids = {by_uri[u][0] for u in group}
        sample = normalize(by_uri[min(group)][1])[:200]
        for did in sorted(dids):
            out.append({"did": did, "signal": "near_duplicate_text", "value": len(dids),
                        "evidence": {"accounts": len(dids), "posts": len(group), "text": sample}})
    return out
```

</details>

<details>
<summary>Show example: step 6, the flagged view (bluesky_bots/storage/views.py)</summary>

```python
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
```

</details>

<details>
<summary>Show example: step 7, saving signals (in DuckDBStore)</summary>

```python
class DuckDBStore:
    ...

    def save_signals(self, rows: Iterable[dict]) -> None:
        """Append signal rows."""
        now = now_utc()
        self._insert("signals", ({"window_start": now, "computed_at": now, **r} for r in rows))
```

</details>

<details>
<summary>Show example: step 7, computing everything (bluesky_bots/signals/run.py)</summary>

```python
from .neardup import near_duplicates
from .queries import account_age, behavior_shift, bursts, synchronized_reposts


def compute_signals(store) -> dict[str, int]:
    """Run all five signals over the stored data and save the rows. Returns rows saved per signal."""
    con = store.analytics()
    rows = account_age(con) + bursts(con) + synchronized_reposts(con) + behavior_shift(con)
    recent = con.execute("SELECT uri, did, text FROM posts "
                         "WHERE created_at >= now() - INTERVAL 1 DAY").fetchall()
    rows += near_duplicates(recent)
    store.save_signals(rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["signal"]] = counts.get(row["signal"], 0) + 1
    return counts
```

</details>
