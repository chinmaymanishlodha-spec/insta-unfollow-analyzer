"""Unit tests for the pure set logic in analysis.py."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import Account, analyze, apply_whitelist, normalize


def _map(*usernames: str) -> dict[str, Account]:
    return {normalize(u): Account(username=u) for u in usernames}


def test_three_sets_basic():
    following = _map("alice", "Bob", "carol", "dave", "EVE")
    followers = _map("Alice", "bob", "Frank", "GRACE", "heidi")

    result = analyze(following, followers)

    assert [a.username for a in result.not_following_back] == ["carol", "dave", "EVE"]
    assert [a.username for a in result.not_followed_back] == ["Frank", "GRACE", "heidi"]
    assert [a.username for a in result.mutuals] == ["alice", "Bob"]
    assert result.counts == {
        "not_following_back": 3,
        "not_followed_back": 3,
        "mutuals": 2,
    }


def test_case_insensitive_matching():
    following = _map("CoolUser")
    followers = _map("cooluser")
    result = analyze(following, followers)
    # Same person despite case difference -> a mutual, nothing unfollowing-back.
    assert result.counts == {"not_following_back": 0, "not_followed_back": 0, "mutuals": 1}
    # Display value preserved from the following side.
    assert result.mutuals[0].username == "CoolUser"


def test_mutual_prefers_following_record_for_timestamp():
    following = {"x": Account("x", timestamp=111)}
    followers = {"x": Account("x", timestamp=999)}
    result = analyze(following, followers)
    assert result.mutuals[0].timestamp == 111


def test_empty_inputs():
    result = analyze({}, {})
    assert result.counts == {"not_following_back": 0, "not_followed_back": 0, "mutuals": 0}


def test_sorting_is_case_insensitive():
    following = _map("zoe", "Adam", "mike")
    followers = {}
    result = analyze(following, followers)
    assert [a.username for a in result.not_following_back] == ["Adam", "mike", "zoe"]


def test_apply_whitelist_removes_case_insensitively_and_strips_at():
    accounts = [Account("carol"), Account("Dave"), Account("EVE")]
    filtered = apply_whitelist(accounts, ["dave", "@EVE", "", "   "])
    assert [a.username for a in filtered] == ["carol"]


def test_apply_whitelist_noop_when_empty():
    accounts = [Account("carol"), Account("dave")]
    assert apply_whitelist(accounts, []) == accounts
