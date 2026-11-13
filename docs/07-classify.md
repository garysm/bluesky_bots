# 07 Classify

Build a workflow that takes a topic's unlabeled posts, asks a model to label each one with the scheme the topic file defines, stores the labels, and queues the posts the model could not settle for a person.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/classify/` (`scheme.py` and `workflow.py` on this page) |
| Reads | a topic's label scheme; the topic's unlabeled posts, from storage |
| Writes | `labels`; the review queue |
| Command | `python -m bluesky_bots.classify label --topic NAME` |
| Must not know | any label value, entity or subject. They all come from the topic file. |

Needs: `LABEL_MODEL_FAST` in `.env` ([16](16-choosing-models.md)) to run it for real; the tests need no model. Do [06](06-adk-workflows.md) first; this page uses its workflow API without explaining it again. This page uses one model; [08](08-escalating-labels.md) builds on it with cheaper and stronger tiers.

Read first:

- [Simple agents](https://google.github.io/adk-docs/agents/llm-agents/) in the ADK docs: `Agent`, instructions and `output_schema`
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/), and [`create_model`](https://docs.pydantic.dev/latest/concepts/models/#dynamic-model-creation) for building one at run time
- [14 Guardrails](14-guardrails.md). Two of its rules shape the instruction in step 2.

## What you are building

```
START -> load_batch -> classify (once per post) -> check -> persist
                    -> skip                             -> queue_review
```

You are done when `pytest tests/test_classify.py -k "not tier and not train"` passes, and a run on your own data labels a handful of posts you can check by hand.

Which posts get labeled is not decided here. `load_batch` asks storage for the topic's posts that have no label yet under the current scheme version, and membership in the topic was decided on [02](02-topics.md). There is no keyword filter in this workflow.

## Step 1: Say what a label is, from the topic

**Concept.** A model asked for a "stance" in free text will answer with a paragraph, in different words each time. Ask instead for a fixed structure with a closed set of allowed values, and you get something you can count. In ADK you describe the structure as a Pydantic model and the framework holds the model's answer to it.

In a single-purpose tool you would write that class by hand. Here the allowed values come from a topic file, so the class is built when the workflow is: one field per dimension, restricted to that dimension's values.

Two structures are needed:

- `Item`, what a model *sees*: a position number `i`, the `text`, and the text of the post it replies to. It is already in `scheme.py`. It has no `uri` on purpose. A URI contains the author's DID, and with a cloud model whatever you send leaves this PC. The posts stay in the workflow's state, and the number is matched back to the URI at the very end.
- The label, what a model *returns*: `i` copied back, `entities` (which of the topic's entities the post is about; only when the topic has entities), and one field per dimension.

**Your task.** In `bluesky_bots/classify/scheme.py`, write `build_label_model(topic)`. It returns a Pydantic model class.

**Hints.**

- `typing.Literal["a", "b"]` restricts a field to those values. `Literal[tuple(values)]` does the same from a list you have at run time.
- `create_model("Label", **fields)`, where each field is a `(type, default)` pair and `...` as the default means "required".
- A list field restricted to the entity names is `list[Literal[...]]`.
- Keep every field about the *post*. There is no field asking whether the author is genuine or automated. The model has no evidence for that, and the project's first principle rules it out.
- Why does the label repeat `i`? Think about how you will match answers to posts when several are classified at the same time.

**Check.** `pytest tests/test_classify.py -k label_model`. A value that is not in the topic file is rejected before it can reach the database.

## Step 2: The instruction

**Concept.** The instruction is where the project's principles become behavior. Whatever you leave unsaid, the model fills in by itself.

It has three parts, joined in this order:

1. **The base rules**, `BASE_INSTRUCTION` in `scheme.py`: label what the post says and nothing about who wrote it; treat every allowed value as equally ordinary; say "cannot tell" when sarcasm or missing context makes it uncertain; copy `i` unchanged. They are in code, not in the topic file, so that no topic can leave them out.
2. **The topic's own wording**, `labels.instruction` in the topic file. This is where you say what the dimension means. In the example topic: stance is toward the *named leader*, not toward the party or the subject. ("I'm furious they're attacking Jeffries" is angry and supportive.)
3. **The allowed answers**, generated from the scheme: the entity names, and each dimension with its values and its "cannot tell" value.

**Your task.** Write `build_instruction(topic)`. Then reread the `instruction` in your own topic file from [02](02-topics.md) with fresh eyes.

**Hints.**

- Short and literal beats long and clever. A small model follows a ten-line instruction better than a page.
- Change `labels.version` in the topic file every time you change its wording, a dimension or a value. Labels are stored under the version, so labels made with different wordings are never mixed.

**Check.** `pytest tests/test_classify.py -k instruction`. Print `build_instruction(get_topic("dem-leadership"))` and read it as if you were the model.

## Step 3: From a label to rows

**Concept.** The `labels` table is long: one row per post, topic, scheme version, model, **target** and **dimension**. A topic with two dimensions gives two rows per post; a post about two entities gives a row for each. `target` is the entity's name, or `''` when the label is about the post as a whole. That shape is what lets any scheme be stored without changing a table.

**Your task.** Write two small functions:

- `is_unsure(topic, label)`: true when any dimension of a label holds that dimension's `unsure` value.
- `label_rows(topic, uri, label, model, tier, confidence=None)`: the rows to store for one post's label.

`label` is the model's answer as a dict, for example `{"i": 0, "entities": ["schumer"], "stance": "critical"}`.

**Hints.**

- The targets are `label["entities"]` when it names any, otherwise `[""]`.
- `tier` says which step produced the row. A single model is tier 1. [08](08-escalating-labels.md) uses 0 and 2 as well.

**Check.** `pytest tests/test_classify.py -k "label_rows or two_dimensions"`

## Step 4: The storage methods this service needs

**Your task.** In `DuckDBStore` ([05](05-storage.md)), write:

- `unlabeled_posts(topic, scheme_version, model=None, limit=None)`: posts in the topic with no label under this scheme version, from that model or from any
- `save_labels(rows)`: store label rows; a row with the same key replaces the old one

Compare with the same methods in `sqlite_store.py`.

**Hints.**

- "With no label" is `NOT EXISTS (SELECT 1 FROM labels ...)` added to the query you wrote for `posts_in_topic`.
- Replacing on conflict is `ON CONFLICT (key columns) DO UPDATE SET value = excluded.value, ...`. `excluded` is the row that was refused.
- A row may leave out `target` and `labeled_at`; fill in `''` and now.
- The `labels_final` view in `views.py` keeps, for each post, topic, scheme version, target and dimension, the row from the highest tier. Read it now: [`QUALIFY`](https://duckdb.org/docs/stable/sql/query_syntax/qualify) filters on a window function without a subquery. Charts and the agent read that view, so a post is counted once however many models labeled it.

**Check.** `pytest tests/test_store_contract.py -m page07 -k duckdb`

## Step 5: The workflow

**Concept.** The workflow is built by a function, `build_workflow(topic, store, model=None, labeler=None)`, because its nodes need the topic and the store. Nodes defined inside the function can use both.

| Node | Does |
| --- | --- |
| `load_batch` | asks the store for unlabeled posts, keeps them in `ctx.state["posts"]`, and returns one `Item` per post. Routes to `classify`, or to `skip` when there is nothing to do. |
| `classify` | the labeler, wrapped as a parallel worker so it runs once per item ([06](06-adk-workflows.md) step 5) |
| `check` | turns the answers into dicts, puts the unsure ones in `ctx.state["unsure"]`, and routes to `persist`, plus `review` when any are unsure |
| `persist` | turns each `i` back into a URI, builds the rows and saves them |
| `queue_review` | puts the unsure posts on the review queue ([11](11-review.md)) |
| `skip` | says there was nothing to classify |

The labeler is normally an `Agent`: a model plus your instruction, with `output_schema` set to your label class so its answer is parsed instead of coming back as text. `labeler` is a parameter so that a test can pass a plain function in its place. That is how this page's tests check the routing, the storage and what the model is sent, without a model.

**Your task.** In `bluesky_bots/classify/workflow.py`, write `build_workflow`.

**Hints.**

- Wrap the labeler **once** with `node(..., name="classify", parallel_worker=True, max_parallel_workers=...)` and use that same object in both chains. Wrapping twice raises "Duplicate node names".
- `max_parallel_workers` is your politeness setting for a paid API, and your memory limit for a local model.
- State has to hold plain data. Store the posts as dicts, and `model_dump()` each answer.
- A type hint such as `node_input: list[Label]` on `check`, using the class you built, turns the worker's dicts back into objects.
- Assigning a *list* to `ctx.route` fires several branches. Only one end node may return a value, so `queue_review` returns `None`.
- A parameter named `unsure` is filled from `ctx.state["unsure"]`.
- Every label is saved, including the unsure ones. That records what the model answered, and it keeps the post from being sent again on the next run.

**Check.** `pytest tests/test_classify.py -k workflow`. Look at what the test asserts about `seen`, the list of everything the stand-in labeler was sent: no `at://`, no `did:`, and no post from outside the topic.

## Step 6: Run a batch

**Your task.** Write `run_workflow(workflow, session_id, limit=None, verbose=False)`, modeled on `run` from [06](06-adk-workflows.md), with `limit` in the starting state. It returns the message from the workflow's last node. Then label a few posts for real:

```bash
python -m bluesky_bots.classify label --topic dem-leadership --limit 5 --verbose
```

**Check.**

- The printed lines show each node's output in order: the items, one label per item, the checked labels, then `saved N label rows for M posts`.
- Look at the items line. That list is what the model was sent.
- Running it again labels the next five. When none are left it says `nothing to classify`.
- Find a sarcastic post in your data, such as "Oh sure, Schumer is a master strategist, just look at all those wins", and see what your model does with it. Compare with "What a first run showed" below.

## Turning thinking off

Many models reason step by step before answering, which is slow and, on paid APIs, costs output tokens. For a `provider/model` name, build the agent with:

```python
model=LiteLlm(model=name, reasoning_effort="none"),   # from google.adk.models.lite_llm import LiteLlm
```

Native Gemini names use `generate_content_config` instead; [16](16-choosing-models.md) shows both.

## What a first run showed

Five sample posts on 2026-11-11, with an earlier version of this workflow that had the stance scheme written into the code and also asked the model for a `tone` and a `confidence`. The model was Gemma 4 `e2b` running locally through Ollama ([16](16-choosing-models.md)), while a game was using most of the GPU. Other models will differ; repeat this check for whichever model you use.

| Result | What to do about it |
| --- | --- |
| Clearly critical and clearly supportive posts were labeled correctly. | The pipeline works. |
| "Oh sure, Schumer is a master strategist, just look at all those wins" was labeled **supportive**. | Sarcasm fools this model. Hand-check a sample that includes sarcastic posts before trusting any trend. |
| `confidence` was 1.0 on every post, including the wrong one. | A model's stated confidence filters nothing. That is why the label has no such field now; escalate on things you can measure, as [08](08-escalating-labels.md) does. |
| `tone` was "angry" for almost everything and changed between runs. | Measure a dimension before you rely on it. If you add one to a topic, hand-check it first. |
| Thinking on: about 38 seconds per post. Thinking off: about 10. | Roughly 2,000 to 8,000 labels a day in that state. Re-time with the GPU free, and label a sample rather than everything. |
| With thinking off, a neutral announcement was also labeled supportive. | Faster is less accurate. Compare both on your hand-checked sample. |

## Good to know

- **Only text leaves the PC.** A model receives `Item` (a number, the post text, the parent text), never the `uri`. The number is matched back in `persist`.
- **The base rules are in code.** A topic file adds to `BASE_INSTRUCTION`; it cannot replace it.
- **Change `labels.version` whenever the scheme changes.** Under a new version every post in the topic counts as unlabeled again.
- **Labels record what produced them**: the model string, the scheme version and the tier. Use pinned model names for anything you will publish ([16](16-choosing-models.md)).
- **Use a new session per run.** The command makes one from the topic name and the time. A reused session lets an earlier run leak into a later model call.
- **A new dimension is a new measurement.** Before trusting it, label a sample by hand on [11](11-review.md) and compare.
- To settle easy posts cheaply and send hard ones to a stronger model, move to the tiered workflow in [08](08-escalating-labels.md).

## Example solution

`tests/test_classify.py` passes against this code (run on 2026-11-13), with a plain function standing in for the model. It has not yet been run with a real model in this form; the earlier fixed-scheme version was, on 2026-11-11.

<details>
<summary>Show example: steps 1 to 3, the scheme (bluesky_bots/classify/scheme.py)</summary>

```python
from typing import Literal

from pydantic import BaseModel, create_model

from ..topics import Topic


# Sent to the model before every topic's own instruction, so a topic file
# cannot leave these rules out. See docs/14-guardrails.md.
BASE_INSTRUCTION = """You label one Bluesky post.
Label only what the post says. Do not guess whether the author is sincere,
automated, or part of a campaign; that is not your job and you lack the evidence.
Every allowed value is equally ordinary. Apply the same care to each of them.
When sarcasm or missing context makes an answer uncertain, give the "cannot tell" value named below.
Copy i unchanged."""


class Item(BaseModel):
    """What a model sees of a post: a position number and text. No uri, so no DID leaves this PC."""
    i: int
    text: str
    parent_text: str | None = None


def build_label_model(topic: Topic) -> type[BaseModel]:
    """The Pydantic model a labeler must answer with, built from the topic's label scheme.

    Fields: `i` (the position number, copied back), `entities` (which of the
    topic's entities the post is about; only when the topic has entities),
    and one field per dimension, restricted to that dimension's values.
    """
    fields = {"i": (int, ...)}
    if topic.entities:
        fields["entities"] = (list[Literal[tuple(topic.entities)]], ...)
    for name, dim in topic.labels.dimensions.items():
        fields[name] = (Literal[tuple(dim.values)], ...)
    return create_model("Label", **fields)


def build_instruction(topic: Topic) -> str:
    """The full instruction for a labeler: the base rules, the topic's wording, then the allowed answers."""
    lines = [BASE_INSTRUCTION, "", topic.labels.instruction.strip(), ""]
    if topic.entities:
        lines.append("entities: every one of these the post is about, or an empty list: "
                     + ", ".join(topic.entities) + ".")
    for name, dim in topic.labels.dimensions.items():
        line = f"{name}: one of {', '.join(dim.values)}."
        if dim.unsure:
            line += f' The "cannot tell" value is {dim.unsure}.'
        lines.append(line)
    return "\n".join(lines)


def is_unsure(topic: Topic, label: dict) -> bool:
    """True when any dimension of a label holds that dimension's "cannot tell" value."""
    return any(dim.unsure is not None and label.get(name) == dim.unsure
               for name, dim in topic.labels.dimensions.items())


def label_rows(topic: Topic, uri: str, label: dict, model: str, tier: int,
               confidence: float | None = None) -> list[dict]:
    """The `labels` table rows for one post's label: one row per target and dimension.

    The targets are the entities the label names, or '' (the post as a
    whole) when it names none.
    """
    targets = label.get("entities") or [""]
    return [{"uri": uri, "topic": topic.name, "scheme_version": topic.labels.version, "model": model,
             "target": target, "dimension": name, "value": label[name],
             "confidence": confidence, "tier": tier}
            for target in targets for name in topic.labels.dimensions]
```

</details>

<details>
<summary>Show example: step 4, the storage methods (in DuckDBStore)</summary>

```python
class DuckDBStore:
    ...

    def unlabeled_posts(self, topic, scheme_version, model=None, limit=None) -> list[dict]:
        """Posts in a topic with no label under this scheme version (from `model`, or from any model)."""
        extra = """ AND NOT EXISTS (
            SELECT 1 FROM labels l
            WHERE l.uri = p.uri AND l.topic = t.topic AND l.scheme_version = ?"""
        params = [scheme_version]
        if model is not None:
            extra += " AND l.model = ?"
            params.append(model)
        return self._topic_posts(topic, extra + ")", params, limit)

    def save_labels(self, rows: Iterable[dict]) -> None:
        """Store label rows. A row with the same key replaces the old one."""
        now = now_utc()
        key = ", ".join(TABLES["labels"].key)
        self._insert("labels", ({"target": "", "labeled_at": now, **r} for r in rows),
                     on_conflict=f"({key}) DO UPDATE SET value = excluded.value, "
                                 "confidence = excluded.confidence, tier = excluded.tier, "
                                 "labeled_at = excluded.labeled_at")
```

</details>

<details>
<summary>Show example: steps 5 and 6, the workflow (bluesky_bots/classify/workflow.py)</summary>

```python
from google.adk import Agent, Context, Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START, Workflow, node
from google.genai import types

from .. import config
from ..topics import Topic
from .scheme import Item, build_instruction, build_label_model, is_unsure, label_rows


def build_workflow(topic: Topic, store, model: str | None = None, labeler=None,
                   max_workers: int = 2) -> Workflow:
    """The labeling workflow for one topic.

    model:   the name recorded with each label and, unless `labeler` is given,
             the model that does the labeling. Defaults to LABEL_MODEL_FAST.
    labeler: what labels one post. Left out, it is an Agent built from the
             topic's scheme. A test passes a plain function (ctx, node_input)
             that returns a label, so no model is called.
    """
    Label = build_label_model(topic)
    model = model or config.model("LABEL_MODEL_FAST")
    if labeler is None:
        labeler = Agent(name="classify_post", model=model, instruction=build_instruction(topic),
                        output_schema=Label)
    # Wrap once and use the same object in both chains; ADK rejects two nodes with one name.
    classify = node(labeler, name="classify", parallel_worker=True, max_parallel_workers=max_workers)

    @node
    def load_batch(ctx: Context) -> list[Item]:
        posts = store.unlabeled_posts(topic.name, topic.labels.version, model,
                                      limit=ctx.state.get("limit"))
        # The posts stay here. A model is sent a position number, never a uri.
        ctx.state["posts"] = [{"uri": p["uri"], "text": p["text"] or "", "parent_text": p["parent_text"]}
                              for p in posts]
        ctx.route = "classify" if posts else "skip"
        return [Item(i=i, text=p["text"], parent_text=p["parent_text"])
                for i, p in enumerate(ctx.state["posts"])]

    @node
    def check(ctx: Context, node_input: list[Label]) -> list[dict]:
        labels = [label.model_dump() for label in node_input]
        unsure = [label for label in labels if is_unsure(topic, label)]
        ctx.state["unsure"] = unsure
        ctx.route = ["persist", "review"] if unsure else "persist"
        return labels

    @node
    def persist(ctx: Context, node_input: list[dict]) -> str:
        posts = ctx.state["posts"]          # the position number turns back into a uri here
        rows = [row for label in node_input
                for row in label_rows(topic, posts[label["i"]]["uri"], label, model, tier=1)]
        store.save_labels(rows)
        return f"saved {len(rows)} label rows for {len(node_input)} posts"

    @node
    def queue_review(ctx: Context, unsure: list[dict]) -> None:
        # Returns nothing: only one end node of a run may produce output.
        posts = ctx.state["posts"]
        store.enqueue_review({"item_type": "post", "item_id": posts[label["i"]]["uri"],
                              "topic": topic.name, "reason": "the model could not tell"}
                             for label in unsure)

    @node
    def skip(ctx: Context) -> str:
        return "nothing to classify"

    return Workflow(
        name="label_posts",
        edges=[
            (START, load_batch, {"classify": classify, "skip": skip}),
            (classify, check, {"persist": persist, "review": queue_review}),
        ],
    )


async def run_workflow(workflow: Workflow, session_id: str, limit: int | None = None,
                       verbose: bool = False) -> str | None:
    """Run a labeling workflow once and return the message from its last node."""
    runner = Runner(node=workflow, session_service=InMemorySessionService(), auto_create_session=True)
    start = types.Content(role="user", parts=[types.Part(text="run")])
    result = None
    async for event in runner.run_async(user_id="pipeline", session_id=session_id,
                                        new_message=start, state_delta={"limit": limit}):
        if event.output is not None:
            if verbose:
                print(event.node_info.path, event.output)
            if isinstance(event.output, str):
                result = event.output
    return result
```

</details>
