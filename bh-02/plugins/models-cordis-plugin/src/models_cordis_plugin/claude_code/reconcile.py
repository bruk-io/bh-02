"""What Claude Code's session holds, against what `agent:loop` asks next: pure.

The loop sends the whole conversation with every request (CONTRACTS.md: model); Claude
Code keeps its own copy in its session. `Held` is what that copy is, as the loop's transcript
knows it: the first `count` non-system messages (their `digest`), the step this provider
emitted last, which the loop has not answered yet, and how that step ended. `reconcile` reads
a request against it and says what to do: send one user line (`Send`), hand the parked calls
their results (`Deliver`, with a line the person typed meanwhile as a steer), or write Claude
Code a new session from the transcript and resume that (`Rebuild`).

Accepted without a rebuild (each measured to leave Claude Code's session equivalent, and the
prompt cache warm; README.md):
- the loop's entry for the emitted step: its `provider` is the emitted message;
- for a step this provider cut short (a truncated, silent, refused or undecodable one, which
  it interrupts so that the loop's classification decides, not Claude Code's own recovery), an
  entry without `provider` whose text is what the step said;
- for a step the person stopped, the loop's `[stopped]` entry, which starts with what it said;
- tool results for exactly the open calls, then any user lines.

Anything else is a rebuild: a prefix that differs (`/clear`, a transcript edited or cut), a step
that failed (Claude Code's state unknown), results that are not the open calls', a user line
in place of the open calls' results.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Final

__all__ = [
    "CLEAN",
    "CONTINUE",
    "CUT",
    "FAILED",
    "OPEN",
    "RUNNING",
    "STOPPED",
    "STRAYED",
    "Deliver",
    "Held",
    "Rebuild",
    "Send",
    "digest",
    "reconcile",
]

type Json = Mapping[str, Any]

# How the step Claude Code ran last ended:
CLEAN: Final = "clean"  # answered: the query reached its result (or nothing ran yet)
OPEN: Final = "open"  # asked for tools: the query is open, its calls parked on bh-02's results
CUT: Final = "cut"  # truncated, silent, refused or undecodable: interrupted at its end, so the loop decides
STOPPED: Final = "stopped"  # the person stopped it mid-stream: interrupted there
FAILED: Final = "failed"  # the step raised: what Claude Code holds is unknown
STRAYED: Final = "strayed"  # Claude Code did something bh-02 did not ask for (answered a call itself)
RUNNING: Final = "running"  # a step is streaming (a saved state saying so is from a crash)

# What a rebuilt session is asked when the transcript ends in tool results, not a user line:
# the results are in the session; this line only starts the next step.
CONTINUE: Final = "[bh-02 restored this conversation; the tool results above are in. Carry on.]"


@dataclass(frozen=True, slots=True)
class Held:
    """What Claude Code's session holds (module docstring). `said` is the text the emitted step
    streamed, which is what the loop's entry for a cut or stopped step carries."""

    count: int = 0
    digest: str = ""
    emitted: Json | None = None
    said: str = ""
    ended: str = CLEAN
    calls: tuple[str, ...] = field(default=())

    def to_json(self) -> dict[str, Any]:
        """As saved in the session's state file."""
        return {
            "count": self.count,
            "digest": self.digest,
            "emitted": self.emitted,
            "said": self.said,
            "ended": self.ended,
            "calls": list(self.calls),
        }

    @classmethod
    def from_json(cls, data: Json) -> Held:
        """From the session's state file. A state saved while calls were parked or a step was
        streaming is from a crash: Claude Code's session holds a call nothing answered, and its
        own resume would invent an answer, so it reads as failed (a rebuild)."""
        ended = str(data.get("ended") or FAILED)
        held = cls(
            int(data.get("count") or 0),
            str(data.get("digest") or ""),
            data.get("emitted") if isinstance(data.get("emitted"), Mapping) else None,
            str(data.get("said") or ""),
            ended,
            tuple(str(c) for c in data.get("calls") or ()),
        )
        return replace(held, ended=FAILED) if ended in (OPEN, RUNNING) else held


@dataclass(frozen=True, slots=True)
class Send:
    """Ask Claude Code one user line: a new query."""

    text: str


@dataclass(frozen=True, slots=True)
class Deliver:
    """Answer the open calls (`results`: call id, content) and, first, push `steer` (a line the
    person typed after a stop) at priority `next`, so the model reads it with the results."""

    results: tuple[tuple[str, str], ...]
    steer: str | None = None


@dataclass(frozen=True, slots=True)
class Rebuild:
    """Write Claude Code a session holding the first `prefix` messages, resume it, and ask `send`."""

    why: str
    prefix: int
    send: str


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON")


def digest(messages: Sequence[Json]) -> str:
    """A stable fingerprint of transcript messages (key order and tuple-or-list aside)."""
    text = json.dumps(list(messages), sort_keys=True, default=_plain, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _accepts(held: Held, entry: Json) -> bool:
    """Whether `entry` is the loop's answer to the step `held` says Claude Code ran last."""
    if entry.get("role") != "assistant":
        return False
    provider = entry.get("provider")
    said = str(entry.get("content") or "")
    if held.ended in (OPEN, CLEAN):
        return provider is not None and provider == held.emitted
    if held.ended == CUT:
        return (provider is not None and provider == held.emitted) or (provider is None and said == held.said)
    if held.ended == STOPPED:
        return provider is None and said.startswith(held.said.rstrip())
    return False


def _expects_entry(held: Held) -> bool:
    return held.ended in (OPEN, CUT, STOPPED) or held.emitted is not None


def _rebuild(why: str, rest: Sequence[Json]) -> Rebuild:
    """Everything but a trailing user line goes in the session; that line is asked."""
    if rest and rest[-1].get("role") == "user":
        return Rebuild(why, len(rest) - 1, str(rest[-1].get("content") or ""))
    return Rebuild(why, len(rest), CONTINUE)


def reconcile(held: Held, rest: Sequence[Json]) -> Send | Deliver | Rebuild:
    """What to do for a request whose non-system messages are `rest` (module docstring)."""
    if held.ended in (FAILED, STRAYED, RUNNING):
        why = {
            FAILED: "the last step failed",
            STRAYED: "Claude Code answered a call itself",
            RUNNING: "a step never finished",
        }[held.ended]
        return _rebuild(why, rest)
    if len(rest) < held.count or (held.count and digest(rest[: held.count]) != held.digest):
        return _rebuild("the conversation is not the one Claude Code holds", rest)
    delta = list(rest[held.count :])
    if _expects_entry(held):
        if not delta or not _accepts(held, delta[0]):
            return _rebuild("the loop's record of the last step is not the step Claude Code ran", rest)
        delta = delta[1:]
    if held.ended == OPEN:
        results = [m for m in delta if m.get("role") == "tool"]
        after = delta[len(results) :]
        if delta[: len(results)] != results or any(m.get("role") != "user" for m in after):
            return _rebuild("the tool results are out of order", rest)
        if sorted(str(m.get("call_id")) for m in results) != sorted(held.calls):
            return _rebuild("the tool results are not the open calls'", rest)
        steer = "\n\n".join(str(m.get("content") or "") for m in after) or None
        return Deliver(tuple((str(m["call_id"]), str(m.get("content") or "")) for m in results), steer)
    if len(delta) == 1 and delta[0].get("role") == "user":
        return Send(str(delta[0].get("content") or ""))
    return _rebuild("the request is not one new user line", rest)
