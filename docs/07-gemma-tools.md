# 07 Gemma with tools

An agent that calls Python functions you give it. Here it queries the database for aggregate numbers and drafts a paragraph from them.

Needs: Ollama running, `load_dotenv()` first, a database with `posts`, `labels`, `narratives` and the `flagged` view from [09](09-signals.md).

## The agent

```python
import duckdb
from google.adk import Agent
from google.adk.models.lite_llm import LiteLlm
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

def narrative_share(run_date: str, top_n: int = 10) -> list[dict]:
    """Top narratives on one date with their share of all tracked posts."""
    con = duckdb.connect(DB, read_only=True)
    return con.execute("""
        SELECT name, n_posts, round(n_posts * 100.0 / sum(n_posts) OVER (), 1) AS share_pct
        FROM narratives WHERE run_date = ? ORDER BY n_posts DESC LIMIT ?
    """, [run_date, top_n]).df().to_dict("records")

analyst = Agent(
    name="analyst",
    model=LiteLlm(model="ollama_chat/gemma4:e2b"),
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

## How tools work

- Any plain Python function can be a tool. Pass it in `tools=[...]`.
- The function name, type hints and docstring are what the model sees, so write the docstring for the model.
- Return JSON-friendly values: strings, numbers, lists, dicts. Cast dates to text in SQL.
- Gemma 4 calls tools natively; ADK needs no special class for it.
- `run_debug(..., verbose=True)` prints each tool call and its result.

## What a first run showed

- Gemma called `leader_stance_by_day` on its own with correct dates.
- It passed "Schumer" with a capital S while labels store lowercase, and got nothing back. The tool now lowercases its input. Expect to normalize whatever a model sends.
- With an empty result it said no data was returned and did not invent numbers.
- With data it quoted two days exactly (32 posts from all accounts, 12 excluding flagged), then wrote that the two series were "consistently close". They were not.
- It took one and a half to three minutes per request.

Use it for a rough first draft at most, and check every sentence against the table.

## Good to know

- **The tools are the safety boundary.** These return daily counts only, so the agent cannot repeat a handle or DID it never receives. Keep it that way: no tool should return rows about individual accounts.
- Open the database `read_only=True` inside tools.
- For a single agent, `InMemoryRunner` plus `run_debug` is enough. Use a `Workflow` when there are several steps or branches.
