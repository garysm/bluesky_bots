# Build notes

Step-by-step guides for building the Bluesky narrative research tool. Each page covers one piece and stands on its own.

Pages 02 to 10 and 14 are written to be worked through, not copied. Each step explains one idea, sets a task, and says how to check your work. The finished code is at the bottom of the page under "Example solution", collapsed behind a "Show example" label, so you can try first and compare afterwards. That code was run on this PC on 2026-11-11, unless the page says otherwise (12 to 14 have not been run yet). Where Bluesky's own documentation covers a topic, the page links to it and builds on it.

## Pages

| Page | What it gives you |
| --- | --- |
| [01 Setup](01-setup.md) | What is installed where, choosing a model, a first model call |
| [02 Live stream](02-live-stream.md) | Listen to Bluesky in real time and keep the relevant posts |
| [03 Backfill](03-backfill.md) | Fetch history: an account's posts, search results, profiles |
| [04 Storage](04-storage.md) | DuckDB tables, loading, deletes, reading from a notebook |
| [05 ADK workflows](05-adk-workflows.md) | The workflow API in one small example, no model needed |
| [06 Labeling posts](06-gemma-labels.md) | A workflow that labels stance toward a leader |
| [07 An agent with tools](07-gemma-tools.md) | An agent that queries your database to draft text |
| [08 Narratives](08-narratives.md) | Embed posts, cluster them, name the clusters |
| [09 Coordination signals](09-signals.md) | Behavioral flags in SQL and Python |
| [10 Reports](10-reports.md) | The with/without chart and a safe export |
| [11 Guardrails](11-guardrails.md) | How the project's principles show up in code |
| [12 Google Cloud later](12-google-cloud.md) | Where each local piece would move |
| [13 Choosing models](13-choosing-models.md) | Where each model is set, suggested models per job, local runtimes, resources |
| [14 Escalating labels](14-escalating-labels.md) | Cheap classifier first, stronger models only for the posts it is unsure about |
| [15 Async Python](15-async-python.md) | `async`, `await` and `asyncio`, with the patterns the other pages use |

## Where to start

If `async def` and `await` are new to you, read [15](15-async-python.md) first. Pages 02 and 05 to 07 rely on it.

Pages 02 to 04 get data flowing and need no model. Start capture early: deleted posts cannot be recovered later.

Pages 05 to 07 are the ADK and model part. Page 05 runs without a model, so it is the quickest way to learn the workflow API. Pick models with [13](13-choosing-models.md) before page 06, and read [14](14-escalating-labels.md) once single-model labeling works.

Pages 08 to 10 are analysis and only make sense once there is data.

## Every session

If `.env` points at a local runtime, start it and leave its terminal open ([13](13-choosing-models.md) has the command for Ollama on this PC). Cloud models need nothing started.

In VS Code or JupyterLab choose the kernel "Python (bsky)". In a terminal, open "Anaconda Prompt (miniconda3)" and run:

```bash
conda activate bsky
```

Begin every notebook or script that uses a model with:

```python
from dotenv import load_dotenv
load_dotenv()
```

## Stack

- Bluesky [Jetstream](https://bsky.network/docs/jetstream) v2 for live data, the AppView [HTTP API](https://endpoints.bsky.app) for history
- DuckDB for storage
- Google ADK 2.7.1 for workflows and agents
- Any chat or embedding model, named in `.env` and reached through ADK and LiteLLM; suggestions in [13](13-choosing-models.md)
- scikit-learn for the light first-tier classifier ([14](14-escalating-labels.md))
- Jupyter for analysis and reports
