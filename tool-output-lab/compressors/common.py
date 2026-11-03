"""Shared pieces: the token estimate, call ids, query terms and the anomaly signal."""

import hashlib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def estimate_tokens(text: str) -> int:
    """About four characters per token: fine for comparing branches, not for billing."""
    return math.ceil(len(text) / 4)


def call_id_for(raw: str) -> str:
    return "call_" + hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:12]


@dataclass(frozen=True)
class Compressed:
    """What the model sees in place of a tool result, and how it got there."""

    text: str
    branch: str  # passthrough | json | lines | html | text
    call_id: str | None  # None when nothing was folded, so nothing needs recovering
    raw_tokens: int
    out_tokens: int


ANOMALY_RE = re.compile(
    r"\b(?:error|errors|err|fail|failed|failure|fatal|exception|traceback|panic|abort|aborted|crash"
    r"|crashed|timeout|timed out|denied|refused|invalid|unhealthy|segfault|oomkilled|killed)\b"
    r"|\w+(?:error|exception)\b",  # ValueError, NullPointerException
    re.IGNORECASE,
)

_STOPWORDS = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "were",
        "have",
        "has",
        "had",
        "what",
        "when",
        "where",
        "which",
        "who",
        "how",
        "why",
        "can",
        "could",
        "should",
        "would",
        "will",
        "into",
        "about",
        "there",
        "their",
        "true",
        "false",
        "null",
        "none",
        "home",
        "user",
        "users",
    ]
)


def split_identifiers(text: str) -> list[str]:
    """camelCase, snake_case and paths into lowercase words of three or more characters."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    words = re.findall(r"[a-z0-9]{3,}", spaced.lower())
    return [w for w in words if w not in _STOPWORDS]


def query_terms(args: Mapping[str, Any]) -> frozenset[str]:
    """Words from the tool call's own arguments: the only query signal the design uses."""
    terms: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, str):
            terms.update(split_identifiers(value))
        elif isinstance(value, Mapping):
            for v in value.values():
                walk(v)
        elif isinstance(value, list | tuple):
            for v in value:
                walk(v)

    walk(args)
    return frozenset(t for t in terms if len(t) >= 4)
