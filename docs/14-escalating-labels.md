# 14 Escalating labels

Build a labeling workflow that settles easy posts cheaply and sends only the hard ones to a stronger model:

1. **Tier 0**, a small classifier on embeddings, labels the posts it is sure about.
2. **Tier 1**, a fast LLM (`LABEL_MODEL_FAST`), labels the rest.
3. **Tier 2**, a strong LLM (`LABEL_MODEL_STRONG`), gets the posts tier 1 could not settle.
4. Posts tier 2 still calls `"unclear"` go to human review.

Each step explains one idea, sets a task, and tells you how to check your work. The example code is at the bottom under [Example solution](#example-solution), collapsed.

Not yet run on this PC. It uses only the workflow pieces from [05](05-adk-workflows.md) and [06](06-gemma-labels.md), which were. Read [13](13-choosing-models.md) for what to put in each model key.

Needs: `load_dotenv()` first, `LABEL_MODEL_FAST`, `LABEL_MODEL_STRONG` and `EMBED_MODEL` in `.env`, the `embed()` function from [08](08-narratives.md), and `scikit-learn`. Do [06](06-gemma-labels.md) first; this page changes that workflow and does not explain its parts again.

Read first:

- [Logistic regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html) in scikit-learn, and `predict_proba` in particular
- [Probability calibration](https://scikit-learn.org/stable/modules/calibration.html), for why a classifier's probability can be checked and an LLM's stated confidence cannot
- [Workflows](https://google.github.io/adk-docs/workflows/) in the ADK docs

## What you are building

```
START -> load_batch -> prefilter -> score_classifier -> label_fast -> check_fast -> label_strong -> check_strong -> persist
                                 -> skip             -> persist                  -> persist                      -> queue_review
```

Every arrow that leaves the top line early is a post that was settled without the more expensive step. You are done when a batch runs end to end with no classifier file present (every post goes to tier 1), and again with one (some posts stop at tier 0).

## What decides escalation

An LLM's own `confidence` field cannot be used: in [06](06-gemma-labels.md) Gemma reported 1.0 on every post, including the wrong one. The signals here are ones you can measure:

| Step | Moves a post up when |
| --- | --- |
| Tier 0 to tier 1 | the classifier's top probability is below `T0`. The probability is real and can be checked against hand-checked posts. |
| Tier 1 to tier 2 | the fast model answers `"unclear"`, or it disagrees with tier 0's best guess. |
| Tier 2 to review | the strong model answers `"unclear"`. |

Until a classifier is trained, tier 0 passes every post through and tier 1 escalates on `"unclear"` alone.

## Step 1: Decide what a model may see

**Concept.** In [06](06-gemma-labels.md) the model received each post's `uri` and copied it back. A URI contains the author's DID, and with a cloud model that leaves this PC. Here the model gets a position number instead. The posts stay in workflow state, and the number is matched back to the URI at the very end.

So there are three structures: `Post` (what you load, with a `uri`), `Item` (what a model sees: an index `i`, the text, the parent text) and `Label` (what a model returns: `i`, the leaders, the stance).

**Your task.** Write the three models and the constants: the leader patterns, `PROMPT_VERSION`, the two model names, the path of the classifier file, the name that `labels.model` should record for tier 0, and the threshold `T0`.

**Hints.**

- `Label` has no `tone` and no `confidence`. [06](06-gemma-labels.md) found both unreliable.
- Tier 0's recorded name should include the embedding model. A classifier trained on one embedding model means nothing with another.
- `T0 = 0.9` is a placeholder. Step 10 shows how to choose it.

## Step 2: Two labelers from one instruction

**Concept.** The fast and the strong model must be given the same instruction. Otherwise a disagreement between them could be a difference in what they were asked, and their labels could not be compared.

**Your task.** Write the instruction (adapt yours from [06](06-gemma-labels.md): the model now copies `i`, not a URI, and there is no confidence to report). Then write `labeler(name, model)`, which builds an agent and returns it wrapped as a parallel worker. Use it to create `label_fast` and `label_strong`.

**Hints.**

- Wrap each agent once and keep the result in a variable. The same object is used wherever the node appears in the edges ([05](05-adk-workflows.md)).
- The two agents need different names.

## Step 3: Load, prefilter, and remember the posts

**Concept.** Because models only see indexes, something has to hold the real posts. `prefilter` stores the posts that passed in `ctx.state["posts"]`, as a list. A post's index `i` is its position in that list for the rest of the run. It also starts an empty `ctx.state["labels"]`, which every tier will add rows to.

**Your task.** Write two helpers and two nodes:

- `leaders_in(text)` returns the leaders whose pattern matches.
- `as_item(posts, i)` builds the `Item` for position `i`.
- `load_batch`, as in [06](06-gemma-labels.md).
- `prefilter` keeps posts that mention a leader, stores them and the empty label list in state, and routes to `score` or `skip`.

**Hints.**

- State holds plain data: `model_dump()` each post before storing it.

## Step 4: Tier 0, the classifier

**Concept.** A logistic regression on embeddings costs milliseconds per post and gives a probability for each stance. When its top probability is high, accept its label. When it is not, pass the post up.

This node has to work on day one, before any classifier exists.

**Your task.** Write the `score_classifier` node.

- If the classifier file does not exist, route to `fast` and return every post as an `Item`.
- Otherwise load it, embed the post texts, and get probabilities. For every post, add a tier 0 row to `ctx.state["labels"]` and remember the classifier's guess in `ctx.state["guess"]`. Collect the posts whose top probability is under `T0`.
- Route to `fast` if any are unsure, and straight to `persist` if none are. Return the unsure ones.

**Hints.**

- `clf.predict_proba(x)` gives one row of probabilities per post; `clf.classes_` gives the stance each column stands for.
- A label row here is a dict with `i`, `leaders`, `stance`, `confidence`, `model` and `tier`.
- Record a tier 0 row for *every* post, including the unsure ones. You will want to know later how often tier 0's guess agreed with the models above it.
- Keys in state are safest as strings: store the guess under `str(i)`.

## Step 5: Check tier 1

**Concept.** The fast model has labeled the posts tier 0 passed up. Now decide which of its answers to accept. Two signals say "not settled": the model said `"unclear"`, or it contradicts tier 0's guess. Two cheap, different methods that agree are probably right; when they disagree, it is worth paying for a third opinion.

**Your task.** Write `check_fast`. It adds a tier 1 row for every label, collects the posts to escalate, and routes to `strong` or `persist`.

**Hints.**

- Tier 1 rows have `confidence` of `None`. Only tier 0 has a number worth storing.
- When there is no classifier there is no guess, and the disagreement test must not fire.

## Step 6: Check tier 2

**Your task.** Write `check_strong`. It adds a tier 2 row for every label, puts the indexes of posts still `"unclear"` in `ctx.state["unsure"]`, and routes to `persist`, plus `review` when any are unsure. It returns nothing.

**Hints.**

- Why nothing? Three different nodes lead to `persist`, each with different output. So `persist` reads state, and this node has no need to hand it anything.

## Step 7: Persist, review, skip

**Concept.** Every tier keeps its row. A post settled at tier 2 also has its tier 0 and tier 1 rows, so you can measure how often the tiers agree. The `labels` primary key `(uri, model, prompt_version)` already allows this.

**Your task.** Write the three end nodes.

- `persist` reads the posts and label rows from state, attaches each row's `uri` (from the post at index `i`) and the prompt version, and returns a short message. Later it becomes an insert.
- `queue_review` takes `unsure` from state and records how many.
- `skip` says there was nothing to classify.

**Hints.**

- This is where the index turns back into a URI. It is the only place in the workflow that needs to.
- Only one end node that runs in a given batch may return a value ([05](05-adk-workflows.md)). Check which of yours can run together.

## Step 8: Wire it and run

**Your task.** Create the `Workflow` named `label_tiers` to match the diagram in "What you are building", and a `run_batch` as in [06](06-gemma-labels.md). Try it with the three sample posts from that page.

**Hints.**

- There are four chains. Each starts where the previous one branched.
- **Fewer tiers.** To skip tier 0, leave the classifier file absent. To go straight from tier 0 to the strong model, replace `label_fast` and `check_fast` with the strong pair. Write those edges yourself, then compare with the example.

**Check.**

- With no classifier file, the trace should pass through `score_classifier`, `label_fast` and `check_fast`, and end in `persisted 2 rows for 2 posts` when the fast model is sure of both.
- The weather post never reaches a model.
- Look at what `score_classifier` returns in the trace. That list is what the model is sent: each item has `i`, `text` and `parent_text`, and there is no `at://` anywhere in it.

## Step 9: Store the tiers

**Concept.** The database needs two additions: a place to record which tier produced a row, and a single answer per post for charts and for the agent's tools in [07](07-gemma-tools.md).

**Your task.** Add an integer `tier` column to `labels`. Then create a view `labels_final` that keeps, for each post and prompt version, the row from the highest tier.

**Hints.**

- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` is safe to run more than once.
- "The top row per group" is `row_number() OVER (PARTITION BY ... ORDER BY ...)`, and DuckDB's [`QUALIFY`](https://duckdb.org/docs/stable/sql/query_syntax/qualify) filters on it without a subquery.

**Check.** A post with rows at tiers 0, 1 and 2 appears once in `labels_final`, with its tier 2 stance.

## Step 10: Train tier 0 and choose `T0`

**Concept.** At first there is no classifier, so every post goes to the LLMs. Once you have a few hundred labeled posts per stance, train one. The training labels can be the strong model's, as long as you test the result against posts you checked by hand.

`T0` trades cost against accuracy: higher means fewer posts settled at tier 0 but fewer mistakes among them.

**Your task.**

1. Read the text and stance of every post labeled by the strong model under the current prompt version, leaving out `"unclear"`.
2. Embed the texts, split them into training and test sets, fit a logistic regression, and save it to the classifier path.
3. On the test set, for each candidate threshold from 0.6 to 0.95, print the share of posts whose top probability reaches it and the accuracy among those posts.

**Hints.**

- `train_test_split(..., stratify=...)` keeps the stance proportions the same in both sets.
- `class_weight="balanced"` stops the commonest stance from dominating.
- `joblib.dump(clf, path)` saves; `joblib.load` is what `score_classifier` calls.

**Check.** As the threshold rises, the settled share falls and the accuracy rises. Pick the lowest threshold whose accuracy you would be willing to publish. Then check it again on hand-checked posts, and look at mistakes in both directions (critical read as supportive, and the reverse). Use one threshold for every stance: a separate, looser threshold for one side would break the even-handed rule in [11](11-guardrails.md). If the probabilities look too sure of themselves, see scikit-learn's [calibration guide](https://scikit-learn.org/stable/modules/calibration.html).

Retrain, and pick `T0` again, whenever `PROMPT_VERSION` or `EMBED_MODEL` changes. A classifier trained on one embedding model cannot score vectors from another.

## Step 11: Measure it

**Your task.** Write two queries: how many posts were settled at each tier, and, for posts that reached both LLM tiers, how the fast and strong stances compare.

**Check.** Read the results against these:

- If most posts reach tier 2, tier 0 or tier 1 is not earning its place: raise the training set, try a different fast model, or drop a tier.
- If the fast and strong models almost always agree, tier 1 can settle more on its own.
- Publish the error rate of the final labels with the models and prompt version ([11](11-guardrails.md)).

## Good to know

- **Only text leaves the PC.** The models receive `Item` (an index, the post text, the parent text), never the `uri`, which contains the author's DID. The index is matched back to the `uri` in `persist`.
- **Same instruction for both LLM tiers**, so their labels can be compared. Change `PROMPT_VERSION` whenever `INSTRUCTION` changes.
- **One output at the end.** `persist` and `skip` are the only nodes that return a value, and only one of them runs per batch (the rule from [05](05-adk-workflows.md)). `check_strong` and `queue_review` return `None`.
- **Charts and the agent tools** in [07](07-gemma-tools.md) should read `labels_final` once you use tiers.
- **Asking twice is another signal.** Running the fast model twice (thinking on and off, or two wordings) and escalating disagreements catches cases a single run hides. It doubles tier 1's cost.
- **Thinking.** Tier 1 usually does not need it; tier 2 may. See [13](13-choosing-models.md) for the setting per provider.
- **`tone` and `confidence` are gone from the LLM schema.** [06](06-gemma-labels.md) found both unreliable. `labels.confidence` now holds tier 0's probability only.

## Example solution

Read top to bottom, the blocks for steps 1 to 8 make one module.

<details>
<summary>Show example: step 1, what a model may see</summary>

```python
import os, re
from pathlib import Path
from typing import Literal
import joblib
from pydantic import BaseModel
from google.adk import Agent, Context, Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import Workflow, node, START
from google.genai import types
# embed() is the function from page 08, copied into your own module

LEADERS = {"schumer": r"\bschumer\b", "jeffries": r"\bjeffries\b"}
PROMPT_VERSION = "stance-v1"
FAST = os.environ["LABEL_MODEL_FAST"]
STRONG = os.environ["LABEL_MODEL_STRONG"]
CLASSIFIER = Path("data/models/stance_logreg.joblib")
TIER0 = "logreg-v1+" + os.environ["EMBED_MODEL"]   # what labels.model records for tier 0
T0 = 0.9                                           # placeholder; choose it as shown below

class Post(BaseModel):
    uri: str
    text: str
    parent_text: str | None = None

class Item(BaseModel):          # what a model sees: no uri, so no DID leaves the PC
    i: int
    text: str
    parent_text: str | None = None

class Label(BaseModel):
    i: int
    leaders: list[Literal["schumer", "jeffries"]]
    stance: Literal["critical", "supportive", "neutral", "unclear"]
```

</details>

<details>
<summary>Show example: step 2, two labelers from one instruction</summary>

```python
INSTRUCTION = """You label one Bluesky post about US Democratic leaders.
Label only what the post says. Do not guess whether the author is sincere,
automated, or part of a campaign; that is not your job and you lack the evidence.
Criticism and support are equally ordinary. Apply the same care to both.
stance is toward the named leader, not toward the party or the topic.
If sarcasm or missing context makes the stance uncertain, answer "unclear".
Copy i unchanged."""

def labeler(name: str, model: str):
    agent = Agent(name=name, model=model, instruction=INSTRUCTION, output_schema=Label)
    return node(agent, parallel_worker=True, max_parallel_workers=4)

label_fast = labeler("label_fast", FAST)       # wrap once, reuse (see 05)
label_strong = labeler("label_strong", STRONG)
```

</details>

<details>
<summary>Show example: step 3, loading, prefiltering and remembering the posts</summary>

```python
def leaders_in(text: str) -> list[str]:
    return [k for k, rx in LEADERS.items() if re.search(rx, text, re.I)]

def as_item(posts: list[dict], i: int) -> Item:
    p = posts[i]
    return Item(i=i, text=p["text"], parent_text=p.get("parent_text"))

@node
def load_batch(ctx: Context) -> list[Post]:
    # Replace with: posts that have no labels row for this PROMPT_VERSION.
    return [Post(**row) for row in ctx.state.get("batch", [])]

@node
def prefilter(ctx: Context, node_input: list[Post]) -> list[Post]:
    hits = [p for p in node_input if leaders_in(p.text)]
    ctx.state["posts"] = [p.model_dump() for p in hits]   # i = position in this list
    ctx.state["labels"] = []
    ctx.route = "score" if hits else "skip"
    return hits
```

</details>

<details>
<summary>Show example: step 4, tier 0</summary>

```python
@node
def score_classifier(ctx: Context, node_input: list[Post]) -> list[Item]:
    posts = ctx.state["posts"]
    if not CLASSIFIER.exists():                  # no classifier yet: everything goes on
        ctx.route = "fast"
        return [as_item(posts, i) for i in range(len(posts))]
    clf = joblib.load(CLASSIFIER)
    proba = clf.predict_proba(embed([p["text"] for p in posts]))
    rows, guess, unsure = [], {}, []
    for i, pr in enumerate(proba):
        stance, p_top = str(clf.classes_[pr.argmax()]), float(pr.max())
        guess[str(i)] = stance
        rows.append({"i": i, "leaders": leaders_in(posts[i]["text"]), "stance": stance,
                     "confidence": p_top, "model": TIER0, "tier": 0})
        if p_top < T0:
            unsure.append(as_item(posts, i))
    ctx.state["labels"] = rows
    ctx.state["guess"] = guess
    ctx.route = "fast" if unsure else "persist"
    return unsure
```

</details>

<details>
<summary>Show example: step 5, checking tier 1</summary>

```python
@node
def check_fast(ctx: Context, node_input: list[Label]) -> list[Item]:
    posts, guess = ctx.state["posts"], ctx.state.get("guess", {})
    rows, escalate = list(ctx.state["labels"]), []
    for l in node_input:
        rows.append({**l.model_dump(), "confidence": None, "model": FAST, "tier": 1})
        g = guess.get(str(l.i))
        if l.stance == "unclear" or (g is not None and g != l.stance):
            escalate.append(as_item(posts, l.i))
    ctx.state["labels"] = rows
    ctx.route = "strong" if escalate else "persist"
    return escalate
```

</details>

<details>
<summary>Show example: step 6, checking tier 2</summary>

```python
@node
def check_strong(ctx: Context, node_input: list[Label]) -> None:
    rows = list(ctx.state["labels"])
    rows += [{**l.model_dump(), "confidence": None, "model": STRONG, "tier": 2}
             for l in node_input]
    unsure = [l.i for l in node_input if l.stance == "unclear"]
    ctx.state["labels"] = rows
    ctx.state["unsure"] = unsure
    ctx.route = ["persist", "review"] if unsure else "persist"
```

</details>

<details>
<summary>Show example: step 7, persist, review and skip</summary>

```python
@node
def persist(ctx: Context) -> str:
    # Reads state rather than node_input, because three different nodes lead here.
    # Replace with INSERT INTO labels (uri, model, prompt_version, leaders, stance,
    # confidence, tier, labeled_at) ... ON CONFLICT DO NOTHING.
    posts = ctx.state["posts"]
    rows = [{**r, "uri": posts[r["i"]]["uri"], "prompt_version": PROMPT_VERSION}
            for r in ctx.state["labels"]]
    return f"persisted {len(rows)} rows for {len(posts)} posts"

@node
def queue_review(ctx: Context, unsure: list[int]) -> None:
    # Replace with an INSERT into a post-level review queue (uri from ctx.state["posts"]).
    ctx.state["queued_for_review"] = len(unsure)

@node
def skip(ctx: Context) -> str:
    return "nothing to classify"
```

</details>

<details>
<summary>Show example: step 8, wiring and running</summary>

```python
label_tiers = Workflow(
    name="label_tiers",
    edges=[
        (START, load_batch, prefilter, {"score": score_classifier, "skip": skip}),
        (score_classifier, {"fast": label_fast, "persist": persist}),
        (label_fast, check_fast, {"strong": label_strong, "persist": persist}),
        (label_strong, check_strong, {"persist": persist, "review": queue_review}),
    ],
)

async def run_batch(batch: list[dict], session_id: str):
    runner = Runner(node=label_tiers, session_service=InMemorySessionService(),
                    auto_create_session=True)
    start = types.Content(role="user", parts=[types.Part(text="run")])
    async for event in runner.run_async(user_id="pipeline", session_id=session_id,
                                        new_message=start,
                                        state_delta={"batch": batch}):
        if event.output is not None:
            print(event.node_info.path, event.output)
```

Try it with the three sample posts from [06](06-gemma-labels.md):

```python
await run_batch([
    {"uri": "at://a/1", "text": "Schumer caved again. Every single time. He needs to go."},
    {"uri": "at://a/2", "text": "Lovely weather in Brooklyn today."},
    {"uri": "at://a/3", "text": "Honestly Jeffries handled that press conference well."},
], session_id="tiers-1")
```

</details>

<details>
<summary>Show example: step 9, storing the tiers</summary>

Add a column for the tier once:

```sql
ALTER TABLE labels ADD COLUMN IF NOT EXISTS tier INTEGER;
```

One final label per post comes from a view that takes the highest tier:

```sql
CREATE OR REPLACE VIEW labels_final AS
SELECT * FROM labels
QUALIFY row_number() OVER (PARTITION BY uri, prompt_version ORDER BY tier DESC) = 1;
```

</details>

<details>
<summary>Show example: step 8, fewer tiers</summary>

To go straight from tier 0 to the strong model, use these edges (the route keeps the name `"fast"`):

```python
edges=[
    (START, load_batch, prefilter, {"score": score_classifier, "skip": skip}),
    (score_classifier, {"fast": label_strong, "persist": persist}),
    (label_strong, check_strong, {"persist": persist, "review": queue_review}),
]
```

</details>

<details>
<summary>Show example: step 10, training tier 0 and choosing T0</summary>

```python
import duckdb, joblib
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

con = duckdb.connect("data/narrative.duckdb", read_only=True)
df = con.execute("""
    SELECT p.text, l.stance FROM labels l JOIN posts p USING (uri)
    WHERE l.model = ? AND l.prompt_version = ? AND l.stance <> 'unclear'
""", [STRONG, PROMPT_VERSION]).df()

x = embed(df.text.tolist())
x_tr, x_te, y_tr, y_te = train_test_split(x, df.stance.values, test_size=0.25,
                                          stratify=df.stance, random_state=0)
clf = LogisticRegression(max_iter=1000, class_weight="balanced").fit(x_tr, y_tr)

Path("data/models").mkdir(parents=True, exist_ok=True)
joblib.dump(clf, "data/models/stance_logreg.joblib")
```

Choosing `T0`:

```python
proba = clf.predict_proba(x_te)
top, pred = proba.max(axis=1), clf.classes_[proba.argmax(axis=1)]
for t in (0.6, 0.7, 0.8, 0.9, 0.95):
    keep = top >= t
    print(t, f"settled {keep.mean():.0%}", f"accuracy {(pred[keep] == y_te[keep]).mean():.0%}")
```

</details>

<details>
<summary>Show example: step 11, measuring it</summary>

```sql
-- where posts are settled
SELECT tier, count(*) AS n FROM labels_final WHERE prompt_version = 'stance-v1' GROUP BY 1 ORDER BY 1;

-- fast vs strong on the posts that reached both
SELECT a.stance AS fast, b.stance AS strong, count(*) AS n
FROM labels a JOIN labels b USING (uri, prompt_version)
WHERE a.tier = 1 AND b.tier = 2 AND a.prompt_version = 'stance-v1'
GROUP BY 1, 2 ORDER BY 3 DESC;
```

</details>
