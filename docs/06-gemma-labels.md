# 06 Labeling posts

Build a workflow that takes a batch of posts, drops the ones that mention no leader, asks a model for the stance of each remaining post, and separates unsure labels for review.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed.

Needs: `load_dotenv()` first, `LABEL_MODEL_FAST` in `.env` ([13](13-choosing-models.md)). Do [05](05-adk-workflows.md) first; this page uses its workflow API without explaining it again. This page uses one model; [14](14-escalating-labels.md) builds on it with cheaper and stronger tiers.

Read first:

- [Simple agents](https://google.github.io/adk-docs/agents/llm-agents/) in the ADK docs: `Agent`, instructions and `output_schema`
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/), which you use to say what a label is
- [11 Guardrails](11-guardrails.md). Two of its rules shape the prompt you write in step 2.

## What you are building

```
START -> load_batch -> prefilter -> classify (once per post) -> check_confidence -> persist
                                 -> skip                                         -> queue_review
```

You are done when three sample posts (one critical, one off-topic, one supportive) produce two labels, the off-topic post never reaches the model, and the run ends with `persisted 2`.

## Step 1: Say what a label is

**Concept.** A model asked for a "stance" in free text will answer with a paragraph, in different words each time. Ask instead for a fixed structure with a closed set of allowed values, and you get something you can count. In ADK you describe the structure as a Pydantic model and the framework holds the model's answer to it.

You need two structures:

- `Post`, what goes in: a `uri`, the `text`, and optionally the text of the post it replies to.
- `PostLabel`, what comes out: the `uri` again, which leaders the post is about, the stance toward them, the tone, and a confidence between 0 and 1.

**Your task.** Write both as Pydantic models, with the constants the page will need: the leaders and a pattern for each, a `PROMPT_VERSION` string, and the model name read from the environment.

**Hints.**

- `typing.Literal["a", "b"]` restricts a field to those values. Decide your stance values before reading on. You need one for "cannot tell".
- `Field(ge=0, le=1)` bounds a number.
- Keep every field about the *post*. Do not add one that asks whether the author is genuine or automated. The model has no evidence for that, and the project's first principle rules it out.
- Why does the label repeat the `uri`? Think about how you will match answers to posts when several are classified at the same time.

## Step 2: Write the instruction

**Concept.** The instruction is where the project's principles become behavior. Whatever you leave unsaid, the model fills in by itself.

**Your task.** Write the instruction text for a model that labels one post. Write your own before you open the example. It should cover each of these:

- Label what the post says, and nothing about who wrote it or why.
- Treat criticism and support as equally ordinary, with the same care for both.
- The stance is toward the *named leader*, not toward the party or the topic. ("I'm furious they're attacking Jeffries" is angry and supportive.)
- What to answer when sarcasm or missing context makes the stance uncertain.
- Return the `uri` unchanged.

**Hints.**

- Short and literal beats long and clever. A small model follows a seven-line instruction better than a page.
- Change `PROMPT_VERSION` every time you change the wording. The `labels` table is keyed by it, so labels made with different wordings are never mixed.

## Step 3: The classifier agent

**Concept.** An `Agent` is a model plus an instruction. With `output_schema` set, its answer is parsed into your Pydantic model instead of coming back as text.

**Your task.** Create an agent named `classify_post` from your model name, your instruction and `PostLabel`.

**Hints.**

- `from google.adk import Agent`
- You can try an agent by itself before building the workflow; [01](01-setup.md) shows `InMemoryRunner` and `run_debug`.

## Step 4: Load a batch and filter it before the model

**Concept.** The cheapest model call is the one you do not make. Most posts in a batch mention no leader, and a regular expression can tell. So the first two nodes are plain Python: one produces the batch, one keeps only posts that match a leader pattern and routes the run to `classify`, or to `skip` when nothing is left.

**Your task.** Write `load_batch` and `prefilter`.

**Hints.**

- For now `load_batch` builds `Post` objects from a list of dicts in `ctx.state["batch"]`. Later you replace its body with a database query.
- `prefilter` receives the list through `node_input`, sets `ctx.route`, and returns the posts that matched.

## Step 5: Separate sure from unsure, and finish

**Concept.** After the model has labeled the posts, split the labels: the ones to store, and the ones a person should look at. Then the run ends in up to two branches at once: `persist` always, `review` only when something is unsure.

Two workflow rules from [05](05-adk-workflows.md) matter here:

- Assigning a *list* to `ctx.route` fires several branches.
- Only one end node may return a value. The others return `None` and leave their result in state.

**Your task.** Write four nodes:

- `check_confidence` receives the labels. A label is sure when its confidence is at least 0.6 and its stance is not the "cannot tell" value. It puts the unsure ones in `ctx.state["unsure"]`, routes, and returns the sure ones.
- `persist` receives the sure labels and returns a short message saying how many.
- `queue_review` takes `unsure` from state, records how many there were, and returns nothing.
- `skip` returns a message saying there was nothing to classify.

**Hints.**

- A parameter named `unsure` is filled from `ctx.state["unsure"]`.
- State has to hold plain data. `label.model_dump()` turns a Pydantic object into a dict.
- `persist` and `queue_review` are placeholders for database inserts. Keep them small for now.

## Step 6: Fan out and wire the workflow

**Concept.** The agent labels one post; the batch has many. Wrapping the agent with `node(..., parallel_worker=True)` gives you a node that takes the list and runs the agent once per post (step 5 of [05](05-adk-workflows.md)).

The workflow has two chains. The first ends in a branch (`classify` or `skip`). The second starts from the `classify` node and carries on to the end.

**Your task.** Wrap the agent, then create the `Workflow` named `label_posts` to match the diagram in "What you are building".

**Hints.**

- Wrap the agent **once** and use that same object in both chains. Wrapping twice, or using the bare agent in one place and the wrapped one in another, raises "Duplicate node names".
- `max_parallel_workers` is your politeness setting for a paid API, and your memory limit for a local model.

## Step 7: Run a batch

**Your task.** Write `async def run_batch(batch, session_id)`, modeled on `run` from [05](05-adk-workflows.md), with the batch in the starting state. Try it on three posts: one clearly critical of Schumer, one about the weather, one clearly supportive of Jeffries.

**Check.**

- The printed lines show each node's output in order. The labels arrive as one list at `label_posts@1/classify_post@1`, then `check_confidence`, then `persisted N`.
- The weather post is not in the list. It never reached the model.
- Now add a sarcastic post, such as "Oh sure, Schumer is a master strategist, just look at all those wins", and see what your model does with it. Compare with "What a first run showed" below.

## Turning thinking off

Many models reason step by step before answering, which is slow and, on paid APIs, costs output tokens. For a `provider/model` name, replace the `model=` line inside `Agent(...)` with:

```python
model=LiteLlm(model=MODEL, reasoning_effort="none"),   # from google.adk.models.lite_llm import LiteLlm
```

Native Gemini names use `generate_content_config` instead; [13](13-choosing-models.md) shows both.

## What a first run showed

Five sample posts, Gemma 4 `e2b` running locally through Ollama ([13](13-choosing-models.md)), while a game was using most of the GPU. Other models will differ; repeat this check for whichever model you use.

| Result | What to do about it |
| --- | --- |
| Clearly critical and clearly supportive posts were labeled correctly. The off-topic post never reached the model. | The pipeline works. |
| "Oh sure, Schumer is a master strategist, just look at all those wins" was labeled **supportive**. | Sarcasm fools this model. Hand-check a sample that includes sarcastic posts before trusting any trend. |
| `confidence` was 1.0 on every post, including the wrong one. | The 0.6 cut in `check_confidence` filters nothing. Escalate on signals you can measure instead, as [14](14-escalating-labels.md) does. |
| `tone` was "angry" for almost everything and changed between runs. | Drop the field or measure it before using it. |
| Thinking on: about 38 seconds per post. Thinking off: about 10. | Roughly 2,000 to 8,000 labels a day in that state. Re-time with the GPU free, and label a sample rather than everything. |
| With thinking off, a neutral announcement was also labeled supportive. | Faster is less accurate. Compare both on your hand-checked sample. |

## Making it yours

- Replace `load_batch` with a query for posts that have no row in `labels` for the current `MODEL` and `PROMPT_VERSION`.
- For replies, fill `parent_text` from the `posts` table so the model sees what is being answered.
- Replace `persist` and `queue_review` with inserts.
- Change `PROMPT_VERSION` whenever you change `INSTRUCTION`.
- To settle easy posts cheaply and send hard ones to a stronger model, move to the tiered workflow in [14](14-escalating-labels.md).
- Posts sent to a cloud model leave this PC, and `uri` contains the author's DID. [14](14-escalating-labels.md) sends an index instead; see also [13](13-choosing-models.md).
- Keep the schema about the post. Do not add fields that ask whether the author is genuine; the model has no basis for that, and the project's first principle rules it out.

## Example solution

This is the code that was run on this PC. Read top to bottom, the blocks make one module.

<details>
<summary>Show example: step 1, what a label is</summary>

```python
import os, re
from typing import Literal
from pydantic import BaseModel, Field
from google.adk import Agent, Context, Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import Workflow, node, START
from google.genai import types

LEADERS = {"schumer": r"\bschumer\b", "jeffries": r"\bjeffries\b"}
PROMPT_VERSION = "stance-v1"
MODEL = os.environ["LABEL_MODEL_FAST"]   # e.g. gemini-flash-lite-latest; see 13

class Post(BaseModel):
    uri: str
    text: str
    parent_text: str | None = None

class PostLabel(BaseModel):
    uri: str
    leaders: list[Literal["schumer", "jeffries"]]
    stance: Literal["critical", "supportive", "neutral", "unclear"]
    tone: Literal["angry", "mocking", "measured", "other"]
    confidence: float = Field(ge=0, le=1)
```

</details>

<details>
<summary>Show example: step 2, the instruction</summary>

```python
INSTRUCTION = """You label one Bluesky post about US Democratic leaders.
Label only what the post says. Do not guess whether the author is sincere,
automated, or part of a campaign; that is not your job and you lack the evidence.
Criticism and support are equally ordinary. Apply the same care to both.
stance is toward the named leader, not toward the party or the topic.
If sarcasm or missing context makes the stance uncertain, answer "unclear"
with low confidence. Copy the uri unchanged."""
```

</details>

<details>
<summary>Show example: step 3, the classifier agent</summary>

```python
classify_post = Agent(
    name="classify_post",
    model=MODEL,
    instruction=INSTRUCTION,
    output_schema=PostLabel,
)
```

</details>

<details>
<summary>Show example: step 4, loading and prefiltering</summary>

```python
@node
def load_batch(ctx: Context) -> list[Post]:
    # Replace with: unlabeled posts from DuckDB for this model + prompt version.
    return [Post(**row) for row in ctx.state.get("batch", [])]

@node
def prefilter(ctx: Context, node_input: list[Post]) -> list[Post]:
    hits = [p for p in node_input
            if any(re.search(rx, p.text, re.I) for rx in LEADERS.values())]
    ctx.route = "classify" if hits else "skip"
    return hits
```

</details>

<details>
<summary>Show example: step 5, sure, unsure and the end nodes</summary>

```python
@node
def check_confidence(ctx: Context, node_input: list[PostLabel]) -> dict:
    sure = [l for l in node_input if l.confidence >= 0.6 and l.stance != "unclear"]
    unsure = [l for l in node_input if l not in sure]
    ctx.state["unsure"] = [l.model_dump() for l in unsure]
    ctx.route = ["persist", "review"] if unsure else "persist"
    return {"sure": [l.model_dump() for l in sure]}

@node
def persist(ctx: Context, node_input: dict) -> str:
    # Replace with an INSERT into labels(model=MODEL, prompt_version=PROMPT_VERSION).
    return f"persisted {len(node_input['sure'])}"

@node
def queue_review(ctx: Context, unsure: list[dict]) -> None:
    # Replace with an INSERT into a post-level review queue. Returns nothing:
    # a workflow may have only one terminal node that produces output.
    ctx.state["queued_for_review"] = len(unsure)

@node
def skip(ctx: Context) -> str:
    return "nothing to classify"
```

</details>

<details>
<summary>Show example: step 6, fanning out and wiring</summary>

```python
# Wrap once and reuse the same object in both chains; ADK rejects two nodes with one name.
classify = node(classify_post, parallel_worker=True, max_parallel_workers=2)

label_posts = Workflow(
    name="label_posts",
    edges=[
        (START, load_batch, prefilter, {"classify": classify, "skip": skip}),
        (classify, check_confidence, {"persist": persist, "review": queue_review}),
    ],
)
```

</details>

<details>
<summary>Show example: step 7, running a batch</summary>

```python
async def run_batch(batch: list[dict], session_id: str):
    runner = Runner(node=label_posts, session_service=InMemorySessionService(),
                    auto_create_session=True)
    start = types.Content(role="user", parts=[types.Part(text="run")])
    async for event in runner.run_async(user_id="pipeline", session_id=session_id,
                                        new_message=start,
                                        state_delta={"batch": batch}):
        if event.output is not None:
            print(event.node_info.path, event.output)
```

Try it:

```python
await run_batch([
    {"uri": "at://a/1", "text": "Schumer caved again. Every single time. He needs to go."},
    {"uri": "at://a/2", "text": "Lovely weather in Brooklyn today."},
    {"uri": "at://a/3", "text": "Honestly Jeffries handled that press conference well."},
], session_id="try-1")
```

</details>
