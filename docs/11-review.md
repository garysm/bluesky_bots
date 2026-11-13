# 11 Review

The queue of things a person has to look at, and where their decisions go.

Each step explains one idea, sets a task, and tells you how to check your work. The example code is at the bottom under [Example solution](#example-solution), collapsed.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/review/` |
| Reads | the review queue; signal evidence; a queued post's text and current labels |
| Writes | `reviews` (decisions about accounts); `labels` (a person's label, at the highest tier) |
| Command | `python -m bluesky_bots.review queue`, `accounts`, `account`, `posts` and `post` |
| Must not know | who an account is. It shows an anonymous ID and evidence. |

Needs: `ANON_SALT` in `.env` and `anon_id` from [13](13-reports.md) step 1 (do that step first; it is short). Labels from [07](07-classify.md) or signals from [10](10-signals.md) to have something to review.

Read first:

- [14 Guardrails](14-guardrails.md): "human review" and "evidence over verdicts"

## What you are building

Two kinds of item reach the queue:

| Item | Put there by | A person decides |
| --- | --- | --- |
| a post | classification, when no model could settle a label ([07](07-classify.md), [08](08-escalating-labels.md)) | the label |
| an account | this service, from the `flagged` view ([10](10-signals.md)) | whether the behavior looks coordinated |

| Function | Does |
| --- | --- |
| `queue_flagged(store)` | puts every flagged account on the queue |
| `pending_accounts(store)` | queued accounts as a reviewer should see them |
| `decide_account(store, account, reviewer, decision, notes)` | records the decision |
| `pending_posts(store, topic)` | a topic's queued posts with their text and current labels |
| `decide_post(store, topic, uri, reviewer, values, target)` | records a person's label |

You are done when `pytest tests/test_review_reports_agent.py -k "anonymous or persons"` passes.

The two halves do different jobs. Reviewing accounts is the check on the behavioral signals: until it has happened, every chart calls the excluded group "unreviewed". Reviewing posts gives you labels you can trust, which is the only way to measure how good the models' labels are.

## Step 1: The storage methods

**Your task.** In `DuckDBStore` ([05](05-storage.md)), write the four queue methods:

- `enqueue_review(rows)`: add items. Each row has `item_type` (`'post'` or `'account'`), `item_id` (a URI or a DID), `reason`, and for posts a `topic`. An item already queued is left alone.
- `pending_reviews(item_type=None, topic=None)`: queued items, oldest first
- `resolve_review(item_type, item_id, topic="")`: take an item off the queue
- `save_review(row)`: record a decision about an account in `reviews`

**Hints.**

- The queue's key is `(item_type, item_id, topic)`, so the same post can wait in two topics, and queueing twice adds nothing.
- An account item has no topic. Store `''`, because a key column cannot be empty.
- Compare with the same methods in `sqlite_store.py`.

**Check.** `pytest tests/test_store_contract.py -m page11 -k duckdb`

## Step 2: Put flagged accounts on the queue

**Your task.** In `bluesky_bots/review/queue.py`, write `queue_flagged(store)`. It reads the `flagged` view through `store.analytics()`, queues each account, and returns how many are flagged.

**Hints.**

- The reason is the same for all of them: two or more different behavioral signals.
- Running it again must not duplicate anything. The store already guarantees that.

## Step 3: Show an account as evidence, not as a person

**Concept.** A behavioral call does not need to know who the person is, and knowing invites judging their politics. So the reviewer never sees a handle or a DID. They see a stable anonymous ID, from `anon_id` on [13](13-reports.md), and the evidence rows: which signals fired, with what was observed.

**Your task.** Write `pending_accounts(store)`. For each queued account it returns the anonymous ID, the reason, and a list of evidence, each with the signal's name, its value, what was observed (the stored JSON, decoded) and the window.

**Hints.**

- The DID is needed to look up the evidence. It must not be in what you return.
- Evidence rows were written by [10](10-signals.md) to hold observations only. This is where that pays off: they can be shown as they are.

**Check.** `pytest tests/test_review_reports_agent.py -k anonymous` asserts that the string `did:` appears nowhere in what the function returns.

## Step 4: Record a decision about an account

**Concept.** The reviewer answers with the anonymous ID they were shown. The function finds which queued account that is by computing `anon_id` for each, records the decision, and takes the item off the queue.

The decisions are `coordinated`, `not_coordinated` and `undecided`. The `flagged` view ([10](10-signals.md) step 6) leaves out any account with a `not_coordinated` decision, so a cleared account stops being excluded from charts.

**Your task.** Write `decide_account(store, account, reviewer, decision, notes="")`.

**Hints.**

- Refuse a decision that is not one of the three. A typo should not become a fourth category.
- An ID that matches nothing queued is an error to report, not to ignore.

## Step 5: Review a post

**Concept.** A queued post is one the models answered "cannot tell" about. The reviewer needs the text, the post it replies to, and what the models said.

Their answer is stored as a label like any other, with two differences: the model is recorded as `human:<reviewer>`, and the tier is `HUMAN_TIER`, which is higher than any model's. The `labels_final` view ([07](07-classify.md) step 4) keeps the highest tier, so from then on every chart and every tool uses the person's answer. The models' rows stay beside it, which is what lets you measure them.

**Your task.** Write `pending_posts(store, topic)` and `decide_post(store, topic, uri, reviewer, values, target="")`. `values` maps a dimension to the value chosen, for example `{"stance": "critical"}`.

**Hints.**

- A queued post may have been deleted since. `delete_record` took it off the queue, but check that the post is still there before showing it.
- Each item carries its `uri`, because a decision needs it. Do not print it: it contains the author's DID. The command numbers the posts instead.
- Check each value against the topic's scheme before storing it. The label class did that for the models; nothing does it for a person unless you do.

**Check.** `pytest tests/test_review_reports_agent.py -k persons`

## Step 6: Use it

```bash
python -m bluesky_bots.review queue
```

```bash
python -m bluesky_bots.review accounts
```

```bash
python -m bluesky_bots.review account acct_3f9a1c0b77de not_coordinated --reviewer gm --notes "live coverage of a debate"
```

```bash
python -m bluesky_bots.review posts --topic dem-leadership
```

```bash
python -m bluesky_bots.review post 1 --topic dem-leadership --reviewer gm --set stance=critical --target schumer
```

## Building a hand-checked sample

The queue only holds what the models were unsure of. To learn how often they are wrong when they are *sure*, you also need to label a random sample of settled posts yourself, without looking at the model's answer first. Queue a sample by hand:

```python
import random
from bluesky_bots.storage import open_store
from bluesky_bots.topics import get_topic

topic, store = get_topic("dem-leadership"), open_store()
posts = store.posts_in_topic(topic.name)
sample = random.sample(posts, min(100, len(posts)))
store.enqueue_review({"item_type": "post", "item_id": p["uri"], "topic": topic.name,
                      "reason": "hand-check sample"} for p in sample)
```

Then compare your labels with the models' rows for the same posts. Look at mistakes in both directions, and publish the rates with the model names and the scheme version ([14](14-guardrails.md)).

## Good to know

- **Until accounts are reviewed, say so.** Call the excluded group "accounts with two or more behavioral signals (unreviewed)" on every chart.
- **A cleared account stays cleared.** New signals do not put it back in `flagged`. To look again, record a new decision.
- **A person's label is the top tier**, and it is per reviewer. Two reviewers who disagree both have rows; `labels_final` keeps the more recent.
- **Review notes are free text.** Do not write a handle or a quote from the post in them. Notes are not covered by `export_public`'s checks unless you export them.
- **The anonymous ID changes if `ANON_SALT` changes.** Keep the salt ([13](13-reports.md)).

## Example solution

`tests/test_review_reports_agent.py` passes against this code (run on 2026-11-13), and the `queue` and `accounts` commands were run on made-up data.

<details>
<summary>Show example: step 1, the queue in storage (in DuckDBStore)</summary>

```python
class DuckDBStore:
    ...

    def enqueue_review(self, rows: Iterable[dict]) -> None:
        """Add items for a person to look at. An item already queued is left alone."""
        now = now_utc()
        self._insert("review_queue", ({"topic": "", "queued_at": now, **r} for r in rows))

    def pending_reviews(self, item_type=None, topic=None) -> list[dict]:
        """Queued items, oldest first."""
        sql, params = "SELECT * FROM review_queue WHERE 1 = 1", []
        if item_type is not None:
            sql += " AND item_type = ?"
            params.append(item_type)
        if topic is not None:
            sql += " AND topic = ?"
            params.append(topic)
        return self._rows("review_queue", sql + " ORDER BY queued_at, item_id", params)

    def resolve_review(self, item_type: str, item_id: str, topic: str = "") -> None:
        """Take an item off the queue."""
        self.con.execute("DELETE FROM review_queue WHERE item_type = ? AND item_id = ? AND topic = ?",
                         [item_type, item_id, topic])

    def save_review(self, row: dict) -> None:
        """Record a reviewer's decision about an account."""
        self._insert("reviews", [{"reviewed_at": now_utc(), **row}])
```

</details>

<details>
<summary>Show example: steps 2 to 4, reviewing accounts (bluesky_bots/review/queue.py)</summary>

```python
import json

from ..privacy import anon_id
from ..storage import HUMAN_TIER
from ..topics import Topic


DECISIONS = ("coordinated", "not_coordinated", "undecided")


def queue_flagged(store) -> int:
    """Put every account in the `flagged` view on the review queue. Returns how many are flagged."""
    dids = [row[0] for row in store.analytics().execute("SELECT did FROM flagged ORDER BY 1").fetchall()]
    store.enqueue_review({"item_type": "account", "item_id": did,
                          "reason": "two or more different behavioral signals"} for did in dids)
    return len(dids)


def pending_accounts(store) -> list[dict]:
    """Queued accounts as a reviewer should see them: an anonymous ID and the evidence rows."""
    con = store.analytics()
    out = []
    for item in store.pending_reviews("account"):
        rows = con.execute("SELECT signal, value, evidence, window_start FROM signals "
                           "WHERE did = ? ORDER BY signal, window_start", [item["item_id"]]).fetchall()
        out.append({"account": anon_id(item["item_id"]), "reason": item["reason"],
                    "evidence": [{"signal": s, "value": v, "observed": json.loads(e), "window_start": w}
                                 for s, v, e, w in rows]})
    return out


def decide_account(store, account: str, reviewer: str, decision: str, notes: str = "") -> None:
    """Record a reviewer's decision about a queued account, named by its anonymous ID."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    for item in store.pending_reviews("account"):
        if anon_id(item["item_id"]) == account:
            store.save_review({"did": item["item_id"], "reviewer": reviewer, "decision": decision,
                               "notes": notes})
            store.resolve_review("account", item["item_id"])
            return
    raise KeyError(f"no queued account is called {account}")
```

</details>

<details>
<summary>Show example: step 5, reviewing posts</summary>

```python
def pending_posts(store, topic: Topic) -> list[dict]:
    """Queued posts of a topic with their text and the label the models settled on.

    Each item carries its uri so a decision can be recorded; do not show it
    to the reviewer, because it contains the author's DID.
    """
    con = store.analytics()
    out = []
    for item in store.pending_reviews("post", topic=topic.name):
        text = con.execute("""
            SELECT p.text, parent.text FROM posts p LEFT JOIN posts parent ON parent.uri = p.reply_parent
            WHERE p.uri = ?""", [item["item_id"]]).fetchone()
        if text is None:
            continue
        labels = con.execute("""
            SELECT target, dimension, value FROM labels_final
            WHERE uri = ? AND topic = ? AND scheme_version = ? ORDER BY 1, 2""",
            [item["item_id"], topic.name, topic.labels.version]).fetchall()
        out.append({"uri": item["item_id"], "text": text[0], "parent_text": text[1],
                    "reason": item["reason"],
                    "labels": [{"target": t, "dimension": d, "value": v} for t, d, v in labels]})
    return out


def decide_post(store, topic: Topic, uri: str, reviewer: str, values: dict[str, str],
                target: str = "") -> None:
    """Record a person's label for a queued post and take it off the queue.

    values maps a dimension to the value the reviewer chose. The label is
    stored with model 'human:<reviewer>' at the highest tier, so labels_final
    prefers it to any model's answer.
    """
    for name, value in values.items():
        dim = topic.labels.dimensions.get(name)
        if dim is None or value not in dim.values:
            raise ValueError(f"'{value}' is not an allowed value of '{name}' in topic {topic.name}")
    store.save_labels({"uri": uri, "topic": topic.name, "scheme_version": topic.labels.version,
                       "model": f"human:{reviewer}", "target": target, "dimension": name, "value": value,
                       "confidence": None, "tier": HUMAN_TIER} for name, value in values.items())
    store.resolve_review("post", uri, topic.name)
```

</details>
