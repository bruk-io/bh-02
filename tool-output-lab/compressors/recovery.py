"""Serve a slice of a raw tool result the model saw folded.

`recover` is pure: the caller looks the raw text up by call id and passes it in. Bad queries come
back as text that says what to write instead, because the reader is the model.
"""

import json
import re
from typing import Any

from compressors.common import estimate_tokens, split_lines
from compressors.html import html_to_text, looks_like_html
from compressors.json_fold import child_path, parse_json_or_jsonl

_MAX_GREP_HITS = 40
_PATH_STEP = re.compile(
    r"\.(?P<key>[A-Za-z_][A-Za-z0-9_-]*)"
    r"|\[(?P<quoted>\"(?:[^\"\\]|\\.)*\")\]"
    r"|\[(?P<start>-?\d*):(?P<stop>-?\d*)\]"
    r"|\[(?P<index>-?\d+)\]"
)


class RecoveryError(ValueError):
    """A query that cannot be answered; the message says what to write instead."""


def _resolve(value: Any, path: str) -> Any:
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


def _grep_json(value: Any, needle: str, path: str = "$") -> list[str]:
    """Paths of the innermost objects or scalars whose text contains the needle."""
    hits: list[str] = []

    def walk(v: Any, p: str) -> None:
        if len(hits) >= _MAX_GREP_HITS:
            return
        if isinstance(v, dict):
            leaves = [x for x in v.values() if not isinstance(x, dict | list)]
            if any(needle in json.dumps(x, ensure_ascii=False).lower() for x in leaves) or any(
                needle in k.lower() for k in v
            ):
                hits.append(f"{p}: {json.dumps(v, ensure_ascii=False)[:400]}")
            for k, x in v.items():
                if isinstance(x, dict | list):
                    walk(x, child_path(p, k))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, child_path(p, i))
        elif needle in json.dumps(v, ensure_ascii=False).lower():
            hits.append(f"{p}: {json.dumps(v, ensure_ascii=False)[:400]}")

    walk(value, path)
    return hits


def _range(spec: str, kind: str) -> tuple[int, int]:
    """Raises:
    RecoveryError: the range is not two integers separated by a dash.
    """
    m = re.fullmatch(r"\s*(\d+)\s*[-:]\s*(\d+)\s*", spec)
    if m is None:
        raise RecoveryError(
            f'write a range as "{kind}:<first>-<last>", for example "{kind}:120-180"; got {spec!r}'
        )
    return int(m[1]), int(m[2])


def _cap(text: str, max_tokens: int) -> str:
    if estimate_tokens(text) <= max_tokens:
        return text
    keep = max_tokens * 4
    return text[:keep] + f"\n[... {len(text) - keep} more chars; ask for a narrower range]"


def _answer(raw: str, query: str) -> str:
    """Raises:
    RecoveryError: the query does not fit this result.
    """
    parsed = parse_json_or_jsonl(raw)
    if parsed is not None:
        value = parsed[0]
        if query.startswith("grep:"):
            hits = _grep_json(value, query[5:].strip().lower())
            return "\n".join(hits) if hits else f"no match for {query[5:]!r}"
        return json.dumps(_resolve(value, query.strip()), ensure_ascii=False, indent=1)
    text = html_to_text(raw) if looks_like_html(raw) else raw
    if query.startswith("chars:"):
        start, end = _range(query[6:], "chars")
        return text[start:end]
    lines = split_lines(text)
    if query.startswith("lines:"):
        first, last = _range(query[6:], "lines")
        if first < 1 or first > len(lines):
            raise RecoveryError(f"there are {len(lines)} lines; ask for a range within 1-{len(lines)}")
        return "\n".join(f"{i}: {lines[i - 1]}" for i in range(first, min(last, len(lines)) + 1))
    if query.startswith("grep:"):
        needle = query[5:].strip().lower()
        hits = [f"{i}: {line}" for i, line in enumerate(lines, 1) if needle in line.lower()]
        more = f"\n[{len(hits) - _MAX_GREP_HITS} more matches]" if len(hits) > _MAX_GREP_HITS else ""
        return "\n".join(hits[:_MAX_GREP_HITS]) + more if hits else f"no match for {query[5:]!r}"
    raise RecoveryError(
        'this result is text: ask for "lines:<first>-<last>", "chars:<start>-<end>" or "grep:<text>"; '
        f"got {query!r}"
    )


def recover(raw: str, query: str, *, max_tokens: int = 4000) -> str:
    """The part of `raw` the query names, as the model should see it."""
    try:
        return _cap(_answer(raw, query), max_tokens)
    except RecoveryError as e:
        return f"recover: {e}"
