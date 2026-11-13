"""What a topic file may contain, and how topic files are loaded.

A topic is one YAML file in topics/. It says which posts belong to a
conversation and how those posts should be labeled. Everything else in the
project takes a topic as input; nothing else names a subject.

A misspelled or unknown key is an error, so a typo cannot silently change
what is collected.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .. import config

_NAME = r"^[a-z0-9][a-z0-9-]*$"         # topic names: lower case, digits, hyphens
_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")   # dimension names become field names


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MatchRules(_Strict):
    """A post is in the topic when any one rule matches."""
    keywords: list[str] = []     # whole words or phrases, any case
    patterns: list[str] = []     # regular expressions, for what keywords cannot say
    accounts: list[str] = []     # handles or DIDs: their posts, and replies to, quotes and reposts of them


class Dimension(_Strict):
    """One question asked of every post, with a closed set of answers."""
    values: list[str] = Field(min_length=2)
    unsure: str | None = None    # the value that means "cannot tell"; sends the post to review

    @model_validator(mode="after")
    def _check(self):
        if len(set(self.values)) != len(self.values):
            raise ValueError("values must be different from each other")
        if self.unsure is not None and self.unsure not in self.values:
            raise ValueError(f"unsure value '{self.unsure}' is not one of the values")
        return self


class LabelScheme(_Strict):
    version: str                 # recorded with every label; change it when anything below changes
    instruction: str             # topic-specific wording, added to the base instruction in classify
    dimensions: dict[str, Dimension] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self):
        for name in self.dimensions:
            if not _IDENT.match(name) or name in ("i", "entities"):
                raise ValueError(f"dimension name '{name}' must be lower_case and not 'i' or 'entities'")
        return self


class NarrativeSettings(_Strict):
    min_cluster_size: int = 25   # the smallest group of posts worth calling a narrative


class Marker(_Strict):
    """A dated line drawn on this topic's charts."""
    date: datetime.date
    label: str


class Topic(_Strict):
    name: str = Field(pattern=_NAME)
    title: str = ""
    active: bool = True          # inactive topics are loaded but not captured
    match: MatchRules = MatchRules()
    search: list[str] = []       # queries for the backfill service; defaults to the keywords
    entities: dict[str, list[str]] = {}   # optional: named things a label can be about -> their keywords
    labels: LabelScheme | None = None
    narratives: NarrativeSettings = NarrativeSettings()
    markers: list[Marker] = []
    dids: set[str] = set()       # the accounts as DIDs; filled in when the topic is loaded

    @model_validator(mode="after")
    def _check(self):
        for pattern in self.match.patterns:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"pattern {pattern!r} is not a valid regular expression: {e}") from None
        for entity in self.entities:
            if not entity or entity != entity.strip():
                raise ValueError("entity names must not be empty or padded with spaces")
        self.dids |= {a for a in self.match.accounts if a.startswith("did:")}
        if not self.search:
            self.search = list(self.match.keywords)
        return self

    @property
    def handles(self) -> list[str]:
        """Accounts written as handles, which still need resolving to DIDs."""
        return [a for a in self.match.accounts if not a.startswith("did:")]


def load_topic(path: str | Path) -> Topic:
    """Read and check one topic file."""
    path = Path(path)
    try:
        return Topic(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    except Exception as e:
        raise ValueError(f"{path.name}: {e}") from e


def load_topics(directory: str | Path | None = None, active_only: bool = False) -> list[Topic]:
    """Every topic in the topics directory, in file-name order."""
    topics, seen = [], {}
    for path in sorted(Path(directory or config.TOPICS_DIR).glob("*.yaml")):
        topic = load_topic(path)
        if topic.name in seen:
            raise ValueError(f"{path.name} and {seen[topic.name]} both define topic '{topic.name}'")
        seen[topic.name] = path.name
        if topic.active or not active_only:
            topics.append(topic)
    return topics


def get_topic(name: str, directory: str | Path | None = None) -> Topic:
    """The topic with this name."""
    for topic in load_topics(directory):
        if topic.name == name:
            return topic
    raise KeyError(f"no topic named '{name}' in {directory or config.TOPICS_DIR}")
