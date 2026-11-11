# 09 Coordination signals

Behavioral flags computed from timing, account age and repeated text. No model is involved and stance is never used.

Needs: `duckdb`, `datasketch`, and the tables from [04](04-storage.md) with `accounts` filled in.

## The signals

```python
import re
from datasketch import MinHash, MinHashLSH

# 1. Account age at time of posting
AGE_SQL = """
SELECT p.did, min(date_diff('day', a.created_at, p.created_at)) AS age_days_at_first_post
FROM posts p JOIN accounts a USING (did)
GROUP BY 1 HAVING age_days_at_first_post < 30
"""

# 2. Machine-pace posting: many posts in a short window
BURST_SQL = """
SELECT did, time_bucket(INTERVAL '10 minutes', created_at) AS win, count(*) AS n
FROM posts GROUP BY 1, 2 HAVING n >= 15
"""

# 3. Synchronized reposting: the same pair reposting the same posts within 60 s, repeatedly
SYNC_SQL = """
SELECT a.did AS did_a, b.did AS did_b, count(*) AS n_together
FROM reposts a JOIN reposts b
  ON a.subject_uri = b.subject_uri AND a.did < b.did
 AND abs(date_diff('second', a.created_at, b.created_at)) <= 60
GROUP BY 1, 2 HAVING n_together >= 5
"""

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

## Recording a signal

Store what was observed, in plain terms, so a reviewer sees the evidence and not a verdict.

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
