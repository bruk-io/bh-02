"""`bh-02 watch SESSION AGENT`: one sub-agent's event log, rendered for a person at a terminal.

The log is `<sessions>/SESSION/agents/AGENT/events.jsonl`, written by the agents row
(subagents-cordis-plugin) and kept under the sessions' state directory, which the `host` value's
`secrets` hides from every jail. This module only reads it: through `host_paths.read_beneath`
(a walk that follows no link, from a descriptor it opened read-only), so it opens nothing for
writing and creates nothing. The two names are judged before any path is made of them: only a
session id and an agent name that bh-02 makes are accepted, so neither can be a path (`..`, a
`/`, an absolute path, a link's name).

What the log holds is what the model said, so it is shown as text: no escape sequence and no
control character but newline and tab reaches the terminal.
"""

import json
import re
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from host_paths import Link, read_beneath

__all__ = ["Refused", "clean", "refused", "refused_agent", "refused_session", "rendered", "watched"]

# A session id as `sessions.create` makes it (`20261012-091500-ab12`), an agent's name as the
# agents row gives it (`TYPE-N`; a type's name is at most 32 of lower-case letters, digits, `_`
# and `-`, starting with a letter).
_SESSION = re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{4}")
_AGENT = re.compile(r"[a-z][a-z0-9_-]{0,31}-[0-9]{1,6}")
_LOG = "events.jsonl"
_CAP = 64 * 1024 * 1024  # a log larger than this is not read
_POLL_S = 0.5
# C0 and C1 controls (escape sequences among them), and the bidirectional overrides and isolates
# (U+202A-202E, U+2066-2069), which can make a line read in another order than it is written
_UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
_CLIP = 400  # characters of a call's input or result shown on one line


class Refused(Exception):
    """The log can't be shown: `message` says why and what to do."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def refused_session(session: str) -> str | None:
    """Why `session` is not a session id bh-02 made (so no path is built from it), or None."""
    if not _SESSION.fullmatch(session):
        return (
            f"{session!r} is not a session id bh-02 made (such as 20261012-091500-ab12); "
            "`bh-02 sessions` lists this directory's"
        )
    return None


def refused_agent(agent: str) -> str | None:
    """Why `agent` is not an agent name bh-02 made (so no path is built from it), or None."""
    if not _AGENT.fullmatch(agent):
        return (
            f"{agent!r} is not an agent name bh-02 made (a type and a number, such as general-1); "
            "`/agents` lists the running ones"
        )
    return None


def refused(session: str, agent: str) -> str | None:
    """Why `session` and `agent` are not names bh-02 made (so no path is built from them), or None."""
    return refused_session(session) or refused_agent(agent)


def clean(text: str) -> str:
    """`text` less every control character but newline and tab (escape sequences included)."""
    return _UNSAFE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))


def _clipped(text: str) -> str:
    one = " ".join(clean(text).split())
    return one if len(one) <= _CLIP else f"{one[:_CLIP]}…"


def rendered(line: bytes, inline: bool) -> tuple[str, bool, bool]:
    """One record of the log as text for the terminal: the text, whether the output now ends in the
    middle of a line (streamed `text` does, until the next event), and whether this record ends
    the log (`agent_end`). `inline` is whether it did before this record. A line that is not a
    record is said so and skipped."""
    try:
        record = json.loads(line)
        event = record["event"]
        stamp = str(record["at"])[11:19]
        kind = str(event.get("type"))
    except json.JSONDecodeError, KeyError, TypeError, AttributeError:
        return _after("? a line of the log that is not a record\n", inline), False, False
    if kind == "text":
        return clean(str(event.get("text", ""))), True, False
    body, last = _described(kind, event)
    return _after(f"{stamp}  {body}\n", inline), False, last


def _after(text: str, inline: bool) -> str:
    """`text` on a line of its own: after the newline a streamed text leaves unfinished."""
    return f"\n{text}" if inline else text


def _described(kind: str, event: Mapping[str, Any]) -> tuple[str, bool]:
    """One event as a line (no newline), and whether it is the log's last."""
    match kind:
        case "agent_start":
            where = "background" if event.get("background") else "foreground"
            asked = _clipped(str(event.get("prompt", "")))
            return f"agent {event.get('name')} ({event.get('agent_type')}, {where}) was asked: {asked}", False
        case "agent_end":
            return f"ended. Its report to its parent: {_clipped(str(event.get('report', '')))}", True
        case "tool_call":
            call = _clipped(json.dumps(event.get("input"), default=str))
            return f"-> {clean(str(event.get('name')))} {call}", False
        case "tool_result":
            failed = "error " if event.get("is_error") else ""
            return f"<- {failed}{_clipped(str(event.get('content', '')))}", False
        case "thinking":
            return f"thinking: {_clipped(str(event.get('text', '')))}", False
        case "usage":
            return (
                f"used {event.get('input_tokens', 0)} input, {event.get('output_tokens', 0)} output tokens",
                False,
            )
        case "stop":
            return f"step ended: {clean(str(event.get('reason')))}", False
        case "note":
            return f"note: {_clipped(str(event.get('text', '')))}", False
    return f"({clean(kind)})", False


def _read(root: Path, session: str, agent: str) -> bytes:
    """The log's bytes, through no link, read-only.

    Raises:
        Refused: it is not there, is a link, is not a plain file, or is too large.
    """
    where = root / session / "agents" / agent / _LOG
    try:
        data = read_beneath(root, [session, "agents", agent, _LOG], cap=_CAP)
    except FileNotFoundError:
        raise Refused(
            f"no event log at {where}: session {session} has no agent {agent} "
            "(or it was started without a state directory)"
        ) from None
    except OSError as error:
        raise Refused(f"can't read the event log {where}: {error}") from None
    if isinstance(data, Link):
        raise Refused(f"{where} is a link, which bh-02 did not make; it is not read")
    return data


def watched(
    root: Path,
    session: str,
    agent: str,
    *,
    follow: bool,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[str]:
    """The text of the agent's log, a chunk at a time: what is there, then (with `follow`) what is
    added, until the agent's end is read. The file is read again for each poll and never opened
    for writing.

    Raises:
        Refused: the names are not bh-02's, or the log can't be read (`refused`, `_read`).
    """
    if (why := refused(session, agent)) is not None:
        raise Refused(why)
    done, offset, inline = False, 0, False
    while not done:
        data = _read(root, session, agent)
        end = data.rfind(b"\n") + 1  # only whole lines: the writer may be half through one
        for line in data[offset:end].splitlines():
            text, inline, last = rendered(line, inline)
            done = done or last
            yield text
        offset = max(offset, end)
        if not follow:
            break
        if not done:
            sleep(_POLL_S)
    if inline:
        yield "\n"
