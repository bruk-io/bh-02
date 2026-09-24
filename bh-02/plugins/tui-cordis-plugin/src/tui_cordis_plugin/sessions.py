"""What the sessions row needs (the `sessions` and `frame` values), and how a session reads
in the sidebar. Everything here is pure (`listing` builds a reader and reads nothing)."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

__all__ = ["SessionSink", "SessionSource", "listing", "marked", "resume_note", "session_label"]


@runtime_checkable
class SessionSource(Protocol):
    """What the sessions row needs of the `sessions` value (CONTRACTS.md: sessions)."""

    @property
    def current(self) -> str: ...
    def listed(self) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class SessionSink(Protocol):
    """What the sessions row needs of the `frame` value (CONTRACTS.md: frame)."""

    def sessions(self, listed: Callable[[], Sequence[Mapping[str, Any]]]) -> Callable[[], None]: ...


def listing(source: SessionSource) -> Callable[[], list[dict[str, Any]]]:
    """What the sessions row pushes: a function that lists `source`'s sessions, read afresh
    each time the sidebar asks, the running one marked. Building it reads nothing."""

    def listed() -> list[dict[str, Any]]:
        return marked(source.current, source.listed())

    return listed


def marked(current: str, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """`items` as the frame lists them: each with `current`, true for the running session."""
    return [{**item, "current": item.get("id") == current} for item in items]


def session_label(item: Mapping[str, Any]) -> tuple[str, ...]:
    """A session's lines in the sidebar: its id, then its title or when and on what stack it
    ran, then the patches it started with, if any (a patch may have replaced the stack's model,
    so `claude` alone would not say what answered). A record that can't be read (`broken`)
    says so; choosing it says what is wrong."""
    if item.get("broken"):
        return str(item.get("id", "?")), "broken · Enter says why"
    created = str(item.get("created", "")).replace("T", " ")[:16]
    detail = str(item.get("title") or f"{created} · {item.get('stack', '?')}")
    patches = item.get("patches") or ()
    patched = (f"patched: {', '.join(str(p) for p in patches)}",) if patches else ()
    return str(item.get("id", "?")), detail, *patched


def resume_note(item: Mapping[str, Any]) -> str:
    """What choosing a session in the sidebar says: how to continue it (switching live is not
    offered; a session's kernel and model belong to the run that started it), or, for a record
    that can't be read, what is wrong with it and what to do."""
    sid = item.get("id", "?")
    if item.get("broken"):
        return str(item["broken"])
    if item.get("retired"):
        return str(item["retired"])
    command = str(item.get("resume") or f"bh-02 --resume {sid}")  # the lister's, which knows the stack
    if item.get("current"):
        return f"session {sid} is this one; after you leave, `{command}` continues it"
    return f"to continue session {sid}, leave (Ctrl-Q) and run `{command}`"
