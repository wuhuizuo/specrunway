"""Unit tests for remote identity normalization/matching."""

from __future__ import annotations

import pytest

from hubcoord.remotes import normalize_identity, normalize_remote_url, remote_matches

CASES = [
    ("github:example.org/repo-a", "https://github.com/example.org/repo-a.git", True),
    ("github:example.org/repo-a", "git@github.com:example.org/repo-b.git", False),
    ("github:example.org/repo-a", "ssh://git@github.com/example.org/repo-a.git", True),
    ("https://example.org/acme/lib.git", "https://example.org/acme/lib.git", True),
    ("https://example.org/acme/lib.git", "https://example.org/acme/other.git", False),
    ("git@github.com:example.org/repo-b.git", "git@github.com:example.org/repo-b.git", True),
    ("github:example.org/repo-a", "https://github.com/example.org/repo-a", True),
]


@pytest.mark.parametrize("identity,url,expected", CASES)
def test_matches(identity: str, url: str, expected: bool):
    assert remote_matches(identity, url) is expected


def test_normalize_identity_shorthand():
    assert normalize_identity("github:example.org/repo-a") == (
        "github.com",
        "example.org/repo-a",
    )


def test_normalize_url_scp():
    assert normalize_remote_url("git@github.com:example.org/repo-b.git") == (
        "github.com",
        "example.org/repo-b.git",
    )
