"""`host_allowed` and `split_host_port`: the whole allow/deny decision.

This matcher IS `connect_proxy`'s security claim, and it is pure, so it is
tested exhaustively here and the integration tier is left to prove only
that a real connection reaches it. Both directions on every case: a
matcher tested only on what it accepts cannot distinguish "correct" from
"allows everything", which is the vacuous shape
`.claude/rules/unit-tests.md` names.
"""

from __future__ import annotations

import pytest

from brig.proxy.filter import DENIAL_PREFIX, host_allowed, split_host_port

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "host",
    [
        "example.com",
        "EXAMPLE.COM",  # case-insensitive
        "example.com.",  # one trailing root dot
        " example.com ",  # incidental whitespace
    ],
)
def test_exact_pattern_allows_the_name_it_names(host: str) -> None:
    assert host_allowed(host, ("example.com",))


@pytest.mark.parametrize(
    "host",
    [
        # The two matchers field evidence records as broken, both rejected
        # by construction: a suffix test would pass the first, a prefix
        # test the second.
        "evil-example.com",
        "notexample.com",
        "example.com.attacker.net",
        "example.commercial.io",
        "sub.example.com",  # an exact pattern is not a wildcard
        "example.co",
        "",
        "   ",
    ],
)
def test_exact_pattern_denies_everything_else(host: str) -> None:
    assert not host_allowed(host, ("example.com",))


@pytest.mark.parametrize("host", ["a.example.com", "a.b.example.com", "A.EXAMPLE.COM"])
def test_wildcard_allows_subdomains_at_any_depth(host: str) -> None:
    assert host_allowed(host, ("*.example.com",))


@pytest.mark.parametrize(
    "host",
    [
        # A wildcard does not match its own parent -- "allow the
        # subdomains" and "allow the site" are different intentions.
        "example.com",
        # ... nor a name that merely ends with the letters.
        "evilexample.com",
        "aexample.com",
        "a.example.com.attacker.net",
    ],
)
def test_wildcard_denies_the_parent_and_near_misses(host: str) -> None:
    assert not host_allowed(host, ("*.example.com",))


def test_an_author_who_means_both_writes_both() -> None:
    allow = ("example.com", "*.example.com")
    assert host_allowed("example.com", allow)
    assert host_allowed("api.example.com", allow)
    assert not host_allowed("example.net", allow)


def test_empty_allow_list_denies_everything() -> None:
    """No `--allow` at all is a valid policy, not a disabled filter."""
    for host in ("example.com", "localhost", "127.0.0.1", "*"):
        assert not host_allowed(host, ())


def test_a_literal_star_is_not_a_wildcard() -> None:
    """`*` alone has no allow-all meaning; only `*.suffix` is a form."""
    assert not host_allowed("example.com", ("*",))


@pytest.mark.parametrize(
    ("authority", "default", "expected"),
    [
        ("example.com", 443, ("example.com", 443)),
        ("example.com:8443", 443, ("example.com", 8443)),
        ("example.com", 80, ("example.com", 80)),
        ("127.0.0.1:9", 80, ("127.0.0.1", 9)),
        ("[::1]:8080", 443, ("::1", 8080)),
        ("[::1]", 443, ("::1", 443)),
        (" example.com:1 ", 443, ("example.com", 1)),
    ],
)
def test_split_host_port_reads_every_authority_form(
    authority: str, default: int, expected: tuple[str, int]
) -> None:
    assert split_host_port(authority, default_port=default) == expected


@pytest.mark.parametrize(
    "authority",
    [
        "",
        "   ",
        ":443",  # empty host
        "example.com:",  # empty port
        "example.com:http",  # non-numeric
        "example.com:0",
        "example.com:65536",
        "::1",  # bare IPv6 must be bracketed, else the port is ambiguous
        "[::1",  # unterminated
        "[::1]junk",
    ],
)
def test_split_host_port_refuses_what_it_cannot_read(authority: str) -> None:
    """Refusal, never a guess: an authority this cannot parse is one the
    matcher cannot be trusted to have matched correctly either, and the
    server answers a `ValueError` here with a denial."""
    with pytest.raises(ValueError):
        split_host_port(authority, default_port=443)


def test_denial_prefix_is_specific_enough_to_be_a_signature() -> None:
    """SPEC.md section 8: a signature must match its mechanism's real
    denial and NOT a generic failure. The negative direction is the one
    that keeps a probe from passing vacuously."""
    assert DENIAL_PREFIX in f"{DENIAL_PREFIX}example.com\nnot in allow list\n"
    for unrelated in (
        "HTTP/1.1 403 Forbidden",  # an upstream server's own 403
        "curl: (7) Failed to connect",
        "Could not resolve host: example.com",
        "Connection refused",
    ):
        assert DENIAL_PREFIX not in unrelated
