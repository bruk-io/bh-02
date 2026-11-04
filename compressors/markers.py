"""The markers an envelope writes, and the one way to read each back.

A line cut short says how much was cut (`clipped`); a JSON Lines envelope opens with a note on its
records (`jsonl_note`); an envelope's anomalies part says how many it names. Everything that reads
them (layer 1's checks, the scorers) uses the patterns here, so the two cannot drift.
"""

import re


def clipped(text: str, max_chars: int) -> str:
    """A long line, cut, saying how much was cut."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"...[+{len(text) - max_chars} chars]"


CLIPPED = re.compile(r"\.\.\.\[\+(?P<chars>\d+) chars\]$")


# --- JSON -----------------------------------------------------------------------------------------


def jsonl_note(records: int, by_line: bool) -> str:
    """The line above a JSON Lines envelope: the records are read as one array, and how to read item i."""
    where = "index i is line i+1" if by_line else "blank lines are skipped, so index i is not line i+1"
    return f"JSONL shown as one array of {records} records; {where}; jq -s '.[i]' reads item i."


JSONL_NOTE = re.compile(r"\AJSONL shown as one array of (?P<records>\d+) records; (?P<where>[^;]+);[^\n]*\n")
ENVELOPE_ANOMALIES = re.compile(r"(?m)^anomalies: [1-9]")  # an envelope's anomalies part names some
