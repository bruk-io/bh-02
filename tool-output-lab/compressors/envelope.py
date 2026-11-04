"""The envelope: what a large output becomes before the model sees it, in four parts.

    shape: .items: array[100] of object ...        what the data is, in exact numbers
    anomalies: 7 rows, all listed                  what breaks the shape, each with its address
      .items[11] web-7123f922cc: .ready false
    samples:                                       what items look like, verbatim
      .items[0]: {"name":"web-e16d5e5a2f",...}
    get more:                                      how to fetch the rest
      jq '.items[] | select(.ready != true) | .name' FILE

An envelope is composed from a recipe: a producer for each part. Producers run in dependency order,
each given the parts made before it (an anomaly means something only against a shape; a typical
sample avoids the anomalies; a command fetches what the others found), and they read one another
through what each part claims. So parts from different recipes mix: change one producer, keep the
rest, and the difference is that part's.

Each part offers its text at one or more levels, fullest first, each with the claims it makes.
`compose` starts every part at its tersest level, then, in the recipe's priority order, raises each
to the fullest level the budget still allows: the budget is a ceiling, never a target. The claims
are what layer 1 checks against the data (every count, listed anomaly, sample and command), and the
text a level shows says each of its claims.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from compressors.common import estimate_tokens

type Address = str  # in the data's own terms: a jq path for JSON (line-addressed claims take numbers)


class Role(StrEnum):
    SHAPE = "shape"
    ANOMALIES = "anomalies"
    SAMPLES = "samples"
    NAV = "nav"


ROLES = tuple(Role)  # the order parts are made and shown in
_TITLES = {Role.SHAPE: "shape", Role.ANOMALIES: "anomalies", Role.SAMPLES: "samples", Role.NAV: "get more"}


# --- claims: what a level asserts, for layer 1 to check against the data ------------------------------


@dataclass(frozen=True)
class Count:
    """The collection at `at` holds `n` rows."""

    at: Address
    n: int


@dataclass(frozen=True)
class Values:
    """Over the rows at `at`, `field` holds each of these values (as JSON) this many times, and no other."""

    at: Address
    field: str
    counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Breaks:
    """The row at `row` breaks the shape as `note` says (a value, a missing or extra key, a type)."""

    row: Address
    note: str


@dataclass(frozen=True)
class Lists:
    """Every row at `at` whose `field` holds a value other than `usual` (as JSON) is among `rows`."""

    at: Address
    field: str
    usual: str
    rows: tuple[Address, ...]


@dataclass(frozen=True)
class Verbatim:
    """The item at `at`, as compact text, is `text` (`whole`), or starts with it."""

    at: Address
    text: str
    whole: bool


@dataclass(frozen=True)
class Fetches:
    """`command`, run on the input, prints `pick` of every row at `at` whose `field` is not `usual`."""

    command: str
    at: Address
    field: str
    usual: str
    pick: str


@dataclass(frozen=True)
class Selects:
    """`command`, run on the input, prints `pick` of every row at `at` whose `field` is `value` (as
    JSON), and there are `n` of them."""

    command: str
    at: Address
    field: str
    value: str
    pick: str
    n: int


# Line-addressed claims, for every format read as lines (logs, trees, code, documents). Lines are
# numbered from 1 in the source: the text the commands read (the raw output, or a copy of it
# pretty-printed or converted to text). A template is a line with every token (letters, digits, `_`
# and `-`) that holds a digit or a part of six or more hex digits, and every quoted string when
# `quoted`, replaced by <*>; its slots are what those holes hold, in order.


@dataclass(frozen=True)
class Shows:
    """Source lines `first`, `first + 1`, ... read as `lines`: each whole, or cut short with the clip
    marker (`...[+N chars]`, N the characters cut)."""

    first: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Total:
    """The source has `lines` lines, and `templates` distinct templates among its non-blank ones."""

    lines: int
    templates: int
    quoted: bool = False


@dataclass(frozen=True)
class Alike:
    """`n` source lines among `first` to `last` have `template`, and hold `value` in slot `slot`
    (counted from 1) when `slot` is set."""

    template: str
    n: int
    first: int
    last: int
    quoted: bool = False
    slot: int = 0
    value: str = ""


@dataclass(frozen=True)
class Prints:
    """`command`, run on the source, prints exactly source lines `lines` (grep -n or sed -n)."""

    command: str
    lines: tuple[int, ...]


type Claim = Count | Values | Breaks | Lists | Verbatim | Fetches | Selects | Shows | Total | Alike | Prints


# --- parts ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Level:
    """A part at one level of detail: the rest of its title line, the lines under it, and its claims."""

    head: str
    body: tuple[str, ...]
    claims: tuple[Claim, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.head and not self.body


NOTHING = Level("", ())  # a level that shows nothing: the part is left out


@dataclass(frozen=True)
class Part:
    role: Role
    levels: tuple[Level, ...]  # fullest first, at least one

    def __post_init__(self) -> None:
        if not self.levels:
            raise ValueError(f"a {self.role} part needs at least one level (NOTHING, to show none)")


def nothing(role: Role) -> Part:
    """A part that shows nothing (a recipe with no samples, say)."""
    return Part(role, (NOTHING,))


# --- producers: one protocol per part, each given the parts made before it ----------------------------


class Shaper[D](Protocol):
    def __call__(self, data: D, /) -> Part: ...


class Spotter[D](Protocol):
    def __call__(self, data: D, shape: Part, /) -> Part: ...


class Sampler[D](Protocol):
    def __call__(self, data: D, shape: Part, anomalies: Part, /) -> Part: ...


class Navigator[D](Protocol):
    def __call__(self, data: D, shape: Part, anomalies: Part, samples: Part, /) -> Part: ...


_PRIORITY = (Role.SHAPE, Role.ANOMALIES, Role.NAV, Role.SAMPLES)


@dataclass(frozen=True)
class Recipe[D]:
    """One envelope design: a producer for each part, and the order the parts claim the budget in."""

    shape: Shaper[D]
    anomalies: Spotter[D]
    samples: Sampler[D]
    nav: Navigator[D]
    priority: tuple[Role, ...] = _PRIORITY


def priority(text: str) -> tuple[Role, ...]:
    """A priority from its config form, "shape,anomalies,nav,samples".

    Raises:
        ValueError: it does not name each part exactly once.
    """
    names = tuple(x.strip() for x in text.split(","))
    if sorted(names) != sorted(ROLES):
        raise ValueError(f"a priority names each part once, as {','.join(_PRIORITY)}; not {text!r}")
    return tuple(Role(n) for n in names)


class Chosen(Protocol):
    """What names a recipe: a format's envelope knobs, a producer's name for each part ("" leaves
    the part to the view's recipe) and the priority."""

    @property
    def shape(self) -> str: ...
    @property
    def anomalies(self) -> str: ...
    @property
    def samples(self) -> str: ...
    @property
    def nav(self) -> str: ...
    @property
    def priority(self) -> str: ...


@dataclass(frozen=True)
class Producers[D]:
    """A format's producers for each part, by name."""

    shape: Mapping[str, Shaper[D]]
    anomalies: Mapping[str, Spotter[D]]
    samples: Mapping[str, Sampler[D]]
    nav: Mapping[str, Navigator[D]]


_PARTS = ("shape", "anomalies", "samples", "nav")


def recipe_of[D](
    section: str, producers: Producers[D], presets: Mapping[str, Chosen], chosen: Chosen, view: str
) -> Recipe[D]:
    """The view's recipe (a preset), with each part `chosen` names in place of the view's.

    Raises:
        ValueError: the view names no preset, a part names no producer, or the priority does not name
            each part once.
    """
    if view not in presets:
        raise ValueError(f"{section}: no view {view!r}; the views are {', '.join(presets)}")
    names = {p: getattr(chosen, p) or getattr(presets[view], p) for p in _PARTS}
    for p in _PARTS:
        table = getattr(producers, p)
        if names[p] not in table:
            raise ValueError(f"{section}.{p} is one of {', '.join(table)}; not {names[p]!r}")
    return Recipe(
        producers.shape[names["shape"]],
        producers.anomalies[names["anomalies"]],
        producers.samples[names["samples"]],
        producers.nav[names["nav"]],
        priority(chosen.priority),
    )


# --- the envelope -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Envelope:
    parts: tuple[Part, ...]  # one per role, in ROLES order
    chosen: tuple[int, ...]  # the level each part shows

    def level(self, role: Role) -> Level:
        k = ROLES.index(role)
        return self.parts[k].levels[self.chosen[k]]

    def claims(self) -> tuple[Claim, ...]:
        return tuple(c for role in ROLES for c in self.level(role).claims)

    def text(self) -> str:
        return render(self.parts, self.chosen)


def render(parts: tuple[Part, ...], chosen: tuple[int, ...]) -> str:
    """The parts at the chosen levels: each a title line (with its head), then its lines indented."""
    out: list[str] = []
    for part, i in zip(parts, chosen, strict=True):
        level = part.levels[i]
        if level.empty:
            continue
        out.append(f"{_TITLES[part.role]}:" + (f" {level.head}" if level.head else ""))
        out += [f"  {line}" for line in level.body]
    return "\n".join(out)


def build[D](recipe: Recipe[D], data: D) -> tuple[Part, ...]:
    """Every part, in dependency order.

    Raises:
        ValueError: a producer made a part for another role.
    """
    shape = recipe.shape(data)
    anomalies = recipe.anomalies(data, shape)
    samples = recipe.samples(data, shape, anomalies)
    nav = recipe.nav(data, shape, anomalies, samples)
    parts = (shape, anomalies, samples, nav)
    for role, part in zip(ROLES, parts, strict=True):
        if part.role is not role:
            raise ValueError(
                f"the {role} producer made a {part.role} part: a producer makes its own role's part"
            )
    return parts


def fit(parts: tuple[Part, ...], budget_tokens: int, order: tuple[Role, ...] = _PRIORITY) -> Envelope:
    """Every part at its tersest level, then each in `order` raised to the fullest level that keeps
    the whole within the budget. When even the tersest levels do not fit, they are what is shown."""
    chosen = [len(p.levels) - 1 for p in parts]
    for role in order:
        k = ROLES.index(role)
        for i in range(len(parts[k].levels)):
            trial = (*chosen[:k], i, *chosen[k + 1 :])
            if estimate_tokens(render(parts, trial)) <= budget_tokens:
                chosen[k] = i
                break
    return Envelope(parts, tuple(chosen))


def compose[D](recipe: Recipe[D], data: D, budget_tokens: int) -> Envelope:
    """The envelope a recipe makes of the data, within the budget."""
    return fit(build(recipe, data), budget_tokens, recipe.priority)
