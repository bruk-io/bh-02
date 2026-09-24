"""The event record: `Event`, `EventKind`, and its dict encoding.

Per SPEC.md section 13's `core` row (amended by decision-060, which confirmed
decision-052, and again by decision-152): "`Event` and its serialization"
belong in `core`, which is otherwise pure -- no I/O, no clock, no randomness,
no subprocess. `ts` is a plain field the caller supplies; nothing in this
module reads a clock, and this module defines no appender.

**There is no appender any more.** decision-152 (2026-09-08) deleted the
per-jail JSONL stream: `run` stamps `ts` and `jail_id` onto the payloads a
mechanism's `EventSource` returns and hands the resulting `Event`s back to
the embedder, which owns a log of its own. `brig/run/events.py` therefore
ships `stamp`/`stamp_all` where it used to ship `EventLog`, and this module
ships `to_dict`/`from_dict` where it used to ship `to_json_line`/
`from_json_line` -- a line-oriented encoding is what a file wanted; a dict is
what a `Handle` carries and what an embedder's own encoder takes.

`Step.events` and `EventSource` are NOT here -- they are `mech`'s (per
decision-052's residual, ruled at the M3 gate), parameterized over this
module's `Event`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

# `Mapping` deliberately comes from `typing`, not `collections.abc` (ruff's
# UP035 wants the latter): `collections.abc` is not in the closed stdlib set
# this module is pure against (tests/unit/test_core_events_purity.py pins the
# set), and `Mapping`'s covariance -- `dict` is invariant in its value type --
# is what lets a caller pass e.g. `dict[str, int]` as `data`, which callers do.
from typing import Any, Final, Mapping  # noqa: UP035

EVENT_VERSION: Final = 1

#: A `data` value's type is closed to JSON scalars -- no nested object, no
#: array. `bool` is listed explicitly (not folded into `int`) and every
#: check below tests `type(value) is ...`/`type(value) in ...` rather than
#: `isinstance`, because `isinstance(True, int)` is `True` in Python and
#: would silently let a bool masquerade as an int (the same reasoning
#: `brig/core/spec.py`'s `Limits.__post_init__` already applies).
DataValue = str | int | float | bool | None
_DATA_VALUE_TYPES: Final = (str, int, float, bool, type(None))


class EventKind(Enum):
    """What a mechanism's sensor is reporting. Two kinds, one per shape of
    thing an `EventSource` can know (SPEC.md sections 6 and 11):

    `SPAWN` is a fact about the jail AS COMPILED, known the instant
    `Mechanism.compile()` returns and before the workload is launched --
    `env_scrub`'s applied env policy and `connect_proxy`'s allowed
    destinations are the two that ship. It is `EventSource.known_at_compile`'s
    kind.

    `LIMIT_TRIP` is `rlimits`' `EventSource.classify_exit` recognizing a
    `SIGXCPU` termination as its own cpu limit tripping -- the one kind that
    can only be known once the workload has ended.

    `EGRESS` is one allow/deny the `connect_proxy` filter made WHILE the
    workload ran (decision-157, 2026-09-08). It is a third shape rather than
    a variant of the other two because of where it comes from: the filter is
    a separate process that may not import brig at all (decision-133), so its
    decisions cannot travel through `EventSource`'s two pure, compile-time
    and exit-time methods. They arrive instead through `brig/run/egress.py`,
    the reader that folds the proxy's own JSONL into the same stamped
    `Event`s everything else in this feed is made of. Without the kind, the
    reader would have to label a live network decision `SPAWN`, which is a
    lie about when it was known.

    **The four lifecycle kinds are gone** (`EXEC`, `EXEC_END`, `KILL`,
    `EXIT`, deleted by decision-152, 2026-09-08). They existed to be written
    into the per-jail JSONL stream and read back off disk: `EXIT` was how a
    rehydrated `Handle` learned an exit status, `EXEC`/`EXEC_END` were how
    teardown found live exec siblings, `KILL` was the audit copy of a
    `KillReport` the caller already holds. With the stream deleted, each of
    those readers has a better source -- see `brig/run/_waiters.py`,
    `brig/run/_execs.py`, and `Handle.kill`'s own return value -- and a kind
    nothing produces is exactly the declared-but-never-used shape this
    library refuses. Pinned by set equality in
    `tests/unit/test_core_events_purity.py`, both directions -- dropping a
    member or adding an unreviewed one is loud."""

    SPAWN = "SPAWN"
    LIMIT_TRIP = "LIMIT_TRIP"
    EGRESS = "EGRESS"


_TOP_LEVEL_KEYS: Final = frozenset({"version", "ts", "kind", "jail_id", "data"})
_REQUIRED_TOP_LEVEL_KEYS: Final = ("ts", "kind", "jail_id")


@dataclass(frozen=True, slots=True)
class Event:
    """One sensor record, stamped.

    Attributes:
        ts: Wall-clock epoch seconds. Injected by the caller (see
            `brig/run/events.py`'s `stamp`) -- never read inside this type,
            which keeps `Event` itself clockless and testable.
        kind: One of `EventKind`'s members.
        jail_id: Which jail this record is about.
        data: Free-form kind-specific payload. Defensively copied at
            construction and exposed immutable (same posture as
            `brig/core/spec.py` and `brig/mech`'s `Step`). Every key must
            be `str`; every value must be `str | int | float | bool |
            None` -- a nested object or array is refused here, at
            construction, which is also what makes `from_dict` refuse one
            (it re-runs this same construction).
    """

    ts: float
    kind: EventKind
    jail_id: str
    data: Mapping[str, DataValue]

    def __post_init__(self) -> None:
        data_copy: dict[str, DataValue] = {}
        for key, value in self.data.items():
            if type(key) is not str:
                raise ValueError(f"Event.data keys must be str, got {key!r} of type {type(key)!r}")
            if type(value) not in _DATA_VALUE_TYPES:
                raise ValueError(
                    f"Event.data[{key!r}] must be str, int, float, bool, or None; "
                    f"got {value!r} of type {type(value)!r}"
                )
            data_copy[key] = value
        object.__setattr__(self, "data", MappingProxyType(data_copy))

    def to_dict(self) -> dict[str, Any]:
        """Versioned, JSON-native, deterministic key order. The embedder's
        own encoder turns this into whatever its log speaks;
        `Handle.to_dict` embeds it directly."""
        return {
            "version": EVENT_VERSION,
            "ts": self.ts,
            "kind": self.kind.value,
            "jail_id": self.jail_id,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Event:
        """Inverse of `to_dict`. Raises `ValueError` for: an unknown
        top-level key; a missing `version`, `ts`, `kind`, or `jail_id`; an
        unsupported `version`; a `kind` string naming no `EventKind`
        member; a `jail_id` that is not a string or a `ts` that is not a
        number. `data` is handed to `Event`'s own constructor unexamined
        beyond "is it an object" -- that constructor is what refuses a
        non-scalar value (a nested object/array), which is the "unknown key
        at any level" refusal applied to `data`'s own, otherwise-open, key
        set: `data`'s contract permits no nested structure at all, so any
        key inside a nested object found there is unaccounted for by
        construction.
        """
        if not isinstance(d, Mapping):
            raise ValueError(f"Event.from_dict: expected a mapping, got {d!r}")

        unknown = set(d) - _TOP_LEVEL_KEYS
        if unknown:
            raise ValueError(f"Event.from_dict: unknown key(s) {sorted(unknown)!r} at top level")

        if "version" not in d:
            raise ValueError("Event.from_dict: missing required key 'version'")
        version = d["version"]
        if version != EVENT_VERSION:
            raise ValueError(
                f"Event.from_dict: unsupported version {version!r}, expected {EVENT_VERSION!r}"
            )

        for required in _REQUIRED_TOP_LEVEL_KEYS:
            if required not in d:
                raise ValueError(f"Event.from_dict: missing required key {required!r}")

        ts = d["ts"]
        if type(ts) not in (int, float):
            raise ValueError(f"Event.from_dict: 'ts' must be a number, got {ts!r}")

        jail_id = d["jail_id"]
        if type(jail_id) is not str:
            raise ValueError(f"Event.from_dict: 'jail_id' must be a str, got {jail_id!r}")

        raw_kind = d["kind"]
        try:
            kind = EventKind(raw_kind)
        except ValueError:
            raise ValueError(
                f"Event.from_dict: {raw_kind!r} is not a valid EventKind value"
            ) from None

        data_raw = d.get("data", {})
        if not isinstance(data_raw, Mapping):
            raise ValueError(f"Event.from_dict: 'data' must be an object, got {data_raw!r}")

        return cls(ts=ts, kind=kind, jail_id=jail_id, data=data_raw)
