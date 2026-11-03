"""Every marker a fold writes, and the one way to read each back.

A marker says what a fold left out and where it is, so a reader can fetch exactly that. The folds
write markers only through the functions here, and everything that reads them (the hook's banner,
layer 1's coverage check, the promotion detector) uses the patterns here, so the two cannot drift.
Line numbers are 1-based and inclusive; character offsets are 0-based, end exclusive.
"""

import re

# --- line ranges (trees, logs, page text) ---------------------------------------------------------


def lines_folded(first: int, last: int, what: str) -> str:
    """A tree's hidden lines: a node's body ("12 lines") or a run of siblings ("40 siblings")."""
    return f"[... lines {first}-{last} folded ({what})]"


def siblings(count: int, more_standouts: int = 0) -> str:
    """What a hidden run of siblings holds, for `lines_folded`."""
    return f"{count} siblings" + (f"; {more_standouts} of them stand out too" if more_standouts else "")


def lines_omitted(first: int, last: int) -> str:
    """A log's hidden lines."""
    return f"[... lines {first}-{last} omitted ({last - first + 1} lines)]"


def repeated(count: int, first: int, last: int) -> str:
    """Lines of the same shape as the line before, numbers aside."""
    return f"[... same line pattern repeated {count} more times, lines {first}-{last}]"


def signals_hidden(count: int) -> str:
    return f"[{count} more lines matching error words or the query were omitted; use grep]"


def chars_omitted(start: int, end: int) -> str:
    return f"[... chars {start}-{end} omitted]"


# A marker standing alone on its line (after an optional number column and indentation).
LINE_RANGE = re.compile(
    r"^\[\.\.\. (?:same line pattern repeated \d+ more times, )?lines (?P<first>\d+)-(?P<last>\d+)"
    r"(?:\]| folded \(| omitted \()"
)
# A marker carried at the end of the line it belongs to (a one-line header).
INLINE = re.compile(r"  \[\.\.\. lines (?P<first>\d+)-(?P<last>\d+) folded \([^)]*\)\]$")
# Any line range a marker names, wherever it is: for a reader's example command.
ANY_RANGE = re.compile(r"\[\.\.\. (?:same line pattern repeated \d+ more times, )?lines (\d+)-(\d+)")
SIBLING_RUN = re.compile(r"(?m)^\t?(?P<indent>\s*)\[\.\.\. lines \d+-\d+ folded \(\d+ siblings[^)]*\)\]")
LOG_GAP = re.compile(r"(?m)^\[\.\.\. lines \d+-\d+ omitted")
NOTE = re.compile(r"^\[\d+ more lines matching")
CLIPPED = re.compile(r"\.\.\.\[\+(?P<chars>\d+) chars\]$")


def clipped(text: str, max_chars: int) -> str:
    """A long line, cut, saying how much was cut."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"...[+{len(text) - max_chars} chars]"


# --- JSON -----------------------------------------------------------------------------------------


def json_slice(path: str, start: int, stop: int, total: int) -> str:
    """The value of a `_folded` entry standing for array items path[start:stop]."""
    return f"{path}[{start}:{stop}] omitted ({stop - start} of {total} items)"


def json_keys(omitted: list[str], total: int, path: str, names_shown: int = 40) -> str:
    """The value of `_folded_keys`: how many of an object's keys are left out, and their names."""
    names = ", ".join(omitted[:names_shown]) + (", ..." if len(omitted) > names_shown else "")
    return f"{len(omitted)} of {total} keys of {path} omitted: {names}"


def json_deep(path: str, depth: int) -> str:
    return f"{path} omitted (nested deeper than {depth})"


def jsonl_note(records: int, by_line: bool) -> str:
    """The line above a JSON Lines fold: the records are shown as one array, and how to read item i."""
    where = "index i is line i+1" if by_line else "blank lines are skipped, so index i is not line i+1"
    return f"JSONL shown as one array of {records} records; {where}; jq -s '.[i]' reads item i."


JSON_SLICE = re.compile(
    r"^(?P<path>\$\S*)\[(?P<start>\d+):(?P<stop>\d+)\] omitted \((?P<count>\d+) of (?P<total>\d+) items\)$"
)
JSON_SLICE_IN_TEXT = re.compile(r'"_folded": "(?P<path>\$[^"\s]*)\[(?P<start>\d+):(?P<stop>\d+)\] omitted')
JSON_KEYS = re.compile(r"^(?P<omitted>\d+) of (?P<total>\d+) keys of (?P<path>\$\S*) omitted")
PROMOTION_KEY = "_next_item_shown_because"
JSONL_NOTE = re.compile(r"\AJSONL shown as one array of (?P<records>\d+) records; (?P<where>[^;]+);[^\n]*\n")
