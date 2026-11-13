# 08 Escalating labels

Build a labeling workflow that settles easy posts cheaply and sends only the hard ones to a stronger model:

1. **Tier 0**, a small classifier on embeddings, labels the posts it is sure about.
2. **Tier 1**, a fast LLM (`LABEL_MODEL_FAST`), labels the rest.
3. **Tier 2**, a strong LLM (`LABEL_MODEL_STRONG`), gets the posts tier 1 could not settle.
4. Posts tier 2 still cannot settle go to human review ([11](11-review.md)).

Each step explains one idea, sets a task, and tells you how to check your work. The example code is at the bottom under [Example solution](#example-solution), collapsed.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/classify/` (`tiers.py` and `train.py` on this page) |
| Reads | a topic's label scheme and unlabeled posts; trained classifiers in `data/models/<topic>/` |
| Writes | `labels`, one row per tier that looked at a post; the review queue |
| Command | `python -m bluesky_bots.classify label --topic NAME --tiered` and `... train --topic NAME --dimension NAME` |
| Must not know | any label value or subject |

Needs: `LABEL_MODEL_FAST`, `LABEL_MODEL_STRONG` and `EMBED_MODEL` in `.env` to run it for real ([16](16-choosing-models.md)); `scikit-learn`. Do [07](07-classify.md) first; this page changes that workflow and does not explain its parts again. Tier 0 uses `embed_posts` from [09](09-narratives.md); you can build the workflow before that page and add tier 0 after.

Read first:

- [Logistic regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html) in scikit-learn, and `predict_proba` in particular
- [Probability calibration](https://scikit-learn.org/stable/modules/calibration.html), for why a classifier's probability can be checked and an LLM's stated confidence cannot
- [Workflows](https://google.github.io/adk-docs/workflows/) in the ADK docs

## What you are building

```
START -> load_batch -> score_classifier -> label_fast -> check_fast -> label_strong -> check_strong -> persist
                    -> skip             -> persist                  -> persist                      -> queue_review
```

Every arrow that leaves the top line early is a post that was settled without the more expensive step. You are done when `pytest tests/test_classify.py -k "tier or train"` passes: a batch runs end to end with no classifier (every post goes to tier 1), and again with one (some posts stop at tier 0).

## What decides escalation

An LLM's own confidence cannot be used: in [07](07-classify.md) Gemma reported 1.0 on every post, including the wrong one. The signals here are ones you can measure:

| Step | Moves a post up when |
| --- | --- |
| Tier 0 to tier 1 | the classifier's top probability is below the threshold, on any dimension. The probability is real and can be checked against hand-checked posts. |
| Tier 1 to tier 2 | the fast model gives a dimension's "cannot tell" value, or it disagrees with tier 0's best guess. |
| Tier 2 to review | the strong model gives a "cannot tell" value. |

Until a classifier is trained, tier 0 passes every post through and tier 1 escalates on "cannot tell" alone.

## Step 1: Where a classifier lives

**Concept.** A tier 0 classifier answers one dimension of one topic under one scheme version. It was trained on vectors from one embedding model and means nothing with another. So its file name carries the topic, the dimension and the version, and the name recorded in `labels.model` for tier 0 carries the embedding model.

**Your task.** In `bluesky_bots/classify/tiers.py`, write:

- `classifier_path(topic, dimension)`: `data/models/<topic>/<dimension>-<version>.joblib`
- `load_classifiers(topic)`: a dict of dimension to classifier, or `None` unless *every* dimension of the topic has a file

**Hints.**

- `config.MODELS_DIR` is `data/models`.
- `joblib.load(path)` reads what `joblib.dump` wrote.
- Why all or nothing? A post is settled at tier 0 only if every dimension is settled. With one classifier missing, no post could be.

## Step 2: The builder, two labelers and the shared state

**Concept.** As on [07](07-classify.md), the workflow is built by a function so its nodes can use the topic and the store: `build_tiered_workflow(topic, store, ...)`.

The fast and the strong model must be given the same instruction. Otherwise a disagreement between them could be a difference in what they were asked, and their labels could not be compared.

Three different nodes lead to `persist`, each with different output, so results are not passed along the chain. They are collected in state:

| State key | Holds |
| --- | --- |
| `posts` | the batch, as dicts. A post's `i` is its position in this list. |
| `labels` | one entry per tier that looked at a post: the label, the model name, the tier, and tier 0's probability |
| `guess` | tier 0's answer per post, for the disagreement test |
| `unsure` | positions of posts that no tier could settle |

**Your task.** Start `build_tiered_workflow`. Build the label class and the two labeler nodes from one instruction, and write `load_batch`, which asks for posts with no label from *any* model under the current version, fills `posts`, empties `labels` and `guess`, and routes to `score` or `skip`.

**Hints.**

- Wrap each agent once, with different node names (`label_fast`, `label_strong`), and keep the results in variables.
- A `labelers` parameter, a dict with `"fast"` and `"strong"`, lets a test stand in for both agents.
- A small helper, `record(ctx, label, model, tier, confidence=None)`, that appends to `ctx.state["labels"]` saves repeating yourself three times. Assign a new list to the key instead of appending in place, so the change is seen as a state change.

## Step 3: Tier 0, the classifier

**Concept.** A logistic regression on embeddings costs milliseconds per post and gives a probability for each value. When its top probability is high, accept its answer. When it is not, pass the post up.

This node has to work on day one, before any classifier exists.

**Your task.** Write the `score_classifier` node.

- With no classifiers, route to `fast` and return every item.
- Otherwise embed the post texts and get probabilities for each dimension. For every post, build a label (the entities from `entities_in` on [02](02-topics.md), and each dimension's most likely value), record it as tier 0 with the *lowest* of its top probabilities, and remember the answer in `guess`. Collect the posts whose lowest top probability is under the threshold.
- Route to `fast` if any are unsure, and straight to `persist` if none are. Return the unsure ones.

**Hints.**

- `clf.predict_proba(x)` gives one row of probabilities per post; `clf.classes_` gives the value each column stands for.
- Record a tier 0 row for *every* post, including the unsure ones. You will want to know later how often tier 0's guess agreed with the models above it.
- Keys in state are safest as strings: store the guess under `str(i)`.
- An `embed_fn` parameter (texts in, vectors out) lets a test supply vectors without an embedding model. Left out, use `embed_posts` from the narratives service, which also saves each vector so nothing is embedded twice.

## Step 4: Check tier 1

**Concept.** The fast model has labeled the posts tier 0 passed up. Now decide which of its answers to accept. Two signals say "not settled": the model gave a "cannot tell" value, or it contradicts tier 0's guess. Two cheap, different methods that agree are probably right; when they disagree, it is worth paying for a third opinion.

**Your task.** Write `check_fast`. It records a tier 1 entry for every answer, collects the posts to escalate, and routes to `strong` or `persist`.

**Hints.**

- Tier 1 entries have no confidence. Only tier 0 has a number worth storing.
- When there is no classifier there is no guess, and the disagreement test must not fire.
- `is_unsure` from [07](07-classify.md) covers every dimension at once.

## Step 5: Check tier 2, then finish

**Your task.** Write the last four nodes and wire the workflow.

- `check_strong` records a tier 2 entry for every answer, puts the positions of posts still unsettled in `ctx.state["unsure"]`, and routes to `persist`, plus `review` when any are unsure. It returns nothing.
- `persist` reads `posts` and `labels` from state, turns each entry into rows with `label_rows`, and saves them.
- `queue_review` takes `unsure` from state and puts those posts on the review queue.
- `skip` says there was nothing to classify.

**Hints.**

- Every tier keeps its rows. A post settled at tier 2 also has its tier 0 and tier 1 rows, so you can measure how often the tiers agree. The primary key of `labels` includes the model, which allows this.
- `persist` is the only place a position number turns back into a URI.
- Only one end node that runs in a given batch may return a value ([06](06-adk-workflows.md)). Check which of yours can run together.
- There are four chains. Each starts where the previous one branched.
- **Fewer tiers.** To skip tier 0, leave the classifier files absent. To go straight from tier 0 to the strong model, pass the strong model's name as `fast`.

**Check.** `pytest tests/test_classify.py -k tier`. The three tests cover: no classifier; a post the strong model cannot settle; and a classifier that is sure of two posts and unsure of the third. Read the assertions on `seen`: with a classifier, only the unsure post reaches any model.

Then, for real:

```bash
python -m bluesky_bots.classify label --topic dem-leadership --tiered --limit 5 --verbose
```

## Step 6: Train tier 0

**Concept.** At first there is no classifier, so every post goes to the LLMs. Once you have a few hundred labeled posts per value, train one. The training labels can be the strong model's, as long as you test the result against posts you checked by hand.

**Your task.** In `bluesky_bots/classify/train.py`, write:

- `training_set(store, topic, dimension, model)`: the uri, text and value of every post that `model` labeled under the topic's current scheme, leaving out the "cannot tell" value. This is analysis, so it is a query on `store.analytics()`.
- `train_classifier(x, y, test_size=0.25)`: split into training and test sets, fit a logistic regression, and return the classifier with the held-back test set.
- `save_classifier(clf, topic, dimension)`: save it where step 1 looks for it.

**Hints.**

- Join `labels` to `posts` on `uri`. `SELECT DISTINCT` keeps a post about two entities from appearing twice with the same value.
- `train_test_split(..., stratify=y)` keeps the proportions of each value the same in both sets.
- `class_weight="balanced"` stops the commonest value from dominating.

**Check.** `pytest tests/test_classify.py -k "training_set or train_classifier"`

## Step 7: Choose the threshold

**Concept.** The threshold trades cost against accuracy: higher means fewer posts settled at tier 0 but fewer mistakes among them.

**Your task.** Write `threshold_table(clf, x_te, y_te, thresholds=(0.6, 0.7, 0.8, 0.9, 0.95))`. For each candidate it reports the share of test posts whose top probability reaches it, and the accuracy among those posts. Then train for real:

```bash
python -m bluesky_bots.classify train --topic dem-leadership --dimension stance
```

**Check.** As the threshold rises, the settled share falls and the accuracy rises. Pick the lowest threshold whose accuracy you would be willing to publish. Then check it again on hand-checked posts, and look at mistakes in both directions (critical read as supportive, and the reverse). Use one threshold for every value: a separate, looser threshold for one side would break the even-handed rule in [14](14-guardrails.md). If the probabilities look too sure of themselves, see scikit-learn's [calibration guide](https://scikit-learn.org/stable/modules/calibration.html).

Retrain, and pick the threshold again, whenever the topic's `labels.version` or `EMBED_MODEL` changes.

## Step 8: Measure it

**Your task.** Write two queries on `store.analytics()`: how many posts were settled at each tier, and, for posts that reached both LLM tiers, how the fast and strong answers compare.

**Check.** Read the results against these:

- If most posts reach tier 2, tier 0 or tier 1 is not earning its place: enlarge the training set, try a different fast model, or drop a tier.
- If the fast and strong models almost always agree, tier 1 can settle more on its own.
- Publish the error rate of the final labels with the models and scheme version ([14](14-guardrails.md)).

## Good to know

- **Only text leaves the PC.** The models receive `Item` (a number, the post text, the parent text), never the `uri`.
- **Same instruction for both LLM tiers**, so their labels can be compared.
- **One output at the end.** `persist` and `skip` are the only nodes that return a value, and only one of them runs per batch. `check_strong` and `queue_review` return `None`.
- **Charts and the agent's tools** read `labels_final`, which keeps the highest tier per post. A person's label on [11](11-review.md) is a higher tier than any model's.
- **Asking twice is another signal.** Running the fast model twice (thinking on and off, or two wordings) and escalating disagreements catches cases a single run hides. It doubles tier 1's cost.
- **Thinking.** Tier 1 usually does not need it; tier 2 may. See [16](16-choosing-models.md) for the setting per provider.
- **If training ends Python with no error message**, NumPy was imported before `bluesky_bots`. See "Good to know" in [01](01-setup.md).

## Example solution

`tests/test_classify.py` passes against this code (run on 2026-11-13), with plain functions standing in for the two models, made-up vectors for embeddings, and a real scikit-learn classifier. It has not been run with real models or real embeddings.

<details>
<summary>Show example: steps 1 to 5, the tiered workflow (bluesky_bots/classify/tiers.py)</summary>

```python
from pathlib import Path

import joblib
from google.adk import Agent, Context
from google.adk.workflow import START, Workflow, node

from .. import config
from ..topics import Topic, entities_in
from .scheme import Item, build_instruction, build_label_model, is_unsure, label_rows


def classifier_path(topic: Topic, dimension: str) -> Path:
    """Where the tier 0 classifier for one dimension of a topic's current scheme is kept."""
    return config.MODELS_DIR / topic.name / f"{dimension}-{topic.labels.version}.joblib"


def load_classifiers(topic: Topic) -> dict | None:
    """One trained classifier per dimension, or None unless every dimension has one."""
    paths = {name: classifier_path(topic, name) for name in topic.labels.dimensions}
    if not all(p.exists() for p in paths.values()):
        return None
    return {name: joblib.load(p) for name, p in paths.items()}


def build_tiered_workflow(topic: Topic, store, fast: str | None = None, strong: str | None = None,
                          embed_model: str | None = None, threshold: float = 0.9,
                          classifiers: dict | None = None, embed_fn=None,
                          labelers: dict | None = None, max_workers: int = 4) -> Workflow:
    """The tiered labeling workflow for one topic.

    fast, strong: model names for tiers 1 and 2 (LABEL_MODEL_FAST, LABEL_MODEL_STRONG).
    threshold:    tier 0 settles a post only when its least sure dimension reaches this probability.
    classifiers:  {dimension: classifier}; left out, they are loaded from classifier_path.
    embed_fn:     texts -> vectors for tier 0; left out, the narratives service's `embed`.
    labelers:     {"fast": ..., "strong": ...} to stand in for the two agents in a test.
    """
    Label = build_label_model(topic)
    fast = fast or config.model("LABEL_MODEL_FAST")
    strong = strong or config.model("LABEL_MODEL_STRONG")
    if classifiers is None:
        classifiers = load_classifiers(topic)
    if classifiers:
        embed_model = embed_model or config.model("EMBED_MODEL")
    tier0 = f"logreg+{embed_model}"         # what labels.model records for tier 0

    def labeler(name: str, model: str):
        # Both tiers get the same instruction, so their answers can be compared.
        agent = (labelers or {}).get(name) or Agent(
            name=f"classify_{name}", model=model, instruction=build_instruction(topic),
            output_schema=Label)
        return node(agent, name=f"label_{name}", parallel_worker=True, max_parallel_workers=max_workers)

    label_fast, label_strong = labeler("fast", fast), labeler("strong", strong)

    def as_item(posts: list[dict], i: int) -> Item:
        return Item(i=i, text=posts[i]["text"], parent_text=posts[i]["parent_text"])

    def record(ctx: Context, label: dict, model: str, tier: int, confidence: float | None = None):
        ctx.state["labels"] = ctx.state["labels"] + [
            {"label": label, "model": model, "tier": tier, "confidence": confidence}]

    @node
    def load_batch(ctx: Context) -> list[Item]:
        posts = store.unlabeled_posts(topic.name, topic.labels.version, limit=ctx.state.get("limit"))
        ctx.state["posts"] = [{"uri": p["uri"], "text": p["text"] or "", "parent_text": p["parent_text"]}
                              for p in posts]           # i = position in this list
        ctx.state["labels"] = []
        ctx.state["guess"] = {}
        ctx.route = "score" if posts else "skip"
        return [as_item(ctx.state["posts"], i) for i in range(len(posts))]

    @node
    def score_classifier(ctx: Context, node_input: list[Item]) -> list[Item]:
        posts = ctx.state["posts"]
        if not classifiers:                             # no classifier yet: everything goes on
            ctx.route = "fast"
            return node_input
        if embed_fn is not None:
            x = embed_fn([p["text"] for p in posts])
        else:
            from ..narratives import embed_posts        # imported here: it loads LiteLLM
            x = embed_posts(store, posts, embed_model)
        proba = {name: clf.predict_proba(x) for name, clf in classifiers.items()}
        guess, unsure = {}, []
        for i in range(len(posts)):
            label = {"i": i}
            if topic.entities:
                label["entities"] = entities_in(topic, posts[i]["text"])
            for name, clf in classifiers.items():
                label[name] = str(clf.classes_[proba[name][i].argmax()])
            p_min = min(float(proba[name][i].max()) for name in classifiers)
            record(ctx, label, tier0, 0, p_min)         # a tier 0 row for every post, sure or not
            guess[str(i)] = {name: label[name] for name in classifiers}
            if p_min < threshold:
                unsure.append(as_item(posts, i))
        ctx.state["guess"] = guess
        ctx.route = "fast" if unsure else "persist"
        return unsure

    @node
    def check_fast(ctx: Context, node_input: list[Label]) -> list[Item]:
        posts, guess = ctx.state["posts"], ctx.state["guess"]
        escalate = []
        for answer in node_input:
            label = answer.model_dump()
            record(ctx, label, fast, 1)
            g = guess.get(str(label["i"]))
            disagrees = g is not None and any(label[name] != value for name, value in g.items())
            if is_unsure(topic, label) or disagrees:
                escalate.append(as_item(posts, label["i"]))
        ctx.route = "strong" if escalate else "persist"
        return escalate

    @node
    def check_strong(ctx: Context, node_input: list[Label]) -> None:
        unsure = []
        for answer in node_input:
            label = answer.model_dump()
            record(ctx, label, strong, 2)
            if is_unsure(topic, label):
                unsure.append(label["i"])
        ctx.state["unsure"] = unsure
        ctx.route = ["persist", "review"] if unsure else "persist"

    @node
    def persist(ctx: Context) -> str:
        # Reads state rather than node_input, because three different nodes lead here.
        posts = ctx.state["posts"]
        rows = [row for r in ctx.state["labels"]
                for row in label_rows(topic, posts[r["label"]["i"]]["uri"], r["label"], r["model"],
                                      r["tier"], r["confidence"])]
        store.save_labels(rows)
        return f"saved {len(rows)} label rows for {len(posts)} posts"

    @node
    def queue_review(ctx: Context, unsure: list[int]) -> None:
        posts = ctx.state["posts"]
        store.enqueue_review({"item_type": "post", "item_id": posts[i]["uri"], "topic": topic.name,
                              "reason": "no model could tell"} for i in unsure)

    @node
    def skip(ctx: Context) -> str:
        return "nothing to classify"

    return Workflow(
        name="label_tiers",
        edges=[
            (START, load_batch, {"score": score_classifier, "skip": skip}),
            (score_classifier, {"fast": label_fast, "persist": persist}),
            (label_fast, check_fast, {"strong": label_strong, "persist": persist}),
            (label_strong, check_strong, {"persist": persist, "review": queue_review}),
        ],
    )
```

</details>

<details>
<summary>Show example: steps 6 and 7, training tier 0 and choosing the threshold (bluesky_bots/classify/train.py)</summary>

```python
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from ..topics import Topic
from .tiers import classifier_path


def training_set(store, topic: Topic, dimension: str, model: str) -> list[dict]:
    """Posts labeled by `model` under the topic's current scheme, as rows of uri, text and value.

    Posts given the dimension's "cannot tell" value are left out.
    """
    unsure = topic.labels.dimensions[dimension].unsure
    cur = store.analytics().execute("""
        SELECT DISTINCT p.uri, p.text, l.value
        FROM labels l JOIN posts p USING (uri)
        WHERE l.topic = ? AND l.scheme_version = ? AND l.dimension = ? AND l.model = ?
          AND (? IS NULL OR l.value <> ?)
        ORDER BY p.uri""", [topic.name, topic.labels.version, dimension, model, unsure, unsure])
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def train_classifier(x: np.ndarray, y, test_size: float = 0.25):
    """Fit a logistic regression on vectors `x` and values `y`.

    Returns (classifier, x_test, y_test); the test part was held back and not trained on.
    """
    y = np.asarray(y)
    x_tr, x_te, y_tr, y_te = train_test_split(x, y, test_size=test_size, stratify=y, random_state=0)
    clf = LogisticRegression(max_iter=1000, class_weight="balanced").fit(x_tr, y_tr)
    return clf, x_te, y_te


def threshold_table(clf, x_te: np.ndarray, y_te, thresholds=(0.6, 0.7, 0.8, 0.9, 0.95)) -> list[dict]:
    """For each candidate threshold: the share of test posts tier 0 would settle, and its accuracy on them."""
    proba = clf.predict_proba(x_te)
    top, pred = proba.max(axis=1), clf.classes_[proba.argmax(axis=1)]
    rows = []
    for t in thresholds:
        keep = top >= t
        rows.append({"threshold": t, "settled": float(keep.mean()),
                     "accuracy": float((pred[keep] == np.asarray(y_te)[keep]).mean()) if keep.any() else None})
    return rows


def save_classifier(clf, topic: Topic, dimension: str):
    """Save a trained classifier where the tiered workflow looks for it. Returns the path."""
    path = classifier_path(topic, dimension)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, path)
    return path
```

</details>

<details>
<summary>Show example: step 8, measuring it</summary>

```sql
-- where posts are settled
SELECT tier, count(DISTINCT uri) AS posts
FROM labels_final
WHERE topic = 'dem-leadership' AND scheme_version = 'stance-v1'
GROUP BY 1 ORDER BY 1;

-- fast against strong, on the posts that reached both and named the same entity
SELECT a.value AS fast, b.value AS strong, count(*) AS n
FROM labels a JOIN labels b USING (uri, topic, scheme_version, target, dimension)
WHERE a.tier = 1 AND b.tier = 2 AND a.topic = 'dem-leadership' AND a.dimension = 'stance'
GROUP BY 1, 2 ORDER BY 3 DESC;
```

</details>
