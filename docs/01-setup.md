# 01 Setup

What is installed on this PC, how the project is laid out, where settings live, and a first model call.

## What is where

| Item | Location |
| --- | --- |
| conda | `E:\miniconda3` (not on PATH; use "Anaconda Prompt (miniconda3)") |
| Environment | `bsky`, Python 3.14, in `C:\Users\garys\.conda\envs\bsky`; Jupyter kernel "Python (bsky)" |
| This project's package | `bluesky_bots/` in the project root, installed into `bsky` in editable mode |
| Topic files | `topics/` in the project root ([02](02-topics.md)) |
| Project settings | `.env` in the project root: model names, API keys, storage location |
| Data | `data/` in the project root unless `.env` says otherwise; not tracked by git |

## Project layout

```
bluesky_bots/            the package: one folder per service
  config.py              every path and setting, read from .env
  aturi.py, privacy.py   small shared helpers
  topics/  stream/  backfill/  storage/  classify/
  narratives/  signals/  review/  agent/  reports/
topics/                  one YAML file per topic
tests/                   each page's checks, runnable with pytest
docs/                    these pages
data/                    landing files, the database, trained classifiers (created as needed)
out/                     charts and exports (created as needed)
```

Each service folder has the same shape: an `__init__.py` listing what the service offers, one or more modules holding its functions, and a `__main__.py` that makes it a command. [README](README.md) has the map of what each service does.

"Editable mode" means Python imports the package straight from this folder, so a change you save is used the next time you run something. It was installed with:

```bash
pip install -e .
```

That was run on this PC on 2026-11-13. You only need to repeat it on another machine.

## Settings in `.env`

`bluesky_bots/config.py` reads `.env` once and is the only place that does. Every key is optional except the model names and keys for the models you use.

| Key | Default | What it sets |
| --- | --- | --- |
| `LABEL_MODEL_FAST`, `LABEL_MODEL_STRONG`, `ANALYST_MODEL`, `NAMING_MODEL`, `EMBED_MODEL` | none | The model for each job ([16](16-choosing-models.md)) |
| `GOOGLE_API_KEY` and other provider keys | none | Credentials for the providers you use |
| `STORAGE_URL` | `duckdb:///data/narrative.duckdb` | Which storage backend, and where ([17](17-choosing-storage.md)) |
| `DATA_DIR` | `data` | Where landing files, the database and trained classifiers go |
| `TOPICS_DIR` | `topics` | Where topic files are read from |
| `OUT_DIR` | `out` | Where charts and exports are written |
| `ANON_SALT` | none | The secret behind anonymous account IDs ([13](13-reports.md)) |

Relative paths are taken from the project root. To keep data on another drive, give an absolute path, for example `DATA_DIR=E:/bluesky-data`.

Until you have built the DuckDB backend on [05](05-storage.md), add this line so the finished SQLite backend is used:

```bash
STORAGE_URL=sqlite:///data/narrative.sqlite
```

## Choose a model

Every page that uses a model reads its name from `.env`, so you can switch between a cloud API and a model running on this PC without changing code. [16](16-choosing-models.md) lists the keys, suggests models for each job, and covers local runtimes.

The quickest start is a cloud model. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) and add to `.env`:

```bash
GOOGLE_API_KEY=your-key-here
LABEL_MODEL_FAST=gemini-flash-lite-latest
```

## First model call

```python
import bluesky_bots                      # first: loads .env
from bluesky_bots import config

from google.adk import Agent
from google.adk.runners import InMemoryRunner

hello = Agent(name="hello", model=config.model("LABEL_MODEL_FAST"),
              instruction="Answer in one sentence.")
runner = InMemoryRunner(agent=hello, app_name="hello")
await runner.run_debug("Say hello and name the model family you belong to.")
```

In a plain script, wrap the last two lines in an `async def main()` and call `asyncio.run(main())`. [18 Async Python](18-async-python.md) explains why a notebook and a script differ here.

ADK picks the right connector from the model name: `gemini-*` goes to the Gemini API, and `provider/model` names such as `anthropic/...` or `ollama_chat/...` go through LiteLLM ([16](16-choosing-models.md)).

This call was run on 2026-11-11 with `os.environ[...]` in place of `config.model(...)`; it has not been repeated in this form.

## Check your work with the tests

`tests/` holds each page's checks. Run one file while you work on its page, or all of them:

```bash
pytest tests/test_topics.py
```

```bash
pytest
```

A test that fails with `NotImplementedError: ... is a task in docs/...` is telling you which page builds that function. On 2026-11-13, with nothing yet written, 20 tests passed (the finished SQLite backend and the topic file format) and the rest failed that way.

## Good to know

- **Import `bluesky_bots` first.** It loads `.env`. Without it the model name, API key and local addresses are missing: a missing key fails at once, and a local runtime call that hangs and then fails to connect usually means the address was not read.
- **NumPy crashes on this PC unless one setting is made first.** Found on 2026-11-13: in the `bsky` environment, any sizeable matrix operation (`a @ a` on a 300 by 300 array, `np.linalg.solve`, scikit-learn's default `LogisticRegression`) ends Python on the spot with no error message. The cause is the threaded part of Intel's math library (MKL 2026.1, alongside `llvm-openmp` 23.1.5). With MKL in single-threaded mode everything works, so `config.py` sets `MKL_THREADING_LAYER=SEQUENTIAL` unless you have set it yourself. It only works if it is set before NumPy is first imported, which is the other reason `import bluesky_bots` goes first. If a notebook dies without a traceback during clustering or training, this is the first thing to check.
- **A cleaner fix, not yet done:** switch the environment from MKL to OpenBLAS with `conda install -n bsky "libblas=*=*openblas"`, then remove the line from `config.py`. It replaces several packages, and drive C: is short of space, so it is left for you to decide.
- **Don't trust a small model's general knowledge.** Asked what the AT Protocol is, Gemma 4 `e2b` described modem commands. Only ask models about text you give them.
- **Posts sent to a cloud model leave this PC.** See "When text leaves the PC" in [16](16-choosing-models.md).
- **Drive C: is nearly full** (3.4 GB free on 2026-11-13; E: has 562 GB). Keep data and local models on E:. The project folder is on E: already, so the default `data/` is fine.

## Rebuilding the environment elsewhere

`environment.yml` in the project root lists everything, including pytest and this package. In an Anaconda Prompt, from the project root:

```bash
conda env create -f environment.yml
```

```bash
conda activate bsky
```

```bash
python -m ipykernel install --user --name bsky --display-name "Python (bsky)"
```

Then copy `.env` (without sharing its keys) and, if you use a local runtime, install it and its models as described in [16](16-choosing-models.md).

`google-adk` must be installed with the `[extensions]` extra (as in `environment.yml`), or LiteLLM is missing and `provider/model` names fail to load.
