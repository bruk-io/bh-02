"""JSON: fold long arrays and wide objects, and keep in view the array items that differ.

A long array keeps its first and last items and, in place between fold markers, the few items that
stand out: a rare value in a field where one value dominates, a key only a few items have, an error
key that is set, a failing status, or a value that matches the query. The first marker in each
folded array summarises all items: their keys and, for fields with few values, the counts of each.
The array stays a JSON array, and every marker says which indices it hides and at which path.
"""

import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from compressors.common import ANOMALY_RE, split_identifiers

_ERROR_KEYS = frozenset({"error", "errors", "err", "exception", "traceback", "fault", "failure", "stderr"})
_STATUS_KEYS = frozenset({"status", "state", "phase", "health", "result", "outcome", "conclusion", "reason"})
_OK_KEYS = frozenset({"ok", "success", "succeeded", "healthy", "valid", "ready", "passed"})
_BAD_STATUS = re.compile(
    ANOMALY_RE.pattern + r"|suspend|reject|degrad|cancel|crashloop|evicted|backoff|oom", re.IGNORECASE
)
_WHOLE_STRING_KEYS = frozenset(
    {
        "id",
        "uuid",
        "url",
        "uri",
        "path",
        "cursor",
        "next_page_token",
        "sha",
        "hash",
        "ref",
        "error",
        "message",
    }
)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")


@dataclass(frozen=True)
class _Limits:
    max_items: int = 6  # arrays longer than this are folded
    head: int = 2
    tail: int = 1
    max_promoted: int = 3
    max_keys: int = 40  # objects wider than this are folded
    keep_keys: int = 15
    max_str: int = 300
    max_depth: int = 12


# Tried in order until the result fits the budget; the last one is used regardless.
_LEVELS = (
    _Limits(),
    _Limits(max_str=120, max_keys=25, keep_keys=10),
    _Limits(max_items=4, head=1, tail=1, max_promoted=2, max_str=80, max_keys=15, keep_keys=8),
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
    items = []
    for line in stripped.splitlines():
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except ValueError:
            return None
    return (items, "jsonl") if len(items) > 1 else None


def child_path(path: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    if _IDENTIFIER.match(key):
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key)}]"


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
        if (
            terms
            and isinstance(v, str | int)
            and not isinstance(v, bool)
            and set(split_identifiers(str(v))) & terms
        ):
            out.append((5, f"{k} matches the query"))
    return out


def _promote(arr: list[Any], terms: frozenset[str], limit: int, shown: set[int]) -> list[tuple[int, str]]:
    """Up to `limit` indices worth showing, strongest first, with why."""
    if all(isinstance(x, Mapping) for x in arr):
        flats = [_flatten(x) for x in arr]
        rare_values, rare_keys = _rarity(flats)
        scored = []
        for i, flat in enumerate(flats):
            if i in shown:
                continue
            reasons = _reasons(flat, rare_values, rare_keys, terms)
            if reasons:
                score = sum(w for w, _ in reasons)
                why = "; ".join(r for _, r in sorted(reasons, reverse=True)[:2])
                scored.append((-score, i, why))
        scored.sort()
        return [(i, why) for _, i, why in scored[:limit]]
    if all(isinstance(x, str) for x in arr):
        hits = []
        for i, s in enumerate(arr):
            if i in shown:
                continue
            if ANOMALY_RE.search(s):
                hits.append((i, "contains an error word"))
            elif terms and set(split_identifiers(s)) & terms:
                hits.append((i, "matches the query"))
        return hits[:limit]
    return []


def _summary(arr: list[Any]) -> dict[str, Any]:
    if all(isinstance(x, Mapping) for x in arr):
        keys: dict[str, str] = {}
        counts: dict[str, Counter[str]] = {}
        for item in arr:
            for k, v in item.items():
                keys.setdefault(k, "null" if v is None else type(v).__name__)
                if isinstance(v, bool | int | str) and not (isinstance(v, str) and len(v) > 40):
                    counts.setdefault(k, Counter())[json.dumps(v)] += 1
        value_counts = {
            k: dict(c.most_common())
            for k, c in counts.items()
            if 1 < len(c) <= 6 and sum(c.values()) == len(arr)
        }
        out: dict[str, Any] = {"keys": keys}
        if value_counts:
            out["value_counts"] = value_counts
        return out
    numbers = [x for x in arr if isinstance(x, int | float) and not isinstance(x, bool)]
    if len(numbers) == len(arr):
        return {"type": "number", "min": min(numbers), "max": max(numbers)}
    return {"types": sorted({type(x).__name__ for x in arr})}


def _fold_array(arr: list[Any], path: str, terms: frozenset[str], lim: _Limits, depth: int) -> list[Any]:
    n = len(arr)
    if n <= lim.max_items:
        return [_fold(v, child_path(path, i), terms, lim, depth + 1) for i, v in enumerate(arr)]
    shown = set(range(lim.head)) | set(range(max(0, n - lim.tail), n))
    why = dict(_promote(arr, terms, lim.max_promoted, shown))
    out: list[Any] = []
    summarised = False
    prev = -1
    for idx in [*sorted(shown | why.keys()), n]:
        if idx > prev + 1:
            marker: dict[str, Any] = {
                "_folded": f"{path}[{prev + 1}:{idx}] omitted ({idx - prev - 1} of {n} items)"
            }
            if not summarised:
                marker["_all_items"] = _summary(arr)
                summarised = True
            out.append(marker)
        if idx == n:
            break
        if idx in why:
            out.append({"_next_item_shown_because": f"{path}[{idx}]: {why[idx]}"})
        out.append(_fold(arr[idx], child_path(path, idx), terms, lim, depth + 1))
        prev = idx
    return out


def _fold_object(obj: Mapping[str, Any], path: str, terms: frozenset[str], lim: _Limits, depth: int) -> dict:
    keys = list(obj)
    if len(keys) <= lim.max_keys:
        kept = keys
    else:
        wanted = {
            k for k in keys[lim.keep_keys :] if k.lower() in _ERROR_KEYS or set(split_identifiers(k)) & terms
        }
        kept = [k for i, k in enumerate(keys) if i < lim.keep_keys or k in wanted]
    out: dict[str, Any] = {k: _fold(obj[k], child_path(path, k), terms, lim, depth + 1) for k in kept}
    if len(kept) < len(keys):
        omitted = [k for k in keys if k not in set(kept)]
        names = ", ".join(omitted[:40]) + (", ..." if len(omitted) > 40 else "")
        out["_folded_keys"] = f"{len(omitted)} keys of {path} omitted: {names}"
    return out


def _fold(value: Any, path: str, terms: frozenset[str], lim: _Limits, depth: int) -> Any:
    if depth > lim.max_depth and isinstance(value, Mapping | list):
        return {"_folded": f"{path} omitted (nested deeper than {lim.max_depth})"}
    if isinstance(value, Mapping):
        return _fold_object(value, path, terms, lim, depth)
    if isinstance(value, list):
        return _fold_array(value, path, terms, lim, depth)
    if isinstance(value, str) and len(value) > lim.max_str:
        leaf = path.rsplit(".", 1)[-1].lower()
        if leaf in _WHOLE_STRING_KEYS:
            return value
        return value[: lim.max_str] + f"...[+{len(value) - lim.max_str} chars]"
    return value


def fold_json(value: Any, terms: frozenset[str], budget_tokens: int) -> str:
    """The folded value as JSON text, at the loosest level that fits the budget."""
    text = ""
    for lim in _LEVELS:
        text = json.dumps(_fold(value, "$", terms, lim, 0), ensure_ascii=False)
        if len(text) / 4 <= budget_tokens:
            break
    return text
