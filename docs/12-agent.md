# 12 An agent with tools

Build an agent that calls Python functions you give it. Here it asks for aggregate numbers about any topic and drafts a paragraph from them.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/agent/` |
| Reads | aggregates only: daily label counts and narrative shares, through a read-only store |
| Writes | nothing |
| Command | `python -m bluesky_bots.agent "your request"` |
| Must not know | anything about an individual account. Its tools never return one. |

Needs: `ANALYST_MODEL` in `.env` ([16](16-choosing-models.md)) to run the agent; the tests of the tools need no model. Labels from [07](07-classify.md), narratives from [09](09-narratives.md), and the `flagged` view from [10](10-signals.md).

Read first:

- [Function tools](https://google.github.io/adk-docs/tools-custom/function-tools/) in the ADK docs
- [Simple agents](https://google.github.io/adk-docs/agents/llm-agents/) in the ADK docs
- DuckDB's [`FILTER` clause](https://duckdb.org/docs/stable/sql/query_syntax/filter), which the main tool leans on

## What you are building

Three tools and one agent:

| Piece | Does |
| --- | --- |
| `list_topics()` | tells the model which topics exist, with their entities, dimensions and values |
| `label_counts_by_day(topic, dimension, start, end, entity="")` | daily counts for each value of one dimension, for all accounts and with flagged accounts left out |
| `narrative_share(topic, run_date="", top_n=10)` | a topic's largest narratives with their share of clustered posts |
| `build_analyst()` | an agent that calls those three and drafts findings from what they return |

You are done when `pytest tests/test_review_reports_agent.py -k "tool or analyst or list_topics"` passes, and the agent, asked for two paragraphs about a topic over a date range, calls your tools with the right arguments and quotes numbers that are in their results.

## Step 1: Write a tool

**Concept.** A tool is a plain Python function. You hand it to an agent, and the model decides when to call it and with what arguments. The model never sees the body. What it sees is the function's **name**, its **type hints** and its **docstring**, so those three are the tool's instructions, and you write them for the model.

A tool is also the boundary of what the agent can know. These return daily counts only. An agent that never receives a handle or a DID cannot repeat one.

**Your task.** In `bluesky_bots/agent/tools.py`, write `label_counts_by_day(topic, dimension, start, end, entity="")`. For each day and value it returns the day, the value, the number of posts from all accounts, and the number from accounts that are not in the `flagged` view.

**Hints.**

- `with _session() as con:` gives you a read-only analysis connection and closes it afterwards. It is already in the file, and a test swaps it for one over a test store.
- Join `posts` to `labels_final` on `uri`, and filter on the topic, its current scheme version and the dimension.
- `count(DISTINCT p.uri)` counts posts. A post about two entities has two label rows, and `count(*)` would count it twice.
- `count(...) FILTER (WHERE ...)` counts a subset in the same pass as the total. That gives you both numbers from one query.
- Return JSON-friendly values: strings, numbers, lists, dicts. A `date` object is not one, so cast the day to text in SQL.
- The docstring should say what comes back and what format the dates take. The model reads it to decide how to call you.
- What will the model send for `topic`: `dem-leadership`, `Dem-Leadership`, with a space after it? Decide what the tool should do about it.

**Check.** `pytest tests/test_review_reports_agent.py -k label_counts_tool`. `n_unflagged` is never larger than `n_all`, and nothing in the result contains `did:` or `at://`.

## Step 2: Two more tools

**Concept.** With one fixed subject, the model could be told the names it needs in its instruction. With topics in files, it has to be able to ask. `list_topics` is the tool that makes the others usable: it returns the exact names the other two take.

**Your task.** Write `list_topics()` and `narrative_share(topic, run_date="", top_n=10)`, the latter returning each narrative's name, its post count, and its share of that run's clustered posts as a percentage.

**Hints.**

- `load_topics()` from the topics service does most of `list_topics`. Leave out topics with no label scheme.
- A share needs the total alongside each row. A window function, `sum(n_posts) OVER ()`, gives you the total without a second query.
- Give `run_date` and `top_n` defaults, so the model can leave them out. An empty `run_date` means the latest run.

**Check.** `pytest tests/test_review_reports_agent.py -k "list_topics or narrative_share"`. Called directly, the shares of all narratives in a run add up to about 100. With `top_n` smaller than the number of narratives they add up to less.

## Step 3: The agent and its instruction

**Concept.** The instruction tells the agent what it is for, and here it also carries the project's rules for anything written about the data ([14 Guardrails](14-guardrails.md)).

**Your task.** In `bluesky_bots/agent/analyst.py`, write `build_analyst(model=None)`, which returns an `Agent` named `analyst` with `ANALYST_MODEL`, your three tools, and `INSTRUCTION`. Read the instruction in the file and reword it in your own words if you like. Whatever the wording, it should make the agent:

- use only numbers that came from its tools, quoted exactly;
- call `list_topics` first, so it uses names that exist;
- describe what was observed, without calling anything a campaign, a bot network or inauthentic;
- say plainly when the flagged and unflagged series are close;
- never mention individual accounts;
- know that a person will edit the draft.

**Hints.**

- Tools go in `tools=[...]` as the functions themselves, not as strings.

**Check.** `pytest tests/test_review_reports_agent.py -k analyst` builds the agent without calling a model and checks that it has exactly those three tools.

## Step 4: Run it and read the trace

**Concept.** For a single agent you do not need a workflow. `InMemoryRunner` with `run_debug` runs one request and, with `verbose=True`, prints each tool call and what it returned. That trace is how you find out what the model actually did. The command does exactly this.

**Your task.**

```bash
python -m bluesky_bots.agent "Draft two paragraphs on stance toward Schumer in dem-leadership, 2026-10-20 to 2026-11-17."
```

**Check.** Read the trace before the draft.

- Did the model call `list_topics`, then `label_counts_by_day` with the topic, dimension, entity and dates from your request?
- Take each number in the draft and find it in a tool's result. Every one should be there.
- Read each claim about the numbers ("close", "rising", "most") against the table. This is where the first run went wrong; see below.

## How tools work

- Any plain Python function can be a tool. Pass it in `tools=[...]`.
- The function name, type hints and docstring are what the model sees, so write the docstring for the model.
- Return JSON-friendly values: strings, numbers, lists, dicts. Cast dates to text in SQL.
- Gemini, Gemma 4, Claude and recent OpenAI models call tools natively. Very small local models may not; test before relying on one.
- `run_debug(..., verbose=True)` prints each tool call and its result.

## What a first run showed

On 2026-11-11, with Gemma 4 `e2b` running locally and an earlier, single-subject version of the counting tool. A stronger model will likely write better drafts; the checks above still apply.

- Gemma called the counting tool on its own with correct dates.
- It passed "Schumer" with a capital S while labels store lowercase, and got nothing back. The tools now lowercase and trim what they are given. Expect to normalize whatever a model sends.
- With an empty result it said no data was returned and did not invent numbers.
- With data it quoted two days exactly (32 posts from all accounts, 12 excluding flagged), then wrote that the two series were "consistently close". They were not.
- It took one and a half to three minutes per request.

Use it for a rough first draft at most, and check every sentence against the table.

## Good to know

- **The tools are the safety boundary.** They return daily counts and narrative shares only, so the agent cannot repeat a handle or DID it never receives. Keep it that way: no tool should return rows about individual accounts. It also means pointing `ANALYST_MODEL` at a cloud model sends only aggregates off this PC.
- **The tools read `labels_final`**, so a post is counted once, under its highest tier.
- **The tools open the store read-only**, through `_session`. With the DuckDB backend that still blocks a batch command from writing while a tool is mid-query ([05](05-storage.md)).
- For a single agent, `InMemoryRunner` plus `run_debug` is enough. Use a `Workflow` when there are several steps or branches.

## Example solution

`tests/test_review_reports_agent.py` passes against this code (run on 2026-11-13): the tools on planted data, and the agent built but not called. The agent has not been run with a model in this form.

<details>
<summary>Show example: steps 1 and 2, the tools (bluesky_bots/agent/tools.py)</summary>

```python
from contextlib import contextmanager

from ..storage import open_store
from ..topics import get_topic, load_topics


@contextmanager
def _session():
    """A read-only analysis connection, closed afterwards. A test replaces this."""
    store = open_store(read_only=True)
    con = store.analytics()
    try:
        yield con
    finally:
        con.close()
        store.close()


def _dicts(cur) -> list[dict]:
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def list_topics() -> list[dict]:
    """The topics that can be asked about. For each: its name, title, the entities
    a label can be about, and each label dimension with its allowed values.
    Call this first to learn the exact names the other tools take."""
    return [{"name": t.name, "title": t.title, "entities": list(t.entities),
             "dimensions": {name: dim.values for name, dim in t.labels.dimensions.items()}}
            for t in load_topics() if t.labels]


def label_counts_by_day(topic: str, dimension: str, start: str, end: str, entity: str = "") -> list[dict]:
    """Daily counts of a topic's posts for each value of one label dimension.
    Each row has day, value, n_all (posts from all accounts) and n_unflagged
    (posts from accounts with no behavioral flags). Dates are YYYY-MM-DD and
    both are included. Pass entity to count only labels about that entity."""
    t = get_topic(topic.strip().lower())                # a model may send "Dem-Leadership"
    with _session() as con:
        return _dicts(con.execute("""
            SELECT CAST(CAST(p.created_at AS DATE) AS VARCHAR) AS day, l.value,
                   count(DISTINCT p.uri) AS n_all,
                   count(DISTINCT p.uri) FILTER (WHERE p.did NOT IN (SELECT did FROM flagged))
                       AS n_unflagged
            FROM posts p JOIN labels_final l USING (uri)
            WHERE l.topic = ? AND l.scheme_version = ? AND l.dimension = ?
              AND (? = '' OR l.target = ?)
              AND p.created_at >= CAST(? AS DATE) AND p.created_at < CAST(? AS DATE) + 1
            GROUP BY 1, 2 ORDER BY 1, 2""",
            [t.name, t.labels.version, dimension.strip().lower(), entity.strip().lower(),
             entity.strip().lower(), start, end]))


def narrative_share(topic: str, run_date: str = "", top_n: int = 10) -> list[dict]:
    """The largest narratives in a topic with their share of the topic's clustered
    posts, as name, n_posts and share_pct. run_date is YYYY-MM-DD; leave it
    empty for the latest clustering run."""
    name = topic.strip().lower()
    with _session() as con:
        return _dicts(con.execute("""
            SELECT name, n_posts, round(n_posts * 100.0 / sum(n_posts) OVER (), 1) AS share_pct
            FROM narratives
            WHERE topic = ? AND run_date = coalesce(
                CAST(nullif(?, '') AS DATE), (SELECT max(run_date) FROM narratives WHERE topic = ?))
            ORDER BY n_posts DESC LIMIT ?""", [name, run_date, name, top_n]))
```

</details>

<details>
<summary>Show example: step 3, the agent (bluesky_bots/agent/analyst.py)</summary>

```python
from google.adk import Agent

from .. import config
from .tools import label_counts_by_day, list_topics, narrative_share


INSTRUCTION = """You draft findings for a research report about conversations on Bluesky.
Use only numbers returned by your tools and quote them exactly. Call list_topics
first to learn the topic names, dimensions and values. Describe what was observed;
do not call anything a campaign, a bot network or inauthentic. Say plainly when the
flagged and unflagged series are close. Never mention individual accounts.
A human will edit your draft."""


def build_analyst(model: str | None = None) -> Agent:
    """The analyst agent: ANALYST_MODEL (or `model`), the instruction above, and the three tools."""
    return Agent(name="analyst", model=model or config.model("ANALYST_MODEL"),
                 instruction=INSTRUCTION, tools=[list_topics, label_counts_by_day, narrative_share])
```

</details>
