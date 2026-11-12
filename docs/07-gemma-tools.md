# 07 An agent with tools

Build an agent that calls Python functions you give it. Here it queries the database for aggregate numbers and drafts a paragraph from them.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed.

Needs: `load_dotenv()` first, `ANALYST_MODEL` in `.env` ([13](13-choosing-models.md)), a database with `posts`, `labels`, `narratives` and the `flagged` view from [09](09-signals.md).

Read first:

- [Function tools](https://google.github.io/adk-docs/tools-custom/function-tools/) in the ADK docs
- [Simple agents](https://google.github.io/adk-docs/agents/llm-agents/) in the ADK docs
- DuckDB's [`FILTER` clause](https://duckdb.org/docs/stable/sql/query_syntax/filter), which both tools lean on

## What you are building

Two tools and one agent:

| Piece | Does |
| --- | --- |
| `leader_stance_by_day(leader, start, end)` | daily counts of critical, supportive and neutral posts about one leader, for all accounts and with flagged accounts left out |
| `narrative_share(run_date, top_n)` | the top narratives on one date with their share of all tracked posts |
| `analyst` | an agent that calls those two and drafts findings from what they return |

You are done when the agent, asked for two paragraphs about one leader over a date range, calls your tool with the right arguments and quotes numbers that are in the tool's result.

## Step 1: Write a tool

**Concept.** A tool is a plain Python function. You hand it to an agent, and the model decides when to call it and with what arguments. The model never sees the body. What it sees is the function's **name**, its **type hints** and its **docstring**, so those three are the tool's instructions, and you write them for the model.

A tool is also the boundary of what the agent can know. This one returns daily counts only. An agent that never receives a handle or a DID cannot repeat one.

**Your task.** Write `leader_stance_by_day(leader: str, start: str, end: str) -> list[dict]`. For each day and stance it returns the day, the stance, the number of posts from all accounts, and the number from accounts that are not in the `flagged` view.

**Hints.**

- Join `posts` to `labels` on `uri`. `labels.leaders` is a list column; `list_contains` tests membership.
- `count(*) FILTER (WHERE ...)` counts a subset in the same pass as the total. That gives you both numbers from one query.
- Return JSON-friendly values: strings, numbers, lists, dicts. A `date` object is not one, so cast the day to text in SQL.
- Open the database `read_only=True` inside the tool. The loader is the only writer ([04](04-storage.md)).
- The docstring should say what comes back and what format the dates take. The model reads it to decide how to call you.
- What will the model send for `leader`: `schumer`, `Schumer`, `Sen. Schumer`? Labels store lowercase names. Decide what the tool should do about it.

**Check.** Call the function yourself, as ordinary Python, with a leader and a date range you have labels for. You get a list of dicts with four keys, and `n_unflagged` is never larger than `n_all`. Call it again with the leader's name capitalized and make sure you still get rows.

## Step 2: A second tool

**Your task.** Write `narrative_share(run_date: str, top_n: int = 10) -> list[dict]`, returning each narrative's name, its post count, and its share of that date's posts as a percentage.

**Hints.**

- A share needs the total alongside each row. A window function, `sum(n_posts) OVER ()`, gives you the total without a second query.
- Give `top_n` a default, so the model can leave it out.

**Check.** Called directly, the shares of all narratives on a date add up to about 100. With `top_n` smaller than the number of narratives they add up to less.

## Step 3: The agent and its instruction

**Concept.** The instruction tells the agent what it is for, and here it also carries the project's rules for anything written about the data ([11 Guardrails](11-guardrails.md)).

**Your task.** Create an `Agent` named `analyst` with `ANALYST_MODEL`, your two tools, and an instruction. Write your own instruction first. It should make the agent:

- use only numbers that came from its tools, quoted exactly;
- describe what was observed, without calling anything a campaign, a bot network or inauthentic;
- say plainly when the flagged and unflagged series are close;
- never mention individual accounts;
- know that a person will edit the draft.

**Hints.**

- Tools go in `tools=[...]` as the functions themselves, not as strings.

## Step 4: Run it and read the trace

**Concept.** For a single agent you do not need a workflow. `InMemoryRunner` with `run_debug` runs one request and, with `verbose=True`, prints each tool call and what it returned. That trace is how you find out what the model actually did.

**Your task.** In a notebook, run the agent on a request such as "Draft two paragraphs on mentions of Schumer, 2026-10-20 to 2026-11-17."

**Hints.**

- `run_debug` is awaited. In a notebook, `await` it directly ([15 Async Python](15-async-python.md)).
- [01](01-setup.md) used the same runner for the first model call.

**Check.** Read the trace before the draft.

- Did the model call the tool, and with the dates from your request?
- Take each number in the draft and find it in the tool's result. Every one should be there.
- Read each claim about the numbers ("close", "rising", "most") against the table. This is where the first run went wrong; see below.

## How tools work

- Any plain Python function can be a tool. Pass it in `tools=[...]`.
- The function name, type hints and docstring are what the model sees, so write the docstring for the model.
- Return JSON-friendly values: strings, numbers, lists, dicts. Cast dates to text in SQL.
- Gemini, Gemma 4, Claude and recent OpenAI models call tools natively. Very small local models may not; test before relying on one.
- `run_debug(..., verbose=True)` prints each tool call and its result.

## What a first run showed

With Gemma 4 `e2b` running locally. A stronger model will likely write better drafts; the checks below still apply.

- Gemma called `leader_stance_by_day` on its own with correct dates.
- It passed "Schumer" with a capital S while labels store lowercase, and got nothing back. The tool now lowercases its input. Expect to normalize whatever a model sends.
- With an empty result it said no data was returned and did not invent numbers.
- With data it quoted two days exactly (32 posts from all accounts, 12 excluding flagged), then wrote that the two series were "consistently close". They were not.
- It took one and a half to three minutes per request.

Use it for a rough first draft at most, and check every sentence against the table.

## Good to know

- **The tools are the safety boundary.** These return daily counts only, so the agent cannot repeat a handle or DID it never receives. Keep it that way: no tool should return rows about individual accounts. It also means pointing `ANALYST_MODEL` at a cloud model sends only aggregates off this PC.
- **With tiered labels** ([14](14-escalating-labels.md)), have the tools read `labels_final` instead of `labels`, or each post is counted once per tier.
- Open the database `read_only=True` inside tools.
- For a single agent, `InMemoryRunner` plus `run_debug` is enough. Use a `Workflow` when there are several steps or branches.

## Example solution

This is the code that was run on this PC. Read top to bottom, the blocks make one module.

<details>
<summary>Show example: step 1, a tool that returns daily counts</summary>

```python
import os
import duckdb
from google.adk import Agent
from google.adk.runners import InMemoryRunner

DB = "data/narrative.duckdb"

def leader_stance_by_day(leader: str, start: str, end: str) -> list[dict]:
    """Daily counts of critical, supportive and neutral posts about one leader,
    for all accounts and excluding flagged accounts. Dates are YYYY-MM-DD."""
    con = duckdb.connect(DB, read_only=True)
    return con.execute("""
        SELECT CAST(CAST(p.created_at AS DATE) AS VARCHAR) AS day, l.stance,
               count(*) AS n_all,
               count(*) FILTER (WHERE p.did NOT IN (SELECT did FROM flagged)) AS n_unflagged
        FROM posts p JOIN labels l USING (uri)
        WHERE list_contains(l.leaders, ?) AND p.created_at BETWEEN ? AND ?
        GROUP BY 1, 2 ORDER BY 1, 2
    """, [leader.strip().lower(), start, end]).df().to_dict("records")   # model may send "Schumer"
```

</details>

<details>
<summary>Show example: step 2, a second tool</summary>

```python
def narrative_share(run_date: str, top_n: int = 10) -> list[dict]:
    """Top narratives on one date with their share of all tracked posts."""
    con = duckdb.connect(DB, read_only=True)
    return con.execute("""
        SELECT name, n_posts, round(n_posts * 100.0 / sum(n_posts) OVER (), 1) AS share_pct
        FROM narratives WHERE run_date = ? ORDER BY n_posts DESC LIMIT ?
    """, [run_date, top_n]).df().to_dict("records")
```

</details>

<details>
<summary>Show example: steps 3 and 4, the agent and running it</summary>

```python
analyst = Agent(
    name="analyst",
    model=os.environ["ANALYST_MODEL"],
    instruction="""You draft findings for a research report. Use only numbers returned
by your tools and quote them exactly. Describe what was observed; do not call anything
a campaign, a bot network or inauthentic. Say plainly when the flagged and unflagged
series are close. Never mention individual accounts. A human will edit your draft.""",
    tools=[leader_stance_by_day, narrative_share],
)

# In a notebook cell:
# runner = InMemoryRunner(agent=analyst, app_name="analyst")
# await runner.run_debug("Draft two paragraphs on mentions of Schumer, "
#                        "2026-10-20 to 2026-11-17.", verbose=True)
```

</details>
