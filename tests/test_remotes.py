"""Unit tests for remote identity normalization/matching."""

from __future__ import annotations

import pytest

from specrunway.remotes import normalize_identity, normalize_remote_url, remote_matches

CASES = [
    ("gitspecrunway:example.org/repo-a", "https://gitspecrunway.com/example.org/repo-a.git", True),
    ("gitspecrunway:example.org/repo-a", "git@gitspecrunway.com:example.org/repo-b.git", False),
    ("gitspecrunway:example.org/repo-a", "ssh://git@gitspecrunway.com/example.org/repo-a.git", True),
    ("https://example.org/acme/lib.git", "https://example.org/acme/lib.git", True),
    ("https://example.org/acme/lib.git", "https://example.org/acme/other.git", False),
    ("git@gitspecrunway.com:example.org/repo-b.git", "git@gitspecrunway.com:example.org/repo-b.git", True),
    ("gitspecrunway:example.org/repo-a", "https://gitspecrunway.com/example.org/repo-a", True),
]


@pytest.mark.parametrize("identity,url,expected", CASES)
def test_matches(identity: str, url: str, expected: bool):
    assert remote_matches(identity, url) is expected


def test_normalize_identity_shorthand():
    assert normalize_identity("gitspecrunway:example.org/repo-a") == (
        "gitspecrunway.com",
        "example.org/repo-a",
    )


def test_normalize_url_scp():
    assert normalize_remote_url("git@gitspecrunway.com:example.org/repo-b.git") == (
        "gitspecrunway.com",
        "example.org/repo-b.git",
    )
