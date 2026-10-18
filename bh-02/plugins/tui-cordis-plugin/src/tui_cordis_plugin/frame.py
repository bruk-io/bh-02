"""What the app's frame says: the status bar's usage and model fields, and the palette's
entries. Pure: every function here is of plain values, so it is tested without an app."""

import functools
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "Keyless",
    "ModelShown",
    "PaletteEntry",
    "Usage",
    "add_usage",
    "completions",
    "enter_takes",
    "slash_line",
    "model_forms",
    "model_text",
    "listed",
    "output_uncounted",
    "phase_after",
    "phase_of",
    "starting_after",
    "keyless_after",
    "palette_entries",
    "total_usage",
    "usage_forms",
    "usage_text",
]


@dataclass(frozen=True, slots=True)
class Usage:
    """A session's running totals of usage events (CONTRACTS.md: event); `cost_usd` is None
    until a provider reports a cost. `cached_tokens` is how many of `input_tokens` were read
    from the provider's prompt cache. `uncounted` is how many replies ended before their provider
    counted their output (a reply stopped mid-stream, its usage still `partial`), so
    `output_tokens` and `cost_usd` are then lower bounds, which the field says with a `+`."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    cached_tokens: int = 0
    uncounted: int = 0


def add_usage(total: Usage, event: Mapping[str, Any]) -> Usage:
    """`total` with one usage event added: each event is one step's usage, so they sum."""
    cost = event.get("cost_usd")
    return Usage(
        total.input_tokens + int(event.get("input_tokens") or 0),
        total.output_tokens + int(event.get("output_tokens") or 0),
        total.cost_usd if cost is None else (total.cost_usd or 0.0) + float(cost),
        total.cached_tokens + int(event.get("cache_read_input_tokens") or 0),
        total.uncounted + int(event.get("uncounted") or 0),  # a `carried` entry's
    )


def output_uncounted(total: Usage) -> Usage:
    """`total` after a reply that ended with its usage still `partial`: its output not counted."""
    return Usage(
        total.input_tokens, total.output_tokens, total.cost_usd, total.cached_tokens, total.uncounted + 1
    )


# Entries that add to the usage totals: a step's usage event, and the history file's own
# `carried` entry (what the usage events it trimmed away added up to; see `history`).
_USAGE_ENTRIES = frozenset({"usage", "carried"})


def total_usage(entries: Iterable[Mapping[str, Any]]) -> Usage:
    """The totals of every usage event in `entries` (a session's history, say), counting each
    reply that ended (`reply_end`) with its last usage event still `partial` as `uncounted`."""
    return functools.reduce(_add_entry, entries, (Usage(), False))[0]


def _add_entry(state: tuple[Usage, bool], entry: Mapping[str, Any]) -> tuple[Usage, bool]:
    """(totals, whether the reply's usage so far is `partial`) after one history entry."""
    total, partial = state
    match entry.get("type"):
        case "usage":
            return add_usage(total, entry), bool(entry.get("partial"))
        case "carried":
            return add_usage(total, entry), partial
        case "reply_end" if partial:
            return output_uncounted(total), False
    return total, partial


def usage_text(total: Usage) -> str:
    """The usage field: tokens in, how many of them came from the prompt cache (when any did),
    tokens out, and the cost when there is one; the last two end in `+` once a stopped reply's
    output went uncounted (they are then at least that)."""
    more = "+" if total.uncounted else ""
    parts = [f"{_tokens(total.input_tokens)} in", f"{_tokens(total.output_tokens)}{more} out"]
    if total.cached_tokens:
        parts.insert(1, f"{_tokens(total.cached_tokens)} cached")
    if total.cost_usd is not None:
        parts.append(f"${total.cost_usd:.4f}{more}")
    return " · ".join(parts)


def usage_forms(total: Usage) -> tuple[str, str]:
    """The usage field, then its short form for a narrow status bar: `12k in · 678 out ·
    $0.1234`, then `12k/678 $0.12` (each count in three or four cells)."""
    more = "+" if total.uncounted else ""
    short = f"{_rounded(total.input_tokens)}/{_rounded(total.output_tokens)}{more}"
    if total.cost_usd is not None:
        short = f"{short} ${total.cost_usd:.2f}{more}"
    return usage_text(total), short


def _rounded(count: int) -> str:
    """A token count in three or four cells: `678`, `1.2k`, `12k`, `1.2M`."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 10_000:
        return f"{count // 1000}k"
    return f"{count / 1000:.1f}k" if count >= 1000 else str(count)


def _tokens(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 10_000:
        return f"{count / 1000:.0f}k"
    return f"{count:,}"


@dataclass(frozen=True, slots=True)
class ModelShown:
    """The model field's model: its `name`, its `provider` (empty when the name is no model there is,
    or the row is another component), and whether the model row can't use it (`unusable`: the
    status bar says so, since a name alone reads as a model that runs)."""

    name: str
    provider: str = ""
    unusable: bool = False


def model_text(current: Mapping[str, Any]) -> ModelShown:
    """The model field's model: the name and provider the `models` value says the model row
    names now, and whether it says that model is unusable (CONTRACTS.md: models; the provider is
    empty when the name is no model there is). A name is never blank: `none` when there is none."""
    return ModelShown(
        str(current.get("name") or "none"),
        str(current.get("provider") or ""),
        bool(current.get("unusable")),
    )


# A row's phase, as the status bar tells it: up, coming (back) up, or failed.
_UP, _STARTING, _FAILED = "up", "starting", "failed"
# Lifecycle kinds (cordis's `Event.kind`) that begin a row's coming up: from the moment it
# unloads (a reload, a restart, a replacement) until it is active again.
_BEGINS = frozenset({"unloading", "reload"})
# Kinds that end it: up, or down for good (failed, retired, cancelled).
_ENDS = frozenset({"active", "inactive", "failed", "failed-inactive", "cancelled"})


def phase_of(status: str | None) -> str:
    """A row's phase from the loader's `status()` for it (cordis's `describe`): `up` when
    active (or not a live row: disabled, not in the composition), `failed` when failed or
    unresolved, else (`loading`, `unloading`, `inactive`) `starting`."""
    if status is None or status == "disabled" or status.startswith("active"):
        return _UP
    if status.startswith(("failed", "unresolved")):
        return _FAILED
    return _STARTING


def phase_after(kind: str, phase: str, listed: bool = True) -> str:
    """A row's phase after one of its lifecycle events: `starting` from `unloading` or
    `reload` (so it stays starting through a restart that reloads it more than once), `up`
    at `active`, `failed` at a failure. A row down for good has nothing to wait for, so it
    is `up` again: `cancelled` (the program shutting down), or `inactive` when the layers no
    longer name it (`listed`: a layer edit removed or disabled it). An `inactive` of a row
    still listed is the moment between a row's old fiber and its replacement, not the end of
    its coming up; any other kind leaves the phase as it was."""
    if kind in _BEGINS:
        return _STARTING
    if kind == "active" or kind == "cancelled" or (kind == "inactive" and not listed):
        return _UP
    if kind in ("failed", "failed-inactive"):
        return _FAILED
    return phase


def listed(entries: Sequence[Any], row: str) -> bool:
    """Whether the layers still name row `row`, enabled (cordis's `Entry.disabled`)."""
    return any(getattr(e, "id", None) == row and not getattr(e, "disabled", False) for e in entries)


def model_forms(model: ModelShown, phase: str) -> tuple[str, ...]:
    """The model field in `phase`, then a shorter form for a narrow status bar: `claude/sonnet
    (claude-code)` then `claude/sonnet` when it is up, `claude/sonnet (claude-code, starting…)` then
    `claude/sonnet…` while the model row comes up, `claude/sonnet (claude-code, failed)` then
    `claude/sonnet ✗` when it failed. A model the row can't use says so, `typo (unusable)` then
    `typo ✗`, whatever the phase adds. No provider: the name alone."""
    said = {_STARTING: "starting…", _FAILED: "failed"}.get(phase)
    flagged = "unusable" if model.unusable else ""
    inside = ", ".join(part for part in (model.provider, flagged, said) if part)
    full = f"{model.name} ({inside})" if inside else model.name
    broken = f"{model.name} ✗"
    short = {_STARTING: f"{model.name}…", _FAILED: broken}.get(
        phase, broken if model.unusable else model.name
    )
    return (full, short) if full != short else (full,)


def starting_after(starting: frozenset[str], kind: str, row: str) -> frozenset[str]:
    """The rows coming (back) up after one lifecycle event: a row joins at `unloading` or
    `reload` and leaves when it is active or down (any other kind changes nothing).

    Unlike `phase_after`, `inactive` ends it: here it cannot be told from a row down for good
    (a dependent whose provider left, a retired row), which must not keep a line waiting. A
    restart's new fiber joins again at its `reload`, and the bridge says a line kept in the
    moment between waits then (`Bridge.row_changed`)."""
    if kind in _BEGINS:
        return starting | {row}
    if kind in _ENDS:
        return starting - {row}
    return starting


@dataclass(frozen=True, slots=True)
class Keyless:
    """What the ui has heard of which rows bind a key. The chat row depends on keys alone, so
    a line never waits on a row that binds none (a status-bar row such as `status`).
    `rows` came up binding nothing; `keyed` have been heard binding a key; `rising` are the
    rows heard from their `reload` on and not yet `active`, and `bound` those of them that
    bound a key on the way."""

    rows: frozenset[str] = frozenset()
    keyed: frozenset[str] = frozenset()
    rising: frozenset[str] = frozenset()
    bound: frozenset[str] = frozenset()

    @property
    def unwaited(self) -> frozenset[str]:
        """The rows no line waits on: those that came up binding nothing, and one coming up for
        the first time the ui hears of that has bound nothing yet (it is named once it binds)."""
        return self.rows | (self.rising - self.keyed)


def keyless_after(keyless: Keyless, kind: str, row: str) -> Keyless:
    """What is known of which rows bind a key after one lifecycle event of `row`: a `reload`
    starts watching its setup, a `bind` records a key, and `active` settles it: keyless if it
    bound nothing on the way up. A row whose setup was not heard from its `reload` on (it came
    up before the ui listened) is not taken for keyless."""
    rows, keyed, rising, bound = keyless.rows, keyless.keyed, keyless.rising, keyless.bound
    if kind == "reload":
        return Keyless(rows, keyed, rising | {row}, bound - {row})
    if kind == "bind":
        return Keyless(rows - {row}, keyed | {row}, rising, bound | {row})
    if kind == "active" and row in rising:
        if row in bound:
            return Keyless(rows - {row}, keyed, rising - {row}, bound - {row})
        return Keyless(rows | {row}, keyed - {row}, rising - {row}, bound)
    return keyless


@dataclass(frozen=True, slots=True)
class PaletteEntry:
    """One command in the palette. `call` is what it runs (`/name`); a command that takes
    arguments (`usage`) is put in the composer to finish instead of run at once."""

    call: str
    help: str
    usage: str = ""

    @property
    def takes_arguments(self) -> bool:
        return bool(self.usage)


# What the ui itself answers besides the broker's commands: `/help` (the broker's own, not in
# its specs) and `/exit`, which the app handles before any line reaches the input.
_OWN = (
    PaletteEntry("/help", "list the commands"),
    PaletteEntry("/exit", "leave bh-02 (or Ctrl-Q)"),
)


def palette_entries(specs: Sequence[Mapping[str, Any]]) -> list[PaletteEntry]:
    """The palette's entries: every command offered (CONTRACTS.md: a spec is name, help,
    usage, and `choices`, the arguments offered as entries of their own: `/model claude/haiku`),
    then `/help` and `/exit`; a call offered twice shows once, the first one. A command's
    `choices` that fail to read (a models file mid-edit) offer none this time. Control
    characters (C0, DEL, C1) are stripped from each entry's call, help and usage: a command's
    text is data from a row, an extension or the models file, and a terminal would act on them.
    Both views of the commands (the palette and the composer's list) read this one function."""
    offered: list[PaletteEntry] = []
    for spec in specs:
        if not spec.get("name"):
            continue
        call = f"/{spec['name']}"
        offered.append(PaletteEntry(call, str(spec.get("help", "")), str(spec.get("usage") or "")))
        offered += [PaletteEntry(f"{call} {c['args']}", str(c.get("help", ""))) for c in _choices(spec)]
    entries: dict[str, PaletteEntry] = {}
    for entry in map(_cleaned, [*offered, *_OWN]):
        if entry.call.strip("/"):
            entries.setdefault(entry.call, entry)
    return list(entries.values())


_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _cleaned(entry: PaletteEntry) -> PaletteEntry:
    """`entry` without control characters in its call, help and usage."""
    return PaletteEntry(*(_CONTROL.sub("", text) for text in (entry.call, entry.help, entry.usage)))


def slash_line(text: str) -> bool:
    """Whether `text` is one line starting with `/`, stripped as the commands broker strips a
    line: what the composer's list completes. A text holding a newline is never one, even a
    newline at its end (the one Ctrl-J inserts), so the check is on the text before stripping."""
    return "\n" not in text and text.strip().startswith("/")


def completions(entries: Sequence[PaletteEntry], text: str) -> tuple[PaletteEntry, ...]:
    """The entries `text` (the composer's) completes: none unless it is a one-line `/` line
    (`slash_line`); else those whose call starts with it, in the palette's order, then those
    that contain it after the `/` (`/ea` finds `/clear`), ignoring case. Leading space is
    ignored and trailing space is kept, so `/model ` matches `/model haiku` and not `/model`.
    Arguments need no rule: `/model h` matches the entry `/model haiku`."""
    if not slash_line(text):
        return ()
    wanted = text.lstrip().lower()
    prefixed = [e for e in entries if e.call.lower().startswith(wanted)]
    inside = wanted.removeprefix("/")
    contained = [e for e in entries if inside in e.call.lower()[1:] and e not in prefixed]
    return (*prefixed, *contained)


def enter_takes(text: str, highlighted: PaletteEntry | None, moved: bool) -> bool:
    """Whether Enter takes the `highlighted` entry rather than sending `text` as typed: only
    when the person moved the highlight, or typed no space yet and `text` is a strict prefix of
    the entry's call (`/he` runs `/help`). Typed text is never replaced by an entry the person
    did not pick: `/model` and `/model ` send as they are, `/model h` sends `/model h`."""
    if highlighted is None:
        return False
    if moved:
        return True
    typed = text.lstrip().lower()
    call = highlighted.call.lower()
    return " " not in typed and call.startswith(typed) and call != typed


def _choices(spec: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """A spec's `choices`, read now; none when it has none or they can't be read."""
    choices = spec.get("choices")
    if not callable(choices):
        return []
    try:
        return [c for c in choices() if isinstance(c, Mapping) and c.get("args")]
    except Exception:  # a command's own reader failing must not break the palette
        return []
