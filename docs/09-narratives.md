# 09 Narratives

Turn a topic's posts into vectors, group similar ones into narratives, name each group, and keep the same narrative ID from run to run.

Each step explains one idea, sets a task, and tells you how to check your work. The example code is at the bottom under [Example solution](#example-solution), collapsed.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/narratives/` |
| Reads | a topic's posts from storage; the topic's `narratives` settings |
| Writes | `embeddings`, `post_narrative`, `narratives` |
| Command | `python -m bluesky_bots.narratives --topic NAME` |
| Must not know | any subject. It clusters whichever topic it is given. |

Needs: `EMBED_MODEL` and `NAMING_MODEL` in `.env` as LiteLLM names to run it for real ([16](16-choosing-models.md)); `scikit-learn`. The tests need neither model.

Read first:

- [LiteLLM: embedding models](https://docs.litellm.ai/docs/embedding/supported_embedding), for the `litellm.embedding` call
- [HDBSCAN](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html) in scikit-learn, and the [clustering overview](https://scikit-learn.org/stable/modules/clustering.html) for what it does differently from k-means
- [LiteLLM: JSON mode](https://docs.litellm.ai/docs/completion/json_mode), for step 6

## What you are building

```
a topic's posts -> embed_posts -> cluster -> centroids -> match_to_previous -> assign_ids -> name_cluster -> save
```

You are done when `pytest tests/test_narratives.py` passes, and a few hundred posts on two or three known subjects come back as groups you would recognize, each with a neutral name, and running it again the next day gives the continuing groups the same ID.

These functions call LiteLLM directly rather than through ADK, so the model names carry a provider prefix (`gemini/...`, not `gemini-...`).

## Step 1: Embed

**Concept.** An embedding model turns a text into a list of numbers, a vector, placed so that texts with similar meaning land close together. "Close" is measured by the angle between vectors (cosine similarity). If you scale every vector to length 1, the cosine similarity of two vectors is simply their dot product, which keeps every later step short.

**Your task.** In `bluesky_bots/narratives/embed.py`, write `embed(texts, model=None, batch=64) -> np.ndarray`, which returns one unit-length row per text.

**Hints.**

- `litellm.embedding(model=..., input=[...])` takes a list of texts; the vectors are in `resp.data`, each under `"embedding"`.
- Send the texts in batches. Providers limit how much one request may carry.
- `np.linalg.norm(x, axis=1, keepdims=True)` gives each row's length in a shape you can divide by.
- Import `litellm` inside the function. It takes seconds to load, and most code that imports this module never calls it.

**Check.** For a handful of texts, `x.shape` is `(number of texts, model dimension)` and `np.linalg.norm(x, axis=1)` is all ones. Embed two posts that say the same thing in different words and one that is unrelated; `x @ x.T` should show the pair scoring higher with each other than with the third.

## Step 2: Never embed a post twice

**Concept.** Embedding is the slow, sometimes paid, step, and a post's vector never changes. So each vector is saved, keyed by the post's URI and the embedding model, and looked up before anything is embedded.

Vectors are kept in storage, in the `embeddings` table, and not in a file beside it. The reason is deletes: when an author deletes a post, `delete_record` removes its vector along with everything else. A vector in a separate file would be left behind.

**Your task.** Two parts:

- In `DuckDBStore` ([05](05-storage.md)), write `save_vectors(model, vectors)`, where `vectors` maps a URI to a NumPy array, and `load_vectors(model, uris=None)`, which returns the stored ones in the same form.
- In `embed.py`, write `embed_posts(store, posts, model=None, embed_fn=None)`. It returns one row per post, in order: stored vectors where there are any, new ones for the rest, and it saves the new ones.

**Hints.**

- DuckDB has a list type, so a vector is stored as a list of floats and comes back as one. The SQLite backend has to pack it into bytes; compare the two.
- A Python list passed as a parameter becomes a DuckDB list, and `unnest(?)` turns it into rows. `WHERE uri IN (SELECT unnest(?))` is how you ask for many URIs at once.
- `embed_fn` (texts in, vectors out) is a parameter so a test can supply vectors without a model. Left out, it is `embed` with the given model.

**Check.** `pytest tests/test_store_contract.py -m page09 -k "duckdb and vectors"` and `pytest tests/test_narratives.py -k embed_posts`

## Step 3: Cluster

**Concept.** You do not know in advance how many narratives there are, and most posts belong to none. HDBSCAN suits both facts: it finds dense groups without being told how many, and it labels everything else `-1`, meaning noise. Its main setting is the smallest group you are willing to call a narrative, which a topic file sets as `narratives.min_cluster_size`.

**Your task.** In `bluesky_bots/narratives/cluster.py`, write `cluster(x, min_size=25) -> np.ndarray`, which returns one integer label per row.

**Hints.**

- `from sklearn.cluster import HDBSCAN`; `fit_predict` returns the labels.
- A large `-1` group is normal. It is not a failure.

**Check.** `pytest tests/test_narratives.py -k cluster`. On real posts: on this PC a tiny test of three planted subjects found two and left the third as `-1`; lower `min_size` for small samples and see the third appear.

## Step 4: Centroids

**Concept.** A cluster's centroid is the average of its vectors: one vector that stands for the whole group. You need it twice, to find the posts most typical of a cluster (for naming) and to recognize the cluster again tomorrow.

**Your task.** Write `centroids(x, labels) -> dict[int, np.ndarray]`, mapping each cluster number to its centroid and leaving out `-1`, and `typical(x, labels, k, centroid, n=15)`, the row numbers of the `n` posts in cluster `k` closest to its centroid.

**Hints.**

- `x[labels == k]` selects one cluster's rows.
- The average of unit vectors is not itself of unit length. Scale it again, so the dot-product shortcut from step 1 still holds.
- "Closest" means highest dot product with the centroid. `np.argsort` on the negated scores sorts highest first.

**Check.** `pytest tests/test_narratives.py -k centroids`

## Step 5: Keep the same ID from run to run

**Concept.** Clustering numbers its groups arbitrarily. Today's cluster 3 may be yesterday's cluster 0, and a chart of "narrative 3 over time" would be nonsense. So after clustering, compare each of today's centroids with the previous run's. If the best match is similar enough, today's cluster takes over that narrative's ID. Otherwise it is a new narrative and gets a number never used before.

**Your task.** Write:

- `match_to_previous(today, previous, threshold=0.8)`: both arguments map a number to a centroid. The result maps each of today's cluster numbers to a previous narrative ID, or to `None` when it is new.
- `assign_ids(mapping, next_id)`: turns that mapping into a final ID for every cluster, handing out new numbers from `next_id` up.

**Hints.**

- Similarity is the dot product, since both are unit vectors.
- Handle the first run, when `previous` is empty.
- Two of today's clusters can match the same previous narrative, when one narrative splits. An ID must not name two groups in one run, so only the first keeps it and the other gets a new one.

**Check.** `pytest tests/test_narratives.py -k "match_to_previous or assign_ids"`

## Step 6: Name a cluster

**Concept.** A model can read a sample of posts and suggest a name. The name will sit on every chart, so it has to describe the subject without taking a side. "Critique of ending the shutdown without concessions" describes; "Schumer's betrayal" does not.

**Your task.** In `bluesky_bots/narratives/naming.py`, reword `NAMING_PROMPT` in your own words if you like, and write `name_cluster(sample_posts, model=None) -> dict`, which returns a `name` and a one-sentence `summary`.

**Hints.**

- Ask for JSON and say exactly which keys. `response_format={"type": "json_object"}` on `litellm.completion` makes the reply parseable.
- Put a word limit on the name.
- Send text only, never URIs or handles. With a cloud model the posts leave this PC ([16](16-choosing-models.md)).

**Check.** Name the same cluster three times. The names should be near-identical and none should read as praise or blame.

## Step 7: The storage methods for a run

**Your task.** In `DuckDBStore`, write:

- `save_narratives(topic, run_date, narratives, assignments)`: replace one run. `narratives` rows have `narrative_id`, `name`, `summary`, `n_posts`; `assignments` rows have `uri`, `narrative_id`.
- `narrative_run(topic, before=None)`: the latest run for a topic, or the latest earlier than a date, as `{"run_date", "narratives", "assignments"}`, or `None`.

**Hints.**

- "Replace" keeps a second run on the same day from leaving two sets of rows.
- `SELECT max(run_date) ...` finds the run; two more queries fetch its rows.

**Check.** `pytest tests/test_store_contract.py -m page09 -k duckdb`

## Step 8: Put it together

**Concept.** One run for a topic, in `bluesky_bots/narratives/run.py`:

1. Take the topic's posts from the last several days, leaving out very short ones.
2. `embed_posts`, `cluster` with the topic's `min_cluster_size`, `centroids`.
3. Get the previous run's centroids. They are not stored; work them out again from the stored vectors of the posts that run assigned to each narrative.
4. `match_to_previous`, then `assign_ids`.
5. A narrative that continues keeps its name. A new one is named from its 15 most typical posts.
6. Save the run.

**Your task.** Write `previous_centroids(store, topic, model, before)` and `run_topic(store, topic, today=None, days=7, ...)`.

**Hints.**

- Cluster a rolling window of several days. Clustering each day from scratch reshuffles the groups.
- A post deleted since the previous run has no vector any more. Skip it.
- `next_id` is one more than the highest ID the topic has ever used, which is a one-line query on `store.analytics()`.
- With fewer posts than `min_cluster_size` there is nothing to cluster. Return early.

**Check.** `pytest tests/test_narratives.py -k run_topic`. The test runs two days in a row on planted groups and checks that every narrative keeps its ID and its name, and that the naming function is not called again for a narrative that continues. Then:

```bash
python -m bluesky_bots.narratives --topic dem-leadership
```

Read each narrative's most typical posts next to its name. If you would not have grouped them yourself, look at `min_cluster_size` and at very short posts before blaming the model.

## Good to know

- **Speed.** With EmbeddingGemma on this PC, 60 short posts embedded in about 13 seconds. Vectors are stored, so that cost is paid once per post.
- **Keep one embedding model.** Vectors from different models cannot be compared. Changing `EMBED_MODEL` means re-embedding the rolling window, and `match_to_previous` cannot link old narratives to new ones across the switch. The model name is stored with every vector.
- **Vectors are the largest thing you store per post.** [17](17-choosing-storage.md) has the numbers and ways to shrink them.
- **Cloud embeddings send post text off this PC**, as any cloud model does ([16](16-choosing-models.md)). Send text only, not URIs.
- **A large unclustered group is normal.** Lower `min_cluster_size` for small samples.
- **What is clustered.** Posts by their own text. A repost belongs with the post it reposts, and a reply with its thread's root; assigning those through the link is a refinement left for later.
- **Very short posts** group by phrasing instead of subject. Posts under 40 characters are left out.
- **Approve names by hand.** Gemma's names were neutral in testing ("Critique of ending the shutdown without concessions"), but a loaded name colors every chart that uses it. A narrative keeps its name once given, so correcting one is a single change.
- **Share of conversation** for a run is posts in the narrative divided by all clustered posts. Show the unclustered group as its own slice.

## Example solution

`tests/test_narratives.py` passes against this code (run on 2026-11-13), with made-up vectors standing in for an embedding model and a function for the naming model. `embed` and `name_cluster` call LiteLLM and have not been run in this form; their earlier versions ran with EmbeddingGemma and Gemma 4 `e2b` through Ollama on 2026-11-11.

<details>
<summary>Show example: step 1, embedding (bluesky_bots/narratives/embed.py)</summary>

```python
from typing import Callable

import numpy as np

from .. import config


def embed(texts: list[str], model: str | None = None, batch: int = 64) -> np.ndarray:
    """One unit-length row per text, from the embedding model named by EMBED_MODEL.

    Sends text only. With a cloud model the text leaves this PC.
    """
    import litellm                      # imported here: it is slow to load and only this function needs it
    model = model or config.model("EMBED_MODEL")
    rows = []
    for i in range(0, len(texts), batch):
        resp = litellm.embedding(model=model, input=texts[i:i + batch])
        rows.extend(d["embedding"] for d in resp.data)
    x = np.asarray(rows, dtype=np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True)
```

</details>

<details>
<summary>Show example: step 2, the storage methods for vectors (in DuckDBStore)</summary>

```python
class DuckDBStore:
    ...

    def save_vectors(self, model: str, vectors: dict[str, np.ndarray]) -> None:
        """Store one vector per uri for an embedding model."""
        if not vectors:
            return
        self.con.execute("DELETE FROM embeddings WHERE model = ? AND uri IN (SELECT unnest(?))",
                         [model, list(vectors)])
        self._insert("embeddings", ({"uri": uri, "model": model, "vector": v}
                                    for uri, v in vectors.items()))

    def load_vectors(self, model: str, uris=None) -> dict[str, np.ndarray]:
        """The stored vectors for these uris (or all of them), keyed by uri."""
        sql, params = "SELECT uri, vector FROM embeddings WHERE model = ?", [model]
        if uris is not None:
            sql += " AND uri IN (SELECT unnest(?))"     # a Python list becomes a DuckDB list
            params.append(list(uris))
        return {r["uri"]: r["vector"] for r in self._rows("embeddings", sql, params)}
```

</details>

<details>
<summary>Show example: step 2, embedding each post once</summary>

```python
def embed_posts(store, posts: list[dict], model: str | None = None,
                embed_fn: Callable[[list[str]], np.ndarray] | None = None) -> np.ndarray:
    """One row per post, in order, taking stored vectors where there are any and embedding the rest.

    posts:    dicts with uri and text
    embed_fn: texts -> vectors; left out, `embed` with this model. A test passes its own.
    New vectors are saved through the store, keyed by uri and model.
    """
    model = model or config.model("EMBED_MODEL")
    have = store.load_vectors(model, [p["uri"] for p in posts])
    missing = [p for p in posts if p["uri"] not in have]
    if missing:
        texts = [p["text"] for p in missing]
        new = embed_fn(texts) if embed_fn else embed(texts, model)
        fresh = {p["uri"]: np.asarray(v, dtype=np.float32) for p, v in zip(missing, new)}
        store.save_vectors(model, fresh)
        have.update(fresh)
    if not posts:
        return np.zeros((0, 0), dtype=np.float32)
    return np.stack([have[p["uri"]] for p in posts])
```

</details>

<details>
<summary>Show example: steps 3 to 5, clusters, centroids and stable IDs (bluesky_bots/narratives/cluster.py)</summary>

```python
import numpy as np
from sklearn.cluster import HDBSCAN


def cluster(x: np.ndarray, min_size: int = 25) -> np.ndarray:
    """One integer label per row of x. -1 means the post belongs to no narrative."""
    return HDBSCAN(min_cluster_size=min_size, copy=True).fit_predict(x)


def centroids(x: np.ndarray, labels: np.ndarray) -> dict[int, np.ndarray]:
    """Each cluster number mapped to its centroid, scaled to unit length. Leaves out -1."""
    out = {}
    for k in sorted(set(labels.tolist()) - {-1}):
        c = x[labels == k].mean(axis=0)
        out[k] = c / np.linalg.norm(c)                           # unit length, so dot = cosine
    return out


def typical(x: np.ndarray, labels: np.ndarray, k: int, centroid: np.ndarray, n: int = 15) -> list[int]:
    """Row numbers of the n posts in cluster k closest to its centroid, closest first."""
    return [int(i) for i in np.argsort(-(x @ centroid)) if labels[i] == k][:n]


def match_to_previous(today: dict, previous: dict, threshold: float = 0.8) -> dict:
    """Map each of today's cluster numbers to a previous narrative id, or None for a new narrative.

    Both arguments map a number to a unit-length centroid.
    """
    mapping = {}
    for k, c in today.items():
        scores = {pid: float(c @ pc) for pid, pc in previous.items()}
        best = max(scores, key=scores.get, default=None)
        mapping[k] = best if best is not None and scores[best] >= threshold else None
    return mapping


def assign_ids(mapping: dict, next_id: int) -> dict[int, int]:
    """Give every cluster a narrative id: the previous id it matched, or a new one from next_id up.

    If two clusters matched the same previous narrative, the first keeps the
    id and the other gets a new one, so an id never names two groups in one run.
    """
    ids, used = {}, set()
    for k, previous in mapping.items():
        if previous is not None and previous not in used:
            ids[k] = previous
        else:
            ids[k] = next_id
            next_id += 1
        used.add(ids[k])
    return ids
```

</details>

<details>
<summary>Show example: step 6, naming a cluster (bluesky_bots/narratives/naming.py)</summary>

```python
import json

from .. import config


NAMING_PROMPT = """Below are posts from one cluster. Give a neutral descriptive name of at
most eight words and a one-sentence summary. Describe the topic, not whether it is right.
Reply as JSON: {"name": "...", "summary": "..."}"""


def name_cluster(sample_posts: list[str], model: str | None = None) -> dict:
    """A {"name", "summary"} dict for a sample of posts, from the model named by NAMING_MODEL.

    Sends text only, never uris or handles.
    """
    import litellm                      # imported here: it is slow to load and only this function needs it
    listing = "\n".join("- " + p for p in sample_posts)
    reply = litellm.completion(model=model or config.model("NAMING_MODEL"),
                               response_format={"type": "json_object"},
                               messages=[{"role": "user", "content": NAMING_PROMPT + "\n\n" + listing}])
    return json.loads(reply.choices[0].message.content)
```

</details>

<details>
<summary>Show example: step 7, the storage methods for a run (in DuckDBStore)</summary>

```python
class DuckDBStore:
    ...

    def save_narratives(self, topic, run_date, narratives, assignments) -> None:
        """Replace one clustering run for a topic and date."""
        day = to_date(run_date)
        self.con.execute("DELETE FROM narratives WHERE topic = ? AND run_date = ?", [topic, day])
        self.con.execute("DELETE FROM post_narrative WHERE topic = ? AND run_date = ?", [topic, day])
        self._insert("narratives", ({**n, "topic": topic, "run_date": day} for n in narratives))
        self._insert("post_narrative", ({**a, "topic": topic, "run_date": day} for a in assignments))

    def narrative_run(self, topic, before=None) -> dict | None:
        """The latest clustering run for a topic (earlier than `before`, if given), or None."""
        sql, params = "SELECT max(run_date) FROM narratives WHERE topic = ?", [topic]
        if before is not None:
            sql += " AND run_date < ?"
            params.append(to_date(before))
        day = self.con.execute(sql, params).fetchone()[0]
        if day is None:
            return None
        return {
            "run_date": day,
            "narratives": self._rows("narratives", "SELECT narrative_id, name, summary, n_posts "
                                     "FROM narratives WHERE topic = ? AND run_date = ? "
                                     "ORDER BY narrative_id", [topic, day]),
            "assignments": self._rows("post_narrative", "SELECT uri, narrative_id FROM post_narrative "
                                      "WHERE topic = ? AND run_date = ?", [topic, day]),
        }
```

</details>

<details>
<summary>Show example: step 8, one run for a topic (bluesky_bots/narratives/run.py)</summary>

```python
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable

import numpy as np

from .. import config
from ..topics import Topic
from .cluster import assign_ids, centroids, cluster, match_to_previous, typical
from .embed import embed_posts
from .naming import name_cluster


MIN_CHARS = 40      # shorter posts group by phrasing, not by topic


def previous_centroids(store, topic: Topic, model: str, before: date) -> tuple[dict, dict]:
    """The centroids and names of the latest run before `before`.

    Returns ({narrative_id: centroid}, {narrative_id: {"name", "summary"}}),
    both empty when there is no earlier run. The centroids are worked out
    again from the stored vectors of the posts in each narrative.
    """
    run = store.narrative_run(topic.name, before=before)
    if run is None:
        return {}, {}
    vectors = store.load_vectors(model, [a["uri"] for a in run["assignments"]])
    groups: dict[int, list] = {}
    for a in run["assignments"]:
        if a["uri"] in vectors:                 # a post deleted since then has no vector
            groups.setdefault(a["narrative_id"], []).append(vectors[a["uri"]])
    cents = {}
    for nid, rows in groups.items():
        c = np.mean(rows, axis=0)
        cents[nid] = c / np.linalg.norm(c)
    names = {n["narrative_id"]: {"name": n["name"], "summary": n["summary"]} for n in run["narratives"]}
    return cents, names


def run_topic(store, topic: Topic, today: date | None = None, days: int = 7, model: str | None = None,
              embed_fn: Callable | None = None, namer: Callable[[list[str]], dict] | None = None) -> dict:
    """Cluster the last `days` days of a topic's posts and save the run under `today`.

    A narrative that continues from the previous run keeps its id and its
    name. Returns {"posts", "narratives", "unclustered"}.
    """
    today = today or datetime.now(timezone.utc).date()
    model = model or config.model("EMBED_MODEL")
    namer = namer or name_cluster
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc)
    posts = [p for p in store.posts_in_topic(topic.name, since=end - timedelta(days=days), until=end)
             if len(p["text"] or "") >= MIN_CHARS]
    if len(posts) < topic.narratives.min_cluster_size:
        return {"posts": len(posts), "narratives": 0, "unclustered": len(posts)}

    x = embed_posts(store, posts, model, embed_fn)
    labels = cluster(x, topic.narratives.min_cluster_size)
    cents = centroids(x, labels)

    prev_cents, prev_names = previous_centroids(store, topic, model, before=today)
    highest = store.analytics().execute(
        "SELECT coalesce(max(narrative_id), -1) FROM narratives WHERE topic = ?", [topic.name]).fetchone()[0]
    ids = assign_ids(match_to_previous(cents, prev_cents), next_id=highest + 1)

    narratives = []
    for k, c in cents.items():
        nid = ids[k]
        named = prev_names.get(nid) or namer([posts[i]["text"] for i in typical(x, labels, k, c)])
        narratives.append({"narrative_id": nid, "name": named["name"], "summary": named["summary"],
                           "n_posts": int((labels == k).sum())})
    assignments = [{"uri": p["uri"], "narrative_id": ids[int(k)]}
                   for p, k in zip(posts, labels) if k != -1]
    store.save_narratives(topic.name, today, narratives, assignments)
    return {"posts": len(posts), "narratives": len(narratives), "unclustered": int((labels == -1).sum())}
```

</details>
