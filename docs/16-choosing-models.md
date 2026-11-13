# 16 Choosing models

Where each model is set, what to pick for each job, and where to read more. The code on the other pages does not care which provider you use: it reads a model name from `.env`.

Nothing on this page has been run on this PC yet, except the notes under "Ollama on this PC". The library behavior described here was checked by reading the installed `google-adk` 2.7.1 and `litellm` 1.109.0 source.

## Where a model is set

Each job reads its model from one `.env` key. These names are suggestions; the pages use them, so keep them unless you also change the pages.

| Key | Used by | Form of the value |
| --- | --- | --- |
| `LABEL_MODEL_FAST` | first LLM tier when labeling ([07](07-classify.md), [08](08-escalating-labels.md)) | ADK model string |
| `LABEL_MODEL_STRONG` | escalation tier ([08](08-escalating-labels.md)) | ADK model string |
| `ANALYST_MODEL` | drafting agent ([12](12-agent.md)) | ADK model string |
| `NAMING_MODEL` | naming clusters ([09](09-narratives.md)) | LiteLLM model string |
| `EMBED_MODEL` | embeddings for clustering and the tier-0 classifier ([09](09-narratives.md), [08](08-escalating-labels.md)) | LiteLLM model string |

Add the credential for whichever provider you use, for example `GOOGLE_API_KEY=` for Gemini. Never paste a key into a notebook or a doc.

Example `.env` lines (values are illustrations, not recommendations of a specific version):

```bash
LABEL_MODEL_FAST=gemini-flash-lite-latest
LABEL_MODEL_STRONG=gemini-pro-latest
ANALYST_MODEL=gemini-flash-latest
NAMING_MODEL=gemini/gemini-flash-lite-latest
EMBED_MODEL=gemini/gemini-embedding-2
GOOGLE_API_KEY=your-key-here
```

### The two string forms

**ADK model strings** go straight into `Agent(model=...)`. ADK 2.7.1 picks the class from the name:

| Name looks like | ADK uses | Notes |
| --- | --- | --- |
| `gemini-*`, `gemma-4*` | its native Gemini class | Gemini API with `GOOGLE_API_KEY` (or `GEMINI_API_KEY`). `gemma-4*` is hosted Gemma 4 on the same API. |
| `provider/model`, e.g. `anthropic/claude-sonnet-5-5`, `openai/gpt-5-mini`, `ollama_chat/gemma4:e2b`, `lm_studio/...`, `hosted_vllm/...` | `LiteLlm` | Any provider LiteLLM knows. The provider's own key variable, e.g. `ANTHROPIC_API_KEY`. |
| bare `claude-*` | its native Claude class | Goes through **Vertex AI**, not an Anthropic API key. Use `anthropic/claude-...` for an API key. |
| bare `gpt-*` | an experimental OpenAI class | Prefer `openai/gpt-...` through LiteLLM. |

So this is all it takes:

```python
import os
from google.adk import Agent

agent = Agent(name="classify_post", model=os.environ["LABEL_MODEL_FAST"],
              instruction="...")
```

Wrap the name yourself only to pass extra settings:

```python
from google.adk.models.lite_llm import LiteLlm
model = LiteLlm(model=os.environ["LABEL_MODEL_FAST"], reasoning_effort="none")   # provider/model names only
```

**LiteLLM model strings** are for code that calls a model outside ADK, as [09](09-narratives.md) does with `litellm.completion` and `litellm.embedding`. These always carry a provider prefix, so Gemini is written `gemini/gemini-...` here.

### Turning thinking down

Thinking makes answers slower and more expensive; for one-word labels it is often not worth it. The setting depends on the class:

```python
# provider/model names (LiteLlm)
model = LiteLlm(model=name, reasoning_effort="none")

# native Gemini names
from google.genai import types
Agent(..., model=name, generate_content_config=types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_level="MINIMAL")))   # Gemini 2.5 models use thinking_budget instead
```

Compare accuracy both ways on your hand-checked sample before keeping either; [07](07-classify.md) found that turning thinking off made Gemma faster and less accurate.

### Aliases versus pinned versions

Names such as `gemini-flash-latest` follow Google's newest model and change without notice. They are handy while prototyping. For labels you will report, use a pinned name from the [Gemini models page](https://ai.google.dev/gemini-api/docs/models), because `labels.model` records the string and an alias makes that record ambiguous.

## What to use for each job

Suggestions, roughly cheapest first. Try a cheap option, measure it on hand-checked posts, and move up only where it fails.

### Very light classifiers (tier 0)

Fast enough to run on every post on this PC's CPU. They need labeled examples, which [08](08-escalating-labels.md) shows how to collect.

| Option | What it needs | Notes |
| --- | --- | --- |
| **Logistic regression on embeddings** (suggested start) | `scikit-learn` (installed) and any `EMBED_MODEL` | Milliseconds per post once embedded. Gives real probabilities to escalate on. A few hundred labeled posts to start. |
| [SetFit](https://huggingface.co/docs/setfit) | `pip install setfit` | Fine-tunes a small sentence model from a few dozen examples per class. |
| Zero-shot NLI, e.g. [deberta-v3-large-zeroshot-v2.0](https://huggingface.co/MoritzLaurer/deberta-v3-large-zeroshot-v2.0) | `pip install transformers torch` | No training. Phrase each label as a hypothesis ("This text criticizes Schumer"). Slower, and weaker on sarcasm. |
| A fine-tuned small encoder, e.g. [ModernBERT](https://huggingface.co/answerdotai/ModernBERT-base) | `transformers`, `torch`, a GPU helps | Most accurate of the light options once you have a thousand or more labels. |

Off-the-shelf sentiment models measure tone, not stance toward a named person ("I'm furious they're attacking Jeffries" is angry and supportive). Use one only as an input feature, not as the stance label.

### Small LLMs (tier 1)

Cheap enough to run on many posts; good for clear cases, weak on sarcasm and missing context.

| Option | Where it runs | Notes |
| --- | --- | --- |
| A Flash-Lite-class Gemini (`gemini-flash-lite-latest`) | Gemini API | The simplest start: no local setup, low cost per post. |
| Hosted Gemma 4 (`gemma-4-26b-a4b-it`, `gemma-4-31b-it`) | Gemini API | Larger Gemma than this GPU can hold, and the same family as the local model. |
| Gemma 4 `e2b` / `e4b`, small Qwen, Llama 3.2 1B/3B, Phi mini | a local runtime (below) | Free per post, nothing leaves the PC. Only `e2b`-sized models fit this PC's 6 GB GPU. See [07](07-classify.md) for how `e2b` did. |

### Strong LLMs (tier 2 and drafting)

For posts the cheaper tiers could not settle, and for the analyst in [12](12-agent.md).

| Option | String | Notes |
| --- | --- | --- |
| Flash-class Gemini | `gemini-flash-latest` | Good balance of cost and accuracy; try it before Pro. |
| Pro-class Gemini | `gemini-pro-latest` | Hardest posts, final checks, report drafting. |
| Claude through LiteLLM | `anthropic/claude-haiku-5-5`, `anthropic/claude-sonnet-5-5` | Needs `ANTHROPIC_API_KEY`. |
| OpenAI through LiteLLM | `openai/gpt-5-mini` | Needs `OPENAI_API_KEY`. |

Because only a small share of posts should reach this tier, its cost per post matters less than its accuracy.

### Embeddings

| Option | `EMBED_MODEL` | Notes |
| --- | --- | --- |
| Gemini embeddings | `gemini/gemini-embedding-2` | No local setup. |
| EmbeddingGemma, locally | `ollama/embeddinggemma`, or load [google/embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m) with `sentence-transformers` | Free, nothing leaves the PC, 621 MB. |
| OpenAI | `openai/text-embedding-3-small` | Needs `OPENAI_API_KEY`. |

Pick one and keep it. Vectors from different embedding models cannot be compared, so changing `EMBED_MODEL` breaks narrative matching across days ([09](09-narratives.md)) and means retraining the tier-0 classifier. Compare candidates on the [MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard).

### Rough cost

A stance label is about 300 input tokens and 60 output tokens, before any thinking tokens. At the Flash-Lite prices listed in `litellm` 1.109.0 ($0.30 in, $2.50 out per million tokens) that is about $0.25 per 1,000 posts. Check the [pricing page](https://ai.google.dev/gemini-api/docs/pricing) for current prices, and read LiteLLM's own estimate with `litellm.completion_cost(response)`.

## Local runtimes

A local runtime serves a model on this PC so nothing leaves it and there is no cost per post. Each is reached through a LiteLLM prefix:

| Runtime | ADK / LiteLLM string | Address setting |
| --- | --- | --- |
| [Ollama](https://ollama.com) | `ollama_chat/<model>` (chat), `ollama/<model>` (embeddings) | `OLLAMA_API_BASE` |
| [LM Studio](https://lmstudio.ai) | `lm_studio/<model>` | `LM_STUDIO_API_BASE` |
| [llama.cpp server](https://github.com/ggml-org/llama.cpp) | `openai/<model>` | `OPENAI_API_BASE` pointed at the server |
| [vLLM](https://docs.vllm.ai) | `hosted_vllm/<model>` | `HOSTED_VLLM_API_BASE` |

Start the runtime before any notebook that uses it, and begin the notebook with `import bluesky_bots` so the address is read.

### Ollama on this PC

These were true on 2026-11-11, when the labeling, agent and narratives pages were first run with Gemma 4 `e2b` through Ollama.

| Item | Location |
| --- | --- |
| Program | `E:\Ollama` |
| Models | `E:\ollama_models`: `gemma4:e2b` (4.6 GB), `embeddinggemma` (621 MB) |
| Address | `http://127.0.0.1:11435` |

Two user environment variables were set: `OLLAMA_HOST=127.0.0.1:11435` and `OLLAMA_MODELS=E:\ollama_models`. `.env` holds `OLLAMA_API_BASE` and `OLLAMA_HOST` for the Python libraries.

Start it, and leave the terminal open (the tray icon does not start the server on this PC):

```bash
E:\Ollama\ollama.exe serve
```

To install on another machine: install Ollama, then `ollama pull gemma4:e2b` and `ollama pull embeddinggemma`. The Python `ollama` package is not needed; LiteLLM talks to the server.

- **Port 11435, not 11434.** Windows forwards port 11434 to a WSL address on this PC (an older Ollama-in-WSL setup). A call that hangs and then fails to connect means `import bluesky_bots` was skipped.
- **To go back to the default port**, run `netsh interface portproxy delete v4tov4 listenport=11434 listenaddress=0.0.0.0` in an administrator prompt, delete the `OLLAMA_HOST` user variable, and change both lines in `.env` to 11434.
- **GPU memory.** `gemma4:e2b` fits the 6 GB GTX 1660 Ti only when little else is using it. Check with `nvidia-smi`. With a game running, it fell back to the CPU at about 7 tokens per second. `e4b`, `12b` and up do not fit.
- **Thinking** is on by default and slow. `LiteLlm(model=..., reasoning_effort="none")` turns it off.
- **The first call** took 85 seconds because it loads the model; the next took 18.

## When text leaves the PC

A cloud model receives whatever you put in the prompt.

- **Send post text only.** Not the `uri` (it contains the author's DID), not handles, not profile data. [08](08-escalating-labels.md) shows a workflow that keys posts by position and attaches the `uri` back afterwards.
- **Read the provider's data terms.** The [Gemini API terms](https://ai.google.dev/gemini-api/terms) say content sent on the free ("unpaid") quota is used to improve Google's products; paid use is treated differently. Other providers have their own terms.
- **Record the model.** `labels.model` stores the exact string that produced each label, so published error rates can name it ([14](14-guardrails.md)).
- The analyst in [12](12-agent.md) is safe to point at a cloud model, because its tools return daily counts only.

## Resources

- [ADK: models](https://google.github.io/adk-docs/agents/models/), how ADK connects to Gemini, Claude, LiteLLM and others
- [LiteLLM providers](https://docs.litellm.ai/docs/providers) and [supported embedding models](https://docs.litellm.ai/docs/embedding/supported_embedding), the prefix and key variable for each provider
- [Gemini API models](https://ai.google.dev/gemini-api/docs/models), [pricing](https://ai.google.dev/gemini-api/docs/pricing), [terms](https://ai.google.dev/gemini-api/terms), [API keys](https://aistudio.google.com/apikey)
- [Gemma docs](https://ai.google.dev/gemma/docs), model sizes and how to run them
- [Hugging Face models](https://huggingface.co/models), small classifiers and encoders to fine-tune
- [MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard), embedding models compared
- [SetFit](https://huggingface.co/docs/setfit), few-shot classifiers
- [scikit-learn: probability calibration](https://scikit-learn.org/stable/modules/calibration.html), making classifier probabilities trustworthy before thresholding them
- [Artificial Analysis](https://artificialanalysis.ai), independent speed, price and quality comparisons of hosted models
