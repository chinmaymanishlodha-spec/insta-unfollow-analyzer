"""Pure set logic for the follower analysis. No I/O — fully unit-testable.

The functions here operate on dictionaries that map a *normalized* (lowercase)
username to an :class:`Account` record holding the original-cased display value
and optional metadata (profile href, followed-on timestamp).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Account:
    """A single Instagram account as it appears in an export file.

    Attributes:
        username: Original-cased username as exported (used for display).
        href: Profile URL from the export, if present.
        timestamp: Unix epoch seconds for the relationship event (follow date),
            if present. May be ``None`` or ``0`` when omitted by Instagram.
    """

    username: str
    href: Optional[str] = None
    timestamp: Optional[int] = None


@dataclass
class AnalysisResult:
    """Container for the three computed relationship sets.

    Each list holds :class:`Account` records sorted by username (case-insensitive).
    """

    not_following_back: list[Account] = field(default_factory=list)
    not_followed_back: list[Account] = field(default_factory=list)
    mutuals: list[Account] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "not_following_back": len(self.not_following_back),
            "not_followed_back": len(self.not_followed_back),
            "mutuals": len(self.mutuals),
        }


def normalize(username: str) -> str:
    """Normalize a username for case-insensitive matching.

    Instagram usernames are case-insensitive; exports sometimes differ in case
    between the followers and following files. We match on the lowercased,
    stripped value but always *display* the original case.
    """

    return username.strip().lower()


def _sorted_accounts(accounts: dict[str, Account]) -> list[Account]:
    """Return accounts sorted case-insensitively by display username."""

    return [accounts[k] for k in sorted(accounts, key=str.lower)]


def analyze(
    following: dict[str, Account],
    followers: dict[str, Account],
) -> AnalysisResult:
    """Compute the three relationship sets from following/followers maps.

    Args:
        following: Map of normalized-username -> Account for accounts *I follow*.
        followers: Map of normalized-username -> Account for accounts that
            *follow me*.

    Returns:
        AnalysisResult where:
          * ``not_following_back`` = following - followers  (headline list)
          * ``not_followed_back``  = followers - following
          * ``mutuals``            = following ∩ followers

        For each set we keep the Account record from the side that is most
        informative: the ``following`` record carries the follow-date timestamp,
        so it is preferred for ``not_following_back`` and ``mutuals``.
    """

    following_keys = set(following)
    followers_keys = set(followers)

    not_following_back = {k: following[k] for k in (following_keys - followers_keys)}
    not_followed_back = {k: followers[k] for k in (followers_keys - following_keys)}
    # For mutuals, prefer the `following` record (has the follow timestamp).
    mutuals = {k: following[k] for k in (following_keys & followers_keys)}

    return AnalysisResult(
        not_following_back=_sorted_accounts(not_following_back),
        not_followed_back=_sorted_accounts(not_followed_back),
        mutuals=_sorted_accounts(mutuals),
    )


def apply_whitelist(accounts: list[Account], whitelist: list[str]) -> list[Account]:
    """Filter out whitelisted usernames (case-insensitive) from a list.

    Args:
        accounts: List of Account records (e.g. the headline unfollow candidates).
        whitelist: Raw usernames to keep/exclude from the candidate list. Entries
            may include surrounding whitespace, ``@`` prefixes, or blank lines;
            these are normalized before comparison.

    Returns:
        A new list with any account whose normalized username is in the
        whitelist removed.
    """

    excluded = {normalize(w.lstrip("@")) for w in whitelist if w.strip()}
    return [a for a in accounts if normalize(a.username) not in excluded]
