"""What the loop records on a transcript's entries besides the conversation: when, how long, who answered.

Each entry is appended once and never changed, and a field is left out only where there is nothing
to record (a step that got no chunk has no `first_chunk`, a call refused before approval has no
`answer`). They are the loop's own: a provider sends an entry's `role`, `content` and the keys it
reads, never these (CONTRACTS.md: message, step record, call record; decision-0009).

Time is data. `at` is UTC ISO-8601 to the millisecond with `Z` (`2026-10-18T03:47:12.345Z`), so it
sorts as text (`stamp`); a duration is seconds from a monotonic clock, rounded to the
millisecond. The loop reads both from one `Clock` it is given, so a test gives its own.

A step's record (`StepRecord`) is built from what the step's chunks said (`step_record`): its
usage chunks summed by the one function `/compact` sums its own with (`summed`), the id that
answered, and the model's settings when they are new to the conversation (`settings_to_record`).

A call's record (`CallRecord`, on its `tool` entry) is built from what the loop saw of the call
(`call_record`): when it reached approval, what approval made of it (`Answer`) and how long the
person took, how long the tool ran, the sub-agent it started and the calls its input made through
`tools` (`nested_record`).

Everything here is pure but the real `Clock` and `day_of`, which reads the machine's time zone.
"""

import datetime
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import partial
from typing import Any, Final, Literal, NotRequired, TypedDict, cast

from agent_cordis_plugin.toolset import LISTED

__all__ = [
    "Answer",
    "CallRecord",
    "Clock",
    "NestedRecord",
    "Settings",
    "StepRecord",
    "Usage",
    "call_record",
    "day_of",
    "nested_record",
    "settings_to_record",
    "stamp",
    "step_record",
    "summed",
]

type Json = Mapping[str, Any]

# The keys of a model's `settings` a transcript records (CONTRACTS.md: model).
_SETTINGS: Final = ("model", "provider", "max_tokens", "temperature")
_MILLISECONDS: Final = 3  # the places a duration is rounded to


@dataclass(frozen=True, slots=True)
class Clock:
    """The one clock the loop reads: `now()` the time as an aware UTC datetime, `monotonic()` seconds
    from a clock that never goes back, for durations. The real clock unless a test gives its own."""

    now: Callable[[], datetime.datetime] = partial(datetime.datetime.now, datetime.UTC)
    monotonic: Callable[[], float] = time.monotonic


class Answer(StrEnum):
    """What approval made of a call (`Asked.approve`): `unasked`, the `approval` rule let it run and
    nobody was asked; `yes` or `no`, the person was asked and said that. A `no` call never runs,
    and the member `no` is a non-empty string, so a use of an answer is a `match` on it, never a
    test of its truth. Written to a call's record as the word."""

    UNASKED = "unasked"
    YES = "yes"
    NO = "no"


class Settings(TypedDict, closed=True):
    """What a model's steps are made with: the named model (`ENDPOINT/MODEL`), its provider, and
    the `max_tokens` and `temperature` it sends (each left out when the model sends none)."""

    model: str
    provider: str
    max_tokens: NotRequired[int]
    temperature: NotRequired[float]


class Usage(TypedDict, closed=True):
    """A step's usage chunks added up (CONTRACTS.md: event): `partial` when its last part is."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    cost_usd: NotRequired[float]
    partial: NotRequired[Literal[True]]


class StepRecord(TypedDict, closed=True):
    """A step's `step` on its assistant entry: `at`, when its request was handed to the model;
    `first_chunk`, the seconds to its first chunk of any kind (a Claude Code start or rebuild and a
    provider's own retry included); `took`, the seconds to its last; `model`, the id that answered
    (the provider's `usage` chunk says it); `usage`, its usage chunks added up; `settings`, only on a
    conversation's first step and one whose settings differ from the last recorded; `tool_changes`,
    only `listed` (absent: `fixed`). No chunk came (a step that failed or was stopped first): no
    `first_chunk` and no `took`; a provider that reported no usage or model leaves those out."""

    at: str
    first_chunk: NotRequired[float]
    took: NotRequired[float]
    model: NotRequired[str]
    usage: NotRequired[Usage]
    settings: NotRequired[Settings]
    tool_changes: NotRequired[Literal["listed"]]


class CallRecord(TypedDict, closed=True):
    """A call's `call` on its `tool` entry: `at`, when it reached approval, or was refused before it
    (an unknown or malformed call, a tool not running); `answer`, what approval made of it
    (`Answer`), left out for a call refused before approval or never reached (the reply was
    stopped first); `waited`, the seconds from the question put to the person to its answer,
    queueing behind another question included, only when someone was asked; `took`, the seconds the
    tool ran (a question the tool puts during its own run stays inside it); `child`, the sub-agent
    the call started; `nested`, the calls its input made through `tools`, in order."""

    at: str
    answer: NotRequired[Answer]
    waited: NotRequired[float]
    took: NotRequired[float]
    child: NotRequired[str]
    nested: NotRequired[list[NestedRecord]]


class NestedRecord(TypedDict, closed=True):
    """A call an input made through `tools.NAME(...)`, in its call's `nested`: a `CallRecord` with
    its tool's `name`, and no `nested` of its own (the calls it made are listed beside it)."""

    name: str
    at: str
    answer: NotRequired[Answer]
    waited: NotRequired[float]
    took: NotRequired[float]
    child: NotRequired[str]


def stamp(moment: datetime.datetime) -> str:
    """`moment` (aware) as a transcript keeps a time: UTC ISO-8601 to the millisecond with `Z`."""
    return moment.astimezone(datetime.UTC).isoformat(timespec="milliseconds").removesuffix("+00:00") + "Z"


def day_of(moment: datetime.datetime) -> str:
    """The date the loop tells the model (`2026-10-07`) at `moment` (aware): the person's day,
    where the program runs, so the model is not told tomorrow in the evening of a west-of-UTC day."""
    return moment.astimezone().date().isoformat()


def summed(usage: Sequence[Json]) -> Usage | None:
    """A step's usage chunks as one, or None for none: each is a part of the step's (CONTRACTS.md:
    event), so the counts and costs add up, and it is `partial` when its last part is (the step
    stopped before its output was counted). One total, so the length of /compact's answer never
    depends on how many parts a provider sends."""
    if not usage:
        return None
    total: Usage = {
        "input_tokens": _added(usage, "input_tokens"),
        "output_tokens": _added(usage, "output_tokens"),
        "cache_read_input_tokens": _added(usage, "cache_read_input_tokens"),
        "cache_creation_input_tokens": _added(usage, "cache_creation_input_tokens"),
    }
    if costs := [float(u["cost_usd"]) for u in usage if u.get("cost_usd") is not None]:
        total["cost_usd"] = sum(costs)
    if usage[-1].get("partial"):
        total["partial"] = True
    return total


def _added(usage: Sequence[Json], key: str) -> int:
    return sum(int(u.get(key) or 0) for u in usage)


def settings_to_record(given: object, messages: Sequence[Json]) -> Settings | None:
    """The model's `given` settings (its optional `settings` attribute: a mapping with at least the
    `model` and `provider` of `Settings`; anything else is none) when the conversation `messages`
    should record them: it has recorded none yet, or the last it recorded (a step's `settings`,
    found from the end, a resumed conversation's included) differs. None otherwise."""
    if not isinstance(given, Mapping):
        return None
    now = {key: given[key] for key in _SETTINGS if given.get(key) is not None}
    if not {"model", "provider"} <= now.keys():  # what a `Settings` always has
        return None
    last = next(
        (m["step"]["settings"] for m in reversed(messages) if "settings" in (m.get("step") or {})), None
    )
    return None if now == last else cast(Settings, now)


def step_record(
    at: datetime.datetime,
    began: float,
    first: float | None,
    last: float | None,
    usage: Sequence[Json],
    settings: Settings | None,
    mode: str,
) -> StepRecord:
    """A step's `step`: it began at `at`, its request handed over at the monotonic reading `began`; its
    first and last chunk came at the readings `first` and `last` (None: none came); `usage`, the
    usage chunks it sent; `settings`, what `settings_to_record` chose; `mode`, how the model wanted
    its tools offered (`toolset.LISTED` is recorded, `fixed` is the absence)."""
    record = StepRecord(at=stamp(at))
    if first is not None and last is not None:
        record["first_chunk"] = round(first - began, _MILLISECONDS)
        record["took"] = round(last - began, _MILLISECONDS)
    if answered := next((str(u["model"]) for u in reversed(usage) if u.get("model")), None):
        record["model"] = answered
    if (total := summed(usage)) is not None:
        record["usage"] = total
    if settings is not None:
        record["settings"] = settings
    if mode == LISTED:
        record["tool_changes"] = LISTED
    return record


def call_record(
    at: datetime.datetime,
    answer: Answer | None,
    waited: float | None,
    took: float | None,
    child: str | None,
    nested: Sequence[NestedRecord],
) -> CallRecord:
    """A call's `call`: it reached approval (or was refused) at `at`; `answer` is what approval made
    of it (None: it was refused before approval, or never reached it); `waited`, the seconds the
    person took (None unless they were asked); `took`, the seconds its tool ran (None: it did not);
    `child`, the sub-agent it started; `nested`, the calls its input made. Each left out when
    there is none."""
    record = CallRecord(at=stamp(at))
    if answer is not None:
        record["answer"] = answer
    if waited is not None:
        record["waited"] = round(waited, _MILLISECONDS)
    if took is not None:
        record["took"] = round(took, _MILLISECONDS)
    if child is not None:
        record["child"] = child
    if nested:
        record["nested"] = list(nested)
    return record


def nested_record(name: str, record: CallRecord) -> NestedRecord:
    """The call `record` an input made through `tools`, as its call's `nested` lists it: with the
    name of its tool, and none of its own `nested`."""
    return cast(
        NestedRecord, {"name": name} | {key: value for key, value in record.items() if key != "nested"}
    )
