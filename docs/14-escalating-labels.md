# 14 Escalating labels

A labeling workflow that settles easy posts cheaply and sends only the hard ones to a stronger model:

1. **Tier 0**, a small classifier on embeddings, labels the posts it is sure about.
2. **Tier 1**, a fast LLM (`LABEL_MODEL_FAST`), labels the rest.
3. **Tier 2**, a strong LLM (`LABEL_MODEL_STRONG`), gets the posts tier 1 could not settle.
4. Posts tier 2 still calls `"unclear"` go to human review.

Not yet run on this PC. It uses only the workflow pieces from [05](05-adk-workflows.md) and [06](06-gemma-labels.md), which were. Read [13](13-choosing-models.md) for what to put in each model key.

Needs: `load_dotenv()` first, `LABEL_MODEL_FAST`, `LABEL_MODEL_STRONG` and `EMBED_MODEL` in `.env`, the `embed()` function from [08](08-narratives.md), and `scikit-learn`.

## What decides escalation

An LLM's own `confidence` field cannot be used: in [06](06-gemma-labels.md) Gemma reported 1.0 on every post, including the wrong one. The signals here are ones you can measure:

| Step | Moves a post up when |
| --- | --- |
| Tier 0 to tier 1 | the classifier's top probability is below `T0`. The probability is real and can be checked against hand-checked posts. |
| Tier 1 to tier 2 | the fast model answers `"unclear"`, or it disagrees with tier 0's best guess. |
| Tier 2 to review | the strong model answers `"unclear"`. |

Until a classifier is trained, tier 0 passes every post through and tier 1 escalates on `"unclear"` alone.

## The workflow

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

@node
def check_strong(ctx: Context, node_input: list[Label]) -> None:
    rows = list(ctx.state["labels"])
    rows += [{**l.model_dump(), "confidence": None, "model": STRONG, "tier": 2}
             for l in node_input]
    unsure = [l.i for l in node_input if l.stance == "unclear"]
    ctx.state["labels"] = rows
    ctx.state["unsure"] = unsure
    ctx.route = ["persist", "review"] if unsure else "persist"

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

## How it fits together

- **Every tier keeps its row.** A post settled at tier 2 also has its tier 0 and tier 1 rows, so you can measure how often the tiers agree. The `labels` primary key `(uri, model, prompt_version)` already allows this. Add a column for the tier once:

  ```sql
  ALTER TABLE labels ADD COLUMN IF NOT EXISTS tier INTEGER;
  ```

- **One final label per post** comes from a view that takes the highest tier:

  ```sql
  CREATE OR REPLACE VIEW labels_final AS
  SELECT * FROM labels
  QUALIFY row_number() OVER (PARTITION BY uri, prompt_version ORDER BY tier DESC) = 1;
  ```

  Charts and the agent tools in [07](07-gemma-tools.md) should read `labels_final` once you use tiers.
- **One output at the end.** `persist` and `skip` are the only nodes that return a value, and only one of them runs per batch (the rule from [05](05-adk-workflows.md)). `check_strong` and `queue_review` return `None`.
- **Fewer tiers.** To skip tier 0, leave the classifier file absent. To go straight from tier 0 to the strong model, use these edges (the route keeps the name `"fast"`):

  ```python
  edges=[
      (START, load_batch, prefilter, {"score": score_classifier, "skip": skip}),
      (score_classifier, {"fast": label_strong, "persist": persist}),
      (label_strong, check_strong, {"persist": persist, "review": queue_review}),
  ]
  ```

## Training tier 0

At first there is no classifier, so every post goes to the LLMs. Once you have a few hundred labeled posts per stance, train one. The training labels can be the strong model's, as long as you test the result against posts you checked by hand.

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

### Choosing `T0`

`T0` trades cost against accuracy: higher means fewer posts settled at tier 0 but fewer mistakes among them.

```python
proba = clf.predict_proba(x_te)
top, pred = proba.max(axis=1), clf.classes_[proba.argmax(axis=1)]
for t in (0.6, 0.7, 0.8, 0.9, 0.95):
    keep = top >= t
    print(t, f"settled {keep.mean():.0%}", f"accuracy {(pred[keep] == y_te[keep]).mean():.0%}")
```

Pick the lowest `t` whose accuracy you would be willing to publish. Then check it again on hand-checked posts, and look at mistakes in both directions (critical read as supportive, and the reverse). Use one threshold for every stance: a separate, looser threshold for one side would break the even-handed rule in [11](11-guardrails.md). If the probabilities look too sure of themselves, see scikit-learn's [calibration guide](https://scikit-learn.org/stable/modules/calibration.html).

Retrain, and pick `T0` again, whenever `PROMPT_VERSION` or `EMBED_MODEL` changes. A classifier trained on one embedding model cannot score vectors from another.

## What to measure

```sql
-- where posts are settled
SELECT tier, count(*) AS n FROM labels_final WHERE prompt_version = 'stance-v1' GROUP BY 1 ORDER BY 1;

-- fast vs strong on the posts that reached both
SELECT a.stance AS fast, b.stance AS strong, count(*) AS n
FROM labels a JOIN labels b USING (uri, prompt_version)
WHERE a.tier = 1 AND b.tier = 2 AND a.prompt_version = 'stance-v1'
GROUP BY 1, 2 ORDER BY 3 DESC;
```

- If most posts reach tier 2, tier 0 or tier 1 is not earning its place: raise the training set, try a different fast model, or drop a tier.
- If the fast and strong models almost always agree, tier 1 can settle more on its own.
- Publish the error rate of the final labels with the models and prompt version ([11](11-guardrails.md)).

## Good to know

- **Only text leaves the PC.** The models receive `Item` (an index, the post text, the parent text), never the `uri`, which contains the author's DID. The index is matched back to the `uri` in `persist`.
- **Same instruction for both LLM tiers**, so their labels can be compared. Change `PROMPT_VERSION` whenever `INSTRUCTION` changes.
- **Asking twice is another signal.** Running the fast model twice (thinking on and off, or two wordings) and escalating disagreements catches cases a single run hides. It doubles tier 1's cost.
- **Thinking.** Tier 1 usually does not need it; tier 2 may. See [13](13-choosing-models.md) for the setting per provider.
- **`tone` and `confidence` are gone from the LLM schema.** [06](06-gemma-labels.md) found both unreliable. `labels.confidence` now holds tier 0's probability only.
