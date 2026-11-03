"""What a task's right answer is, and how an answer or a fold is scored against it.

Every truth is computed by a program from the payload. Each kind has two scorers. `score_answer`
judges a model's answer (layer 2): prompts ask it to end with one line `ANSWER: ...`, and that line
is what is scored, so prose that mentions excluded items or hedges is not misread. `score_fold`
judges whether the answer can be read off the fold alone (layer 1, an upper bound on what a model
can find without fetching more).
"""

import re
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


type Truth = Needle | Absent | Exact | Items | Number | Location


@dataclass(frozen=True)
class Score:
    correct: bool
    recall: float | None = None
    precision: float | None = None
    parsed: bool = True  # whether the answer had the ANSWER line the prompt asks for


# What each kind's ANSWER line holds. "As the question asks" leaves the question to say what is
# listed (codes, orders, versions): saying "name" here made Haiku list Andorra's parishes for their
# codes and answer "the logs have no names" for failed orders (FINDINGS 38).
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
        AssertionError: a kind of truth with no scorer (a new kind added without one).
    """
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
    """Whether the fold shows something as standing out: JSON's promotion marker; a list of siblings
    with something shown between two hidden runs (a tree stand-out); or a log with lines shown
    between two gaps (a window around a signal)."""
    if f'"{markers.PROMOTION_KEY}"' in fold:
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
            if any(s in fold for s in stated):
                return Score(True)
            seen = sum(mentions(fold, x) for x in items) / len(items) if items else 0.0
            return Score(bool(items) and seen == 1.0, seen)
        case Location(line=n, text=t):
            return Score(re.search(rf"(?m)^{n}\t.*{re.escape(t)}", fold) is not None)
        case _ as unreachable:
            raise AssertionError(f"no scorer for {unreachable!r}")
