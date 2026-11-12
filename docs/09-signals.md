# 09 Coordination signals

Behavioral flags computed from timing, account age and repeated text. No model is involved and stance is never used.

Each step explains one signal, sets a task, and tells you how to check your work. The example code is at the bottom under [Example solution](#example-solution), collapsed.

Needs: `duckdb`, `datasketch`, and the tables from [04](04-storage.md) with `accounts` filled in.

Read first:

- [11 Guardrails](11-guardrails.md). "Behavior, not opinions" and "evidence over verdicts" are the two rules this page exists to implement.
- DuckDB's [date functions](https://duckdb.org/docs/stable/sql/functions/date) and [timestamp functions](https://duckdb.org/docs/stable/sql/functions/timestamptz), for `date_diff` and `time_bucket`
- [MinHash](https://ekzhu.com/datasketch/minhash.html) and [MinHash LSH](https://ekzhu.com/datasketch/lsh.html) in the datasketch docs, for step 5

## What you are building

Five signals, each a query or a function that returns accounts with something measurable about them, and one view that combines them:

| Signal | Asks |
| --- | --- |
| Account age | Was the account very new when it first posted here? |
| Burst | Did it post faster than a person plausibly types? |
| Synchronized reposting | Does a pair of accounts keep reposting the same posts within seconds of each other? |
| Behavior shift | Is it suddenly posting far more than its own normal? |
| Near-identical text | Did many accounts post almost the same words? |

No signal is proof of anything. Real people post in bursts and repost quickly during big news. An account enters the review queue only when two or more *different* signals fire, and then a person looks at the evidence.

You are done when the queries run on your data, each row they return can be explained by pointing at posts, and the `flagged` view lists only accounts with two different signals.

## Step 1: Account age

**Concept.** An account created days before it starts posting about your leaders is worth a second look. What matters is its age when it *first appeared in your data*, not its age today.

**Your task.** Write a query `AGE_SQL` that returns each account whose youngest age at posting, in days, was under 30, with that age.

**Hints.**

- Join `posts` to `accounts` on `did`. Both have a `created_at`; one is the post's and one is the account's.
- `date_diff('day', a, b)` counts days from `a` to `b`.
- You want the smallest age per account, and then only the small ones. A filter on an aggregate goes in `HAVING`.

**Check.** Pick one returned account and confirm by hand: its creation date and its earliest post are less than 30 days apart.

## Step 2: Burst

**Concept.** Fifteen posts in ten minutes is one every forty seconds, sustained. Some people do that during a live event; scripts do it all the time.

**Your task.** Write `BURST_SQL`, which returns each account and ten-minute window in which it made 15 or more posts, with the count.

**Hints.**

- `time_bucket(INTERVAL '10 minutes', created_at)` rounds a timestamp down to the start of its window.
- Group by account and window.

**Check.** News outlets on your watch list will probably appear. That is expected, and it is why the composite in step 6 leaves watch-list accounts out.

## Step 3: Synchronized reposting

**Concept.** Two accounts reposting the same post within a minute happens by chance. The same two accounts doing it five times is a pattern. This is the only signal about *pairs*, and it needs a table joined to itself.

**Your task.** Write `SYNC_SQL`, which returns each pair of accounts that reposted the same post within 60 seconds of each other at least five times, with the number of times.

**Hints.**

- Join `reposts` to itself on the reposted post's URI.
- Without a further condition every pair appears twice (A with B, B with A), and every account pairs with itself. One comparison between the two DIDs removes both problems.
- The time gap can be positive or negative. `abs` makes it one test.

**Check.** For one returned pair, list the posts they both reposted and the two times for each. The pattern should be visible to the eye.

## Step 4: Behavior shift

**Concept.** Compare an account with *itself*. Someone who posts fifty times a day every day is not unusual on a fifty-post day. Someone who posts twice a day and then forty times is.

The measure is a z-score: how many standard deviations the recent daily average sits above the account's own earlier average.

**Your task.** Write `SHIFT_SQL`. For each account with at least 20 active days in the 60-day period before last week, compare its average posts per day over the last 7 days with that baseline, and return the accounts whose z-score is 4 or more.

**Hints.**

- Build it in stages with `WITH`: first posts per account per day, then each account's baseline mean and standard deviation, then the comparison.
- `stddev_samp` is the sample standard deviation.
- An account that posts the same number every day has a standard deviation of zero. `nullif(sd, 0)` turns a division by zero into `NULL`, which then fails the filter.
- Keep the baseline period and the recent period from overlapping.

**Check.** This query has only been run on made-up data, so treat it as unproven on real accounts. To test yours, insert an account that posts one to three times a day for two months and then forty times a day for the last week, and see it returned. Then try an account that posts exactly twice a day before its sudden week. It is *not* returned, because its standard deviation is zero. Decide whether that blind spot matters to you.

## Step 5: Near-identical text across accounts

**Concept.** Copy-and-paste campaigns change a word or a hashtag between posts, so exact matching misses them. Comparing every post with every other post is far too slow. MinHash with LSH solves both: it reduces each text to a small sketch, and finds texts whose sketches agree, without comparing all pairs.

The method has three parts:

1. **Normalize** each text so that trivial differences disappear: case, links, mentions, runs of spaces.
2. **Shingle** it into overlapping five-character pieces, and feed those to a MinHash.
3. **Index** the sketches in an LSH, then ask the index, for each post, which others resemble it.

A group of similar posts only matters when it spans *many accounts*. One person repeating themselves is not coordination.

**Your task.** Write `normalize(text) -> str` and `near_duplicate_groups(rows, threshold=0.8, min_accounts=5, min_chars=40)`. `rows` is an iterable of `(uri, did, text)`. The result is a list of groups, each a set of post URIs, each spanning at least `min_accounts` different accounts.

**Hints.**

- Short texts match by accident ("lol", "this."). Skip anything under `min_chars` after normalizing.
- `MinHash(num_perm=128)`, then `m.update(piece.encode())` for each shingle. `MinHashLSH(threshold=..., num_perm=128)`, then `lsh.insert(key, m)` and `lsh.query(m)`.
- Each post's query returns its whole group, so you will meet every group once per member. Track which URIs you have already placed.
- Keep a dict from URI to DID so you can count the distinct accounts in a group.

**Check.** Make five rows with different DIDs and the same sentence of about 90 characters, each ending in a different link and mention, plus twenty unrelated rows. You should get exactly one group, containing the five. Then change one word in each of the five and run it again. In testing here the group disappeared at a threshold of 0.8: a single changed word in a short post is a bigger difference than it looks. That is what tuning the threshold means.

## Step 6: Combine the signals

**Concept.** This is where the page's caution is enforced in code. The `flagged` view lists an account only when:

- it has two or more *different* signal types,
- computed in the last 14 days,
- it is not a self-declared bot and not on the watch list,
- and no reviewer has already decided it is not coordinated.

**Your task.** Write `FLAGGED_VIEW`, a `CREATE OR REPLACE VIEW flagged AS ...` statement over the `signals`, `accounts` and `reviews` tables from [04](04-storage.md).

**Hints.**

- "Different signal types" is `count(DISTINCT signal)`.
- The exclusions are `NOT IN (SELECT ...)` conditions.
- Stance appears nowhere in this view, or in any query on this page. Keep it that way.

**Check.** Give one test account two rows of the same signal and another two rows of different signals. Only the second is in `flagged`. Add a `reviews` row with decision `not_coordinated` for it; it leaves the view.

## Step 7: Record what was observed

**Concept.** The `signals` table stores, for each account and signal, a number and the evidence as JSON. Store what was observed, in plain terms, so a reviewer sees the evidence and not a verdict. `{"age_days_at_first_post": 3}` is evidence. `"suspicious"` is a verdict.

**Your task.** Run your age query and insert one `signals` row per result. Then run the near-duplicate function over the last day of posts.

**Hints.**

- The columns of `signals`, in order: `did`, `signal`, `window_start`, `value`, `evidence`, `computed_at`.
- `json.dumps` turns a dict into the JSON text for `evidence`.
- For a near-duplicate group, think about what a reviewer needs to see: the normalized text and the number of accounts, not a list of names.

**Check.** `SELECT signal, count(*) FROM signals GROUP BY 1` shows your rows, and each `evidence` value reads as a fact.

## Good to know

- **Two signals to flag.** The `flagged` view lists accounts with two or more different signal types in the last 14 days. One signal alone flags nothing, because real people also post in bursts and repost quickly during big news.
- **Every threshold is a guess**: 30 days, 15 posts in 10 minutes, 60 seconds, five co-reposts, z of 4, 0.8 similarity, five accounts. Tune them against accounts you have reviewed by hand.
- **Tested on planted data only.** Eight synthetic accounts built to look coordinated were flagged and forty ordinary ones were not. The behavior-shift query ran but had nothing to find, so it is unproven.
- **Watch-list accounts are left out of `flagged`.** They are the named sources, and outlets post fast enough to trip the burst signal. Their signal rows are still written.
- **Self-declared bots are left out too** and should be shown as their own group. Set `accounts.self_declared_bot` from the profile text, then check matches by hand.
- **Reviewed accounts.** A row in `reviews` with decision `not_coordinated` removes the account from `flagged`.

Common false alarms:

- Share-button text: many people posting an article's headline are not coordinating. Drop posts whose text equals the link title.
- Slogans and quotations: the 40-character floor helps; reading the largest groups helps more.
- New accounts after a wave of sign-ups: age alone means little.

## Example solution

Read top to bottom, the first six blocks make one module. The two imports at the top are used in step 5.

<details>
<summary>Show example: step 1, account age</summary>

```python
import re
from datasketch import MinHash, MinHashLSH

# 1. Account age at time of posting
AGE_SQL = """
SELECT p.did, min(date_diff('day', a.created_at, p.created_at)) AS age_days_at_first_post
FROM posts p JOIN accounts a USING (did)
GROUP BY 1 HAVING age_days_at_first_post < 30
"""
```

</details>

<details>
<summary>Show example: step 2, burst</summary>

```python
# 2. Machine-pace posting: many posts in a short window
BURST_SQL = """
SELECT did, time_bucket(INTERVAL '10 minutes', created_at) AS win, count(*) AS n
FROM posts GROUP BY 1, 2 HAVING n >= 15
"""
```

</details>

<details>
<summary>Show example: step 3, synchronized reposting</summary>

```python
# 3. Synchronized reposting: the same pair reposting the same posts within 60 s, repeatedly
SYNC_SQL = """
SELECT a.did AS did_a, b.did AS did_b, count(*) AS n_together
FROM reposts a JOIN reposts b
  ON a.subject_uri = b.subject_uri AND a.did < b.did
 AND abs(date_diff('second', a.created_at, b.created_at)) <= 60
GROUP BY 1, 2 HAVING n_together >= 5
"""
```

</details>

<details>
<summary>Show example: step 4, behavior shift</summary>

```python
# 4. Behavior shift: last 7 days against the account's own prior 60 days
SHIFT_SQL = """
WITH daily AS (
  SELECT did, CAST(created_at AS DATE) AS day, count(*) AS n FROM posts GROUP BY 1, 2),
base AS (
  SELECT did, avg(n) AS mu, stddev_samp(n) AS sd FROM daily
  WHERE day BETWEEN current_date - 67 AND current_date - 8 GROUP BY 1 HAVING count(*) >= 20)
SELECT d.did, avg(d.n) AS recent, b.mu, (avg(d.n) - b.mu) / nullif(b.sd, 0) AS z
FROM daily d JOIN base b USING (did)
WHERE d.day >= current_date - 7 GROUP BY d.did, b.mu, b.sd HAVING z >= 4
"""
```

</details>

<details>
<summary>Show example: step 5, near-identical text</summary>

```python
# 5. Near-identical text across many accounts
def normalize(text: str) -> str:
    text = re.sub(r"https?://\S+|@[\w.\-]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()

def near_duplicate_groups(rows, threshold=0.8, min_accounts=5, min_chars=40):
    """rows: iterable of (uri, did, text). Returns groups spanning many accounts."""
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
```

</details>

<details>
<summary>Show example: step 6, the flagged view</summary>

```python
# Composite: an account enters the review queue with two or more different signal types.
FLAGGED_VIEW = """
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
<summary>Show example: step 7, recording a signal</summary>

```python
import json

con.execute(FLAGGED_VIEW)
for did, age in con.execute(AGE_SQL).fetchall():
    con.execute("INSERT INTO signals VALUES (?,?,now(),?,?,now())",
                [did, "account_age", age, json.dumps({"age_days_at_first_post": age})])
```

For near-duplicates:

```python
rows = con.execute("SELECT uri, did, text FROM posts WHERE created_at >= now() - INTERVAL 1 DAY").fetchall()
groups = near_duplicate_groups(rows)     # each group is a set of post URIs
```

</details>
