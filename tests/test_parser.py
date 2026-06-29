"""Unit tests for defensive parsing in parser.py.

Exercises both schema shapes, split follower parts, the ZIP path, loose files,
HTML detection, and case-insensitive merging.
"""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import analyze
from parser import (
    HTMLExportError,
    NoDataError,
    parse_files,
    parse_upload,
    parse_zip,
)

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")


def _item(username: str, ts: int = 0) -> dict:
    return {
        "string_list_data": [
            {"href": f"https://www.instagram.com/{username}", "value": username, "timestamp": ts}
        ]
    }


def _load_fixture_blobs() -> dict[str, bytes]:
    blobs = {}
    for name in ("following.json", "followers_1.json", "followers_2.json"):
        with open(os.path.join(SAMPLE_DIR, name), "rb") as fh:
            blobs[name] = fh.read()
    return blobs


def test_loose_fixture_counts_match_expected():
    parsed = parse_files(_load_fixture_blobs())
    result = analyze(parsed.following, parsed.followers)
    assert result.counts == {"not_following_back": 3, "not_followed_back": 3, "mutuals": 2}


def test_zip_fixture_counts_match_expected():
    with open(os.path.join(SAMPLE_DIR, "export.zip"), "rb") as fh:
        parsed = parse_zip(fh.read())
    result = analyze(parsed.following, parsed.followers)
    assert result.counts == {"not_following_back": 3, "not_followed_back": 3, "mutuals": 2}


def test_dict_wrapper_shape():
    blob = json.dumps({"relationships_following": [_item("a"), _item("b")]}).encode()
    parsed = parse_files({"following.json": blob})
    assert set(parsed.following) == {"a", "b"}


def test_top_level_list_shape():
    blob = json.dumps([_item("a"), _item("b")]).encode()
    parsed = parse_files({"followers_1.json": blob})
    assert set(parsed.followers) == {"a", "b"}


def test_old_followers_wrapper_key_shape():
    blob = json.dumps({"relationships_followers": [_item("a")]}).encode()
    parsed = parse_files({"followers.json": blob})
    assert set(parsed.followers) == {"a"}


def test_split_followers_are_merged():
    p1 = json.dumps([_item("a"), _item("b")]).encode()
    p2 = json.dumps([_item("c")]).encode()
    parsed = parse_files({"followers_1.json": p1, "followers_2.json": p2})
    assert set(parsed.followers) == {"a", "b", "c"}


def test_case_insensitive_merge_keys():
    blob = json.dumps([_item("CoolUser")]).encode()
    parsed = parse_files({"followers_1.json": blob})
    assert "cooluser" in parsed.followers
    assert parsed.followers["cooluser"].username == "CoolUser"


def test_nested_path_in_zip_is_found():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("deep/a/b/connections/followers_and_following/following.json",
                    json.dumps({"relationships_following": [_item("z")]}))
    parsed = parse_zip(buf.getvalue())
    assert set(parsed.following) == {"z"}


def test_html_export_detected():
    html = b"<!DOCTYPE html>\n<html><head><title>following</title></head></html>"
    with pytest.raises(HTMLExportError):
        parse_files({"following.json": html})


def test_no_data_raises():
    with pytest.raises(NoDataError):
        parse_files({"unrelated.json": json.dumps([_item("a")]).encode()})


def test_missing_string_list_data_skipped():
    # Restricted/omitted accounts can lack string_list_data -> skipped, no crash.
    blob = json.dumps([{"title": "x"}, _item("real")]).encode()
    parsed = parse_files({"followers_1.json": blob})
    assert set(parsed.followers) == {"real"}


def test_parse_upload_dispatches_zip_and_json():
    with open(os.path.join(SAMPLE_DIR, "export.zip"), "rb") as fh:
        zip_parsed = parse_upload("export.zip", fh.read())
    assert zip_parsed.following and zip_parsed.followers

    json_blob = json.dumps([_item("solo")]).encode()
    json_parsed = parse_upload("followers_1.json", json_blob)
    assert set(json_parsed.followers) == {"solo"}


def test_extras_parsed_from_loose_files():
    cf = json.dumps({"relationships_close_friends": [_item("a"), _item("b")]}).encode()
    parsed = parse_files(
        {"following.json": json.dumps([_item("x")]).encode(), "close_friends.json": cf}
    )
    assert "Close friends" in parsed.extras
    assert set(parsed.extras["Close friends"]) == {"a", "b"}


def test_extras_parsed_from_zip_fixture():
    with open(os.path.join(SAMPLE_DIR, "export.zip"), "rb") as fh:
        parsed = parse_zip(fh.read())
    assert "Close friends" in parsed.extras
    assert set(parsed.extras["Close friends"]) == {"alice", "carol"}


def test_extras_absent_when_not_present():
    parsed = parse_files({"following.json": json.dumps([_item("x")]).encode()})
    assert parsed.extras == {}


def test_recently_unfollowed_variant_name():
    blob = json.dumps([_item("z")]).encode()
    parsed = parse_files(
        {"following.json": json.dumps([_item("x")]).encode(),
         "recently_unfollowed_profiles.json": blob}
    )
    assert "Recently unfollowed" in parsed.extras


def test_timestamp_and_href_parsed():
    blob = json.dumps([_item("a", ts=1609459200)]).encode()
    parsed = parse_files({"following.json": blob})
    acct = parsed.following["a"]
    assert acct.timestamp == 1609459200
    assert acct.href == "https://www.instagram.com/a"
