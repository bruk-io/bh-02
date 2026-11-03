"""Resolve a JSON path, as the fold's markers write them, against the parsed value.

The markers name what they hide as `$.items[2:499]`, `$.pods[312].status` or `$["odd key"]`; this
reads one back. Layer 1 uses it to check every marker against its source, and a reader can do the
same with jq (`.items[2:499]`).
"""

import json
import re
from typing import Any

from compressors.json_fold import child_path

_PATH_STEP = re.compile(
    r"\.(?P<key>[A-Za-z_][A-Za-z0-9_-]*)"
    r"|\[(?P<quoted>\"(?:[^\"\\]|\\.)*\")\]"
    r"|\[(?P<start>-?\d*):(?P<stop>-?\d*)\]"
    r"|\[(?P<index>-?\d+)\]"
)


class RecoveryError(ValueError):
    """A query that cannot be answered; the message says what to write instead."""


def resolve(value: Any, path: str) -> Any:
    """The value at a path such as `$.items[3].name`, `$.items[10:20]` or `$["odd key"]`.

    Raises:
        RecoveryError: the path is malformed or names something that is not there.
    """
    if not path.startswith("$"):
        raise RecoveryError(f'JSON paths start at "$", as in "$.items[3]"; got {path!r}')
    pos, cur, here = 1, value, "$"
    while pos < len(path):
        m = _PATH_STEP.match(path, pos)
        if m is None:
            raise RecoveryError(
                f'cannot read {path!r} from position {pos}: write steps as .key, [3], [10:20] or ["odd key"]'
            )
        pos = m.end()
        if m["key"] is not None or m["quoted"] is not None:
            key = m["key"] if m["key"] is not None else json.loads(m["quoted"])
            if not isinstance(cur, dict):
                raise RecoveryError(f"{here} is a {type(cur).__name__}, not an object; it has no key {key!r}")
            if key not in cur:
                keys = ", ".join(list(cur)[:30])
                raise RecoveryError(f"{here} has no key {key!r}; its keys are: {keys}")
            cur, here = cur[key], child_path(here, key)
        elif m["index"] is not None:
            i = int(m["index"])
            if not isinstance(cur, list):
                raise RecoveryError(f"{here} is a {type(cur).__name__}, not an array; it has no index {i}")
            if not -len(cur) <= i < len(cur):
                raise RecoveryError(f"{here} has {len(cur)} items; index {i} is out of range")
            cur, here = cur[i], child_path(here, i)
        else:
            if not isinstance(cur, list):
                raise RecoveryError(f"{here} is a {type(cur).__name__}, not an array; it cannot be sliced")
            start = int(m["start"]) if m["start"] else None
            stop = int(m["stop"]) if m["stop"] else None
            cur, here = cur[start:stop], f"{here}[{m['start']}:{m['stop']}]"
    return cur
