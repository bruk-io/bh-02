"""The words of the grants prompt (decision-0012 item 8), as one pure function: what is asked for,
who asks and why, when it applies, and what it does to the grades, as the question `output.choose`
puts to the person (CONTRACTS.md: choice). Nothing here asks, reads the environment or knows
cordis: the caller says where hosts keep sockets (`places`, `runtime_dir`).

"When it applies" is `applies`, the one place that says what this build does with a grant, so a
change to when a grant takes effect (live egress, a restart before the next input) changes it here
and nowhere else.
"""

from collections.abc import Sequence
from ipaddress import ip_address
from typing import Any

from runner_cordis_plugin.grants import Answer, Grant, Kind, Request
from runner_cordis_plugin.policy import SELF_MODIFYING

__all__ = [
    "answer_of",
    "applies",
    "decided",
    "question",
    "refusal_reason",
    "revoked",
    "unapplied",
    "ungrantable",
    "unasked",
]

#: The answers, in the order the keys line shows them: the key, the answer it gives and its label.
_CHOICES: tuple[tuple[str, Answer, str], ...] = (
    ("o", Answer.ONCE, "once (for this session)"),
    ("a", Answer.ALWAYS, "always (for this project)"),
    ("n", Answer.NO, "no"),
)


def applies(grant: Grant) -> str:
    """When `grant`, once approved, takes effect in this build: a destination now, on every running
    program (a connection already open is not affected); the rest from the next start of the
    program it is for (`/clear` starts the Python process again)."""
    match grant.kind:
        case Kind.NET:
            return "now, on every running program; connections already open are not affected"
        case Kind.READ | Kind.WRITE | Kind.ENV:
            return "from the program's next start (`/clear` starts the Python process again)"


def question(request: Request, *, places: Sequence[str], runtime_dir: str) -> dict[str, Any]:
    """The choice that asks `request` (CONTRACTS.md: choice): `title`, `lines` (what, who asks and
    why, when it applies, what it does to the grades, in that order), `warning` ('' for none),
    `choices` (once, always, no) and `escape`, the answer Escape gives. `places` are where hosts
    keep sockets and `runtime_dir` is `$XDG_RUNTIME_DIR` ('' when unset): a path that is, holds or
    lies under one would make the jail's network violated."""
    grant = request.grant
    sockets = (*places, *([runtime_dir] if runtime_dir.startswith("/") else []))
    return {
        "title": f"Allow {_what(grant)}?",
        "lines": [
            f"What: {_what(grant)}",
            f"Asked by: {request.asker}, because: {request.reason}",
            f"When: {applies(grant)}",
            f"Grades: {_effect(grant, sockets)}",
        ],
        "warning": " ".join(_warnings(grant, sockets)),
        "choices": [{"key": key, "value": answer.value, "label": label} for key, answer, label in _CHOICES],
        "escape": Answer.NO.value,
    }


def answer_of(value: str) -> Answer | None:
    """The `Answer` a choice's value names, or None for '' (the question was withdrawn) and for a
    value no choice of `question` carries."""
    return next((answer for _, answer, _ in _CHOICES if answer.value == value), None)


def decided(request: Request, answer: Answer) -> str:
    """What the model is told of an answer, in a line: the grant, who asked, what was decided and,
    when it was granted, when it applies."""
    what = f"{_what(request.grant)} (asked by {request.asker})"
    retry = " The call may retry it." if request.grant.kind is Kind.NET else ""
    match answer:
        case Answer.ONCE:
            return f"The person granted {what} for this session; it applies {applies(request.grant)}.{retry}"
        case Answer.ALWAYS:
            return f"The person granted {what} for this project; it applies {applies(request.grant)}.{retry}"
        case Answer.NO:
            return f"The person declined {what}; it is not granted this session and will not be asked again."


def revoked(grant: Grant) -> str:
    """What the person is told when `grant` is revoked, beyond the grant itself; '' for none. A
    destination is refused from the next connection on, but brig never cuts one already open."""
    if grant.kind is not Kind.NET:
        return ""
    return (
        "connections already open through it stay open until the program restarts (`/clear` "
        "restarts the Python process): the proxy judges a connection once, when it names its destination"
    )


def refusal_reason(host: str, port: int, reason: str, address: str) -> str:
    """Why a refused connection is asked, as the asker's `reason`."""
    if reason == "private-address":
        return (
            f"a connection the program made to {host}:{port} was refused: the name resolved to the "
            f"private address {address}, which only a grant of that address itself opens"
        )
    return f"a connection the program made to {host}:{port} was refused: it is not granted"


def unasked(reason: str, host: str, port: int) -> str:
    """What the model is told of a refusal that is not asked, since there is nothing to grant."""
    why = {
        "unresolved": "the name did not resolve from the host, so there is nothing to allow",
        "address-unparseable": "the address it resolved to could not be read, so there is nothing to allow",
        "authority-unparseable": "the request's destination could not be read, so there is nothing to allow",
    }.get(reason, f"the proxy refused it ({reason}), and there is nothing to allow")
    return f"A connection the program made to {host}:{port} was refused: {why}."


def ungrantable(host: str, port: int, problem: str) -> str:
    """What the model is told of a refusal whose destination cannot be a grant."""
    return f"A connection the program made to {host}:{port} was refused, and it cannot be granted: {problem}"


def unapplied(error: Exception) -> str:
    """What the model is told when a grant could not reach a running program's proxy."""
    return (
        f"A destination the person granted could not be applied to the running program ({error}); "
        "it applies from the next start."
    )


def _what(grant: Grant) -> str:
    match grant.kind:
        case Kind.NET:
            return f"net {grant.target}:{grant.port}"
        case Kind.READ | Kind.WRITE | Kind.ENV:
            return f"{grant.kind} {grant.target}"


def _effect(grant: Grant, places: Sequence[str]) -> str:
    if _refused_at_start(grant, places):
        return "none: the program would not start while this grant stands"
    match grant.kind:
        case Kind.NET:
            return "adds a destination the jail may reach; network stays proxied, only what is granted passes"
        case Kind.ENV:
            return "the variable's value reaches the program; no grade changes"
        case Kind.READ:
            return "no grade changes; the jail may read this path"
        case Kind.WRITE:
            return "no grade changes; the jail may write this path"


def _warnings(grant: Grant, places: Sequence[str]) -> list[str]:
    if grant.kind is Kind.NET:
        return _private_warning(grant.target)
    if grant.kind not in (Kind.READ, Kind.WRITE):
        return []
    if _refused_at_start(grant, places):
        # A writable root at or under a socket place is refused at every start (`socket_refusal`):
        # the jail never runs to be graded, so "violated" would be the wrong word.
        meets = " and ".join(
            f"{relation} {place}"
            for place in dict.fromkeys(places)
            if (relation := _relation(grant.target, place)) in ("is", "is under")
        )
        warnings = [
            f"{grant.target} {meets}, where hosts keep sockets: "
            "no jail starts with a writable root there, so the program would not start while this "
            "grant stands (`/grants revoke ID` takes it back)"
        ]
    else:
        warnings = [
            f"{grant.target} {meets} {place}, where hosts keep sockets: the jail's network would be "
            "violated, and approval would stop counting it as confined"
            for place in dict.fromkeys(places)
            if (meets := _relation(grant.target, place))
        ]
    if grant.kind is Kind.WRITE and _self_modifying(grant.target):
        warnings.append(
            f"{grant.target} can run code outside the jail later (a git hook, a shell or editor "
            "setting): a write there can run as you, unconfined"
        )
    return warnings


def _private_warning(target: str) -> list[str]:
    """A warning for a net grant on an IP literal that is not public: it lets the jail reach that
    address on the person's own network."""
    try:
        address = ip_address(target)
    except ValueError:
        return []
    if address.is_global:
        return []
    return [f"{target} is not a public address: this lets the program reach {target} on your network"]


def _refused_at_start(grant: Grant, places: Sequence[str]) -> bool:
    """Whether `grant` is a write root at or under a socket place, which every start refuses."""
    return grant.kind is Kind.WRITE and any(_relation(grant.target, p) in ("is", "is under") for p in places)


def _relation(path: str, place: str) -> str:
    """How `path` meets the socket place `place`: 'is', 'is under' or 'holds it, with', else ''."""
    place = place.rstrip("/")
    if not place:
        return ""
    if path == place:
        return "is"
    if path.startswith(place + "/"):
        return "is under"
    if place.startswith(path + "/"):
        return "holds"
    return ""


def _self_modifying(path: str) -> bool:
    """Whether `path` is, or lies under, a path `SELF_MODIFYING` names (by name, under any root)."""
    parts = path.split("/")
    for name in SELF_MODIFYING:
        words = name.split("/")
        if any(parts[start : start + len(words)] == words for start in range(len(parts) - len(words) + 1)):
            return True
    return False
