"""docs/10-signals.md. Each signal is tested on data planted to trip it, and on data that should not."""
import random
import string
from datetime import date, datetime, timedelta, timezone

from bluesky_bots.signals import (account_age, behavior_shift, bursts, compute_signals,
                                  near_duplicate_groups, near_duplicates, normalize,
                                  synchronized_reposts)

from conftest import POST, post_row

T0 = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


def posts_at(did, times, start=0):
    return [post_row(start + i, did=did, created_at=t) for i, t in enumerate(times)]


def test_account_age(mem):
    mem.upsert_accounts([{"did": "did:plc:new", "created_at": T0 - timedelta(days=3)},
                         {"did": "did:plc:old", "created_at": T0 - timedelta(days=900)},
                         {"did": "did:plc:undated"}])
    mem.add_posts(posts_at("did:plc:new", [T0, T0 + timedelta(days=60)]) + posts_at("did:plc:old", [T0])
                  + posts_at("did:plc:undated", [T0]))
    rows = account_age(mem.analytics())
    assert [(r["did"], r["signal"], r["value"]) for r in rows] == [("did:plc:new", "account_age", 3)]
    assert rows[0]["evidence"] == {"age_days_at_first_post": 3}


def test_bursts(mem):
    fast = [T0 + timedelta(seconds=30 * i) for i in range(16)]            # 16 posts in 8 minutes
    slow = [T0 + timedelta(minutes=5 * i) for i in range(16)]
    mem.add_posts(posts_at("did:plc:fast", fast) + posts_at("did:plc:slow", slow))
    rows = bursts(mem.analytics())
    assert [(r["did"], r["value"]) for r in rows] == [("did:plc:fast", 16)]
    assert rows[0]["window_start"] == T0 and rows[0]["evidence"] == {"posts": 16, "window_minutes": 10}


def test_synchronized_reposts(mem):
    reposts = []
    for i in range(6):
        subject, when = f"at://did:plc:src/{POST}/{i}", T0 + timedelta(hours=i)
        for did, lag in (("did:plc:a", 0), ("did:plc:b", 20), ("did:plc:late", 600)):
            reposts.append({"uri": f"at://{did}/app.bsky.feed.repost/{i}", "did": did,
                            "subject_uri": subject, "created_at": when + timedelta(seconds=lag)})
    mem.add_reposts(reposts)
    rows = sorted(synchronized_reposts(mem.analytics()), key=lambda r: r["did"])
    assert [r["did"] for r in rows] == ["did:plc:a", "did:plc:b"]
    assert rows[0]["evidence"] == {"partners": 1, "most_reposts_together": 6, "within_seconds": 60}
    assert "did:plc:b" not in str(rows[0]["evidence"])                    # partners are counted, not named


def test_behavior_shift(mem):
    today, rows = date(2026, 11, 13), []
    n = 0
    for did, recent in (("did:plc:surge", 40), ("did:plc:steady", 2)):
        for back in range(8, 68):                                         # the 60 days before last week
            day = datetime.combine(today - timedelta(days=back), datetime.min.time(), timezone.utc)
            for k in range(1 + back % 3):                                 # one to three posts a day
                rows.append(post_row(n, did=did, created_at=day + timedelta(hours=k)))
                n += 1
        for back in range(0, 7):
            day = datetime.combine(today - timedelta(days=back), datetime.min.time(), timezone.utc)
            for k in range(recent):
                rows.append(post_row(n, did=did, created_at=day + timedelta(minutes=k)))
                n += 1
    mem.add_posts(rows)
    found = behavior_shift(mem.analytics(), today=today)
    assert [r["did"] for r in found] == ["did:plc:surge"]
    assert found[0]["value"] >= 4 and found[0]["evidence"]["posts_per_day_last_7"] == 40.0


def test_normalize():
    assert normalize("Call NOW https://example.com/x  @some.one   today") == "call now today"


def planted():
    sentence = "Everyone needs to see what they did in the budget vote last night, share this widely"
    same = [(f"at://did:plc:c{i}/{POST}/1", f"did:plc:c{i}", f"{sentence} https://t.example/{i} @user{i}.example")
            for i in range(5)]
    rng = random.Random(0)                                               # twenty texts with nothing in common
    other = [(f"at://did:plc:o{i}/{POST}/1", f"did:plc:o{i}",
              " ".join("".join(rng.choices(string.ascii_lowercase, k=6)) for _ in range(14)))
             for i in range(20)]
    return same, other


def test_near_duplicate_groups():
    same, other = planted()
    groups = near_duplicate_groups(same + other)
    assert groups == [{uri for uri, _, _ in same}]
    one_person = [(f"at://did:plc:solo/{POST}/{i}", "did:plc:solo", text) for i, (_, _, text) in enumerate(same)]
    assert near_duplicate_groups(one_person + other) == []               # one account repeating itself is not a group
    short = [(f"at://did:plc:s{i}/{POST}/1", f"did:plc:s{i}", "this.") for i in range(9)]
    assert near_duplicate_groups(short) == []


def test_near_duplicates_evidence_has_no_names():
    same, other = planted()
    rows = near_duplicates(same + other)
    assert sorted(r["did"] for r in rows) == [f"did:plc:c{i}" for i in range(5)]
    evidence = rows[0]["evidence"]
    assert evidence["accounts"] == 5 and evidence["posts"] == 5 and evidence["text"].startswith("everyone needs")
    assert "did:" not in str(evidence) and "@" not in evidence["text"] and "http" not in evidence["text"]


def test_compute_signals_saves_rows_and_two_kinds_flag_an_account(mem):
    mem.upsert_accounts([{"did": "did:plc:both", "created_at": T0 - timedelta(days=2)},
                         {"did": "did:plc:burst-only", "created_at": T0 - timedelta(days=900)}])
    quick = [T0 + timedelta(seconds=20 * i) for i in range(15)]
    mem.add_posts(posts_at("did:plc:both", quick) + posts_at("did:plc:burst-only", quick, start=100))
    counts = compute_signals(mem)
    assert counts == {"account_age": 1, "burst": 2}
    assert len(list(mem.export_table("signals"))) == 3
    assert mem.analytics().execute("SELECT did FROM flagged").fetchall() == [("did:plc:both",)]
