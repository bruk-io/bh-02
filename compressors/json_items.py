"""JSON input: parsing a payload (JSON, or JSON Lines as one array), and the rules for which items
of an array stand out (the envelope's `standouts` anomalies): a rare value in a field where one
value dominates, a key only a few items have, an error key that is set, a failing status, a false
"ok"-like flag, or a value that matches the query.
"""

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from compressors.common import ANOMALY_RE, discriminating, matches, split_lines

_ERROR_KEYS = frozenset({"error", "errors", "err", "exception", "traceback", "fault", "failure", "stderr"})
_STATUS_KEYS = frozenset({"status", "state", "phase", "health", "result", "outcome", "conclusion", "reason"})
_OK_KEYS = frozenset({"ok", "success", "succeeded", "healthy", "valid", "ready", "passed"})
_BAD_STATUS = re.compile(
    ANOMALY_RE.pattern + r"|suspend|reject|degrad|cancel|crashloop|evicted|backoff|oom", re.IGNORECASE
)


def parse_json_or_jsonl(raw: str) -> tuple[Any, str] | None:
    """The parsed value and "json" or "jsonl", or None when the text is neither."""
    stripped = raw.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped), "json"
    except ValueError:
        pass
    except RecursionError:  # nested deeper than the parser's stack allows: not foldable as JSON
        return None
    items = []
    for line in split_lines(stripped):  # newline only: a record may hold a raw U+2028 or form feed
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except ValueError, RecursionError:
            return None
    return (items, "jsonl") if len(items) > 1 else None


def _flatten(item: Mapping[str, Any], prefix: str = "", depth: int = 0) -> dict[str, Any]:
    """Scalar leaves of an object, two levels down, keyed by dotted path."""
    out: dict[str, Any] = {}
    for k, v in item.items():
        key = f"{prefix}{k}"
        if isinstance(v, Mapping) and depth < 2:
            out.update(_flatten(v, f"{key}.", depth + 1))
        elif isinstance(v, bool | int | float | str) or v is None:
            out[key] = v
    return out


def _hashable(v: Any) -> tuple[str, Any]:
    return (type(v).__name__, v)  # keeps True and 1 apart


def _rarity(flat_items: list[dict[str, Any]]) -> tuple[dict[str, frozenset[tuple[str, Any]]], frozenset[str]]:
    """Rare values of dominated low-cardinality fields, and keys that only a few items have."""
    n = len(flat_items)
    rare_cut = max(1, int(0.05 * n))
    values: dict[str, Counter[tuple[str, Any]]] = {}
    presence: Counter[str] = Counter()
    for item in flat_items:
        for k, v in item.items():
            presence[k] += 1
            if isinstance(v, str) and len(v) > 64:
                continue
            values.setdefault(k, Counter())[_hashable(v)] += 1
    rare_values: dict[str, frozenset[tuple[str, Any]]] = {}
    for k, counts in values.items():
        if not 2 <= len(counts) <= 10:
            continue
        if counts.most_common(1)[0][1] / n < 0.85:
            continue
        rare = frozenset(v for v, c in counts.items() if c <= rare_cut)
        if rare:
            rare_values[k] = rare
    rare_keys = frozenset(k for k, c in presence.items() if c <= rare_cut) if n >= 10 else frozenset()
    if len(rare_keys) > len(presence) / 2:  # items with keys of their own (a host per item): rare is normal
        rare_keys = frozenset()
    return rare_values, rare_keys


def _empty(v: Any) -> bool:
    return v is None or v is False or v == 0 or v == "" or v == [] or v == {}


def _reasons(
    flat: dict[str, Any],
    rare_values: dict[str, frozenset[tuple[str, Any]]],
    rare_keys: frozenset[str],
    terms: frozenset[str],
) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for k, v in flat.items():
        leaf = k.rsplit(".", 1)[-1].lower()
        if k in rare_values and _hashable(v) in rare_values[k]:
            out.append((4, f"{k}={v!r} is rare in this array"))
        if k in rare_keys:
            out.append((3, f"few items have {k!r}"))
        if leaf in _ERROR_KEYS and not _empty(v):
            out.append((3, f"{k} is set"))
        if leaf in _STATUS_KEYS and isinstance(v, str) and _BAD_STATUS.search(v):
            out.append((3, f"{k}={v!r}"))
        if leaf in _OK_KEYS and v is False:
            out.append((3, f"{k} is false"))
        if terms and isinstance(v, str | int) and not isinstance(v, bool):
            hits = sum(matches(str(v), t) for t in terms)
            if hits:
                out.append((5 * hits, f"{k} matches the query"))
    return out


def _text(values: Iterable[Any]) -> str:
    return " ".join(str(v) for v in values if isinstance(v, str | int) and not isinstance(v, bool))


def promote(arr: list[Any], terms: frozenset[str], limit: int, shown: set[int]) -> list[tuple[int, str]]:
    """Up to `limit` indices worth showing, strongest first, with why."""
    if all(isinstance(x, Mapping) for x in arr):
        flats = [_flatten(x) for x in arr]
        rare_values, rare_keys = _rarity(flats)
        terms = discriminating(terms, [_text(f.values()) for f in flats])
        scored = []
        for i, flat in enumerate(flats):
            if i in shown:
                continue
            reasons = _reasons(flat, rare_values, rare_keys, terms)
            if reasons:
                score = sum(w for w, _ in reasons)
                by_field: dict[str, str] = {}
                for _, r in sorted(reasons, key=lambda wr: -wr[0]):  # strongest reason per field
                    by_field.setdefault(r.split("=")[0].split(" ")[0], r)
                why = "; ".join(list(by_field.values())[:2])
                scored.append((-score, i, why))
        scored.sort()
        return [(i, why) for _, i, why in scored[:limit]]
    if all(isinstance(x, str) for x in arr):
        terms = discriminating(terms, arr)
        hits = []
        for i, s in enumerate(arr):
            if i in shown:
                continue
            if ANOMALY_RE.search(s):
                hits.append((i, "contains an error word"))
            elif any(matches(s, t) for t in terms):
                hits.append((i, "matches the query"))
        return hits[:limit]
    return []
