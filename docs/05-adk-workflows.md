# 05 ADK workflows

The ADK 2.x workflow API in one small example. It uses plain functions only, so it runs without Ollama.

Needs: `google-adk` 2.7.1.

## A workflow with a branch

```python
import asyncio
from google.adk import Context, Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import Workflow, node, START
from google.genai import types

@node
def count_words(ctx: Context) -> int:
    return len(ctx.state["text"].split())

@node
def decide(ctx: Context, node_input: int) -> int:
    ctx.route = "long" if node_input > 5 else "short"
    return node_input

@node
def long_post(ctx: Context, node_input: int) -> str:
    return f"long post: {node_input} words"

@node
def short_post(ctx: Context, node_input: int) -> str:
    return f"short post: {node_input} words"

demo = Workflow(
    name="demo",
    edges=[(START, count_words, decide, {"long": long_post, "short": short_post})],
)

async def run(text: str, session_id: str):
    runner = Runner(node=demo, session_service=InMemorySessionService(),
                    auto_create_session=True)
    start = types.Content(role="user", parts=[types.Part(text="go")])
    async for event in runner.run_async(user_id="me", session_id=session_id,
                                        new_message=start, state_delta={"text": text}):
        if event.output is not None:
            print(event.node_info.path, "->", event.output)

asyncio.run(run("Schumer caved again and everyone knows it", "demo-1"))   # notebook: await run(...)
asyncio.run(run("Nice weather", "demo-2"))
```

Output:

```
demo@1/count_words@1 -> 7
demo@1/decide@1 -> 7
demo@1/long_post@1 -> long post: 7 words
demo@1/count_words@1 -> 2
demo@1/decide@1 -> 2
demo@1/short_post@1 -> short post: 2 words
```

## How it works

| Piece | Rule |
| --- | --- |
| `@node` | Turns a function into a workflow step. An `Agent` can be a step too. |
| `edges` | Each tuple is a chain run left to right, beginning at `START`. |
| `{"long": a, "short": b}` | A routing map. The node before it chooses the branch. |
| `ctx.route = "long"` | How a node chooses. Assign a list to fire several branches. |
| `node_input` parameter | Receives the previous node's return value. |
| Any other parameter name | Read from session state, e.g. `def f(ctx, unsure)` gets `ctx.state["unsure"]`. |
| `ctx.state[...]` | Shared state for the run. Set initial values with `state_delta=` on `run_async`. |
| `event.output` | What a node returned. `event.node_info.path` says which node. |

## Running one step per item

```python
classify = node(classify_post, parallel_worker=True, max_parallel_workers=2)
```

A parallel worker receives a list, runs the wrapped function or agent once per item, and returns a list. Pydantic models come out as dicts; a type hint such as `node_input: list[PostLabel]` on the next node turns them back.

## Good to know

- **One output at the end.** If two end nodes both return a value, ADK raises "multiple terminal nodes produced output". Have all but one return `None` and write to `ctx.state` instead.
- **Reuse the same node object.** Wrapping an agent with `node(...)` twice, or wrapping it in one chain and naming it bare in another, raises "Duplicate node names". Assign the wrapped node to a variable and use that everywhere.
- **Use a new `session_id` per run.** A session keeps history; reusing one lets earlier runs leak into later model calls.
- **In a notebook** call `await run(...)`. `asyncio.run` is for scripts.
- `Runner(node=...)` runs a workflow. `InMemoryRunner(agent=...)` with `run_debug` is the quick way to try a single agent; see [07](07-gemma-tools.md).

Next: [06](06-gemma-labels.md) puts a Gemma agent inside this kind of workflow.
