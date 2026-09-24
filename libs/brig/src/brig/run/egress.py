"""Folding the egress proxy's decisions back into the embedder's records.

**The gap this closes (decision-157, 2026-09-08).** `connect_proxy` is a
mechanism whose enforcement happens in a separate PROCESS: the filter runs
trusted-side, outside the jail, and it may not import brig at all
(decision-133's empty layer row). So its live allow/deny decisions cannot
travel through `EventSource`, whose two methods are pure and answer at
compile time and at exit -- neither of which is "while the workload was
running". The proxy therefore writes them itself, as one JSON line per
decision, to `<jail_dir>/proxy-decisions.jsonl`; its own docstring said "a
`run`-layer reader may fold it in wherever the embedder's records go", and
`connect_proxy`'s said the same, and for two milestones **no such reader
existed**. Every decision the proxy made reached a file nobody opened -- the
declared-but-uncalled shape this library refuses everywhere else, in the one
place it had been written down twice.

This module is that reader. It is `run`'s job by SPEC.md section 6's own
rule -- "`run` is the only layer permitted to write" a sensor's payloads, and
the only layer that may supply `ts` and `jail_id` -- and by section 11's:
records come back to the embedder as data, and brig keeps no log.

**Why a cursor rather than a tail.** An embedder folds these into the record
of *the action that made the network call*, so it needs "what is new since I
last looked", not "everything so far". The cursor is a byte offset into an
append-only file and only ever advances past COMPLETE lines, so a read that
catches the proxy mid-write returns what was whole and leaves the rest for
the next call -- the same discipline `_execs.py` gets from writing whole
files and renaming them, applied to a stream that cannot be renamed because
its writer appends to it for the life of the jail.

**A lost line weakens an audit trail and never a denial** (SPEC.md law 8:
events are evidence, never the boundary). Nothing in brig's control or
teardown path reads one of these, and the proxy's own decision has already
been enforced on the wire by the time it is written. So this reader is
forgiving in exactly one direction: a file that is absent, or a trailing
fragment that is not yet whole, is "nothing new", never an error. A line that
is whole and is NOT valid JSON is a different thing entirely -- something
other than the proxy is writing to this path -- and raises.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Final

from brig.core import DataValue, Event, EventKind
from brig.mech import EventPayload
from brig.mech.connect_proxy import DECISIONS_FILE
from brig.run.events import stamp_all

#: Keys the proxy writes on every decision line (`brig/proxy/server.py`'s
#: `_Decisions.record`). Named here so a line missing one is refused rather
#: than silently folded in half-populated: the two files are kept in step by
#: `tests/integration/test_egress_decisions.py` reading what a REAL proxy
#: wrote, the same drift discipline `connect_proxy`'s duplicated denial
#: prefix is under.
_DECISION_KEYS: Final = frozenset({"kind", "decision", "host", "port", "detail", "monotonic"})


def decisions_path(jail_dir: str) -> str:
    """Where this jail's proxy writes its decisions.

    The path is `connect_proxy`'s to name -- it is the mechanism that told
    the proxy where to write -- so it is read from that module rather than
    duplicated here.
    """
    return os.path.join(jail_dir, DECISIONS_FILE)


@dataclass(frozen=True, slots=True)
class EgressRead:
    """What one read of the decisions file found, and where to resume.

    Attributes:
        events: One stamped `Event` per whole decision line found past the
            cursor, in the order the proxy wrote them. Empty when there is
            no proxy, no file, or nothing new -- those are the same answer
            because they are the same fact.
        cursor: The offset to pass to the next read. Advances only past
            complete lines, so a partial trailing write is read next time
            rather than dropped or duplicated.
    """

    events: tuple[Event, ...]
    cursor: int


def _payload(record: Any, path: str) -> EventPayload:
    if not isinstance(record, dict):
        raise ValueError(f"egress decision in {path!r} is not a JSON object: {record!r}")
    unknown = set(record) - _DECISION_KEYS
    missing = _DECISION_KEYS - set(record)
    if unknown or missing:
        raise ValueError(
            f"egress decision in {path!r} does not have the proxy's shape: "
            f"unknown key(s) {sorted(unknown)!r}, missing key(s) {sorted(missing)!r}"
        )
    data: dict[str, DataValue] = {
        "egress_decision": record["decision"],
        "host": record["host"],
        "port": record["port"],
        "detail": record["detail"],
        "monotonic": record["monotonic"],
    }
    return EventPayload(kind=EventKind.EGRESS, data=data)


def read_egress_decisions(jail_dir: str, jail_id: str, *, cursor: int = 0) -> EgressRead:
    """Every egress decision written past `cursor`, stamped for the embedder.

    Raises `ValueError` for a whole line that is not the proxy's own record
    shape -- see this module's docstring for why THAT is loud while an absent
    file and a half-written last line are both simply "nothing new".
    """
    path = decisions_path(jail_dir)
    try:
        with open(path, "rb") as decisions:
            decisions.seek(cursor)
            raw = decisions.read()
    except OSError:
        return EgressRead(events=(), cursor=cursor)

    complete, newline, _partial = raw.rpartition(b"\n")
    if not newline:
        return EgressRead(events=(), cursor=cursor)

    payloads = [
        _payload(json.loads(line), path)
        for line in complete.decode("utf-8").splitlines()
        if line.strip()
    ]
    return EgressRead(
        events=stamp_all(payloads, jail_id),
        cursor=cursor + len(complete) + len(newline),
    )
