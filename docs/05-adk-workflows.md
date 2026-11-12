# 05 ADK workflows

The ADK 2.x workflow API, learned by building one small workflow. It uses plain functions only, so it runs without any model.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed.

Needs: `google-adk` 2.7.1.

Read first:

- [Workflows](https://google.github.io/adk-docs/workflows/) in the ADK docs
- [State](https://google.github.io/adk-docs/sessions/state/) in the ADK docs: the shared values a run carries
- [15 Async Python](15-async-python.md), for the `async for` in step 4

## What you are building

A workflow that takes a piece of text, counts its words, and takes one of two branches depending on the count:

```
START -> count_words -> decide -> long_post
                               -> short_post
```

You are done when your output matches this, for a seven-word text and a two-word text:

```
demo@1/count_words@1 -> 7
demo@1/decide@1 -> 7
demo@1/long_post@1 -> long post: 7 words
demo@1/count_words@1 -> 2
demo@1/decide@1 -> 2
demo@1/short_post@1 -> short post: 2 words
```

Nothing runs until step 4. If you would rather see something work first, do step 1, then step 4 with the one-node workflow `edges=[(START, count_words)]`, and come back.

## Step 1: A node that reads state

**Concept.** A workflow is made of nodes. A node is an ordinary function with the `@node` decorator on it. Its first parameter is a `Context`, and through `ctx.state` it can read and write values that every node in the run shares. Whatever the function returns is the node's output.

**Your task.** Write a node `count_words` that reads the text from `ctx.state["text"]` and returns how many words it has.

**Hints.**

- `from google.adk import Context` and `from google.adk.workflow import node`.
- The return type hint is worth writing. It documents what the next node will receive.

## Step 2: Pass a value along, and choose a branch

**Concept.** Two more rules:

- **A parameter named `node_input` receives the previous node's return value.** That is how nodes hand work to each other without going through state.
- **A node chooses the next branch by assigning to `ctx.route`.** The value is a label of your choosing. Step 3 connects labels to nodes.

**Your task.** Write three nodes:

- `decide`, which receives the word count, sets the route to `"long"` if there are more than five words and `"short"` otherwise, and passes the count on unchanged.
- `long_post` and `short_post`, which each receive the count and return a sentence such as `long post: 7 words`.

**Hints.**

- A node that only routes still has to return what the next node needs.
- Any parameter with a name other than `node_input` is filled from state instead: `def f(ctx, unsure)` receives `ctx.state["unsure"]`. You will use that in [06](06-gemma-labels.md).

## Step 3: Wire the nodes together

**Concept.** A `Workflow` has a name and a list of `edges`. Each edge is a tuple, and a tuple is a chain that runs left to right, beginning at `START`. To branch, end the chain with a dict that maps each route label to the node it leads to.

**Your task.** Create a `Workflow` named `demo` whose single chain matches the diagram in "What you are building".

**Hints.**

- `from google.adk.workflow import Workflow, START`
- The keys of the routing dict must be exactly the labels `decide` assigns.

## Step 4: Run it

**Concept.** A `Runner` executes a workflow inside a *session*, which holds the run's state and history. Running is asynchronous: `runner.run_async(...)` gives you the run's events one at a time, and you read them with `async for`. An event with an `output` is a node that returned something, and `event.node_info.path` tells you which node.

| Piece | What to pass |
| --- | --- |
| `Runner(...)` | `node=` your workflow, `session_service=InMemorySessionService()`, `auto_create_session=True` |
| `runner.run_async(...)` | `user_id=`, `session_id=`, `new_message=`, and `state_delta=` for the starting state |
| `new_message` | A message is required even when no model will read it: `types.Content(role="user", parts=[types.Part(text="go")])`, with `types` from `google.genai` |

**Your task.** Write `async def run(text, session_id)` that runs the workflow with `text` in its starting state and prints each node's path and output. Run it on `"Schumer caved again and everyone knows it"` and on `"Nice weather"`.

**Hints.**

- The starting state is how `count_words` gets its text.
- Print only events whose `output` is not `None`.
- Use a different `session_id` for each run. A session keeps history, and reusing one lets an earlier run leak into a later one.
- In a script, `asyncio.run(run(...))`. In a notebook, `await run(...)`.

**Check.** The six lines under "What you are building".

## Step 5: Run one step per item

**Concept.** Labeling takes a list of posts and does the same thing to each. Wrapping a function or an agent with `node(..., parallel_worker=True)` gives you a node that receives a list, runs the wrapped thing once per item, and returns a list of results:

```python
classify = node(classify_post, parallel_worker=True, max_parallel_workers=2)
```

`max_parallel_workers` caps how many run at the same moment, which is the semaphore pattern from [15 Async Python](15-async-python.md). Pydantic models come out of a parallel worker as dicts; a type hint such as `node_input: list[PostLabel]` on the next node turns them back.

You will use this in [06](06-gemma-labels.md). There is nothing to build here yet.

## The rules in one table

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

## Good to know

- **One output at the end.** If two end nodes both return a value, ADK raises "multiple terminal nodes produced output". Have all but one return `None` and write to `ctx.state` instead.
- **Reuse the same node object.** Wrapping an agent with `node(...)` twice, or wrapping it in one chain and naming it bare in another, raises "Duplicate node names". Assign the wrapped node to a variable and use that everywhere.
- **Use a new `session_id` per run.** A session keeps history; reusing one lets earlier runs leak into later model calls.
- **In a notebook** call `await run(...)`. `asyncio.run` is for scripts.
- `Runner(node=...)` runs a workflow. `InMemoryRunner(agent=...)` with `run_debug` is the quick way to try a single agent; see [07](07-gemma-tools.md).

Next: [06](06-gemma-labels.md) puts a model-backed agent inside this kind of workflow, and [14](14-escalating-labels.md) chains several of them.

## Example solution

This is the code that was run on this PC. Read top to bottom, the blocks make one script.

<details>
<summary>Show example: step 1, a node that reads state</summary>

```python
import asyncio
from google.adk import Context, Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import Workflow, node, START
from google.genai import types

@node
def count_words(ctx: Context) -> int:
    return len(ctx.state["text"].split())
```

</details>

<details>
<summary>Show example: step 2, passing a value and choosing a branch</summary>

```python
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
```

</details>

<details>
<summary>Show example: step 3, wiring the nodes</summary>

```python
demo = Workflow(
    name="demo",
    edges=[(START, count_words, decide, {"long": long_post, "short": short_post})],
)
```

</details>

<details>
<summary>Show example: step 4, running it</summary>

```python
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

</details>
