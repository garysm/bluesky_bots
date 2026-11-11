# 01 Setup

What is installed on this PC, how to start it, and a first call to Gemma.

## What is where

| Item | Location |
| --- | --- |
| conda | `E:\miniconda` (not on PATH; use "Anaconda Prompt (miniconda3)") |
| Environment | `narrative`, Python 3.13, Jupyter kernel "Python (narrative)" |
| Ollama program | `E:\Ollama` |
| Ollama models | `E:\ollama_models`: `gemma4:e2b` (4.6 GB), `embeddinggemma` (621 MB) |
| Ollama address | `http://127.0.0.1:11435` |
| Project settings | `.env` in the project root |

Two user environment variables were set: `OLLAMA_HOST=127.0.0.1:11435` and `OLLAMA_MODELS=E:\ollama_models`.

## Start Ollama

```bash
E:\Ollama\ollama.exe serve
```

Leave that terminal open. The Ollama tray icon does not start the server on this PC; this command does.

## First Gemma call

```python
from dotenv import load_dotenv
load_dotenv()

from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner

hello = Agent(name="hello", model=LiteLlm(model="ollama_chat/gemma4:e2b"),
              instruction="Answer in one sentence.")
runner = InMemoryRunner(agent=hello, app_name="hello")
await runner.run_debug("Say hello and name the model family you belong to.")
```

In a plain script, wrap the last two lines in an `async def main()` and call `asyncio.run(main())`.

You should see Gemma's reasoning followed by a one-sentence answer. The first call took 85 seconds in testing because it loads the model; the next took 18.

## Good to know

- **Port 11435, not 11434.** Windows forwards port 11434 to a WSL address on this PC (an older Ollama-in-WSL setup), so the Windows Ollama uses 11435. `.env` tells the Python libraries. A call that hangs and then fails to connect means `load_dotenv()` was skipped.
- **To go back to the default port**, run `netsh interface portproxy delete v4tov4 listenport=11434 listenaddress=0.0.0.0` in an administrator prompt, delete the `OLLAMA_HOST` user variable, and change both lines in `.env` to 11434.
- **GPU memory.** `gemma4:e2b` fits the 6 GB GTX 1660 Ti only when little else is using it. Check with `nvidia-smi`. With a game running, Gemma fell back to the CPU at about 7 tokens per second.
- **Larger Gemma models** (`e4b`, `12b` and up) do not fit this GPU.
- **Thinking mode** is on by default and slow. Turn it off per agent with `LiteLlm(model=..., reasoning_effort="none")`; see [06](06-gemma-labels.md) for the trade-off.
- **The model's general knowledge is unreliable.** Asked what the AT Protocol is, it described modem commands. Only ask it about text you give it.
- **Drive C: is nearly full** (under 5 GB free). Keep data on E:.

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

Then install Ollama and pull the two models:

```bash
ollama pull gemma4:e2b
```

```bash
ollama pull embeddinggemma
```

`google-adk` must be installed with the `[extensions]` extra (as in `environment.yml`), or importing `LiteLlm` fails.
