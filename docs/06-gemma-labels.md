# 06 Labeling posts

A workflow that takes a batch of posts, drops the ones that mention no leader, asks a model for the stance of each remaining post, and separates unsure labels for review.

Needs: `load_dotenv()` first, `LABEL_MODEL_FAST` in `.env` ([13](13-choosing-models.md)). Read [05](05-adk-workflows.md) for the workflow API. This page uses one model; [14](14-escalating-labels.md) builds on it with cheaper and stronger tiers.

## The workflow

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

INSTRUCTION = """You label one Bluesky post about US Democratic leaders.
Label only what the post says. Do not guess whether the author is sincere,
automated, or part of a campaign; that is not your job and you lack the evidence.
Criticism and support are equally ordinary. Apply the same care to both.
stance is toward the named leader, not toward the party or the topic.
If sarcasm or missing context makes the stance uncertain, answer "unclear"
with low confidence. Copy the uri unchanged."""

classify_post = Agent(
    name="classify_post",
    model=MODEL,
    instruction=INSTRUCTION,
    output_schema=PostLabel,
)

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

# Wrap once and reuse the same object in both chains; ADK rejects two nodes with one name.
classify = node(classify_post, parallel_worker=True, max_parallel_workers=2)

label_posts = Workflow(
    name="label_posts",
    edges=[
        (START, load_batch, prefilter, {"classify": classify, "skip": skip}),
        (classify, check_confidence, {"persist": persist, "review": queue_review}),
    ],
)

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

The printed lines show each node's output. The labels arrive as one list at `label_posts@1/classify_post@1`, then `check_confidence`, then `persisted N`.

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
