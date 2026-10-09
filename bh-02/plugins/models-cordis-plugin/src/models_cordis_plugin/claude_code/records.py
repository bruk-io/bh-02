"""A Claude Code session written from `agent:loop`'s transcript: what a rebuild resumes.

Claude Code keeps a session as JSON lines under `<CLAUDE_CONFIG_DIR>/projects/<cwd slug>/<id>.jsonl`,
one record per message, each naming its parent (`parentUuid`), so a linear conversation is a
chain. `records_for` is the transcript as that chain (pure): a user line as string content, a
tool message as a user record holding one `tool_result`, an assistant message from its
`provider` blocks as received (thinking and its signature included; a tool name gets the
`mcp__bh__` prefix Claude Code gave it, so a session from before this provider replays too), or
from its text and calls when there is none. Every assistant record names the resolved model id:
with an alias (`sonnet`) in it, Claude Code resent the whole conversation uncached (measured).

The record format is Claude Code's own and undocumented (the CLI the SDK pins, README.md); the
e2e tests resume a rebuilt session and check the model recalls what it held.
"""

import json
import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

# The bundled CLI's version: a private SDK module, with no public route to it; the SDK pin
# (pyproject.toml) keeps it where it is.
from claude_agent_sdk._cli_version import __cli_version__

from models_cordis_plugin.claude_code.stream import SERVER

__all__ = ["project_dir", "records_for", "session_file", "write_session"]

type Json = Mapping[str, Any]

_SLUG_MAX: Final = 200  # Claude Code cuts a longer slug and appends a hash of the path


def _slug(cwd: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", cwd)


def project_dir(config_dir: Path, cwd: str) -> Path | None:
    """Where Claude Code keeps the sessions of `cwd`: its path with every character that is not
    a letter or digit turned into `-`. A path longer than 200 such characters gets a hash of
    Claude Code's own after it, which only an existing directory can tell: None when there is none."""
    slug = _slug(cwd)
    projects = config_dir / "projects"
    if len(slug) <= _SLUG_MAX:
        return projects / slug
    found = sorted(projects.glob(f"{slug[:_SLUG_MAX]}-*")) if projects.is_dir() else []
    return found[0] if found else None


def session_file(config_dir: Path, session: str) -> Path | None:
    """The file Claude Code keeps session `session` in, if there is one."""
    projects = config_dir / "projects"
    found = sorted(projects.glob(f"*/{session}.jsonl")) if projects.is_dir() else []
    return found[0] if found else None


def _prefixed(block: Json) -> dict[str, Any]:
    out = dict(block)
    if out.get("type") == "tool_use" and not str(out.get("name", "")).startswith("mcp__"):
        out["name"] = f"mcp__{SERVER}__{out.get('name')}"
    return out


def _assistant(message: Json) -> list[dict[str, Any]]:
    provider = message.get("provider")
    if isinstance(provider, Mapping) and isinstance(provider.get("content"), list):
        return [_prefixed(block) for block in provider["content"]]
    text = str(message.get("content") or "")
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}] if text.strip() else []
    return blocks + [
        {"type": "tool_use", "id": c["id"], "name": f"mcp__{SERVER}__{c['name']}", "input": dict(c["input"])}
        for c in message.get("tool_calls") or []
    ]


def records_for(
    messages: Sequence[Json], *, session: str, cwd: str, model: str, now: datetime, ids: Sequence[str]
) -> list[dict[str, Any]]:
    """The transcript's non-system `messages` as Claude Code session records. `ids` are the
    records' uuids, one per message (a message with nothing to say is left out, its id unused)."""
    out: list[dict[str, Any]] = []
    parent: str | None = None
    stamp = now.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    common: dict[str, Any] = {
        "isSidechain": False,
        "userType": "external",
        "entrypoint": "sdk-py",
        "cwd": cwd,
        "sessionId": session,
        "version": __cli_version__,
    }
    for message, rid in zip(messages, ids, strict=False):
        body: dict[str, Any]
        match message.get("role"):
            case "user":
                kind, body = "user", {"role": "user", "content": str(message.get("content") or "")}
            case "tool":
                result = {
                    "tool_use_id": message.get("call_id"),
                    "type": "tool_result",
                    "content": [{"type": "text", "text": str(message.get("content") or "")}],
                }
                kind, body = "user", {"role": "user", "content": [result]}
            case "assistant":
                blocks = _assistant(message)
                if not blocks:
                    continue
                calls = any(b.get("type") == "tool_use" for b in blocks)
                kind, body = (
                    "assistant",
                    {
                        "model": model,
                        "id": f"msg_bh02_{rid.replace('-', '')[:24]}",
                        "type": "message",
                        "role": "assistant",
                        "content": blocks,
                        "stop_reason": "tool_use" if calls else "end_turn",
                        "stop_sequence": None,
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    },
                )
            case _:
                continue
        out.append(
            {"parentUuid": parent, **common, "type": kind, "message": body, "uuid": rid, "timestamp": stamp}
        )
        parent = rid
    return out


def write_session(config_dir: Path, cwd: str, messages: Sequence[Json], model: str) -> str | None:
    """Write `messages` as a new Claude Code session for `cwd`; its id, or None when Claude
    Code's directory for `cwd` can't be named (a path too long, never seen by Claude Code). A
    new id every time: a Claude Code process that outlived an abort could still be appending to
    the old file."""
    where = project_dir(config_dir, cwd)
    if where is None:
        return None
    session = str(uuid.uuid4())
    ids = [str(uuid.uuid4()) for _ in messages]
    records = records_for(messages, session=session, cwd=cwd, model=model, now=datetime.now(UTC), ids=ids)
    where.mkdir(parents=True, exist_ok=True)
    (where / f"{session}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return session
