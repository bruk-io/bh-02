"""What the model is told when its instructions change partway through a conversation.

A request sends the system prompt first, so a model server can reuse its work on a
conversation only up to the first token that differs from the last request: a prompt that
changes (an extension loaded, the git branch switched, CLAUDE.md edited) makes the whole
conversation new to it again. With a local model that is minutes of prompt processing before
the first new token, which looks like a freeze; with Claude, a restart of Claude Code and the
loss of its prompt cache. So the loop keeps the prompt a conversation began with, and says what
changed after the conversation's latest message instead (`changes`).

The transcript keeps the prompt whole once, as the conversation began with it. A later reading
that differs is kept as the edits that turn the reading before it into this one (`edits`), not
as another whole copy, and what the model was last told is found by applying them in turn over
the first (`latest`).
"""

import difflib
from collections.abc import Iterable, Mapping
from typing import Any

__all__ = ["changes", "edits", "latest"]

_NAMED = 100  # how much of a gone part's first line names it
_BLANK = "\n\n"  # where `edits` splits a reading into paragraphs, exactly


def _parts(text: str) -> list[str]:
    return [part.strip() for part in text.split("\n\n") if part.strip()]


def changes(before: str, after: str) -> str:
    """What the model is told when its instructions read `after` and it was last told `before`:
    each part (a paragraph) that is new or reads differently, whole, and the first line of each
    part that is gone. '' when nothing changed."""
    old, new = _parts(before), _parts(after)
    now: list[str] = []
    gone: list[str] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if op in ("replace", "insert"):
            now += new[j1:j2]
        if op in ("replace", "delete"):
            gone += old[i1:i2]
    # A part that reads differently mostly starts the same way (the one with the working
    # directory and the branch; a CLAUDE.md section under its heading): its new reading
    # says enough, so it is not also named as gone.
    starts = {part.splitlines()[0] for part in now}
    named = [_named(part) for part in gone if part.splitlines()[0] not in starts]
    if not now and not named:
        return ""
    head = "(bh-02: your instructions have changed since this conversation began."
    quoted = "; ".join(f'"{line}"' for line in named)
    if not now:
        return f"{head} No longer in them: {quoted}.)"
    lines = [f"{head} Where they differ, they now read:)", "", "\n\n".join(now)]
    if named:
        lines += ["", f"(No longer in them: {quoted}.)"]
    return "\n".join([*lines, "", "(End of what changed.)"])


def _named(part: str) -> str:
    """A part, by its first line (cut short)."""
    line = part.splitlines()[0].strip()
    return line if len(line) <= _NAMED else line[: _NAMED - 1] + "…"


def edits(before: str, after: str) -> list[dict[str, Any]]:
    """What turns the reading `before` into `after`, by paragraph: for each run of `before`'s
    paragraphs that reads differently, where it starts (`at`, counting from 0), how many of them
    are gone from there (`drop`) and the paragraphs that stand there now (`add`), in order. The
    split is exact (at every blank line, nothing stripped), so applying them (`latest`) gives
    `after` to the character. [] when the two read the same."""
    old, new = before.split(_BLANK), after.split(_BLANK)
    return [
        {"at": i1, "drop": i2 - i1, "add": new[j1:j2]}
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes()
        if op != "equal"
    ]


def latest(entries: Iterable[Mapping[str, Any]]) -> str | None:
    """The prompt as the transcript's `system` entries, in order, say the model was last told it:
    an entry with `edits` is the reading before it with those applied; any other is a reading
    kept whole, its `content` (a conversation's first, and every one in a transcript kept before
    the loop kept edits). None when there are none."""
    reading: str | None = None
    for entry in entries:
        if "edits" in entry:
            reading = _applied(reading or "", entry["edits"])
        else:
            reading = str(entry.get("content") or "")
    return reading


def _applied(before: str, steps: Iterable[Mapping[str, Any]]) -> str:
    """`before` with `edits(before, after)` applied, which is `after`."""
    old = before.split(_BLANK)
    new: list[str] = []
    kept = 0  # how many of `old`'s paragraphs are dealt with
    for step in steps:
        at = int(step["at"])
        new += [*old[kept:at], *(str(part) for part in step["add"])]
        kept = at + int(step["drop"])
    return _BLANK.join([*new, *old[kept:]])
