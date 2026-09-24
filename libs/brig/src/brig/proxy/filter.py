"""Host-matching for the egress proxy: pure, so it is unit-testable.

Split from `server.py` on purpose. The allow/deny decision is the whole
security claim of `connect_proxy`, and it is the one part of a networking
process that can be tested exhaustively without a socket -- so it is
written as a pure function over strings and pinned in the unit tier, while
the integration tier proves only that a real connection reaches this
decision and honours it.
"""

from __future__ import annotations

#: The body a denied request is answered with. Its first line is the
#: mechanism's denial signature (SPEC.md §8: proxy "403"); the host is
#: echoed so a probe's normalized denial string names WHAT was denied and
#: cannot be confused with an unrelated 403 from an upstream server -- the
#: distinction that keeps a probe from being vacuous.
DENIAL_PREFIX = "brig: egress denied by policy: "


def split_host_port(authority: str, *, default_port: int) -> tuple[str, int]:
    """Split `host:port`, `host`, or `[v6]:port` into its two parts.

    Raises `ValueError` on anything it cannot read as an authority. The
    proxy answers a `ValueError` here with a denial, never with a guess:
    an authority this cannot parse is one the matcher below cannot be
    trusted to have matched correctly either.
    """
    authority = authority.strip()
    if not authority:
        raise ValueError("empty authority")
    if authority.startswith("["):
        close = authority.find("]")
        if close == -1:
            raise ValueError(f"unterminated IPv6 literal: {authority!r}")
        host = authority[1:close]
        rest = authority[close + 1 :]
        if not rest:
            return host, default_port
        if not rest.startswith(":"):
            raise ValueError(f"junk after IPv6 literal: {authority!r}")
        return host, _port(rest[1:])
    if authority.count(":") > 1:
        raise ValueError(f"bare IPv6 literal must be bracketed: {authority!r}")
    if ":" in authority:
        host, _, port = authority.partition(":")
        if not host:
            raise ValueError(f"empty host: {authority!r}")
        return host, _port(port)
    return authority, default_port


def _port(text: str) -> int:
    if not text.isdigit():
        raise ValueError(f"non-numeric port: {text!r}")
    port = int(text)
    if not 1 <= port <= 65535:
        raise ValueError(f"port out of range: {port}")
    return port


def host_allowed(host: str, allow: tuple[str, ...]) -> bool:
    """Report whether `host` is permitted by the `allow` patterns.

    Two pattern forms, and no others:

    - an exact name (`example.com`), matched case-insensitively after
      stripping one trailing dot from each side (the root label is not a
      distinction anyone means here);
    - a wildcard (`*.example.com`), matching exactly one or more leading
      labels -- `a.example.com` and `a.b.example.com` match, the bare
      `example.com` does NOT.

    A wildcard deliberately does not match its own parent. "Allow the
    subdomains" and "allow the site" are different intentions, and a
    matcher that silently merges them widens a policy its author wrote
    narrowly. An author who means both writes both.

    There is no substring, prefix, or regex form. Every host-allowlist bug
    field evidence records is a matcher that was more clever than
    `endswith` on a label boundary -- `evil-example.com` passing a
    `example.com` suffix test, `example.com.attacker.net` passing a prefix
    test. Both are rejected here by construction, and pinned as tests.
    """
    subject = host.strip().rstrip(".").lower()
    if not subject:
        return False
    for raw in allow:
        pattern = raw.strip().rstrip(".").lower()
        if not pattern:
            continue
        if pattern.startswith("*."):
            suffix = pattern[1:]  # keeps the leading dot: ".example.com"
            parent = pattern[2:]
            if subject.endswith(suffix) and subject != parent:
                return True
            continue
        if subject == pattern:
            return True
    return False
