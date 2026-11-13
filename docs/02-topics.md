# 02 Topics

Say what a conversation is in a file, then write the code that decides whether a post belongs to it.

Each step explains one idea, sets a task, and tells you how to check your work. The code that was run on this PC is at the bottom under [Example solution](#example-solution), collapsed. Open it when you are stuck or want to compare.

| Service contract | |
| --- | --- |
| Code | `bluesky_bots/topics/`, plus `bluesky_bots/aturi.py` |
| Reads | `topics/*.yaml`; stored posts, through the storage service |
| Writes | which posts belong to which topic (`post_topic`); the watch-list flag on accounts |
| Command | `python -m bluesky_bots.topics check` and `... assign` |
| Must not know | how posts are fetched, which model labels them, or which database holds them |

Needs: nothing beyond the environment. No login, no model, no network.

Read first:

- `topics/dem-leadership.yaml` and `topics/example-remote-work.yaml`, the two example topic files
- [Posts in-depth](https://bsky.network/docs/about-bluesky-content/posts) in the Bluesky docs, for what replies and quote posts look like inside a record. You need it in step 5.
- Python's [regular expression HOWTO](https://docs.python.org/3/howto/regex.html), if `re` is new to you

## What you are building

Every other service asks this one "is this post part of the conversation?". Nothing else in the project names a keyword, an account or a label value. To study something new you add a file here, and no code changes.

| Function | Gives you |
| --- | --- |
| `keyword_regex`, `match_text` | does this text mention the topic? |
| `at_uri`, `did_of`, `quoted_uri` | the small AT URI helpers everything else uses |
| `match_post` | which rule, if any, puts a post in the topic |
| `event_fields`, `match_event` | the same answer for a live Jetstream event |
| `capture_filter` | the function the stream uses to decide what to keep |
| `entities_in` | which of the topic's named entities a text mentions |
| `assign` | records which stored posts belong to the topic |

You are done when `pytest tests/test_topics.py` passes.

The decision "which posts are relevant" is made in three places, and each can be changed without touching the others:

1. **Capture.** The stream keeps an event if any active topic matches it (step 6).
2. **Membership.** Storage records which topics each stored post belongs to, and that record can be recomputed whenever a topic file changes (step 8).
3. **Selection.** Classification and clustering work on one topic's members at a time ([07](07-classify.md), [09](09-narratives.md)).

## Step 1: Write a topic file

**Concept.** A topic file has four parts. Only `name` is required.

| Part | Says |
| --- | --- |
| `match` | Which posts are in: `keywords` (whole words or phrases, any case), `patterns` (regular expressions, for what keywords cannot say), `accounts` (handles or DIDs: their posts, and replies to, quotes and reposts of them). A post is in when any one rule matches. |
| `entities` | Optional. Named things a label can be about, each with the words that suggest it. |
| `labels` | How to label the topic's posts: a `version`, an `instruction` in your words, and one or more `dimensions`, each a question with a closed set of `values`. A dimension may name one value as `unsure`, meaning "cannot tell". |
| `search`, `narratives`, `markers`, `active` | Queries for backfill, the smallest cluster worth calling a narrative, dated lines for charts, and whether the stream captures this topic. |

The format is defined in `bluesky_bots/topics/schema.py`, which is already written. It is strict on purpose: a misspelled key is an error, so a typo cannot silently change what you collect.

**Your task.** Read the two example files, then `schema.py`. Then write a topic file of your own, for a conversation you would like to follow, and save it in `topics/` with `active: false`.

**Hints.**

- A dimension is a question with a fixed set of answers. "What is the stance toward the named person?" and "Is this news, opinion or personal experience?" are both dimensions. Two dimensions in one topic are labeled in the same model call.
- Entities are for topics where the label is about someone or something in particular. A topic about remote work has none; a topic about two politicians has two.
- Keep keywords simple. A surname catches other people with the same name; the labeling step ([07](07-classify.md)) decides who is meant.

**Check.**

```bash
python -m bluesky_bots.topics check
```

It should list your topic beside the two examples. Then break it on purpose: misspell `keywords`, or give `unsure` a value that is not in `values`, and read the error.

## Step 2: Keywords into one pattern

**Concept.** Checking a text against twenty keywords one at a time is slow and easy to get wrong. One regular expression that matches any of them is neither. Three details matter:

- **Whole words only.** `schumer` must not match "schumerism". The usual tool is `\b`, a word boundary, but it fails for keywords that begin or end with a symbol, such as `#rto`. `(?<!\w)` before and `(?!\w)` after say the same thing ("no word character on this side") and work for every keyword.
- **Keywords are text, not patterns.** `c++` contains characters that mean something in a regular expression. `re.escape` makes them literal.
- **Compile once.** The stream calls this about sixty times a second. [`functools.lru_cache`](https://docs.python.org/3/library/functools.html#functools.lru_cache) remembers the result for arguments it has seen, as long as they can be hashed. A list cannot; a tuple can.

**Your task.** In `bluesky_bots/topics/match.py`, write `keyword_regex(keywords, patterns)` and `match_text(topic, text)`.

**Hints.**

- Join the alternatives with `|`. Wrap each raw pattern in `(?:...)` so its own `|` cannot leak into its neighbours.
- `re.I` ignores case.
- With no keywords and no patterns, an empty pattern would match everything. Return `None` instead and have `match_text` answer `False`.

**Check.** `pytest tests/test_topics.py -k keywords`

## Step 3: AT URIs

**Concept.** A record's address is its [AT URI](https://atproto.com/specs/at-uri-scheme): `at://<did>/<collection>/<rkey>`. Three small functions turn up on almost every page, so they live in one shared module, `bluesky_bots/aturi.py`.

A post that quotes another carries the quoted post's URI in its `embed`, in one of two shapes. A plain quote has `embed.record.uri`. A quote that also has images or video has type [`app.bsky.embed.recordWithMedia`](https://github.com/bluesky-social/bsky/blob/main/lexicons/app/bsky/embed/recordWithMedia.json), which wraps the same reference one level deeper: `embed.record.record.uri`. Other embeds (images alone, link cards) have no `record` at all.

**Your task.** Write `at_uri(event)`, `did_of(uri)` and `quoted_uri(record)`.

**Hints.**

- Split an AT URI on `/` and count which piece the DID is.
- Look for a way to reduce the two quote shapes to one before you read the `uri`. Every lookup on the way down needs a default, because most posts quote nothing.

**Check.** `pytest tests/test_topics.py -k aturi`

## Step 4: The rules for one post

**Concept.** Whether a post is in a topic depends on three facts about it: who wrote it, what it says, and whose posts it is attached to (by replying, quoting or reposting). Stated that way, the rule does not care where the post came from, so the same function serves the live stream and posts already in storage.

| The post | In the topic? | Rule name |
| --- | --- | --- |
| is by one of the topic's accounts | yes | `account` |
| has text matching a keyword or pattern | yes | `keyword` |
| replies to, quotes or reposts a post by one of the topic's accounts | yes | `linked` |
| anything else | no | |

The topic's accounts are in `topic.dids`, a set of DIDs. Step 9 explains how handles get there.

**Your task.** Write `match_post(topic, did, text="", linked=())`. It returns the name of the first rule that matches, or `None`.

**Hints.**

- `linked` is whatever collection of DIDs the caller has; `set.intersection` accepts any iterable.
- Returning the rule's name costs nothing and is stored with the membership, so you can later ask how much of a topic came in through keywords and how much through accounts.

**Check.** `pytest tests/test_topics.py -k match_post`

## Step 5: From a live event to those three facts

**Concept.** A Jetstream event ([03](03-stream.md) step 2 has the full shape) carries the author's `did`, a `collection`, and for creates a `record`:

```
record (post):   text, reply?{parent{uri}, root{uri}}, embed?
record (repost): subject{uri}
```

So the three facts are spread around: the author at the top, the text in the record, and the linked accounts inside up to three URIs for a post (reply parent, thread root, quoted post) or one for a repost (its subject).

**Your task.** Write `event_fields(event)`, which returns a dict with `did`, `text` and `linked` ready to pass to `match_post`, and `match_event(topic, event)`, which does exactly that.

**Hints.**

- A repost has no `text`, `reply` or `embed`. Deal with it first.
- Records are written by other people's apps. A reply with no `parent`, or a repost with no `subject`, should give you an empty `linked`, not an exception. `(x or {}).get(...)` is a compact way to stay safe.
- You already wrote `quoted_uri` and `did_of`.

**Check.** `pytest tests/test_topics.py -k "match_event or capture"` (the second part needs step 6).

## Step 6: The capture filter

**Concept.** The stream does not know what a topic is. It is handed one function, `keep(event)`, and writes down whatever that function accepts. This step builds the usual `keep`: an event is kept when *any* of the topics you pass matches it.

One kind of event is kept no matter what: a delete. A delete event does not say what the post was, only its address, so the filter cannot tell whether you stored it. Keeping every delete lets storage remove the post if it is there. Removing content its author deleted is one of this project's rules ([14 Guardrails](14-guardrails.md)) and one of Bluesky's [developer guidelines](https://bsky.network/docs/developer-guidelines).

**Your task.** Write `capture_filter(topics)`. It returns a function.

**Hints.**

- A function defined inside another can use the outer function's variables. That is how `keep` remembers the topics.
- Work out `event_fields` once per event, not once per topic.
- With no topics at all, the filter should still keep deletes.

**Check.** `pytest tests/test_topics.py -k capture`. Thirteen of those cases are the rows of the table in step 4, one made-up event each.

## Step 7: Which entities a text mentions

**Concept.** A topic with entities needs a cheap first guess at which ones a post is about. The first-tier classifier in [08](08-escalating-labels.md) uses it. It is only a guess: the word "Schumer" can mean the comedian. A model makes the real call in [07](07-classify.md).

**Your task.** Write `entities_in(topic, text)`, returning the names of the entities whose words appear in the text, in the order the topic lists them.

**Hints.**

- You have a function that turns a list of words into a whole-word pattern.

**Check.** `pytest tests/test_topics.py -k entities`

## Step 8: Record membership

**Concept.** The capture filter decided what to keep at the moment a post went by. But topic files change: you add a keyword, or a second topic that happens to cover posts you already hold. So membership is stored separately from the posts, in a table of (post, topic, rule), and worked out again whenever you ask.

This function is the first to use the storage service. A **store** is an object with methods such as `iter_posts()` and `set_post_topics()`; [05](05-storage.md) explains it. You do not need the DuckDB backend yet: the test hands you a finished SQLite store.

For a stored post, the three facts come from its row: `did`, `text`, and the DIDs inside `reply_parent`, `reply_root` and `quote_of`.

**Your task.** In `bluesky_bots/topics/assign.py`, write `assign(store, topic)`. It checks every stored post, replaces the topic's earlier membership with the new result, and returns how many posts are in the topic.

**Hints.**

- `store.iter_posts()` yields one dict per post.
- `store.set_post_topics(topic.name, rows)` replaces that topic's membership; each row needs `uri` and `matched_by`.
- "Replace" is what makes running it twice safe, and what lets a narrowed topic lose members.

**Check.** `pytest tests/test_topics.py -k assign`. Then, once you have posts stored:

```bash
python -m bluesky_bots.topics assign
```

**What it cannot do.** `assign` only sees posts that are stored. A post that matched no active topic when it went by was never kept, so a new topic starts with whatever your other topics happened to capture. For its history, use the backfill service ([04](04-backfill.md)).

## Step 9: Handles and DIDs

**Concept.** People write handles; the network uses [DIDs](https://atproto.com/specs/did), the permanent account identifiers. A handle can change and a DID cannot, so matching works on DIDs only.

A topic file may list either. An entry starting with `did:` goes straight into `topic.dids` when the file is loaded. A handle has to be looked up, which needs the network, so it happens separately: `resolve_accounts` in `topics/resolve.py` (already written) looks up each handle once and remembers the answer in `data/state/dids.json`. The lookup function it uses is `resolve_did`, which you write on [04](04-backfill.md).

There is nothing to build in this step. Until page 04 is done, list accounts as DIDs. `did:plc:z72i7hdynmk6r22z27h6tvur` is the `bsky.app` account, and the example topic uses it as a placeholder.

## Good to know

- **Three places to change what is relevant**: what the stream keeps, which topics a stored post belongs to, and which topic a later step works on. Changing a topic file changes the first on the next stream restart, the second when you run `topics assign`, and the third at once.
- **A new topic has no history** beyond what other topics captured. Backfill it.
- **Every active topic widens capture.** The filter keeps the union. Watch the size of `data/raw` after adding one ([17](17-choosing-storage.md)).
- **Change `labels.version` whenever the instruction, a dimension or a value changes.** Labels are stored under the version, so labels made under different schemes are never mixed.
- **Surname matching catches other people** with the same name. Keep keywords simple and let labeling decide who is meant.
- **The watch list is every account named in an active topic file.** `topics assign` marks those accounts in storage, and [10](10-signals.md) leaves them out of flagging.
- **To capture everything**, the stream command takes `--all`, which swaps the filter for one that always says yes. Read [17](17-choosing-storage.md) first: it is roughly 5 million events a day.

## Example solution

This is the code that was run on this PC on 2026-11-13: `tests/test_topics.py` passes against it.

<details>
<summary>Show example: step 2, keywords into one pattern</summary>

```python
from __future__ import annotations

import re
from functools import lru_cache
from typing import Callable, Iterable

from ..aturi import did_of, quoted_uri
from .schema import Topic


REPOST = "app.bsky.feed.repost"


@lru_cache(maxsize=None)
def keyword_regex(keywords: tuple[str, ...], patterns: tuple[str, ...] = ()) -> re.Pattern | None:
    """One compiled, case-insensitive pattern for a topic's keywords and patterns.

    Each keyword matches only as a whole word or phrase. Returns None when
    there is nothing to match. Arguments are tuples so the result can be cached.
    """
    parts = [rf"(?<!\w){re.escape(k)}(?!\w)" for k in keywords] + [f"(?:{p})" for p in patterns]
    return re.compile("|".join(parts), re.I) if parts else None


def match_text(topic: Topic, text: str) -> bool:
    """True when the text contains one of the topic's keywords or matches one of its patterns."""
    rx = keyword_regex(tuple(topic.match.keywords), tuple(topic.match.patterns))
    return bool(rx and rx.search(text))
```

</details>

<details>
<summary>Show example: step 3, AT URIs (bluesky_bots/aturi.py)</summary>

```python
def at_uri(event: dict) -> str:
    """The AT URI of the record a Jetstream event is about, built from its did, collection and rkey."""
    return f"at://{event['did']}/{event['collection']}/{event['rkey']}"


def did_of(uri: str) -> str:
    """The DID inside an AT URI."""
    return uri.split("/")[2]


def quoted_uri(record: dict) -> str | None:
    """The URI of the post a record quotes, or None if it quotes nothing.

    Handles both shapes: a plain quote (embed.record.uri) and a quote that
    also carries images or video (embed.record.record.uri).
    """
    quoted = (record.get("embed") or {}).get("record") or {}
    quoted = quoted.get("record", quoted)      # quote-with-media nests one level deeper
    return quoted.get("uri")
```

</details>

<details>
<summary>Show example: step 4, the rules for one post</summary>

```python
def match_post(topic: Topic, did: str, text: str = "", linked: Iterable[str] = ()) -> str | None:
    """Which rule puts a post in the topic: 'account', 'keyword', 'linked', or None for no match.

    did:    the author
    text:   the post's text ('' for a repost)
    linked: DIDs of the accounts whose posts this one replies to, quotes or reposts
    """
    if did in topic.dids:
        return "account"
    if match_text(topic, text):
        return "keyword"
    if topic.dids.intersection(linked):
        return "linked"
    return None
```

</details>

<details>
<summary>Show example: step 5, from a live event to those three facts</summary>

```python
def event_fields(event: dict) -> dict:
    """The did, text and linked DIDs of a Jetstream create or update event, as match_post takes them."""
    rec = event.get("record") or {}
    if event.get("collection") == REPOST:
        uris = [(rec.get("subject") or {}).get("uri")]
    else:
        reply = rec.get("reply") or {}
        uris = [(reply.get("parent") or {}).get("uri"), (reply.get("root") or {}).get("uri"),
                quoted_uri(rec)]
    return {"did": event["did"], "text": rec.get("text", ""),
            "linked": {did_of(u) for u in uris if u}}


def match_event(topic: Topic, event: dict) -> str | None:
    """Which rule puts a Jetstream event in the topic, or None."""
    return match_post(topic, **event_fields(event))
```

</details>

<details>
<summary>Show example: step 6, the capture filter</summary>

```python
def capture_filter(topics: Iterable[Topic]) -> Callable[[dict], bool]:
    """The stream's default `keep` function: keep an event if any of these topics matches it.

    Deletes are always kept. A delete does not say what the post was, so the
    only way to honor it is to pass it on and let storage remove the post if
    it is there.
    """
    topics = list(topics)

    def keep(event: dict) -> bool:
        if event.get("operation") == "delete":
            return True
        fields = event_fields(event)
        return any(match_post(t, **fields) for t in topics)

    return keep
```

</details>

<details>
<summary>Show example: step 7, which entities a text mentions</summary>

```python
def entities_in(topic: Topic, text: str) -> list[str]:
    """The topic's entities whose keywords appear in the text."""
    return [name for name, words in topic.entities.items()
            if keyword_regex(tuple(words)).search(text)]
```

</details>

<details>
<summary>Show example: step 8, recording membership (bluesky_bots/topics/assign.py)</summary>

```python
from __future__ import annotations

from ..aturi import did_of
from .match import match_post
from .schema import Topic


def assign(store, topic: Topic) -> int:
    """Work out which stored posts are in the topic and save that as its membership.

    Replaces the topic's earlier membership, so it is safe to run again after
    the topic file changes. Returns how many posts are in the topic.
    """
    rows = []
    for post in store.iter_posts():
        linked = {did_of(u) for u in (post["reply_parent"], post["reply_root"], post["quote_of"]) if u}
        rule = match_post(topic, did=post["did"], text=post["text"] or "", linked=linked)
        if rule:
            rows.append({"uri": post["uri"], "matched_by": rule})
    store.set_post_topics(topic.name, rows)
    return len(rows)
```

</details>
