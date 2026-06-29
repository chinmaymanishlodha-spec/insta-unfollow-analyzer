"""Generate realistic Instagram-export fixtures for testing.

Creates, alongside this script:
  * following.json   -> dict + 'relationships_following' wrapper shape
  * followers_1.json -> top-level LIST shape (no wrapper key)
  * followers_2.json -> top-level LIST shape (split second part)
  * export.zip       -> the three files nested under
                        connections/followers_and_following/

The data is deliberately constructed with mixed casing and known overlaps so the
expected analysis counts can be hand-computed (see EXPECTED below and the tests).

following  = {alice, Bob, carol, dave, EVE}          (5)
followers  = {alice, bob (part1), Frank, GRACE (part2), heidi}  (5)
                                       ^ split across two files
normalized following = {alice, bob, carol, dave, eve}
normalized followers = {alice, bob, frank, grace, heidi}

not_following_back = following - followers = {carol, dave, eve}   -> 3
not_followed_back  = followers - following = {frank, grace, heidi} -> 3
mutuals            = following & followers = {alice, bob}          -> 2
"""

from __future__ import annotations

import json
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

# (display_username, unix_timestamp)
FOLLOWING = [
    ("alice", 1609459200),   # 2021-01-01
    ("Bob", 1612137600),     # mutual, different case in followers
    ("carol", 1614556800),   # not following back
    ("dave", 1617235200),    # not following back
    ("EVE", 1619827200),     # not following back, upper case
]

FOLLOWERS_PART1 = [
    ("Alice", 1609459200),   # mutual, different case from following
    ("bob", 1612137600),     # mutual
    ("Frank", 1620000000),   # I don't follow back
]
FOLLOWERS_PART2 = [
    ("GRACE", 1625000000),   # I don't follow back (split part)
    ("heidi", 1626000000),   # I don't follow back
]

EXPECTED = {
    "not_following_back": 3,   # carol, dave, eve
    "not_followed_back": 3,    # frank, grace, heidi
    "mutuals": 2,              # alice, bob
}


def _item(username: str, timestamp: int) -> dict:
    """Build a single relationship item in Instagram's shape."""
    return {
        "title": "",
        "media_list_data": [],
        "string_list_data": [
            {
                "href": f"https://www.instagram.com/{username}",
                "value": username,
                "timestamp": timestamp,
            }
        ],
    }


def build() -> None:
    # following.json -> dict-with-relationships_* shape
    following_obj = {"relationships_following": [_item(u, t) for u, t in FOLLOWING]}
    # followers_*.json -> top-level LIST shape
    followers1 = [_item(u, t) for u, t in FOLLOWERS_PART1]
    followers2 = [_item(u, t) for u, t in FOLLOWERS_PART2]

    files = {
        "following.json": following_obj,
        "followers_1.json": followers1,
        "followers_2.json": followers2,
    }
    for name, obj in files.items():
        path = os.path.join(HERE, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2)

    # export.zip nesting the files at the real export depth
    zip_path = os.path.join(HERE, "export.zip")
    nested = "connections/followers_and_following"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, obj in files.items():
            zf.writestr(f"{nested}/{name}", json.dumps(obj, indent=2))

    print("Wrote fixtures to", HERE)
    for name in list(files) + ["export.zip"]:
        print("  -", name)
    print("Expected counts:", EXPECTED)


if __name__ == "__main__":
    build()
