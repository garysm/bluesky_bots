"""docs/09-narratives.md. Made-up vectors stand in for an embedding model, and a function for the naming model."""
from datetime import date, datetime, timezone

import numpy as np
import pytest

from bluesky_bots.narratives import (assign_ids, centroids, cluster, embed_posts, match_to_previous,
                                     run_topic, typical)

from conftest import make_topic, post_row

DIM = 16


def blobs(n_topics: int, per_topic: int, seed: int = 0):
    """Unit vectors gathered around n_topics different directions, and the group each belongs to."""
    rng = np.random.default_rng(seed)
    centers = np.eye(DIM)[:n_topics]
    x = np.vstack([rng.normal(c, 0.05, (per_topic, DIM)) for c in centers]).astype(np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True), np.repeat(np.arange(n_topics), per_topic)


def test_cluster_finds_planted_groups_and_leaves_noise_out():
    x, truth = blobs(3, 40)
    noise = np.random.default_rng(5).normal(0, 1, (10, DIM)).astype(np.float32)
    x = np.vstack([x, noise / np.linalg.norm(noise, axis=1, keepdims=True)])
    labels = cluster(x, min_size=10)
    assert len(set(labels.tolist()) - {-1}) == 3                         # three groups, without being told how many
    for group in range(3):
        assert len(set(labels[:120][truth == group].tolist())) == 1     # each planted group stays together
    assert (labels[120:] == -1).any()                                    # some scattered points join no group


def test_centroids_are_unit_length_and_closest_to_their_own_posts():
    x, truth = blobs(3, 40)
    cents = centroids(x, truth)
    assert set(cents) == {0, 1, 2}
    for k, c in cents.items():
        assert np.isclose(np.linalg.norm(c), 1.0)
        assert set(truth[np.argsort(-(x @ c))[:40]].tolist()) == {k}
    assert -1 not in centroids(x, np.full(len(x), -1))
    assert typical(x, truth, 1, cents[1], n=5) == [int(i) for i in np.argsort(-(x @ cents[1]))[:5]]


def test_match_to_previous():
    x, truth = blobs(3, 40)
    cents = centroids(x, truth)
    assert match_to_previous(cents, cents) == {0: 0, 1: 1, 2: 2}
    assert match_to_previous(cents, {}) == {0: None, 1: None, 2: None}
    renumbered = {7: cents[2], 8: cents[0]}
    assert match_to_previous(cents, renumbered) == {0: 8, 1: None, 2: 7}


def test_assign_ids():
    assert assign_ids({0: 8, 1: None, 2: 7}, next_id=9) == {0: 8, 1: 9, 2: 7}
    assert assign_ids({0: None, 1: None}, next_id=0) == {0: 0, 1: 1}
    assert assign_ids({0: 5, 1: 5}, next_id=6) == {0: 5, 1: 6}         # one id never names two groups


def test_embed_posts_embeds_each_post_once(mem):
    calls = []

    def fake(texts):
        calls.append(list(texts))
        return np.array([[len(t), 1.0] for t in texts], dtype=np.float32)

    posts = [{"uri": "at://x/1", "text": "a"}, {"uri": "at://x/2", "text": "bbb"}]
    first = embed_posts(mem, posts, "m", fake)
    assert first.shape == (2, 2) and calls == [["a", "bbb"]]
    more = posts[::-1] + [{"uri": "at://x/3", "text": "cc"}]
    second = embed_posts(mem, more, "m", fake)
    assert calls == [["a", "bbb"], ["cc"]]                               # only the new post was embedded
    assert second[:, 0].tolist() == [3.0, 1.0, 2.0]                      # rows follow the order of the posts
    assert embed_posts(mem, [], "m", fake).shape[0] == 0


def test_run_topic_keeps_ids_and_names_from_day_to_day(mem):
    topic = make_topic(narratives={"min_cluster_size": 10})
    x, truth = blobs(3, 30)
    vectors, rows = {}, []
    for n, (v, group) in enumerate(zip(x, truth)):
        text = f"group {group} post number {n:03d} padded out past forty characters"
        vectors[text] = v
        rows.append(post_row(n, text=text, created_at=datetime(2026, 11, 4, 12, tzinfo=timezone.utc)))
    rows.append(post_row(500, text="too short", created_at=datetime(2026, 11, 4, 12, tzinfo=timezone.utc)))
    mem.add_posts(rows)
    mem.set_post_topics(topic.name, [{"uri": r["uri"], "matched_by": "keyword"} for r in rows])

    named = []

    def namer(sample):
        named.append(sample)
        return {"name": "about group " + sample[0].split()[1], "summary": "s"}

    def embed_fn(texts):
        return np.array([vectors[t] for t in texts])

    day1 = run_topic(mem, topic, today=date(2026, 11, 5), model="m", embed_fn=embed_fn, namer=namer)
    assert day1 == {"posts": 90, "narratives": 3, "unclustered": 0}
    first = mem.narrative_run(topic.name)
    names = {n["narrative_id"]: n["name"] for n in first["narratives"]}
    assert sorted(names.values()) == ["about group 0", "about group 1", "about group 2"]
    assert len(named) == 3 and all(len(sample) == 15 for sample in named)
    assert sum(n["n_posts"] for n in first["narratives"]) == 90 == len(first["assignments"])

    day2 = run_topic(mem, topic, today=date(2026, 11, 6), model="m", embed_fn=embed_fn, namer=namer)
    second = mem.narrative_run(topic.name)
    assert day2["narratives"] == 3 and second["run_date"] == date(2026, 11, 6)
    assert {n["narrative_id"]: n["name"] for n in second["narratives"]} == names
    assert len(named) == 3                                               # continuing narratives are not renamed
    where1 = {a["uri"]: a["narrative_id"] for a in first["assignments"]}
    where2 = {a["uri"]: a["narrative_id"] for a in second["assignments"]}
    assert where1 == where2


def test_run_topic_with_too_few_posts(mem, topic):
    mem.add_posts([post_row(1, text="x" * 50)])
    mem.set_post_topics(topic.name, [{"uri": post_row(1)["uri"], "matched_by": "keyword"}])
    result = run_topic(mem, topic, today=date(2026, 11, 5), model="m",
                       embed_fn=lambda texts: pytest.fail("should not embed"))
    assert result == {"posts": 1, "narratives": 0, "unclustered": 1}
