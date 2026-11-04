"""The `grant` tool, as pure functions (decision-0012 items 1, 4 and 5): its spec, the section that
tells the model of it, a call's arguments as a `Request`, and the words of what came of it. The
caller (`wiring.grant_prompt`) holds the broker, the runner and what is not pure (does this runner
confine, where a path leads); nothing here asks, reads the filesystem or knows cordis.

An input calls it across the socket as every tool is called (`tools.grant(kind=..., target=...,
reason=...)`), and the model may call it directly. Its result says what the model can act on: whether
it was granted and when it holds (a path or variable from the next input, after the Python process
starts again and loses its variables; a destination now), or why it was not.
"""

from collections.abc import Callable, Mapping
from typing import Any

from runner_cordis_plugin.broker import Outcome
from runner_cordis_plugin.grants import Asker, Grant, Invalid, Kind, Request, Source
from runner_cordis_plugin.prompting import applies

__all__ = ["ASKER", "GRANT", "NOTHING", "answered", "refused", "requested", "section"]

#: Who asks when the model calls `grant`, from an input or directly: the python tool's input.
ASKER = Asker(Source.INPUT, "python")

#: The tool's spec. What the model is told of how to use it is the `system` section's, not this.
GRANT: Mapping[str, Any] = {
    "name": "grant",
    "description": (
        "Ask the person to let the jail read or write a path, see an environment variable, or reach "
        "a network destination."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": [kind.value for kind in Kind],
                "description": "What to allow.",
            },
            "target": {
                "type": "string",
                "description": "An absolute path (read, write), a variable's name (env), or a host name, "
                "`*.suffix` or IP address (net).",
            },
            "port": {"type": "integer", "description": "The port, for net."},
            "reason": {"type": "string", "description": "Why, in a sentence the person can decide on."},
        },
        "required": ["kind", "target", "reason"],
    },
}

#: What a call answers when the runner confines nothing: there is no jail to grant anything to.
NOTHING = (
    "Nothing runs in a jail here (`--no-jail`), so there is nothing to grant and nobody was asked: "
    "inputs run with the person's own permissions, and each is put to them."
)

_TARGETS: Mapping[Kind, str] = {
    Kind.READ: "absolute path to read",
    Kind.WRITE: "absolute path to write",
    Kind.ENV: "name of the environment variable",
    Kind.NET: "host name, `*.suffix` or IP address",
}


def section(confined: bool) -> str:
    """What the model is told about `grant`, as a section of its prompt (`system`): what it asks for,
    when an answer holds, and that a call is a question to the person."""
    if not confined:
        return (
            "## Grants\n\n`grant` asks the person to widen the jail, and nothing here runs in one "
            "(`--no-jail`), so a call says there is nothing to grant and asks nothing."
        )
    return (
        "## Grants\n\n"
        "`grant(kind, target, reason)` asks the person to let the jail you run in do what it does not: "
        "`read` or `write` an absolute path, see an environment variable (`env`), or reach a network "
        "destination (`net`: a host name, `*.suffix` or an IP address, with `port`). In a python input it "
        "is `tools.grant(kind=..., target=..., reason=...)`. The person is asked, shown your reason, and "
        "answers once (this session), always (this project) or no; a no is not asked again. A `net` "
        "grant holds at once. A `read`, `write` or `env` grant holds from your next python input: the "
        "Python process starts again first, and what earlier inputs defined is gone, so finish with it "
        "before you ask. Some requests are never granted (bh-02's secrets, configuration and code, what "
        "would run outside the jail, a variable a model's key reads); the call says why, and nobody is "
        "asked."
    )


def requested(input: Mapping[str, Any], asker: Asker, resolved: Callable[[str], str]) -> Request | str:
    """The `Request` a call's arguments make, or the words that say what to write instead. `resolved`
    gives the path a `read` or `write` target leads to (a grant holds for what the jail will see, never
    for a link); it is asked of absolute targets only."""
    kind, target, port, reason = (input.get(key) for key in ("kind", "target", "port", "reason"))
    try:
        which = Kind(kind) if isinstance(kind, str) else None
    except ValueError:
        which = None
    if which is None:
        return f"error: `kind` is one of {', '.join(k.value for k in Kind)}, not {kind!r}"
    if not isinstance(target, str):
        return f"error: `target` is the {_TARGETS[which]}, as a string"
    if not isinstance(reason, str):
        return "error: `reason` says why, in a sentence the person can decide on, as a string"
    if which is Kind.NET:
        if isinstance(port, bool) or not isinstance(port, int):
            return "error: a net grant takes the `port`, as an integer (443)"
        number = port
    elif port not in (None, 0):
        return f"error: only a net grant has a `port`; a {which} grant is the {_TARGETS[which]} alone"
    else:
        number = 0
    if which in (Kind.READ, Kind.WRITE) and target.startswith("/"):
        target = resolved(target)
    try:
        return Request(Grant(which, target, number), asker, reason)
    except Invalid as error:
        return f"error: {error}"


def refused(request: Request, why: str) -> str:
    """What a call answers for a request that is never granted (`why`: the floor's words), when
    nobody was asked."""
    return f"Not granted, and nobody was asked: {request.grant} is never granted. {why}"


def answered(request: Request, outcome: Outcome) -> str:
    """What a call answers once the broker has: whether the grant holds, and when."""
    grant = request.grant
    match outcome:
        case Outcome.NO:
            return (
                f"Not granted: the person did not allow {grant}. It is not asked again this session; "
                "go on without it or tell the person what you need."
            )
        case Outcome.STANDING:
            return f"{grant} is already granted; it holds {applies(grant)}."
        case Outcome.ONCE:
            return f"Granted for this session: {grant}; it holds {applies(grant)}."
        case Outcome.ALWAYS:
            return f"Granted for this project: {grant}; it holds {applies(grant)}."
