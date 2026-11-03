"""Claude Code transcripts -> one row per tool result, with the assistant's next step.

    ./lab extract ~/.claude/projects [more paths] -o corpus/results.jsonl

Reads every `*.jsonl` under the given paths (sub-agent transcripts included). A row holds the tool
call (name, arguments), the result as the model saw it (text blocks joined; images counted, not
kept) and the assistant message that came next, which is the ground truth for the replay stage.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NextStep:
    text: str
    tool_uses: list[dict[str, Any]] = field(default_factory=list)  # {"name", "input"}


@dataclass(frozen=True)
class ToolResultRow:
    source: str  # transcript file
    record_uuid: str  # the user record holding the result, for replay to find its place
    tool_use_id: str
    tool_name: str
    args: dict[str, Any]
    text: str
    images: int  # image blocks in the result, which compression would not touch
    is_error: bool
    sidechain: bool  # from a sub-agent
    next_step: NextStep | None


def _blocks(record: dict[str, Any]) -> list[dict[str, Any]]:
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _result_text(content: Any) -> tuple[str, int]:
    if isinstance(content, str):
        return content, 0
    if not isinstance(content, list):
        return "", 0
    texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    images = sum(1 for b in content if isinstance(b, dict) and b.get("type") == "image")
    return "\n".join(texts), images


def _next_step(records: list[dict[str, Any]], start: int) -> NextStep | None:
    """The first assistant message after `start`, joined across the records it was streamed in."""
    message_id = None
    texts: list[str] = []
    uses: list[dict[str, Any]] = []
    for record in records[start + 1 :]:
        if record.get("type") == "user" and any(b.get("type") == "tool_result" for b in _blocks(record)):
            if message_id is not None:
                break
            continue
        if record.get("type") != "assistant":
            continue
        mid = record.get("message", {}).get("id")
        if message_id is None:
            message_id = mid
        elif mid != message_id:
            break
        for b in _blocks(record):
            if b.get("type") == "text":
                texts.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                uses.append({"name": b.get("name"), "input": b.get("input")})
    if message_id is None:
        return None
    return NextStep("\n".join(texts), uses)


def rows_from_records(records: list[dict[str, Any]], source: str) -> list[ToolResultRow]:
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    rows: list[ToolResultRow] = []
    for i, record in enumerate(records):
        for b in _blocks(record):
            if record.get("type") == "assistant" and b.get("type") == "tool_use":
                calls[b.get("id", "")] = (b.get("name", "?"), b.get("input") or {})
            elif record.get("type") == "user" and b.get("type") == "tool_result":
                tid = b.get("tool_use_id", "")
                name, args = calls.get(tid, ("?", {}))
                text, images = _result_text(b.get("content"))
                rows.append(
                    ToolResultRow(
                        source=source,
                        record_uuid=record.get("uuid", ""),
                        tool_use_id=tid,
                        tool_name=name,
                        args=args,
                        text=text,
                        images=images,
                        is_error=bool(b.get("is_error")),
                        sidechain=bool(record.get("isSidechain")),
                        next_step=_next_step(records, i),
                    )
                )
    return rows


def _transcripts(paths: Iterable[Path]) -> Iterator[Path]:
    for p in paths:
        if p.is_dir():
            yield from sorted(p.rglob("*.jsonl"))
        elif p.suffix == ".jsonl":
            yield p


def _read_records(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                value = json.loads(line)
            except ValueError:
                continue  # a transcript cut mid-write; the rest of the file is still good
            if isinstance(value, dict):
                records.append(value)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("-o", "--out", type=Path, default=Path("corpus/results.jsonl"))
    ns = parser.parse_args(argv)
    count = files = 0
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    with ns.out.open("w", encoding="utf-8") as out:
        for path in _transcripts(ns.paths):
            files += 1
            for row in rows_from_records(_read_records(path), str(path)):
                out.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
                count += 1
    print(f"{count} tool results from {files} transcripts -> {ns.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
