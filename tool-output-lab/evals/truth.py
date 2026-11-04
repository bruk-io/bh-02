"""What a task's right answer is, and how an answer or a fold is scored against it.

Every truth is computed by a program from the payload. Each kind has two scorers. `score_answer`
judges a model's answer (layer 2): prompts ask it to end with one line `ANSWER: ...`, and that line
is what is scored, so prose that mentions excluded items or hedges is not misread. `score_fold`
judges whether the answer can be read off the fold alone (layer 1, an upper bound on what a model
can find without fetching more).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from compressors import markers


def mentions(text: str, token: str) -> bool:
    """The token as a whole word: `e123` is not in `e1234`, and version `8.1` is not in `8.1.7`
    (a sentence's full stop after a token still counts)."""
    return re.search(rf"(?<![\w.-]){re.escape(token)}(?![\w-]|\.\w)", text) is not None


@dataclass(frozen=True)
class Needle:
    token: str  # the one thing that answers "what stands out?"
    also: frozenset[str] = frozenset()  # other names of the same item: a log line's request beside its order

    def names(self) -> frozenset[str]:
        return self.also | {self.token}


@dataclass(frozen=True)
class Absent:
    candidates: frozenset[str]  # nothing stands out: naming any of these is an invented anomaly


@dataclass(frozen=True)
class Exact:
    value: str  # a looked-up value


@dataclass(frozen=True)
class Items:
    expected: frozenset[str]
    universe: frozenset[str]  # every name that could be listed: precision, and resolving a short name


@dataclass(frozen=True)
class Number:
    value: int
    items: frozenset[str] = frozenset()  # the things counted, as they show in the payload
    stated: tuple[str, ...] = ()  # texts that state the count itself (a summary entry, a marker)


@dataclass(frozen=True)
class Location:
    line: int  # 1-based
    text: str  # what is on that line, e.g. "def create_server"


@dataclass(frozen=True)
class Edited:
    """An edit to make in a copy of the file. `check(original, edited)` is None when the asked change
    is made and nothing else changed, or else what is wrong; it needs the edited file, so layer 2
    scores it with `score_edit`, not from the answer."""

    target: str  # the definition the edit starts from ("def create_server"): what a fold must show
    check: Callable[[str, str], str | None]


@dataclass(frozen=True)
class Fact:
    """One thing a claim states that a right answer must say: a number (`value`; an integer matched
    exactly, a decimal within 1%), a quoted title, or a name (matched as words, case and curly quotes
    aside)."""

    kind: str  # number | quote | name
    text: str
    value: float | None = None


@dataclass(frozen=True)
class Claims:
    """What a right answer claims (MCP-Atlas), each claim as its facts. A claim holds when the answer
    states all its numbers and quoted titles and at least two thirds of its names; the answer is
    right when every claim holds."""

    claims: tuple[tuple[Fact, ...], ...]
    in_payload: tuple[Fact, ...] = ()  # the facts the large tool output holds: what a fold must keep


type Truth = Needle | Absent | Exact | Items | Number | Location | Edited | Claims


_CURLY = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " "})
_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?!\w)")


def plain(text: str) -> str:
    """Text as facts are matched in it: lower case, straight quotes, one space between words."""
    return re.sub(r"\s+", " ", text.translate(_CURLY)).lower()


def numbers_in(text: str) -> list[float]:
    out = []
    for m in _NUMBER.finditer(text):
        try:
            out.append(float(m[0].replace(",", "")))
        except ValueError:
            continue
    return out


def fact_holds(fact: Fact, text: str, numbers: list[float] | None = None) -> bool:
    """Whether `text` (already `plain`) states the fact; `numbers` are the text's, when known."""
    if fact.value is not None:
        found = numbers_in(text) if numbers is None else numbers
        if "." not in fact.text:
            return fact.value in found
        return any(abs(n - fact.value) <= max(0.01, 0.01 * abs(fact.value)) for n in found)
    return mentions(text, plain(fact.text))


def claim_holds(facts: tuple[Fact, ...], text: str, numbers: list[float] | None = None) -> bool:
    names = [f for f in facts if f.kind == "name"]
    if not all(fact_holds(f, text, numbers) for f in facts if f.kind != "name"):
        return False
    return sum(fact_holds(f, text, numbers) for f in names) * 3 >= len(names) * 2


@dataclass(frozen=True)
class Score:
    correct: bool
    recall: float | None = None
    precision: float | None = None
    parsed: bool = True  # whether the answer had the ANSWER line the prompt asks for


# What each kind's ANSWER line holds. "As the question asks" leaves the question to say what is
# listed (codes, orders, versions): saying "name" here made Haiku list Andorra's parishes for their
# codes and answer "the logs have no names" for failed orders.
_ONE = "End your reply with one line: ANSWER: <the item, as the question asks for it>, or ANSWER: none"
ANSWER_INSTRUCTION = {
    "spot": _ONE,
    "absent": _ONE,
    "lookup": "End your reply with one line: ANSWER: <the value>",
    "enumerate": (
        "End your reply with one line: ANSWER: <every item, as the question asks for them, separated by "
        "commas>, or ANSWER: none"
    ),
    "count": "End your reply with one line: ANSWER: <the number>",
    "locate": "End your reply with one line: ANSWER: <the line number>",
    "edit": "End your reply with one line: ANSWER: done, or ANSWER: not done",
}
_ANSWER = re.compile(r"(?im)^\W{0,3}ANSWER:\s*(.*?)\s*$")
_NONE = {"none", "nothing", "no", "n/a", "-", ""}


def answer_line(answer: str) -> str | None:
    """The last `ANSWER:` line's content, or None when the answer has none."""
    found = _ANSWER.findall(answer)
    return found[-1].strip(" .`*") if found else None


def answer_items(line: str) -> list[str]:
    """The names an ANSWER line lists: split on commas, semicolons or `and`; quotes and markup
    stripped; an answer of none is no names."""
    if line.strip(" .`*").lower() in _NONE:
        return []
    parts = re.split(r"\s*(?:,|;|\band\b)\s*", line)
    return [p.strip(" .`*'\"()[]") for p in parts if p.strip(" .`*'\"()[]")]


def _named_by(listed: str, candidates: frozenset[str]) -> frozenset[str]:
    """The candidates a listed item names: those it is or holds as a whole word ("Card N7697
    (hidden)" names Card N7697), or else the one candidate that holds it as a whole word ("N7697"
    names Card N7697; "Card", which every card holds, names none)."""
    holds = frozenset(x for x in candidates if listed == x or mentions(listed, x))
    if holds:
        return holds
    held_by = [x for x in candidates if mentions(x, listed)]
    return frozenset(held_by) if len(held_by) == 1 else frozenset()


def _first_number(line: str) -> int | None:
    m = re.search(r"-?\d[\d,]*", line)
    return int(m[0].replace(",", "")) if m else None


def score_answer(truth: Truth, answer: str) -> Score:
    """A model's answer against the truth, read from its ANSWER line.

    Without one, the answer is scored leniently on its prose and marked `parsed=False`, so a run
    report can show how often the instruction was not followed.

    Raises:
        ValueError: the truth is an edit, which is scored from the edited file (`score_edit`).
        AssertionError: a kind of truth with no scorer (a new kind added without one).
    """
    if isinstance(truth, Edited):
        raise ValueError("an edit is scored from the edited file: use score_edit(truth, original, edited)")
    if isinstance(truth, Claims):  # a free answer, read whole: there is no ANSWER line to ask for
        text = plain(answer)
        found = numbers_in(text)
        held = [claim_holds(c, text, found) for c in truth.claims]
        return Score(all(held), sum(held) / len(held) if held else 1.0)
    line = answer_line(answer)
    if line is None:
        return _score_prose(truth, answer)
    match truth:
        case Needle() as needle:
            names = needle.names()
            return Score(
                any(n == t or mentions(n, t) for n in answer_items(line) for t in names) or line in names
            )
        case Exact(value=t):
            return Score(any(n == t or mentions(n, t) for n in answer_items(line)) or line == t)
        case Absent():
            return Score(answer_items(line) == [])
        case Items(expected=e, universe=u):
            listed = set(answer_items(line))
            named = {n: _named_by(n, e | u) for n in listed}
            hit = {x for x in e if any(x in xs for xs in named.values())}
            recall = len(hit) / len(e) if e else float(not listed)
            right = {n for n, xs in named.items() if xs & e}
            precision = len(right) / len(listed) if listed else float(not e)
            return Score(recall >= 0.9 and precision >= 0.9, recall, precision)
        case Number(value=v) | Location(line=v):
            return Score(_first_number(line) == v)
        case _ as unreachable:
            raise AssertionError(f"no scorer for {unreachable!r}")


def _score_prose(truth: Truth, answer: str) -> Score:
    match truth:
        case Needle() as needle:
            return Score(any(mentions(answer, t) for t in needle.names()), parsed=False)
        case Exact(value=t):
            return Score(mentions(answer, t), parsed=False)
        case Absent(candidates=c):
            return Score(not any(mentions(answer, x) for x in c), parsed=False)
        case Items(expected=e):
            recall = sum(mentions(answer, x) for x in e) / len(e) if e else 1.0
            return Score(recall >= 0.9, recall, None, parsed=False)
        case Number(value=v) | Location(line=v):
            return Score(mentions(answer, str(v)), parsed=False)
        case _ as unreachable:
            raise AssertionError(f"no scorer for {unreachable!r}")


def promotes(fold: str) -> bool:
    """Whether the fold shows something as standing out: an envelope's anomalies; a list of siblings
    with something shown between two hidden runs (a tree stand-out); or a log with lines shown
    between two gaps (a window around a signal)."""
    if markers.ENVELOPE_ANOMALIES.search(fold):
        return True
    runs_per_indent: dict[str, int] = {}
    for indent in markers.SIBLING_RUN.findall(fold):
        runs_per_indent[indent] = runs_per_indent.get(indent, 0) + 1
    if any(n >= 2 for n in runs_per_indent.values()):
        return True
    return len(markers.LOG_GAP.findall(fold)) >= 2


def score_fold(truth: Truth, fold: str) -> Score:
    """Whether the answer can be read off the fold text alone.

    A count is sufficient when the fold states it (a summary's entry, a marker's count) or shows
    every counted item; a number that merely appears (a line number, a date) is not enough. A
    location needs the line shown with its number; an absent anomaly needs nothing promoted.

    Raises:
        AssertionError: a kind of truth with no scorer (a new kind added without one).
    """
    match truth:
        case Needle() as needle:
            return Score(any(mentions(fold, t) for t in needle.names()))
        case Exact(value=t):
            return Score(mentions(fold, t))
        case Absent():
            return Score(not promotes(fold))
        case Items(expected=e):
            recall = sum(mentions(fold, x) for x in e) / len(e) if e else 1.0
            return Score(recall >= 0.9, recall)
        case Number(items=items, stated=stated):
            if any(re.search(re.escape(s) + r"(?!\d)", fold) for s in stated):  # a count of 2 is not 20
                return Score(True)
            seen = sum(mentions(fold, x) for x in items) / len(items) if items else 0.0
            return Score(bool(items) and seen == 1.0, seen)
        case Location(line=n, text=t):
            return Score(re.search(rf"(?m)^{n}\t.*{re.escape(t)}", fold) is not None)
        case Edited(target=t):  # where to start: the definition shown with its line number
            return Score(re.search(rf"(?m)^\d+\t.*{re.escape(t)}\b", fold) is not None)
        case Claims(in_payload=facts):  # the answer's facts the large output holds must survive the fold
            text = plain(fold)
            found = numbers_in(text)
            kept = [fact_holds(f, text, found) for f in facts]
            return Score(all(kept), sum(kept) / len(kept) if kept else 1.0)
        case _ as unreachable:
            raise AssertionError(f"no scorer for {unreachable!r}")


def score_edit(truth: Edited, original: str, edited: str) -> tuple[Score, str | None]:
    """An edit's score, and what is wrong with it when it is wrong."""
    problem = truth.check(original, edited)
    return Score(problem is None), problem
