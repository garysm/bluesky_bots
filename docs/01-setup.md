# 01 Setup

What is installed on this PC, where models are chosen, and a first model call.

## What is where

| Item | Location |
| --- | --- |
| conda | `E:\miniconda` (not on PATH; use "Anaconda Prompt (miniconda3)") |
| Environment | `narrative`, Python 3.13, Jupyter kernel "Python (narrative)" |
| Project settings | `.env` in the project root: model names, API keys, local runtime addresses |

## Choose a model

Every page that uses a model reads its name from `.env`, so you can switch between a cloud API and a model running on this PC without changing code. [13](13-choosing-models.md) lists the keys, suggests models for each job, and covers local runtimes, including the Ollama setup already on this PC.

The quickest start is a cloud model. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) and add to `.env`:

```bash
GOOGLE_API_KEY=your-key-here
LABEL_MODEL_FAST=gemini-flash-lite-latest
```

## First model call

```python
import os
from dotenv import load_dotenv
load_dotenv()

from google.adk import Agent
from google.adk.runners import InMemoryRunner

hello = Agent(name="hello", model=os.environ["LABEL_MODEL_FAST"],
              instruction="Answer in one sentence.")
runner = InMemoryRunner(agent=hello, app_name="hello")
await runner.run_debug("Say hello and name the model family you belong to.")
```

In a plain script, wrap the last two lines in an `async def main()` and call `asyncio.run(main())`.

ADK picks the right connector from the model name: `gemini-*` goes to the Gemini API, and `provider/model` names such as `anthropic/...` or `ollama_chat/...` go through LiteLLM ([13](13-choosing-models.md)).

## Good to know

- **Call `load_dotenv()` first.** Without it the model name, API key and local addresses are missing. A missing key fails at once; a local runtime call that hangs and then fails to connect usually means the address was not read.
- **Don't trust a small model's general knowledge.** Asked what the AT Protocol is, Gemma 4 `e2b` described modem commands. Only ask models about text you give them.
- **Posts sent to a cloud model leave this PC.** See "When text leaves the PC" in [13](13-choosing-models.md).
- **Drive C: is nearly full** (under 5 GB free). Keep data and local models on E:.

## Rebuilding the environment elsewhere

`environment.yml` in the project root lists everything. In an Anaconda Prompt:

```bash
conda env create -f environment.yml
```

```bash
conda activate narrative
```

```bash
python -m ipykernel install --user --name narrative
```

Then copy `.env` (without sharing its keys) and, if you use a local runtime, install it and its models as described in [13](13-choosing-models.md).

`google-adk` must be installed with the `[extensions]` extra (as in `environment.yml`), or LiteLLM is missing and `provider/model` names fail to load.
