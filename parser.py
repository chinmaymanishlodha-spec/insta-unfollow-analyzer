"""Defensive parsing of Instagram 'Download Your Information' exports.

Handles the real-world messiness of the export format:

* Files may arrive as a ZIP (with the JSONs nested anywhere in the tree) or as
  loose uploaded JSON files.
* Followers are frequently split across ``followers_1.json``, ``followers_2.json``,
  ... — all parts must be merged.
* Schema asymmetry: a relationship file may be EITHER
    - a top-level JSON **list** of relationship items, OR
    - a JSON **object** with a single ``relationships_*`` key whose value is the
      list of items.
  Either shape can appear for either followers or following depending on the
  account/export era, so we branch on what we actually observe.
* Each relationship item carries ``string_list_data: [{href, value, timestamp}]``
  where ``value`` is the username.
* HTML exports are detected and rejected with a clear, actionable message.

Nothing here writes the social graph to disk or makes network calls.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import PurePosixPath
from typing import Iterable, Optional, Union

from analysis import Account, normalize


class HTMLExportError(Exception):
    """Raised when the user supplied an HTML export instead of JSON."""


class NoDataError(Exception):
    """Raised when no recognizable followers/following files were found."""


# Basename prefixes we care about (case-insensitive), checked against the file
# stem so both ``following.json`` and ``following_1.json`` match.
_FOLLOWING_PREFIX = "following"
_FOLLOWERS_PREFIX = "followers"


def _looks_like_html(raw: bytes) -> bool:
    """Heuristically detect an HTML export by sniffing the leading bytes."""

    head = raw.lstrip()[:512].lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<head" in head[:200]


def _classify(filename: str) -> Optional[str]:
    """Classify a file path as 'following', 'followers', or None.

    Matching is done on the *basename stem* (lowercased) so nested paths and the
    split-part suffixes (``_1``, ``_2``) are handled. Only ``.json`` files count.
    """

    name = PurePosixPath(filename.replace("\\", "/")).name.lower()
    if not name.endswith(".json"):
        return None
    stem = name[: -len(".json")]
    # `following`/`following_1` vs `followers`/`followers_1`. Order matters:
    # check the longer prefix ("followers") first since both start with "follow".
    if stem.startswith(_FOLLOWERS_PREFIX):
        return "followers"
    if stem.startswith(_FOLLOWING_PREFIX):
        return "following"
    return None


def _extract_items(payload: object) -> list[dict]:
    """Pull the list of relationship items from either schema shape.

    Accepts:
      * a top-level ``list`` -> returned (filtered to dict items), or
      * a ``dict`` with a ``relationships_*`` key -> that key's list value.

    Returns an empty list for anything unrecognized rather than raising, so a
    stray/empty file never crashes the whole parse.
    """

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        # Prefer an explicit relationships_* wrapper key.
        for key, value in payload.items():
            if key.startswith("relationships_") and isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        # Fallback: some exports may wrap under another single list-valued key.
        for value in payload.values():
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _accounts_from_items(items: Iterable[dict]) -> dict[str, Account]:
    """Convert raw relationship items into a normalized-username -> Account map.

    Each item is expected to have ``string_list_data`` (a list); the username is
    the ``value`` field of its first entry. Items missing this are skipped (this
    is the shape Instagram uses for omitted/restricted accounts). On duplicate
    usernames the first occurrence wins.
    """

    accounts: dict[str, Account] = {}
    for item in items:
        sld = item.get("string_list_data")
        if not isinstance(sld, list) or not sld:
            continue
        entry = sld[0]
        if not isinstance(entry, dict):
            continue
        username = entry.get("value")
        if not username or not isinstance(username, str):
            continue
        key = normalize(username)
        if key in accounts:
            continue
        ts = entry.get("timestamp")
        accounts[key] = Account(
            username=username,
            href=entry.get("href") or None,
            timestamp=int(ts) if isinstance(ts, (int, float)) and ts else None,
        )
    return accounts


def _parse_json_bytes(raw: bytes, *, source: str) -> list[dict]:
    """Decode JSON bytes into relationship items, detecting HTML exports."""

    if _looks_like_html(raw):
        raise HTMLExportError(
            f"'{source}' looks like an HTML export. Please re-download your "
            "information from Instagram choosing the JSON format (Accounts "
            "Center -> Download your information -> Format: JSON)."
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise NoDataError(f"Could not parse '{source}' as JSON: {exc}") from exc
    return _extract_items(payload)


# --- Public API ------------------------------------------------------------


class ParsedExport:
    """Result of parsing an export: following + followers account maps.

    Attributes:
        following: normalized-username -> Account for accounts I follow.
        followers: normalized-username -> Account for accounts following me.
        sources: human-readable list of file names that contributed data.
    """

    def __init__(
        self,
        following: dict[str, Account],
        followers: dict[str, Account],
        sources: list[str],
    ) -> None:
        self.following = following
        self.followers = followers
        self.sources = sources


def parse_files(named_blobs: dict[str, bytes]) -> ParsedExport:
    """Parse a collection of named JSON blobs (loose files or unzipped members).

    Args:
        named_blobs: Map of filename (may include path) -> raw file bytes.

    Returns:
        ParsedExport with merged following/followers maps.

    Raises:
        HTMLExportError: if any relevant file is an HTML export.
        NoDataError: if no followers/following JSON files are found.
    """

    following: dict[str, Account] = {}
    followers: dict[str, Account] = {}
    sources: list[str] = []

    for name, raw in named_blobs.items():
        kind = _classify(name)
        if kind is None:
            continue
        items = _parse_json_bytes(raw, source=PurePosixPath(name.replace("\\", "/")).name)
        accounts = _accounts_from_items(items)
        if not accounts:
            continue
        target = following if kind == "following" else followers
        for key, acct in accounts.items():
            target.setdefault(key, acct)  # merge split parts; first wins
        sources.append(f"{PurePosixPath(name.replace(chr(92), '/')).name} ({kind}, {len(accounts)})")

    if not following and not followers:
        raise NoDataError(
            "No 'followers_*.json' or 'following*.json' files were found in the "
            "upload. Make sure you exported 'Followers and following' in JSON "
            "format and uploaded the ZIP or those JSON files."
        )
    return ParsedExport(following, followers, sources)


def parse_zip(data: Union[bytes, io.BytesIO, "zipfile.ZipFile"]) -> ParsedExport:
    """Parse an Instagram export ZIP, locating relevant JSONs anywhere in it.

    Args:
        data: ZIP content as raw bytes, a BytesIO, or an open ZipFile.

    Returns:
        ParsedExport with merged following/followers maps.
    """

    own = False
    if isinstance(data, zipfile.ZipFile):
        zf = data
    else:
        buf = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
        zf = zipfile.ZipFile(buf)
        own = True

    try:
        named_blobs: dict[str, bytes] = {}
        for info in zf.infolist():
            if info.is_dir():
                continue
            if _classify(info.filename) is None:
                continue
            named_blobs[info.filename] = zf.read(info)
        return parse_files(named_blobs)
    finally:
        if own:
            zf.close()


def parse_upload(filename: str, raw: bytes) -> ParsedExport:
    """Dispatch a single uploaded file to the ZIP or single-JSON parser."""

    lower = filename.lower()
    if lower.endswith(".zip") or zipfile.is_zipfile(io.BytesIO(raw)):
        return parse_zip(raw)
    return parse_files({filename: raw})
