# Build notes

Short how-to pages for building the Bluesky narrative research tool. Each page covers one piece, stands on its own, and is built around code that was run on this PC on 2026-11-11. Copy what you need into your own modules and notebooks.

## Pages

| Page | What it gives you |
| --- | --- |
| [01 Setup](01-setup.md) | What is installed where, how to start Ollama, a first Gemma call |
| [02 Live stream](02-live-stream.md) | Listen to Bluesky in real time and keep the relevant posts |
| [03 Backfill](03-backfill.md) | Fetch history: an account's posts, search results, profiles |
| [04 Storage](04-storage.md) | DuckDB tables, loading, deletes, reading from a notebook |
| [05 ADK workflows](05-adk-workflows.md) | The workflow API in one small example, no model needed |
| [06 Labeling posts with Gemma](06-gemma-labels.md) | A workflow that labels stance toward a leader |
| [07 Gemma with tools](07-gemma-tools.md) | An agent that queries your database to draft text |
| [08 Narratives](08-narratives.md) | Embed posts, cluster them, name the clusters |
| [09 Coordination signals](09-signals.md) | Behavioral flags in SQL and Python |
| [10 Reports](10-reports.md) | The with/without chart and a safe export |
| [11 Guardrails](11-guardrails.md) | How the project's principles show up in code |
| [12 Google Cloud later](12-google-cloud.md) | Where each local piece would move |

## Where to start

Pages 02 to 04 get data flowing and need no model. Start capture early: deleted posts cannot be recovered later.

Pages 05 to 07 are the ADK and Gemma part. Page 05 runs without Ollama, so it is the quickest way to learn the workflow API.

Pages 08 to 10 are analysis and only make sense once there is data.

## Every session

Start the model server in a terminal and leave it open (only needed for pages 06 to 08):

```bash
E:\Ollama\ollama.exe serve
```

In VS Code or JupyterLab choose the kernel "Python (narrative)". In a terminal, open "Anaconda Prompt (miniconda3)" and run:

```bash
conda activate narrative
```

Begin every notebook or script that talks to Ollama with:

```python
from dotenv import load_dotenv
load_dotenv()
```

## Stack

- Bluesky Jetstream v2 for live data, the AppView HTTP API for history
- DuckDB for storage
- Google ADK 2.7.1 for workflows and agents
- Gemma 4 `e2b` and EmbeddingGemma through Ollama
- Jupyter for analysis and reports
