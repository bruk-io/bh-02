"""What a task's right answer is, and how an answer or a fold is scored against it.

Every truth is computed by a program from the payload. Each kind has two scorers: `score_answer`
judges a model's answer (layer 2), `score_fold` judges whether the answer can be read off the fold
alone (layer 1, an upper bound on what a model can find without fetching more).
"""

import re
from dataclasses import dataclass


def mentions(text: str, token: str) -> bool:
    """The token as a whole word: `e123` is not in `e1234`, and version `8.1` is not in `8.1.7`
    (a sentence's full stop after a token still counts)."""
    return re.search(rf"(?<![\w.-]){re.escape(token)}(?![\w-]|\.\w)", text) is not None


@dataclass(frozen=True)
class Needle:
    token: str  # the one thing that answers "what stands out?"


@dataclass(frozen=True)
class Absent:
    candidates: frozenset[str]  # nothing stands out: naming any of these is an invented anomaly


@dataclass(frozen=True)
class Exact:
    value: str  # a looked-up value


@dataclass(frozen=True)
class Items:
    expected: frozenset[str]
    universe: frozenset[str]  # every name that could be listed; naming one outside `expected` is wrong


@dataclass(frozen=True)
class Number:
    value: int
    items: frozenset[str] = frozenset()  # the things counted, when known: seeing them all is enough to count


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


_PROMOTION = '"_next_item_shown_because"'


def _named(text: str, names: frozenset[str]) -> frozenset[str]:
    return frozenset(n for n in names if mentions(text, n))


def score_answer(truth: Truth, answer: str) -> Score:
    """A model's answer against the truth. Items need 90% recall and 90% precision."""
    match truth:
        case Needle(token=t) | Exact(value=t):
            return Score(mentions(answer, t))
        case Absent(candidates=c):
            return Score(not _named(answer, c))
        case Items(expected=e, universe=u):
            recall = len(_named(answer, e)) / len(e)
            named = _named(answer, u | e)
            precision = len(named & e) / len(named) if named else 1.0
            return Score(recall >= 0.9 and precision >= 0.9, recall, precision)
        case Number(value=v):
            return Score(mentions(answer, str(v)))
        case Location(line=n):
            return Score(mentions(answer, str(n)))
        case _ as unreachable:
            raise AssertionError(f"no scorer for {unreachable!r}")


def score_fold(truth: Truth, fold: str) -> Score:
    """Whether the answer can be read off the fold text alone.

    A count is sufficient if the number is shown (a summary's value counts, a marker's count) or
    every counted item is (so it can be counted, though the fold does not say nothing else is
    hidden); a location only if the line is shown with its number; an absent anomaly only
    if the fold promotes nothing as standing out.
    """
    match truth:
        case Needle(token=t) | Exact(value=t):
            return Score(mentions(fold, t))
        case Absent():
            return Score(_PROMOTION not in fold)
        case Items(expected=e):
            recall = len(_named(fold, e)) / len(e)
            return Score(recall >= 0.9, recall)
        case Number(value=v, items=items):
            if mentions(fold, str(v)):
                return Score(True)
            seen = len(_named(fold, items)) / len(items) if items else 0.0
            return Score(bool(items) and seen == 1.0, seen)
        case Location(line=n, text=t):
            return Score(re.search(rf"(?m)^{n}\t.*{re.escape(t)}", fold) is not None)
        case _ as unreachable:
            raise AssertionError(f"no scorer for {unreachable!r}")
