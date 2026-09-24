"""Event record encode/decode: round-trip and unknown-key refusal,
mirroring SPEC.md section 5's serialization posture. Pure, no I/O -- and
there is no file half to pair it with any more: decision-152 (2026-09-08)
deleted the per-jail JSONL stream, so `to_dict`/`from_dict` replaced
`to_json_line`/`from_json_line` and the one-record-per-line and
newline-escaping cases went with the line format that needed them.

Per decision-052/decision-060 (task-028), the record lives in
`brig.core.events`, not `brig.run.events` -- imported from its home.
"""

from __future__ import annotations

import pytest

from brig.core.events import EVENT_VERSION, Event, EventKind


def _base_obj() -> dict[str, object]:
    return {
        "version": EVENT_VERSION,
        "ts": 1234.5,
        "kind": "SPAWN",
        "jail_id": "jail-1",
        "data": {"argv": "echo hi"},
    }


@pytest.mark.unit
@pytest.mark.parametrize("kind", list(EventKind))
def test_round_trip_all_kinds(kind: EventKind) -> None:
    """AC #2: for each kind, to_dict then from_dict returns an equal
    Event -- object equality, not dict identity."""
    event = Event(
        ts=42.5,
        kind=kind,
        jail_id="jail-1",
        data={"str_val": "x", "int_val": 1, "float_val": 2.5, "bool_val": True, "none_val": None},
    )
    encoded = event.to_dict()
    result = Event.from_dict(encoded)
    assert result == event


@pytest.mark.unit
def test_a_newline_inside_a_data_value_round_trips() -> None:
    """What survives from the deleted one-record-per-line test: a literal
    newline in a data value is content, and comes back unchanged. The
    escaping half was a property of the JSONL line format, which is gone
    (decision-152)."""
    event = Event(ts=1.0, kind=EventKind.SPAWN, jail_id="jail-1", data={"msg": "line1\nline2"})
    assert Event.from_dict(event.to_dict()).data["msg"] == "line1\nline2"


@pytest.mark.unit
def test_unknown_top_level_key_refused_control_parses() -> None:
    """AC #4: an extra top-level key raises; the same dict without it
    parses (control)."""
    base = _base_obj()
    bad = dict(base, extra_field="not part of the schema")

    with pytest.raises(ValueError):
        Event.from_dict(bad)

    # Control: the same dict without the extra key parses.
    Event.from_dict(base)


@pytest.mark.unit
def test_unknown_key_nested_in_data_refused_control_parses() -> None:
    """AC #4: an extra key nested inside `data` raises. `data`'s value
    type is closed to JSON scalars (str, int, float, bool, None) -- a
    nested object is refused outright by Event's own constructor (which
    from_dict re-runs), so any key inside that nested object is
    unaccounted for by construction. Control: the same line without that
    entry parses.
    """
    base = _base_obj()
    bad = dict(base, data={"argv": "echo hi", "nested": {"unexpected_inner_key": 1}})

    with pytest.raises(ValueError):
        Event.from_dict(bad)

    # Control: the same dict without the offending (nested) data entry parses.
    good = dict(base, data={"argv": "echo hi"})
    Event.from_dict(good)


@pytest.mark.unit
def test_missing_version_refused() -> None:
    obj = _base_obj()
    del obj["version"]
    with pytest.raises(ValueError):
        Event.from_dict(obj)


@pytest.mark.unit
def test_wrong_version_refused() -> None:
    obj = dict(_base_obj(), version=EVENT_VERSION + 1)
    with pytest.raises(ValueError):
        Event.from_dict(obj)


@pytest.mark.unit
def test_unknown_kind_refused() -> None:
    obj = dict(_base_obj(), kind="NOT_A_REAL_KIND")
    with pytest.raises(ValueError):
        Event.from_dict(obj)


@pytest.mark.unit
def test_data_defensively_copied_and_immutable() -> None:
    """Same posture as task-014/task-015: mutating the caller's dict after
    construction must not affect the Event, and the exposed mapping must
    reject direct mutation."""
    source = {"a": 1}
    event = Event(ts=1.0, kind=EventKind.SPAWN, jail_id="jail-1", data=source)
    source["a"] = 2
    assert event.data["a"] == 1

    with pytest.raises(TypeError):
        event.data["a"] = 3  # type: ignore[index]


@pytest.mark.unit
def test_data_rejects_non_scalar_value_at_construction() -> None:
    with pytest.raises(ValueError):
        Event(
            ts=1.0,
            kind=EventKind.SPAWN,
            jail_id="jail-1",
            data={"nested": {"x": 1}},  # type: ignore[dict-item]
        )


@pytest.mark.unit
def test_data_rejects_bool_masquerading_via_isinstance_gap() -> None:
    """type()-based checks, not isinstance: bool is a legitimate data
    value type on its own, but this pins that the check is exact-type (a
    regression to isinstance(..., int) would still accept this, silently
    changing nothing observable here -- the real regression this guards
    is an accidental *rejection* of bool via an int-first isinstance
    check elsewhere)."""
    event = Event(ts=1.0, kind=EventKind.SPAWN, jail_id="jail-1", data={"flag": True})
    assert event.data["flag"] is True
