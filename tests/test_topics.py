"""docs/02-topics.md"""
from pathlib import Path

import pytest

from bluesky_bots.aturi import at_uri, did_of, quoted_uri
from bluesky_bots.topics import (Topic, assign, capture_filter, entities_in, keyword_regex,
                                 load_topic, load_topics, match_event, match_post, match_text,
                                 resolve_accounts)

from conftest import POST, REPOST, WATCHED, ev, make_topic, post_row

TOPICS_DIR = Path(__file__).parent.parent / "topics"
THEIRS = {"uri": f"at://{WATCHED}/{POST}/abc"}                    # a post by a watched account
OTHER = {"uri": f"at://did:plc:nobody/{POST}/xyz"}                # someone else's post


def test_example_topic_files_are_valid():
    topics = load_topics(TOPICS_DIR)
    assert {t.name for t in topics} >= {"dem-leadership", "example-remote-work"}
    assert [t.name for t in load_topics(TOPICS_DIR, active_only=True)] == ["dem-leadership"]


def test_a_misspelled_key_is_an_error(tmp_path):
    (tmp_path / "bad.yaml").write_text("name: bad\nmatch: {keywrods: [x]}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bad.yaml"):
        load_topic(tmp_path / "bad.yaml")


def test_unsure_must_be_one_of_the_values():
    with pytest.raises(ValueError):
        make_topic(labels={"version": "v", "instruction": "x",
                           "dimensions": {"stance": {"values": ["a", "b"], "unsure": "c"}}})


def test_aturi_helpers():
    e = ev("did:plc:a", rkey="3k")
    assert at_uri(e) == f"at://did:plc:a/{POST}/3k"
    assert did_of(at_uri(e)) == "did:plc:a"
    assert quoted_uri({"embed": {"record": THEIRS}}) == THEIRS["uri"]
    assert quoted_uri({"embed": {"record": {"record": THEIRS}, "media": {}}}) == THEIRS["uri"]
    assert quoted_uri({"embed": {"images": []}}) is None
    assert quoted_uri({}) is None


def test_keywords_match_whole_words_only(topic):
    assert match_text(topic, "What is SCHUMER doing?")
    assert not match_text(topic, "schumerism is not a word")
    assert not match_text(topic, "good morning")


def test_keywords_can_be_phrases_and_symbols():
    t = make_topic(match={"keywords": ["remote work", "#rto"], "patterns": [r"\bWFH\b"]})
    assert match_text(t, "I love Remote Work, honestly")
    assert match_text(t, "back in the office #RTO")
    assert match_text(t, "wfh today")
    assert not match_text(t, "remote workers unite")
    assert keyword_regex((), ()) is None


def test_match_post_names_the_rule(topic):
    assert match_post(topic, did=WATCHED, text="good morning") == "account"
    assert match_post(topic, did="did:plc:x", text="Jeffries spoke") == "keyword"
    assert match_post(topic, did="did:plc:x", text="agreed", linked={WATCHED}) == "linked"
    assert match_post(topic, did="did:plc:x", text="agreed", linked={"did:plc:y"}) is None


# The rules of the original capture filter, one case per row of the table in the guide.
CASES = [
    (ev("did:plc:stranger", operation="delete"), True),
    (ev(WATCHED, text="good morning"), True),
    (ev("did:plc:stranger", text="good morning"), False),
    (ev("did:plc:stranger", text="What is SCHUMER doing?"), True),
    (ev("did:plc:stranger", text="schumerism is not a word"), False),
    (ev("did:plc:stranger", REPOST, subject=THEIRS), True),
    (ev("did:plc:stranger", REPOST, subject=OTHER), False),
    (ev("did:plc:stranger", text="agreed", reply={"parent": OTHER, "root": THEIRS}), True),
    (ev("did:plc:stranger", text="agreed", reply={"parent": OTHER, "root": OTHER}), False),
    (ev("did:plc:stranger", text="look", embed={"record": THEIRS}), True),
    (ev("did:plc:stranger", text="look", embed={"record": {"record": THEIRS}, "media": {}}), True),
    (ev("did:plc:stranger", text="look", embed={"record": OTHER}), False),
    (ev("did:plc:stranger", text="a photo", embed={"images": []}), False),
]


@pytest.mark.parametrize("event,expected", CASES)
def test_capture_filter(topic, event, expected):
    assert capture_filter([topic])(event) is expected


def test_capture_filter_is_the_union_of_topics(topic):
    other = make_topic(name="other", match={"keywords": ["weather"]}, entities={})
    keep = capture_filter([topic, other])
    assert keep(ev("did:plc:x", text="lovely weather"))
    assert keep(ev("did:plc:x", text="Schumer again"))
    assert not keep(ev("did:plc:x", text="lunch"))
    assert not capture_filter([])(ev("did:plc:x", text="Schumer again"))
    assert capture_filter([])(ev("did:plc:x", operation="delete"))


def test_match_event_survives_a_malformed_record(topic):
    assert match_event(topic, ev("did:plc:x", REPOST)) is None           # a repost with no subject
    assert match_event(topic, ev("did:plc:x", reply={})) is None


def test_entities_in(topic):
    assert entities_in(topic, "Schumer and Jeffries met") == ["schumer", "jeffries"]
    assert entities_in(topic, "Jeffries spoke") == ["jeffries"]
    assert entities_in(topic, "nobody") == []


def test_resolve_accounts_uses_and_fills_the_cache(tmp_path):
    t = make_topic(match={"accounts": ["did:plc:known", "someone.example"]})
    assert t.dids == {"did:plc:known"} and t.handles == ["someone.example"]
    calls = []

    def resolve(handle):
        calls.append(handle)
        return "did:plc:resolved"

    resolve_accounts([t], resolve, tmp_path / "dids.json")
    assert t.dids == {"did:plc:known", "did:plc:resolved"}
    again = make_topic(match={"accounts": ["someone.example"]})
    resolve_accounts([again], resolve, tmp_path / "dids.json")
    assert again.dids == {"did:plc:resolved"} and calls == ["someone.example"]


def test_assign_records_membership_and_can_be_rerun(mem, topic):
    mem.add_posts([
        post_row(1, text="Schumer caved again"),
        post_row(2, text="lovely weather"),
        post_row(3, did=WATCHED, text="good morning"),
        post_row(4, text="agreed", reply_root=THEIRS["uri"]),
    ])
    assert assign(mem, topic) == 3
    rules = {r["uri"].rsplit("/", 1)[1]: r["matched_by"] for r in mem.export_table("post_topic")}
    assert rules == {"1": "keyword", "3": "account", "4": "linked"}

    narrower = make_topic(match={"keywords": ["weather"]})          # the topic file changed
    assert assign(mem, narrower) == 1
    assert [r["uri"].rsplit("/", 1)[1] for r in mem.export_table("post_topic")] == ["2"]
