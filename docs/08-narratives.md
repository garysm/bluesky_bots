# 08 Narratives

Turn posts into vectors, group similar ones into narratives, name each group, and keep the same narrative ID from day to day.

Each step explains one idea, sets a task, and tells you how to check your work. The example code is at the bottom under [Example solution](#example-solution), collapsed.

Needs: `load_dotenv()` first, `EMBED_MODEL` and `NAMING_MODEL` in `.env` as LiteLLM names ([13](13-choosing-models.md)), `scikit-learn`.

Read first:

- [LiteLLM: embedding models](https://docs.litellm.ai/docs/embedding/supported_embedding), for the `litellm.embedding` call
- [HDBSCAN](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html) in scikit-learn, and the [clustering overview](https://scikit-learn.org/stable/modules/clustering.html) for what it does differently from k-means
- [LiteLLM: JSON mode](https://docs.litellm.ai/docs/completion/json_mode), for step 5

## What you are building

Five small functions that turn a list of post texts into named groups:

```
texts -> embed -> cluster -> centroids -> match_to_previous -> name_cluster
```

You are done when a few hundred posts on two or three known topics come back as groups you would recognize, each with a neutral name, and running it again the next day gives the continuing topics the same ID.

These functions call LiteLLM directly rather than through ADK, so the model names carry a provider prefix (`gemini/...`, not `gemini-...`). The code was first run with EmbeddingGemma and Gemma 4 `e2b` through Ollama; the LiteLLM version in the example has not been run yet.

## Step 1: Embed

**Concept.** An embedding model turns a text into a list of numbers, a vector, placed so that texts with similar meaning land close together. "Close" is measured by the angle between vectors (cosine similarity). If you scale every vector to length 1, the cosine similarity of two vectors is simply their dot product, which keeps every later step short.

**Your task.** Write `embed(texts, batch=64) -> np.ndarray`, which returns one unit-length row per text.

**Hints.**

- `litellm.embedding(model=..., input=[...])` takes a list of texts; the vectors are in `resp.data`, each under `"embedding"`.
- Send the texts in batches. Providers limit how much one request may carry.
- `np.linalg.norm(x, axis=1, keepdims=True)` gives each row's length in a shape you can divide by.

**Check.** For a handful of texts, `x.shape` is `(number of texts, model dimension)` and `np.linalg.norm(x, axis=1)` is all ones. Embed two posts that say the same thing in different words and one that is unrelated; `x @ x.T` should show the pair scoring higher with each other than with the third.

## Step 2: Cluster

**Concept.** You do not know in advance how many narratives there are, and most posts belong to none. HDBSCAN suits both facts: it finds dense groups without being told how many, and it labels everything else `-1`, meaning noise. Its main setting is the smallest group you are willing to call a narrative.

**Your task.** Write `cluster(x, min_size=25) -> np.ndarray`, which returns one integer label per row.

**Hints.**

- `from sklearn.cluster import HDBSCAN`; `fit_predict` returns the labels.
- A large `-1` group is normal. It is not a failure.

**Check.** Plant three topics in a small test set. On this PC a tiny test of three planted topics found two and left the third as `-1`; lower `min_size` for small samples and see the third appear.

## Step 3: Centroids

**Concept.** A cluster's centroid is the average of its vectors: one vector that stands for the whole group. You need it twice, to find the posts most typical of a cluster (for naming) and to recognize the cluster again tomorrow.

**Your task.** Write `centroids(x, labels) -> dict[int, np.ndarray]`, mapping each cluster number to its centroid. Leave out `-1`.

**Hints.**

- `x[labels == k]` selects one cluster's rows.
- The average of unit vectors is not itself of unit length. Scale it again, so the dot-product shortcut from step 1 still holds.

**Check.** Every centroid has length 1, and each centroid's highest dot product is with posts from its own cluster.

## Step 4: Keep the same ID from day to day

**Concept.** Clustering numbers its groups arbitrarily. Today's cluster 3 may be yesterday's cluster 0, and a chart of "narrative 3 over time" would be nonsense. So after clustering, compare each of today's centroids with yesterday's. If the best match is similar enough, today's cluster takes over yesterday's ID. Otherwise it is a new narrative.

**Your task.** Write `match_to_previous(today, previous, threshold=0.8) -> dict`. Both arguments are centroid dicts. The result maps each of today's cluster numbers to a previous narrative ID, or to `None` when it is new.

**Hints.**

- Similarity is the dot product, since both are unit vectors.
- Handle the first day, when `previous` is empty.
- Could two of today's clusters match the same previous narrative? Decide whether that is acceptable for you; the example allows it.

**Check.** Match a centroid dict against itself: every cluster maps to its own number. Match it against an empty dict: every cluster maps to `None`.

## Step 5: Name a cluster

**Concept.** A model can read a sample of posts and suggest a name. The name will sit on every chart, so it has to describe the topic without taking a side. "Critique of ending the shutdown without concessions" describes; "Schumer's betrayal" does not.

**Your task.** Write a prompt, and `name_cluster(sample_posts) -> dict`, which returns a `name` and a one-sentence `summary`.

**Hints.**

- Ask for JSON and say exactly which keys. `response_format={"type": "json_object"}` on `litellm.completion` makes the reply parseable.
- Put a word limit on the name.
- Send text only, never URIs or handles. With a cloud model the posts leave this PC ([13](13-choosing-models.md)).

**Check.** Name the same cluster three times. The names should be near-identical and none should read as praise or blame.

## Step 6: Put it together

**Your task.** For a list of post texts: embed, cluster, compute centroids, and for each cluster print its number and the name suggested from its 15 most typical posts.

**Hints.**

- "Most typical" means highest dot product with the centroid, among posts in that cluster. `np.argsort` on the negated scores sorts highest first.
- The next day, call `match_to_previous` with today's and yesterday's centroids to carry the IDs forward.

**Check.** Read each cluster's 15 posts next to its name. If you would not have grouped them yourself, look at `min_size` and at very short posts (see below) before blaming the model.

## Good to know

- **Speed.** With EmbeddingGemma on this PC, 60 short posts embedded in about 13 seconds. Save vectors to Parquet keyed by post URI so nothing is embedded twice.
- **Keep one embedding model.** Vectors from different models cannot be compared. Changing `EMBED_MODEL` means re-embedding the rolling window, and `match_to_previous` cannot link old narratives to new ones across the switch. Record the model name next to the saved vectors.
- **Cloud embeddings send post text off this PC**, as any cloud model does ([13](13-choosing-models.md)). Send text only, not URIs.
- **A large unclustered group is normal.** On a tiny test of three planted topics, two were found and the third was left as `-1`. Lower `min_size` for small samples.
- **What to cluster.** Original posts and quote posts by their own text. Give a repost the narrative of the post it reposts, and a reply the narrative of its root post.
- **Very short posts** group by phrasing instead of topic. Skip posts under about 40 characters and assign them through their thread.
- **Stable IDs.** Cluster a rolling window of several days and use `match_to_previous`; re-clustering each day from scratch reshuffles the numbers.
- **Approve names by hand.** Gemma's names were neutral in testing ("Critique of ending the shutdown without concessions"), but a loaded name colors every chart that uses it.
- **Share of conversation** for a day is posts in the narrative divided by all tracked posts that day. Show the unclustered group as its own slice.

## Example solution

Read top to bottom, the blocks make one module.

<details>
<summary>Show example: step 1, embedding</summary>

```python
import json, os
import litellm
import numpy as np
from sklearn.cluster import HDBSCAN

EMBED_MODEL = os.environ["EMBED_MODEL"]     # e.g. gemini/gemini-embedding-2 or ollama/embeddinggemma
NAMING_MODEL = os.environ["NAMING_MODEL"]   # e.g. gemini/gemini-flash-lite-latest

def embed(texts: list[str], batch: int = 64) -> np.ndarray:
    rows = []
    for i in range(0, len(texts), batch):
        resp = litellm.embedding(model=EMBED_MODEL, input=texts[i:i + batch])
        rows.extend(d["embedding"] for d in resp.data)
    x = np.asarray(rows, dtype=np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True)
```

</details>

<details>
<summary>Show example: step 2, clustering</summary>

```python
def cluster(x: np.ndarray, min_size: int = 25) -> np.ndarray:
    return HDBSCAN(min_cluster_size=min_size, copy=True).fit_predict(x)   # -1 = no narrative
```

</details>

<details>
<summary>Show example: step 3, centroids</summary>

```python
def centroids(x, labels) -> dict[int, np.ndarray]:
    out = {}
    for k in set(labels.tolist()) - {-1}:
        c = x[labels == k].mean(axis=0)
        out[k] = c / np.linalg.norm(c)                           # unit length, so dot = cosine
    return out
```

</details>

<details>
<summary>Show example: step 4, matching to the previous day</summary>

```python
def match_to_previous(today: dict, previous: dict, threshold: float = 0.8) -> dict:
    """Map today's cluster number to a stable narrative id, or None for a new narrative."""
    mapping = {}
    for k, c in today.items():
        scores = {pid: float(c @ pc) for pid, pc in previous.items()}
        best = max(scores, key=scores.get, default=None)
        mapping[k] = best if best is not None and scores[best] >= threshold else None
    return mapping
```

</details>

<details>
<summary>Show example: step 5, naming a cluster</summary>

```python
NAMING_PROMPT = """Below are posts from one cluster. Give a neutral descriptive name of at
most eight words and a one-sentence summary. Describe the topic, not whether it is right.
Reply as JSON: {"name": "...", "summary": "..."}"""

def name_cluster(sample_posts: list[str]) -> dict:
    listing = "\n".join("- " + p for p in sample_posts)
    reply = litellm.completion(model=NAMING_MODEL, response_format={"type": "json_object"},
                               messages=[{"role": "user", "content": NAMING_PROMPT + "\n\n" + listing}])
    return json.loads(reply.choices[0].message.content)
```

</details>

<details>
<summary>Show example: step 6, putting it together</summary>

```python
x = embed(texts)                         # texts: list of post strings
labels = cluster(x)                      # one number per post; -1 means no narrative
cents = centroids(x, labels)

for k, c in cents.items():
    nearest = [i for i in np.argsort(-(x @ c)) if labels[i] == k][:15]
    print(k, name_cluster([texts[i] for i in nearest]))

# next day: carry yesterday's ids forward
# mapping = match_to_previous(todays_centroids, yesterdays_centroids)
```

</details>
