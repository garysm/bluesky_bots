# 18 Async Python

What `async def`, `await`, `async with` and `async for` mean, how `asyncio` runs them, and where each shows up in this project. Read it before [03 Live stream](03-stream.md).

Every snippet on this page was run with the `bsky` environment's Python on 2026-11-12, and the output shown is what it printed. They need nothing but the standard library, except exercise 3, which uses `websockets`.

Needs: nothing installed beyond Python. Run the snippets as scripts; [In a notebook](#in-a-notebook) explains what changes there.

Read alongside:

- [A conceptual overview of asyncio](https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html), the Python docs' own explanation of how it works underneath
- [Coroutines and tasks](https://docs.python.org/3/library/asyncio-task.html), the reference for almost everything below

## Why this project needs it

Most of what this project does is wait: for the next frame on a websocket, for a model to answer, for a web request to return. A program that waits by standing still can do one thing at a time. `asyncio` lets one thread wait for many things at once: while one piece of code is waiting, another runs.

It does not make computation faster. It helps only when the time goes on waiting for something outside the program.

| Page | Style | Why |
| --- | --- | --- |
| [01](01-setup.md), [12](12-agent.md) | async | `runner.run_debug(...)` is awaited. The tools you give an agent are ordinary functions. |
| [03](03-stream.md) | async | The whole consumer is one coroutine reading a websocket. |
| [04](04-backfill.md) | sync | One request after another, with a pause between them. Nothing else needs to run meanwhile. |
| [05](05-storage.md), [10](10-signals.md), [13](13-reports.md) | sync | DuckDB calls block until they finish, and they run in their own process. |
| [06](06-adk-workflows.md), [07](07-classify.md), [08](08-escalating-labels.md) | async | `runner.run_async(...)` is read with `async for`. The nodes you write are ordinary functions; ADK runs them. |
| [09](09-narratives.md) | sync | `litellm.embedding` and `litellm.completion` are blocking calls. |

## 1. A coroutine is a function that can pause

`async def` defines a coroutine function. Calling it does not run it. It hands you a coroutine object, a paused piece of work that runs only when something drives it.

```python
import asyncio

async def fetch(name, seconds):
    print("start", name)
    await asyncio.sleep(seconds)      # stands in for a network call
    print("done ", name)
    return name.upper()

print(asyncio.run(fetch("a", 1)))
```

```
start a
done  a
A
```

- `asyncio.run(...)` starts an event loop, runs one coroutine to the end, and returns its result. A script calls it once, at the bottom.
- `await` means "pause here until this is finished, and let other work run in the meantime". It is only allowed inside an `async def`.
- `asyncio.sleep` is the simplest thing you can wait for. The rest of this page uses `fetch` as a stand-in for real waiting.

If you call a coroutine function and forget the `await`, nothing happens, and Python tells you so when the program ends:

```
RuntimeWarning: coroutine 'fetch' was never awaited
```

That warning always means the same thing: a call is missing its `await`.

## 2. Waiting for several things at once

Awaiting two coroutines one after the other takes the sum of their times. Handing both to [`asyncio.gather`](https://docs.python.org/3/library/asyncio-task.html#asyncio.gather) runs them together.

```python
import time

async def main():
    t = time.perf_counter()
    await fetch("a", 1)
    await fetch("b", 1)
    print(f"one after the other: {time.perf_counter() - t:.1f}s")

    t = time.perf_counter()
    results = await asyncio.gather(fetch("a", 1), fetch("b", 1))
    print(f"together: {time.perf_counter() - t:.1f}s", results)

asyncio.run(main())
```

```
start a
done  a
start b
done  b
one after the other: 2.0s
start a
start b
done  a
done  b
together: 1.0s ['A', 'B']
```

Look at the order of the lines in the second half. `a` started, reached its `await`, and paused; only then did `b` start. There is one thread, and the loop switches between coroutines at `await` points and nowhere else. That is why you do not need locks around ordinary variables, and it is also the source of the most common mistake, which is next.

## 3. What blocks the loop

A call that waits without `await` stops everything, because the loop never gets control back.

```python
async def bad(name, seconds):
    print("start", name)
    time.sleep(seconds)               # blocks: nothing else can run
    print("done ", name)

async def main():
    t = time.perf_counter()
    await asyncio.gather(bad("a", 1), bad("b", 1))
    print(f"{time.perf_counter() - t:.1f}s")

asyncio.run(main())
```

```
start a
done  a
start b
done  b
2.0s
```

Two seconds, not one, and no interleaving. In this project the blocking calls to watch for are:

| Blocking call | Inside a coroutine, use |
| --- | --- |
| `time.sleep(n)` | `await asyncio.sleep(n)` |
| `httpx.get(...)`, `httpx.Client` | [`httpx.AsyncClient`](https://www.python-httpx.org/async/) |
| a DuckDB query, a model loading, a large file read | `await asyncio.to_thread(function, args...)`, which runs it in a worker thread |

Short blocking calls are fine. Appending one line to a file, as the consumer in [03](03-stream.md) does for each kept event, takes microseconds. The rule of thumb is that anything that could take longer than a few milliseconds should not block.

To find a blocking call, run with `asyncio.run(main(), debug=True)`. The loop then reports any step that held it for more than a tenth of a second:

```
Executing <Task finished name='Task-1' coro=<main() ...> took 0.301 seconds
```

More in [Developing with asyncio](https://docs.python.org/3/library/asyncio-dev.html).

## 4. `async for` and `async with`

These are the ordinary `for` and `with`, for things that have to wait.

**`async for`** loops over a source where getting the next item may involve waiting. You can write such a source yourself with `yield` inside an `async def`:

```python
async def ticker(n):
    for i in range(n):
        await asyncio.sleep(0.2)
        yield i

async def main():
    async for i in ticker(3):
        print(i)

asyncio.run(main())
```

```
0
1
2
```

The loop body runs once per item, and between items the coroutine is paused, so other work can run. You meet it twice in this project:

- `async for frame in ws:` in [03](03-stream.md). Each turn of the loop waits for the next websocket frame.
- `async for event in runner.run_async(...):` in [06](06-adk-workflows.md), [07](07-classify.md) and [08](08-escalating-labels.md). Each turn waits for the workflow's next event.

**`async with`** is a `with` block whose set-up and clean-up may wait. `async with websockets.connect(url) as ws:` waits for the connection handshake on the way in, and for the closing handshake on the way out, including when the block is left by an exception.

## 5. Tasks: starting work without waiting for it

`asyncio.create_task(coro)` schedules a coroutine to run and returns at once with a `Task`, a handle you can await or cancel later. A [`TaskGroup`](https://docs.python.org/3/library/asyncio-task.html#task-groups) starts several and waits for all of them at the end of its block:

```python
async def main():
    async with asyncio.TaskGroup() as tg:
        a = tg.create_task(fetch("a", 1))
        b = tg.create_task(fetch("b", 2))
    print(a.result(), b.result())

asyncio.run(main())
```

```
start a
start b
done  a
done  b
A B
```

- `gather` or `TaskGroup`? Both run things together. If one task in a `TaskGroup` fails, the others are cancelled and the error is raised; that is usually what you want. `gather` is handy when you just want a list of results in order.
- **Keep a reference to a task you create.** The loop holds tasks weakly, so a task nobody refers to can disappear before it finishes. Assign it to a variable or use a `TaskGroup`.

To limit how many run at once, wrap the work in a [`Semaphore`](https://docs.python.org/3/library/asyncio-sync.html#asyncio.Semaphore):

```python
async def limited(sem, name):
    async with sem:
        return await fetch(name, 1)

async def main():
    sem = asyncio.Semaphore(2)
    t = time.perf_counter()
    results = await asyncio.gather(*(limited(sem, n) for n in "abcd"))
    print(results, f"{time.perf_counter() - t:.1f}s")

asyncio.run(main())
```

```
start a
start b
done  a
done  b
start c
start d
done  c
done  d
['A', 'B', 'C', 'D'] 2.0s
```

Four one-second jobs, two at a time, two seconds. This is what `max_parallel_workers=2` does for you in [06](06-adk-workflows.md) and [07](07-classify.md): it keeps you from sending every post to the model at the same moment.

## 6. Timeouts and cancellation

[`asyncio.timeout`](https://docs.python.org/3/library/asyncio-task.html#timeouts) gives a block a time limit:

```python
async def main():
    try:
        async with asyncio.timeout(0.5):
            await fetch("slow", 5)
    except TimeoutError:
        print("gave up")

asyncio.run(main())
```

```
start slow
gave up
```

`done  slow` never printed. A timeout works by *cancelling* the coroutine: an `asyncio.CancelledError` is raised inside it, at the `await` where it was paused. The same thing happens when you call `task.cancel()`, and when you press Ctrl+C in a script. Two rules follow:

- **Clean up with `try`/`finally` or `with`,** so files and connections are closed whichever way the coroutine ends.

  ```python
  async def careful():
      try:
          await asyncio.sleep(5)
      finally:
          print("cleaning up")

  async def main():
      task = asyncio.create_task(careful())
      await asyncio.sleep(0.1)
      task.cancel()
      try:
          await task
      except asyncio.CancelledError:
          print("cancelled")

  asyncio.run(main())
  ```

  ```
  cleaning up
  cancelled
  ```

- **Do not swallow `CancelledError`.** It is not a subclass of `Exception`, so `except Exception:` lets it through, which is what you want. A bare `except:` or `except BaseException:` in a retry loop would catch it and the program could no longer be stopped. This is why the consumer in [03](03-stream.md) names the two errors it retries on and nothing broader.

## 7. Passing work between coroutines with a queue

An [`asyncio.Queue`](https://docs.python.org/3/library/asyncio-queue.html) connects a coroutine that produces items to one that uses them, so neither has to know about the other.

```python
async def reader(q):
    for i in range(5):
        await asyncio.sleep(0.1)      # stands in for a frame arriving
        await q.put(i)
    await q.put(None)                 # nothing more is coming

async def writer(q):
    while (item := await q.get()) is not None:
        print("wrote", item)

async def main():
    q = asyncio.Queue(maxsize=100)
    async with asyncio.TaskGroup() as tg:
        tg.create_task(reader(q))
        tg.create_task(writer(q))

asyncio.run(main())
```

```
wrote 0
wrote 1
wrote 2
wrote 3
wrote 4
```

`maxsize` matters. When the queue is full, `put` waits, which slows the reader down to the writer's pace instead of letting memory fill up. The consumer in [03](03-stream.md) does not need a queue, because its writing is quick. You would add one if handling an event ever became slow, for instance if it called a model.

## 8. Doing something every few seconds

A second task that loops and sleeps runs alongside the main work. This is the shape of "save the stream cursor every few seconds" from step 7 of [03](03-stream.md):

```python
async def every(seconds, fn):
    while True:
        await asyncio.sleep(seconds)
        fn()

async def main():
    state = {"cursor": 0}
    saver = asyncio.create_task(every(0.5, lambda: print("saved", state["cursor"])))
    for i in range(1, 13):            # stands in for the consumer
        await asyncio.sleep(0.1)
        state["cursor"] = i
    saver.cancel()

asyncio.run(main())
```

```
saved 4
saved 9
```

Your numbers may differ by one; the timing is not exact. The two coroutines share `state` without a lock, because only one of them runs at any moment and they swap only at an `await`.

## In a notebook

Jupyter already runs an event loop, so two things change:

- **Use `await` directly in a cell.** `await main()` works at the top level of a notebook cell ([IPython autoawait](https://ipython.readthedocs.io/en/stable/interactive/autoawait.html)).
- **Do not call `asyncio.run` in a cell.** It fails with `RuntimeError: asyncio.run() cannot be called from a running event loop`.

That is why the pages say `await runner.run_debug(...)` for notebooks and `asyncio.run(...)` for scripts. A long-running job such as the stream consumer belongs in a script either way: a kernel restart would stop it.

## What an error is telling you

| Message | Meaning |
| --- | --- |
| `RuntimeWarning: coroutine '...' was never awaited` | You called a coroutine function without `await`, so it never ran. |
| `SyntaxError: 'await' outside async function` | `await` is only allowed inside `async def` (or at the top level of a notebook cell). |
| `RuntimeError: asyncio.run() cannot be called from a running event loop` | You are already inside a loop: in a notebook, or inside another coroutine. Use `await`. |
| `TypeError: 'async_generator' object is not iterable` | You wrote `for` where `async for` is needed. The same goes for `with` and `async with`. |
| `Task was destroyed but it is pending!` | The program ended while a task was still running, or nothing kept a reference to it. |
| Everything freezes; Ctrl+C is slow to respond | Something is blocking the loop. See [section 3](#3-what-blocks-the-loop). |

## Exercises

Work each one out before opening the answer.

**1. Predict.** Without running it, say what this prints and roughly how long it takes. Then run it.

```python
async def main():
    t = time.perf_counter()
    await asyncio.gather(fetch("a", 1), bad("b", 1), fetch("c", 1))
    print(f"{time.perf_counter() - t:.1f}s")
```

<details>
<summary>Show example</summary>

`a` starts and pauses at its `await`. `b` starts and blocks the whole loop for a second in `time.sleep`, so it prints `start b` and `done  b` back to back. Only then does `c` start. By now `a`'s second is already up, so `a` finishes straight away, and `c` finishes a second after it started. About two seconds in all:

```
start a
start b
done  b
start c
done  a
done  c
2.0s
```

Replacing `time.sleep(seconds)` in `bad` with `await asyncio.sleep(seconds)`, or calling it as `await asyncio.to_thread(time.sleep, seconds)`, brings the total back to one second.

</details>

**2. Limit the work.** Write a `main` that computes the squares of 0 to 9, where each one takes half a second of waiting, running at most three at a time. It should print the ten results in order and take about two seconds.

<details>
<summary>Show example</summary>

```python
async def main():
    sem = asyncio.Semaphore(3)

    async def one(i):
        async with sem:
            await asyncio.sleep(0.5)
            return i * i

    t = time.perf_counter()
    print(await asyncio.gather(*(one(i) for i in range(10))), f"{time.perf_counter() - t:.1f}s")

asyncio.run(main())
```

```
[0, 1, 4, 9, 16, 25, 36, 49, 64, 81] 2.0s
```

Ten jobs in groups of three is four rounds of half a second. `gather` returns results in the order the coroutines were passed in, not the order they finished.

</details>

**3. Count the stream.** Write `count_events(seconds)`, which connects to Jetstream, counts frames for that many seconds, and returns the count. The address and subprotocol are in step 1 of [03](03-stream.md). There are two `async with` blocks to nest; decide which goes outside.

<details>
<summary>Show example</summary>

```python
import asyncio
import websockets

URL = ("wss://jetstream.us-east.bsky.network/xrpc/network.bsky.jetstream.subscribeEvents"
       "?collections=app.bsky.feed.post&kinds=commit")

async def count_events(seconds):
    n = 0
    try:
        async with asyncio.timeout(seconds):
            async with websockets.connect(URL, subprotocols=["xrpc.v1.json"]) as ws:
                async for frame in ws:
                    n += 1
    except TimeoutError:
        pass
    return n

print(asyncio.run(count_events(5)))
```

The timeout goes outside, so that it also covers connecting. When it fires, the `async for` is cancelled, the inner `async with` closes the websocket on the way out, and the `TimeoutError` is caught at the top.

</details>

## Further reading

- [asyncio](https://docs.python.org/3/library/asyncio.html), the library's front page in the Python docs
- [Coroutines and tasks](https://docs.python.org/3/library/asyncio-task.html): `gather`, `TaskGroup`, `timeout`, `to_thread`, cancellation
- [Queues](https://docs.python.org/3/library/asyncio-queue.html) and [synchronization primitives](https://docs.python.org/3/library/asyncio-sync.html)
- [Developing with asyncio](https://docs.python.org/3/library/asyncio-dev.html): debug mode and the usual mistakes
- [websockets: asyncio client](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html), the library behind [03](03-stream.md)
- [httpx: async support](https://www.python-httpx.org/async/), if you ever make [04](04-backfill.md) concurrent
