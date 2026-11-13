# Build notes

Step-by-step guides for building a Bluesky conversation research tool: collect posts about any topic you define, label them, group them into narratives, and look at how accounts behave.

The tool is not tied to one subject. A **topic** is a small YAML file that says which posts belong to a conversation and how to label them. The study these notes started from (posts about two congressional leaders) is now one topic file, `topics/dem-leadership.yaml`, and it is the worked example on every page.

## How the project is put together

The code is one Python package, `bluesky_bots/`, split into ten **services**. Each service is a folder with a small set of functions, one job, and its own command. A service does not reach into another's internals; it calls the other's functions or reads what the other stored.

| Service | Its job | Command | Page |
| --- | --- | --- | --- |
| `topics` | Load topic files; decide whether a post belongs to a topic | `python -m bluesky_bots.topics` | [02](02-topics.md) |
| `stream` | Listen to Bluesky in real time and keep what a `keep` function accepts | `python -m bluesky_bots.stream` | [03](03-stream.md) |
| `backfill` | Fetch history: an account's posts, search results, profiles | `python -m bluesky_bots.backfill` | [04](04-backfill.md) |
| `storage` | Hold everything behind one interface; honor deletes | `python -m bluesky_bots.storage` | [05](05-storage.md) |
| `classify` | Label a topic's posts with the scheme its file defines | `python -m bluesky_bots.classify` | [07](07-classify.md), [08](08-escalating-labels.md) |
| `narratives` | Embed posts, cluster them, name the clusters | `python -m bluesky_bots.narratives` | [09](09-narratives.md) |
| `signals` | Behavioral flags from timing, account age and repeated text | `python -m bluesky_bots.signals` | [10](10-signals.md) |
| `review` | What is waiting for a person, and what they decided | `python -m bluesky_bots.review` | [11](11-review.md) |
| `agent` | An analyst agent that drafts text from aggregate numbers | `python -m bluesky_bots.agent` | [12](12-agent.md) |
| `reports` | The with-and-without chart, and the one door data leaves through | `python -m bluesky_bots.reports` | [13](13-reports.md) |

How data moves between them:

```
topics/*.yaml ──> topics ──────────────┐ (a keep function)
                                       v
Jetstream ──────────────────────────> stream ──> data/raw/*.jsonl ──┐
AppView ──> backfill ───────────────────────────────────────────────┤
                                                                    v
                                                                 storage
                                                                    │
        ┌──────────────┬──────────────┬──────────────┬──────────────┤
        v              v              v              v              v
     topics         classify      narratives      signals     reports, agent
   (membership)     (labels)   (vectors, groups)   (flags)     (read only)
                       │                             │
                       └────────────> review <───────┘
```

Three rules hold the design together:

- **Only a topic file names a subject.** No service has a keyword, an account or a label value written into it.
- **Everything that is saved goes through the storage service.** That is the one place a delete is honored, so a post its author removed disappears from every table at once. Storage is an interface with more than one implementation; [17](17-choosing-storage.md) covers the choice.
- **The stream never opens the database.** It writes plain files, and a separate step loads them. A stream that must not fall behind should not wait for anything.

### What is already written and what is yours to write

The package is a skeleton. These parts are finished, because they are contracts between services or plain glue:

- `config.py`, the topic file format (`topics/schema.py`), the storage interface (`storage/base.py`), a complete SQLite backend (`storage/sqlite_store.py`), and each service's command (`__main__.py`).

Everything else is a **stub**: a function with its signature and a docstring saying what it must do, and a body that raises `NotImplementedError` naming the page that sets it as a task. Each page's "Your task" tells you which file to open.

The tests in `tests/` are the pages' "Check" sections in runnable form. They fail until you write the code, then pass:

```bash
pytest tests/test_stream.py
```

They run offline: no model, no network. Where a page needs a model, the tests put a plain function in its place, so they check everything around the model.

## Pages

| Page | What it gives you |
| --- | --- |
| [01 Setup](01-setup.md) | What is installed where, the project layout, choosing a model, a first model call |
| [02 Topics](02-topics.md) | Write a topic file; match posts against it; record which posts belong to it |
| [03 Stream](03-stream.md) | Listen to Bluesky in real time and keep what your topics match |
| [04 Backfill](04-backfill.md) | Fetch history: an account's posts, search results, profiles |
| [05 Storage](05-storage.md) | The storage interface, turning events into rows, and building the DuckDB backend |
| [06 ADK workflows](06-adk-workflows.md) | The workflow API in one small example, no model needed |
| [07 Classify](07-classify.md) | A workflow that labels a topic's posts with one model |
| [08 Escalating labels](08-escalating-labels.md) | A cheap classifier first, stronger models only for the posts it is unsure about |
| [09 Narratives](09-narratives.md) | Embed posts, cluster them, name the clusters, keep IDs stable |
| [10 Signals](10-signals.md) | Behavioral flags in SQL and Python |
| [11 Review](11-review.md) | The review queue: evidence under anonymous IDs, a person's label as the final word |
| [12 Agent](12-agent.md) | An agent that queries aggregates to draft text |
| [13 Reports](13-reports.md) | The with/without chart and a safe export |
| [14 Guardrails](14-guardrails.md) | How the project's principles show up in code |
| [15 Google Cloud later](15-google-cloud.md) | Where each local piece would move |
| [16 Choosing models](16-choosing-models.md) | Where each model is set, suggested models per job, local runtimes |
| [17 Choosing storage](17-choosing-storage.md) | DuckDB in ten minutes, how big the data gets, and the options when it outgrows one file |
| [18 Async Python](18-async-python.md) | `async`, `await` and `asyncio`, with the patterns the other pages use |

Pages 02 to 13, except 06, each build one service. Their example code, collapsed at the bottom of each page, was assembled into a complete copy of the package and run against the tests on this PC on 2026-11-13. Each page says what else was run and what was not.

## Where to start

If `async def` and `await` are new to you, read [18](18-async-python.md) first. Pages 03 and 06 to 08 rely on it. If DuckDB is new to you, read the first section of [17](17-choosing-storage.md) before page 05.

Pages 02 to 05 get data flowing and need no model. Start capture early: deleted posts cannot be recovered later. Until page 05 is done, set `STORAGE_URL=sqlite:///data/narrative.sqlite` in `.env` and the finished SQLite backend stores everything.

Pages 06 to 08 are the ADK and model part. Page 06 runs without a model, so it is the quickest way to learn the workflow API. Pick models with [16](16-choosing-models.md) before page 07.

Pages 09 to 13 are analysis and only make sense once there is data.

## A day of the pipeline

Once the services are written, this is the order they run in. The stream runs all the time in its own terminal; the rest are short batch commands, run one at a time.

```bash
python -m bluesky_bots.stream
```

```bash
python -m bluesky_bots.storage load
```

```bash
python -m bluesky_bots.topics assign
```

```bash
python -m bluesky_bots.classify label --topic dem-leadership --tiered
```

```bash
python -m bluesky_bots.narratives --topic dem-leadership
```

```bash
python -m bluesky_bots.signals
```

```bash
python -m bluesky_bots.review queue
```

Every command takes `--help`.

## Every session

If `.env` points at a local model runtime, start it and leave its terminal open ([16](16-choosing-models.md) has the command for Ollama on this PC). Cloud models need nothing started.

In VS Code or JupyterLab choose the kernel "Python (bsky)". In a terminal, open "Anaconda Prompt (miniconda3)" and run:

```bash
conda activate bsky
```

Begin every notebook with this line, before importing NumPy, pandas or anything else:

```python
import bluesky_bots
```

It loads `.env` (model names, keys, storage location) and applies one setting that has to be in place before NumPy loads on this PC; [01](01-setup.md) explains it.

## Stack

- Bluesky [Jetstream](https://bsky.network/docs/jetstream) v2 for live data, the AppView [HTTP API](https://endpoints.bsky.app) for history
- DuckDB for storage and for all analysis queries; SQLite as a second storage backend ([17](17-choosing-storage.md))
- Google ADK 2.7.1 for workflows and agents
- Any chat or embedding model, named in `.env` and reached through ADK and LiteLLM; suggestions in [16](16-choosing-models.md)
- scikit-learn for the light first-tier classifier ([08](08-escalating-labels.md)) and for clustering
- pytest for the checks in `tests/`
- Jupyter for analysis and reports
