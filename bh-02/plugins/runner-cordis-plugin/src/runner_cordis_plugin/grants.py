"""Capability grants as values (decision-0012 items 1, 2 and 5): what can be asked for, who asked
and why, how it was answered, and what is never grantable. Pure: nothing here reads the
filesystem, the environment or the clock, so a caller resolves a path (`Path.resolve`) before it
builds a `Grant`, and hands `Floor` what it found.

A `Grant` is one capability, of four kinds: `read` and `write` take an absolute path, `env` a
variable name, `net` a destination in the shape brig's `Destination` has (an exact hostname,
`*.suffix` or an IP literal, always with a port). That shape is bh-02's own value here, because
only `brig_spec` imports brig. A `Request` adds who asks (`Asker`: a row, an input, an extension
or an agent, always shown to the person) and why. An `Answer` is once (this session, held in
memory), always (this project, kept by `store`) or no (this session).

The floor (`Floor`, `refusal`) is what no answer can grant: bh-02 refuses it, saying why, before
anyone is asked. Reading or writing what holds a secret or the store itself; writing what the host
reads, runs or trusts (the layer files, bh-02's own code, its configuration, the interpreter and the
directory of each link on the way to it); handing the jail a variable a model key reads, or the
proxy variables brig sets itself.
"""

import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv6Address, ip_address

__all__ = [
    "PROXY_VARIABLES",
    "Answer",
    "Asker",
    "Floor",
    "Grant",
    "Invalid",
    "Kind",
    "Request",
    "Source",
    "refusal",
]

#: What brig sets itself in a jail that has an egress policy (its `PROXY_VARIABLES`), in both cases,
#: since clients disagree on which they read: a grant for one would point the jail's traffic
#: around the proxy that decides which destinations it may reach.
PROXY_VARIABLES: tuple[str, ...] = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
_HEX = frozenset("0123456789abcdefABCDEF")


class Kind(StrEnum):
    """What a grant lets the jail do."""

    READ = "read"
    WRITE = "write"
    ENV = "env"
    NET = "net"


class Answer(StrEnum):
    """What the person said: `ONCE` is for the rest of this session, `ALWAYS` for this project from
    now on, `NO` is kept for the session so the same request is not asked again."""

    ONCE = "once"
    ALWAYS = "always"
    NO = "no"


class Source(StrEnum):
    """Who can ask: the person always sees which."""

    ROW = "row"
    INPUT = "input"
    EXTENSION = "extension"
    AGENT = "agent"


class Invalid(ValueError):
    """A grant is not one that can be made; the message says what to write instead."""


@dataclass(frozen=True, slots=True)
class Grant:
    """One capability. `target` is the absolute path (`read`, `write`), the variable name (`env`)
    or the host (`net`: an exact hostname, `*.suffix` or an IP literal, lower-case, unbracketed);
    `port` is a `net` grant's and 0 for the others.

    A path is taken as spelled, never resolved (this module touches no filesystem): it must be
    absolute and already normal, with no `..`, `.`, `//` or trailing `/`, so the caller resolves it
    first and the floor compares what the jail will see. A hostname is folded to lower case.

    Raises:
        Invalid: the target is not of the kind's shape (the message names the shape).
    """

    kind: Kind
    target: str
    port: int = 0

    def __post_init__(self) -> None:
        match self.kind:
            case Kind.READ | Kind.WRITE:
                _check_path(self.kind, self.target)
                _check_unported(self.kind, self.port)
            case Kind.ENV:
                _check_name(self.target)
                _check_unported(self.kind, self.port)
            case Kind.NET:
                object.__setattr__(self, "target", _check_host(self.target, self.port))

    def __str__(self) -> str:
        return (
            f"{self.kind}: {self.target}:{self.port}"
            if self.kind is Kind.NET
            else f"{self.kind}: {self.target}"
        )


@dataclass(frozen=True, slots=True)
class Asker:
    """Who asks: a `source` and its `name` (the row's id, the input's tool, the extension's name, the
    agent's name)."""

    source: Source
    name: str

    def __str__(self) -> str:
        return f"{self.source} {self.name}"


@dataclass(frozen=True, slots=True)
class Request:
    """A `grant` asked for by `asker`, for `reason` (in the asker's words, shown to the person).

    Raises:
        Invalid: there is no reason, or no name for who asks: the person decides on both.
    """

    grant: Grant
    asker: Asker
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise Invalid(
                f"a request for {self.grant} from {self.asker} has no reason; say what it is for, in a "
                "sentence the person can decide on"
            )
        if not self.asker.name.strip():
            raise Invalid(
                f"a request for {self.grant} says it is from a {self.asker.source} but not which; "
                "name the row, tool, extension or agent that asks"
            )


def _check_path(kind: Kind, path: str) -> None:
    if not path.startswith("/"):
        raise Invalid(f"a {kind} grant takes an absolute path, got {path!r}; write the whole path, from `/`")
    if "\0" in path:
        raise Invalid(f"a {kind} grant's path can't hold a NUL character; write the path alone")
    if path == "/":
        raise Invalid(
            f"a {kind} grant of `/` would be the whole filesystem; name the directory the program needs"
        )
    if path != posixpath.normpath(path) or path.startswith("//"):
        raise Invalid(
            f"a {kind} grant's path must be normal (no `..`, `.`, `//` or trailing `/`): got {path!r}, "
            f"write {posixpath.normpath(path)!r}"
        )


def _check_unported(kind: Kind, port: int) -> None:
    if port:
        raise Invalid(f"a {kind} grant takes no port, got {port}; only `net` does")


def _check_name(name: str) -> None:
    if not _NAME.fullmatch(name):
        raise Invalid(
            f"an env grant takes a variable name, got {name!r} (letters, digits and _, not starting with "
            "a digit); write the name, never the value"
        )


def _check_host(host: str, port: int) -> str:
    """`host` for a `net` grant, folded to lower case, or Invalid. The rules are brig's
    `Destination`: no port wildcard, no ranges, a `*.` only as the whole first label, hostnames
    of ASCII labels whose last is not numeric, an address bare."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise Invalid(f"a net grant takes a port from 1 to 65535, got {port!r}; there are no port wildcards")
    if not host:
        raise Invalid("a net grant takes a host: an exact hostname, `*.suffix` or an IP literal")
    if host.startswith("[") and host.endswith("]"):
        raise Invalid(f"a net grant names an address bare, without brackets: write {host[1:-1]!r}")
    if "/" in host:
        raise Invalid(
            f"a net grant names one address or name, not a range (got {host!r}); grant each address, "
            "or `*.suffix` for a domain"
        )
    if "*" in host and not (host.startswith("*.") and "*" not in host[2:]):
        raise Invalid(
            f"a `*` in a net grant's host is only the whole first label (`*.example.com`), got {host!r}; "
            "it stands for any name under the suffix, never the suffix itself"
        )
    wild, name = (True, host[2:]) if host.startswith("*.") else (False, host)
    if (address := _literal(name)) is not None:
        if wild:
            raise Invalid(f"`*.` takes a domain, not an address (got {host!r}); grant the address itself")
        return str(address)
    folded = _hostname(name) if name.isascii() else None
    if folded is None:
        raise Invalid(
            f"{host!r} is neither a hostname nor an IP literal: a hostname is ASCII labels of letters, "
            "digits and hyphens (1 to 63 characters, no hyphen at either end) and its last label is not "
            "a number; an international name is written in its `xn--` form; an address has no zone"
        )
    return f"*.{folded}" if wild else folded


def _literal(host: str) -> str | None:
    """`host` as an IP literal's canonical text (an IPv4-mapped one as the IPv4), else None."""
    if "%" in host:
        return None
    try:
        address = ip_address(host)
    except ValueError:
        return None
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return str(address)


def _hostname(name: str) -> str | None:
    """`name` lower-cased, without one trailing dot, when it is a valid hostname."""
    folded = name.lower().removesuffix(".")
    labels = folded.split(".")
    if not folded or len(folded) > 253 or not all(_LABEL.fullmatch(label) for label in labels):
        return None
    last = labels[-1]
    if last.isdigit() or (last.startswith("0x") and all(c in _HEX for c in last[2:])):
        return None  # a resolver would read it as an IPv4 address
    return folded


@dataclass(frozen=True, slots=True)
class Floor:
    """What no grant may reach, as the caller found it (absolute, resolved paths; the host
    computes them, this module only compares). `secrets` (`host.secrets`), `grants` (the store's
    directory, `host.grants`) and `credentials` (the person's credential paths: `CREDENTIALS`
    under the home directory) may be neither read nor written. `layers` (the composition's files),
    `code` (the directory of every package bh-02 runs code from), `trusted` (bh-02's
    configuration directories), `interpreters` (its interpreter's files) and `links` (the
    directory of each link on the way to them, `policy.link_directories` before it is narrowed to
    the writable roots) may not be written. `key_envs` is what `models.key_envs()` answers: each
    variable a model's key reads, to the endpoints that read it."""

    secrets: tuple[str, ...] = ()
    grants: str = ""
    credentials: tuple[str, ...] = ()
    layers: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    trusted: tuple[str, ...] = ()
    interpreters: tuple[str, ...] = ()
    links: tuple[str, ...] = ()
    key_envs: Mapping[str, Sequence[str]] | None = None


def refusal(grant: Grant, floor: Floor) -> str | None:
    """Why `grant` is never granted (it is on the floor), in words that say what to do, else None.
    A path is refused when it is a floor path or lies under one, except a link's directory, which
    only the directory itself is (a file beside the link changes nothing about it). A path that
    holds a floor path is not refused here: `spec_for` masks or denies the floor path inside it."""
    match grant.kind:
        case Kind.READ:
            return _path_refusal(grant, [*_untouchable(floor)], ())
        case Kind.WRITE:
            return _path_refusal(
                grant,
                [
                    *_untouchable(floor),
                    (
                        floor.layers,
                        "a layer file: an input rewriting one would reshape the composition running it",
                    ),
                    (floor.code, "bh-02's own code, which the host imports in its own process"),
                    (floor.trusted, "bh-02's configuration, whose files the host reads and trusts"),
                    (floor.interpreters, "the interpreter bh-02 runs on, which the host would run next"),
                ],
                [(floor.links, "a directory holding a link on the way to the interpreter bh-02 runs on")],
            )
        case Kind.ENV:
            return _env_refusal(grant.target, floor)
        case Kind.NET:
            return None


def _untouchable(floor: Floor) -> list[tuple[Sequence[str], str]]:
    return [
        (floor.secrets, "a secret (the sessions' state, where Claude Code keeps its tokens)"),
        (
            (floor.grants,) if floor.grants else (),
            "the grants store, which only bh-02 writes: a grant that could edit it could grant anything",
        ),
        (floor.credentials, "the person's credentials"),
    ]


def _path_refusal(
    grant: Grant, trees: Sequence[tuple[Sequence[str], str]], exact: Sequence[tuple[Sequence[str], str]]
) -> str | None:
    for paths, why in trees:
        for path in paths:
            if grant.target == path or grant.target.startswith(path.rstrip("/") + "/"):
                return _said(grant, path, why)
    for paths, why in exact:
        if grant.target in paths:
            return _said(grant, grant.target, why)
    return None


def _said(grant: Grant, path: str, why: str) -> str:
    where = "is" if grant.target == path else f"is under {path}, which is"
    return (
        f"{grant} is never granted: {grant.target} {where} {why}. "
        "Nothing can approve it; keep the work to a directory outside it"
    )


def _env_refusal(name: str, floor: Floor) -> str | None:
    if name.upper() in {v.upper() for v in PROXY_VARIABLES}:
        return (
            f"env: {name} is never granted: brig sets the proxy variables itself, to the proxy that "
            "decides which destinations the jail reaches, and a program given another would go around it. "
            "Grant the destination (`net`) instead"
        )
    if readers := (floor.key_envs or {}).get(name):
        return (
            f"env: {name} is never granted: endpoint {', '.join(map(repr, readers))} reads it as its model "
            f"key (`key = {{ env = {name!r} }}`), and the jail would hand that key to the model's code. "
            "Change that endpoint's key, or have the program read its own"
        )
    return None
