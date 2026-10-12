"""The parts of a jail's dict that `Handle` and `Jail` share: its report and
its channels, as JSON-native data and back (SPEC.md section 5's posture: an
unknown key at any level is a refusal)."""

from collections.abc import Mapping, Sequence
from typing import Any, Final

from brig.core import AXES, Axis, Channel, ChannelKind, EnforcementReport, Grade, Graded

_CHANNEL_KEYS: Final = frozenset({"name", "kind", "endpoint"})
_REPORT_AXIS_KEYS: Final = frozenset({"grade", "detail"})


def report_to_dict(report: EnforcementReport) -> dict[str, Any]:
    """`EnforcementReport` has no `to_dict` of its own (core ships only
    `Spec`'s per task-007) -- this is the serialization of it `Handle`'s and
    `Jail`'s dicts share. Same shape idiom as `Spec.to_dict`: enums as
    their `.value` string, one entry per axis."""
    return {
        axis.value: {"grade": report.axes[axis].grade.value, "detail": report.axes[axis].detail}
        for axis in AXES
    }


def report_from_dict(d: Mapping[str, Any], *, who: str) -> EnforcementReport:
    """Inverse of `report_to_dict`; `who` names the caller in a refusal. Runs
    `EnforcementReport`'s own constructor, so a missing axis or bogus grade
    string raises from there, not from a from_dict-specific check (same
    posture as `Spec.from_dict`). Also refuses an unknown key inside any
    per-axis entry (SPEC.md section 5: "an unknown key at any level is a
    refusal"), same shape as `channels_from_list`'s check.

    Raises:
        ValueError: an axis is missing, or an entry has an unknown key or a
            grade that is not one.
    """
    axes: dict[Axis, Graded] = {}
    for axis in AXES:
        if axis.value not in d:
            raise ValueError(f"{who}: report is missing axis {axis.value!r}")
        entry = d[axis.value]
        unknown = set(entry) - _REPORT_AXIS_KEYS
        if unknown:
            raise ValueError(f"{who}: unknown key(s) {sorted(unknown)!r} in report[{axis.value!r}]")
        axes[axis] = Graded(grade=Grade(entry["grade"]), detail=entry.get("detail", ""))
    return EnforcementReport(axes=axes)


def channels_to_list(channels: Mapping[str, Channel]) -> list[dict[str, str]]:
    """`channels` as JSON-native data, one entry per channel."""
    return [
        {"name": c.name, "kind": c.kind.value, "endpoint": c.endpoint} for c in channels.values()
    ]


def channels_from_list(raw: Sequence[Mapping[str, Any]], *, who: str) -> dict[str, Channel]:
    """Inverse of `channels_to_list`, by name; `who` names the caller in a
    refusal.

    Raises:
        ValueError: an entry has an unknown key, or a kind that is not one.
    """
    result: dict[str, Channel] = {}
    for entry in raw:
        unknown = set(entry) - _CHANNEL_KEYS
        if unknown:
            raise ValueError(f"{who}: unknown key(s) {sorted(unknown)!r} in channels[]")
        channel = Channel(
            name=entry["name"],
            kind=ChannelKind(entry["kind"]),
            endpoint=entry["endpoint"],
        )
        result[channel.name] = channel
    return result
