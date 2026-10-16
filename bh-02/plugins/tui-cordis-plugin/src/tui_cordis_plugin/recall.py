"""The lines sent this run, and where the composer is in them (TASK-0089.02): pure.

`Recall` is a value: the lines sent so far, oldest first, and which of them the composer
shows, if it shows one. A step through them (`older`, `newer`) returns the next `Recall` with
the text to show, or None when there is no step to take, and the keys that asked for it then
do what they did before. Nothing here changes a line already sent: a recalled line that is
edited and sent is one more line (`remember`), never a change to the old one.
"""

from dataclasses import dataclass

__all__ = ["Recall", "newer", "older", "recalled", "remember"]


@dataclass(frozen=True, slots=True)
class Recall:
    """Every line sent this run (a message, a `/command`, a `!` line), oldest first, in `sent`.
    `at` is the index of the line the composer shows, or None while it shows the person's own
    text; `draft` is that text, kept from the first step back until a step forward gives it
    back (empty while `at` is None)."""

    sent: tuple[str, ...] = ()
    at: int | None = None
    draft: str = ""


@dataclass(frozen=True, slots=True)
class _Step:
    """One move through the history: where the person is now, and the text to show there."""

    recall: Recall
    text: str


def remember(recall: Recall, line: str) -> Recall:
    """`recall` once `line` is sent: it is the newest line, and the person is writing their
    own text again (the composer was cleared)."""
    return Recall((*recall.sent, line))


def older(recall: Recall, text: str) -> _Step | None:
    """One line back from the composer's `text`: the newest line sent when the person was
    writing (their `text` is kept as the draft), else the one before the one shown. None when
    nothing was sent or the oldest is shown already."""
    if not recall.sent:
        return None
    if recall.at is None:
        newest = len(recall.sent) - 1
        return _Step(Recall(recall.sent, newest, text), recall.sent[newest])
    if recall.at == 0:
        return None
    return _Step(Recall(recall.sent, recall.at - 1, recall.draft), recall.sent[recall.at - 1])


def newer(recall: Recall) -> _Step | None:
    """One line forward: the one after the one shown, or, past the newest, the draft that was
    being typed. None while the person is writing their own text (there is nothing to go
    forward to)."""
    if recall.at is None:
        return None
    if recall.at == len(recall.sent) - 1:
        return _Step(Recall(recall.sent), recall.draft)
    return _Step(Recall(recall.sent, recall.at + 1, recall.draft), recall.sent[recall.at + 1])


def recalled(recall: Recall, text: str) -> bool:
    """Whether `text` is a line recalled from the history, as it was sent: edited, it is the
    person's own again."""
    return recall.at is not None and text == recall.sent[recall.at]
