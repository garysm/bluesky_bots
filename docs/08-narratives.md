# 08 Narratives

Turn posts into vectors, group similar ones into narratives, name each group, and keep the same narrative ID from day to day.

Needs: Ollama running with `embeddinggemma` and `gemma4:e2b`, `load_dotenv()` first, `scikit-learn`.

## Embed, cluster, match, name

```python
import numpy as np
import ollama
from sklearn.cluster import HDBSCAN

def embed(texts: list[str], batch: int = 64) -> np.ndarray:
    rows = []
    for i in range(0, len(texts), batch):
        rows.extend(ollama.embed(model="embeddinggemma", input=texts[i:i + batch])["embeddings"])
    x = np.asarray(rows, dtype=np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True)

def cluster(x: np.ndarray, min_size: int = 25) -> np.ndarray:
    return HDBSCAN(min_cluster_size=min_size, copy=True).fit_predict(x)   # -1 = no narrative

def centroids(x, labels) -> dict[int, np.ndarray]:
    out = {}
    for k in set(labels.tolist()) - {-1}:
        c = x[labels == k].mean(axis=0)
        out[k] = c / np.linalg.norm(c)                           # unit length, so dot = cosine
    return out

def match_to_previous(today: dict, previous: dict, threshold: float = 0.8) -> dict:
    """Map today's cluster number to a stable narrative id, or None for a new narrative."""
    mapping = {}
    for k, c in today.items():
        scores = {pid: float(c @ pc) for pid, pc in previous.items()}
        best = max(scores, key=scores.get, default=None)
        mapping[k] = best if best is not None and scores[best] >= threshold else None
    return mapping

NAMING_PROMPT = """Below are posts from one cluster. Give a neutral descriptive name of at
most eight words and a one-sentence summary. Describe the topic, not whether it is right.
Reply as JSON: {"name": "...", "summary": "..."}"""

def name_cluster(sample_posts: list[str]) -> dict:
    import json
    listing = "\n".join("- " + p for p in sample_posts)
    reply = ollama.chat(model="gemma4:e2b", format="json",
                        messages=[{"role": "user", "content": NAMING_PROMPT + "\n\n" + listing}])
    return json.loads(reply["message"]["content"])
```

## Putting it together

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

## Good to know

- **Speed.** 60 short posts embedded in about 13 seconds. Save vectors to Parquet keyed by post URI so nothing is embedded twice.
- **A large unclustered group is normal.** On a tiny test of three planted topics, two were found and the third was left as `-1`. Lower `min_size` for small samples.
- **What to cluster.** Original posts and quote posts by their own text. Give a repost the narrative of the post it reposts, and a reply the narrative of its root post.
- **Very short posts** group by phrasing instead of topic. Skip posts under about 40 characters and assign them through their thread.
- **Stable IDs.** Cluster a rolling window of several days and use `match_to_previous`; re-clustering each day from scratch reshuffles the numbers.
- **Approve names by hand.** Gemma's names were neutral in testing ("Critique of ending the shutdown without concessions"), but a loaded name colors every chart that uses it.
- **Share of conversation** for a day is posts in the narrative divided by all tracked posts that day. Show the unclustered group as its own slice.
