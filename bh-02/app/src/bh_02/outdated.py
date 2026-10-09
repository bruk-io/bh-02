"""What an earlier bh-02's layer files named that this one does not, and the same layer in
today's names.

bh-02 renamed some of its own rows and dropped others; cordis's own words (plugin, row,
layer, `[[plugin]]`) are unchanged. `translated` turns a layer written for an earlier bh-02
into one for this one and says, one line per row, what it changed and why. A session's own
layer is translated silently on a resume (`sessions.update`); a `--patch` file is the
person's, so the command line refuses it with those lines and `bh-02 update-layer FILE`
rewrites it. Everything here is pure.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from cordis import Row

__all__ = ["clashes", "translated"]

# Rows (and the keys they bind) that were renamed: the kernel row is the python tool's, the jail
# row the runner, which starts the python tool's process and the extensions' worker, and the jail
# field's row, `jail_status`, the runner's grades (`grades`).
_RENAMED = {
    "llm": "loop",
    "mode": "chat",
    "completion": "model",
    "kernel": "python",
    "jail": "runner",
    "jail_status": "grades",
}
# A row a config names for its model (`model_row`, an old `model_status`'s `row`): before the
# completion row, the model was the `llm` row's; then the completion row's; it is the model
# row's now, not the loop's.
_MODEL_ROWS = {"llm": "model", "completion": "model"}
# The model row: named models over their providers. Claude Code's row and Ollama's are
# providers of it now, and a model is chosen by name (`default`), not by the provider's id.
_MODEL = "model"
_MODELS_USE = "models:model"
_CLAUDE_CODE_USE = "claude-code:completion"
_OLLAMA_USE = "ollama:completion"
_BUILT_IN = frozenset({"sonnet", "opus", "haiku"})  # models:model's own names for Claude's
_KEPT = ("state", "env_file", "cwd")  # what the claude-code row took that the model row still does
# Ollama's defaults, as its row had them.
_OLLAMA_HOST, _OLLAMA_MODEL = "http://localhost:11434", "llama3.2"
# bh-02's fake models that bound `completion`, now bound under `model`; and the project context's
# rows, now the system prompt's (agent's) and memory's.
_RENAMED_USES = {
    "bh_02.testing:echo_completion": "bh_02.testing:echo_model",
    "bh_02.testing:slow_completion": "bh_02.testing:slow_model",
    "bh_02.testing:cells_completion": "bh_02.testing:repl_model",
    "context:project": "agent:system",
    "context:on_touch": "memory:on_touch",
    "kernel:kernel": "python:tool",
    "kernel:unjailed": "runner:unconfined",
    "kernel:approval": "runner:approval",
    "kernel:release": "runner:release",
    "brig:jail": "runner:confined",
    "memory:memory": "memory:files",
    "tui:jail_status": "tui:grades",
}
# The broker of what an input's result is told was `memory` (`agent:memory`); it is `notes` now,
# and `memory` is Claude Code's memory, the memory plugin's row.
_OLD_NOTES_USE, _NOTES, _NOTES_USE = "agent:memory", "notes", "agent:notes"
# The project context's row (`system`) read the context files; the system prompt takes only its
# `root`, and memory (CLAUDE.md, where Claude Code reads it) takes its `root` and `home`. Context
# files are gone: memory reads Claude Code's files, from Claude Code's places.
_SYSTEM, _MEMORY_ROW = "system", "memory"
_OLD_SYSTEM_USES = (None, "context:project")
_TO_MEMORY = ("root", "home")
_CONTEXT_GONE = (
    "context files are gone: memory reads CLAUDE.md, AGENTS.md and .claude/rules/ as Claude Code does"
)
# The status row, which the session's and the model's status-bar rows became (the session's id:
# from `sessions`); the jail field is the `grades` row's.
_STATUS = "status"
_STATUS_USE = "tui:status"
_MERGED_USES = frozenset({"tui:model"})
_MERGED_IDS = frozenset({"model_status"})
# How an old `model_status` config reads as the status row's. Its `default` (later the status
# row's `default_model`, the model named when the row named none) is gone: the `models` row says
# which model and provider the model row names, whatever it names.
_STATUS_KEYS = {"row": "model_row"}
_STATUS_GONE = frozenset({"default", "default_model"})
# Rows an earlier bh-02 had and this one does not, by id or by the plugin they named, and why.
# The tool rows of before CodeAct: `tools` was one of them, by the `tools:` plugin; a `tools` row
# naming no plugin is a change to today's broker (`agent:tools`), so only that plugin drops it.
_ONE_TOOL = (
    "the model's tools are registered with `tools` (agent:tools) by the rows that offer them, the "
    "python row's among them, and unjailed each call is put to the person in the modal"
)
_REMOVED_IDS = {
    "fs": _ONE_TOOL,
    "approve": _ONE_TOOL,
    "actions": _ONE_TOOL,
    "guard": _ONE_TOOL,
    "session": "the status row shows the session's id itself",
}
_REMOVED_USES = ("tools:", "fs:", "codeact:", "tui:approver", "bh_02.bootstrap:layer_guard")
# The sidebar: the shipped `sidebar` row, filled by `tui:sessions`, which listed this
# directory's sessions. A `sidebar` row that names a plugin of the person's own still runs, so
# only a change to the shipped row (no `use`) or a row using `tui:sessions` is dropped.
_NO_SIDEBAR = "bh-02 has no sidebar now (`bh-02 sessions` lists this directory's sessions)"
_SIDEBAR, _SIDEBAR_USE = "sidebar", "tui:sessions"
# The shell hints: the shipped `shell-hints` row, filled by `kernel:shell_hints`, which told an
# input that ran `cat` or `sed` through a shell how Python does it. As with the sidebar, a row of
# that id naming a plugin of the person's own still runs.
_NO_SHELL_HINTS = "bh-02 no longer tells the model how Python does what an input ran through a shell"
_SHELL_HINTS, _SHELL_HINTS_USE = "shell-hints", "kernel:shell_hints"
# `/model` was the operator's (`commands:operator`, whose config's `layer` and `model_row` it
# read); it is the models plugin's `switch` row now (`models:switch`), beside the catalog.
_OPERATOR, _OPERATOR_USE = "operator", "commands:operator"
_SWITCH, _SWITCH_USE = "switch", "models:switch"
_TO_SWITCH = ("layer", "model_row")
_SWITCHED = "/model is the models plugin's now (models:switch)"
# `/clear` was the operator's too (its config's `clear`, the rows it restarted, and `forget`, the
# files it emptied first), and `/compact` the `compact` row's (`agent:compact`): both are the
# agent plugin's `conversation` row's now (`agent:conversation`), which finds the transcript's
# file from the transcript row and keeps the old conversation as `.bak`.
_CONVERSATION, _CONVERSATION_USE = "conversation", "agent:conversation"
# The restarts commands ask for run in the `jobs` row (`commands:jobs`), which the chat row waits
# on before it reads a line: a layer that fills the chat row or the operator itself needs it.
_JOBS, _JOBS_USE = "jobs", "commands:jobs"
_CHAT_USE = "chat:session"
_COMPACT, _COMPACT_USE = "compact", "agent:compact"
_CLEARED = "/clear is the conversation row's now (agent:conversation)"
_FORGOTTEN = (
    "`forget` is gone: /clear writes an empty conversation over the transcript row's file, keeping "
    "the old as .bak"
)


def translated(rows: Sequence[Row]) -> tuple[list[Row], list[str]]:
    """`rows` in this bh-02's names, and one line per change saying what changed and what to do.

    - A renamed row takes its new id (`llm` is `loop`, `mode` is `chat`, `completion` is
      `model`, `kernel` is `python`, `jail` is `runner`), and a `clear` naming one names the new
      one; a `model_row` (or an old
      `model_status`'s `row`) naming `llm` or `completion` names `model`, the row that holds
      the model now. A renamed row whose
      new id the layer already has keeps its old id, and the change says to fold the two into
      one by hand (`clashes`): which of them wins is the person's call.
    - `model_status` (and any row using `tui:model`) becomes part of the `status` row:
      `use = "tui:status"` if it named a plugin, its config under the status row's names (`row`
      is `model_row`; `default`, and the status row's own `default_model`, are gone: the
      `models` row says which model the model row names). Its `disabled` is not carried over:
      the status row cannot turn off one part, and turning off all of it would hide the session
      too, so the change says how to turn off both instead (a `status` row already in the layer
      keeps its own `disabled`). A status row with nothing left to say is not written. The jail
      field's row (`jail_status`, `tui:jail_status`) is renamed, as above: it is `grades`
      (`tui:grades`), and keeps its `disabled`.
    - A row bh-02 no longer has is dropped: the tool rows before CodeAct (any using the `tools:`,
      `fs:` or `codeact:` plugins; a `tools` row naming none is today's broker's), a session's
      `session` row, the sidebar (a change to the shipped `sidebar` row, or any row using
      `tui:sessions`), the shell hints (a change to the shipped `shell-hints` row, or any row
      using `kernel:shell_hints`), and a fixed field (`tui:status` with a `field` or `text`,
      whatever its id).
    - The project context's rows are the system prompt's and memory's (`context:project` is
      `agent:system`, `context:on_touch` is `memory:on_touch`), and a `system` row's config of
      more than `root` is split (`_split_system`): its `root` and `home` go to a `memory` row
      too, its `files` and `max_chars` are gone. The broker `agent:memory` is `agent:notes`,
      under the id `notes`.
    - The model row's providers are `models:model`'s now (`_model_row`): `claude-code:completion`
      (or a model row naming no plugin, which was it) names its model as `default`, an id that
      is no built-in name as an `extra` model of its own; `ollama:completion` is an `extra`
      OpenAI-compatible model at its host's `/v1`. bh-02's fakes that bound `completion` bind
      `model` under new names (`echo_completion` is `echo_model`).
    - The kernel plugin is two: the python tool (`kernel:kernel` is `python:tool`) and the
      runner, which the brig plugin became (`brig:jail` is `runner:confined`, `kernel:unjailed`
      `runner:unconfined`, `kernel:approval` `runner:approval`, `kernel:release`
      `runner:release`). Memory's row is `memory:files`.

    - `/model` is the models plugin's `switch` row (`models:switch`): an operator's `layer` and
      `model_row` move to it (added after the operator, unless the layer has one, when the
      change says to set them there by hand), and a layer that fills the operator itself
      (`use = "commands:operator"`) and has no `switch` row gets one.
    - `/clear` and `/compact` are the agent plugin's `conversation` row (`agent:conversation`):
      the `compact` row (or any using `agent:compact`) is renamed to it, an operator's `clear`
      moves to it (added after the operator, as for the switch row), its `forget` is gone, and a
      layer that fills the operator itself and has neither gets one.
    - A layer that fills the chat row or the operator itself (`chat:session`,
      `commands:operator`) and has no `jobs` row gets one (`commands:jobs`): the restarts commands
      ask for run there, and the chat row waits on it.

    Nothing changed is `(list(rows), [])`, so translating twice changes nothing more.
    """
    out: list[Row] = []
    changes: list[str] = []
    merged: list[Row] = []
    at = None  # where the status row goes: where the first of its parts was
    taken = {row.id for row in rows}
    memory_taken = any(row.id == _MEMORY_ROW and row.use != _OLD_NOTES_USE for row in rows)
    for row in rows:
        if row.use == _OLD_NOTES_USE:
            changes.append(
                f"row {row.id!r} (agent:memory) is now {_NOTES!r}, using agent:notes; "
                f'make it id = "{_NOTES}" and use = "{_NOTES_USE}"'
            )
            row = Row(_NOTES if row.id == _MEMORY_ROW else row.id, _NOTES_USE, row.config, row.disabled)
        if row.id == _SYSTEM and row.use in _OLD_SYSTEM_USES and set(row.config or {}) - {"root"}:
            system, memory, said = _split_system(row, memory_taken)
            changes += said
            out += [system, *memory]
            continue
        if (why := _removed(row)) is not None:
            changes.append(f"row {row.id!r} was removed: {why}; delete it")
            continue
        if row.id in _MERGED_IDS or row.use in _MERGED_USES or row.id == _STATUS:
            at = len(out) if at is None else at
            merged.append(row)
            if row.id != _STATUS:
                changes.append(_merged_change(row))
            continue
        if (clash := _clash(row, taken)) is not None:
            changes.append(clash)
        elif row.id in _RENAMED:
            changes.append(f"row {row.id!r} is now {_RENAMED[row.id]!r}; rename its id")
            row = Row(_RENAMED[row.id], row.use, row.config, row.disabled)
        if row.config is not None and (config := _renamed_rows(row.config)) != row.config:
            changes.append(f"row {row.id!r}: its config names a renamed row; make it {_inline(config)}")
            row = Row(row.id, row.use, config, row.disabled)
        if row.use in _RENAMED_USES:
            changes.append(
                f"row {row.id!r}: {row.use} is now {_RENAMED_USES[row.use]}; "
                f"make it use = {json.dumps(_RENAMED_USES[row.use])}"
            )
            row = Row(row.id, _RENAMED_USES[row.use], row.config, row.disabled)
        if row.id == _MODEL and (moved := _model_row(row)) is not None:
            row, change = moved
            changes.append(change)
        out.append(row)
    if at is not None:
        old = any(part.id != _STATUS for part in merged)
        status = _status(merged)
        gone = next(
            (part for part in merged if part.id == _STATUS and _STATUS_GONE & set(part.config or {})), None
        )
        if gone is not None and not old:  # today's status row, but for the default it no longer takes
            changes.append(_status_gone(gone))
        if old or gone is not None:  # rewritten; today's status row alone stays as it is
            out[at:at] = [status] if status != Row(_STATUS) else []
        else:  # today's status row: only a row its config names may have been renamed
            kept = []
            for part in merged:
                if part.config is not None and (config := _renamed_rows(part.config)) != part.config:
                    changes.append(
                        f"row {part.id!r}: its config names a renamed row; make it {_inline(config)}"
                    )
                    part = Row(part.id, part.use, config, part.disabled)
                kept.append(part)
            out[at:at] = kept
    out, said = _switched(out)
    out, cleared = _conversation(out)
    out, jobbed = _jobs(out)
    return out, changes + said + cleared + jobbed


def _jobs(rows: Sequence[Row]) -> tuple[list[Row], list[str]]:
    """`rows` with a `jobs` row when the layer fills the chat row or the operator itself and has
    none, and what changed."""
    if any(row.id == _JOBS for row in rows):
        return list(rows), []
    at = next((n for n, row in enumerate(rows) if row.use in (_CHAT_USE, _OPERATOR_USE)), None)
    if at is None:
        return list(rows), []
    return [*rows[: at + 1], Row(_JOBS, _JOBS_USE), *rows[at + 1 :]], [
        f"the chat row waits on `jobs` now, where commands queue the restarts they ask for: add a "
        f'{_JOBS!r} row with use = "{_JOBS_USE}"'
    ]


def _conversation(rows: Sequence[Row]) -> tuple[list[Row], list[str]]:
    """`rows` with `/clear` and `/compact` as the agent plugin's `conversation` row, and what
    changed: the `compact` row renamed to it, an operator's `clear` moved to it and its `forget`
    dropped, and a layer that fills the operator itself given one."""
    changes: list[str] = []
    renamed: list[Row] = []
    for row in rows:
        if row.id == _COMPACT and row.use in (None, _COMPACT_USE) or row.use == _COMPACT_USE:
            use = _CONVERSATION_USE if row.use is not None else None
            rid = _CONVERSATION if row.id == _COMPACT else row.id
            said = ", ".join(
                [
                    *([f'id = "{rid}"'] if rid != row.id else []),
                    *([f"use = {json.dumps(use)}"] if use else []),
                ]
            )
            changes.append(
                f"row {row.id!r}: /compact is the conversation row's now, with /clear; make it {said}"
            )
            row = Row(rid, use, row.config, row.disabled)
        renamed.append(row)
    has_conversation = any(row.id == _CONVERSATION for row in renamed)
    out: list[Row] = []
    for row in renamed:
        out.append(row)
        if row.id != _OPERATOR and row.use != _OPERATOR_USE:
            continue
        config = dict(row.config or {})
        moved = {"clear": config.pop("clear")} if "clear" in config else {}
        forgot = config.pop("forget", None) is not None
        adds = not has_conversation and (bool(moved) or row.use == _OPERATOR_USE)
        use = _CONVERSATION_USE if row.use is not None else None
        added = ", ".join(
            [*([f"use = {json.dumps(use)}"] if use else []), *([_inline(moved)] if moved else [])]
        )
        told = [_FORGOTTEN] if forgot else []
        if moved and not adds:
            told.append(
                f"{_CLEARED}, which reads {_inline(moved)}: set it on the {_CONVERSATION!r} row by hand"
            )
        elif adds:
            told.append(f"{_CLEARED}: add a {_CONVERSATION!r} row with {added}")
        if moved or forgot:
            out[-1] = Row(row.id, row.use, config or None, row.disabled)
            keep = f"make it {_inline(config)}" if config else "delete its config"
            changes.append(f"row {row.id!r}: {'; '.join(told)}; {keep}")
        elif adds:
            changes.append(told[0])
        if adds:
            out.append(Row(_CONVERSATION, use, moved or None))
            has_conversation = True
    return out, changes


def _switched(rows: Sequence[Row]) -> tuple[list[Row], list[str]]:
    """`rows` with `/model` as the models plugin's `switch` row, and what changed: an operator's
    `layer` and `model_row` move to it, and a layer that fills the operator itself gets one."""
    has_switch = any(row.id == _SWITCH for row in rows)
    out: list[Row] = []
    changes: list[str] = []
    for row in rows:
        out.append(row)
        if row.id != _OPERATOR and row.use != _OPERATOR_USE:
            continue
        config = dict(row.config or {})
        moved = {key: config.pop(key) for key in _TO_SWITCH if key in config}
        if moved:
            out[-1] = Row(row.id, row.use, config or None, row.disabled)
            keep = f"make it {_inline(config)}" if config else "delete its config"
            if has_switch:
                changes.append(
                    f"row {row.id!r}: {_SWITCHED}, which reads {_inline(moved)}: {keep}, and set it on "
                    f"the {_SWITCH!r} row by hand"
                )
                continue
        elif has_switch or row.use != _OPERATOR_USE:
            continue
        use = _SWITCH_USE if row.use is not None else None
        out.append(Row(_SWITCH, use, moved or None))
        has_switch = True
        added = ", ".join(
            [*([f"use = {json.dumps(use)}"] if use else []), *([_inline(moved)] if moved else [])]
        )
        if moved:
            changes.append(f"row {row.id!r}: {_SWITCHED}: {keep}, and add a {_SWITCH!r} row with {added}")
        else:
            changes.append(f"{_SWITCHED}: add a {_SWITCH!r} row with {added}")
    return out, changes


def _split_system(row: Row, memory_taken: bool) -> tuple[Row, list[Row], list[str]]:
    """The project context's `system` row as two: the system prompt's, with its `root`, and the
    memory row's, with its `root` and `home` (unless the layer has a memory row already, which the
    change says to set by hand); and what changed. Its `files` and `max_chars` are gone."""
    config = dict(row.config or {})
    use = "agent:system" if row.use is not None else None
    system = Row(row.id, use, {"root": config["root"]} if "root" in config else None, row.disabled)
    moved = {key: config[key] for key in _TO_MEMORY if key in config}
    gone = sorted(set(config) - {"root", *_TO_MEMORY})
    changes = [
        f"row {row.id!r} is the system prompt now, which takes only `root`; "
        f"make it {_inline(system.config or {})}"
    ]
    memory: list[Row] = []
    if moved and memory_taken:
        changes.append(
            f"row {row.id!r}: set {_inline(moved)} on the {_MEMORY_ROW!r} row by hand: memory reads them now"
        )
    elif moved:
        memory.append(Row(_MEMORY_ROW, None, moved))
        changes.append(f"add a {_MEMORY_ROW!r} row with config {_inline(moved)}: memory reads them now")
    if gone:
        changes.append(
            f"row {row.id!r}: {', '.join(gone)} {'is' if len(gone) == 1 else 'are'} gone ({_CONTEXT_GONE})"
        )
    return system, memory, changes


def _model_row(row: Row) -> tuple[Row, str] | None:
    """The model row as `models:model` fills it, and what changed; None when it already is.

    Claude Code's row (or a model row naming no plugin, whose config was Claude Code's) names
    its model by `default` now, a built-in name as it is and an id as an `extra` model of the
    row's own; Ollama's is an `extra` OpenAI-compatible model at `<host>/v1`, named as its model."""
    config = dict(row.config or {})
    kept = {key: config[key] for key in _KEPT if key in config}
    if row.use == _OLLAMA_USE:
        name = str(config.get("model") or _OLLAMA_MODEL)
        url = str(config.get("host") or _OLLAMA_HOST).rstrip("/") + "/v1"
        fresh = {
            "default": name,
            "extra": {name: {"provider": "openai", "id": name, "base_url": url}},
            **kept,
        }
        why = "Ollama is an OpenAI-compatible model of the model row now"
    elif row.use == _CLAUDE_CODE_USE or (row.use is None and "model" in config):
        fresh = {**_claude(config.get("model")), **kept}
        why = "Claude Code is a provider of the model row now, which names its model `default`"
    else:
        return None
    use = _MODELS_USE if row.use is not None else None
    # a row that named no config still names none: an empty one would replace the session's
    # own model config whole, pinning the model and dropping its `state`
    config_out = fresh if fresh or row.config is not None else None
    moved = Row(row.id, use, config_out, row.disabled)
    parts = [f"use = {json.dumps(use)}"] if use else []
    if config_out is not None:
        parts.append(_inline(fresh))
    said = ", ".join(parts)
    return moved, f"row {row.id!r}: {row.use or 'its config'} is gone: {why}; make it {said}"


def _claude(model: object) -> dict[str, Any]:
    """A Claude Code row's `model` as the model row's config: a built-in name as `default`; an
    id as an `extra` model of the row's own (provider `claude-code`) that `default` names."""
    if not isinstance(model, str) or not model:
        return {}
    if model in _BUILT_IN:
        return {"default": model}
    return {"default": model, "extra": {model: {"provider": "claude-code", "id": model}}}


def _status_gone(row: Row) -> str:
    """What becomes of a status row's `default_model`, which the status row no longer takes."""
    config = _status_config(row.config)
    keep = f"make it {_inline(config)}" if config else "delete its config"
    return (
        f"row {row.id!r}: default_model is gone (the status bar shows the model and provider the "
        f"model row names); {keep}"
    )


def _removed(row: Row) -> str | None:
    """Why bh-02 no longer has `row`, or None when it still does."""
    if row.id in _REMOVED_IDS:
        return _REMOVED_IDS[row.id]
    if row.use is not None and row.use.startswith(_REMOVED_USES):
        return f"{row.use} is gone: {_ONE_TOOL}"
    if row.use == _SIDEBAR_USE:
        return f"{row.use} is gone: {_NO_SIDEBAR}"
    if row.id == _SIDEBAR and row.use is None:
        return _NO_SIDEBAR
    if row.use == _SHELL_HINTS_USE:
        return f"{row.use} is gone: {_NO_SHELL_HINTS}"
    if row.id == _SHELL_HINTS and row.use is None:
        return _NO_SHELL_HINTS
    if row.use == _STATUS_USE and {"field", "text"} & set(row.config or {}):
        return "tui:status is now the status bar's session and model fields, not a fixed field"
    return None


def clashes(rows: Sequence[Row]) -> list[str]:
    """The changes `translated` cannot make for the person: a renamed row whose new id the
    layer already has (both `llm` and `loop`). Empty when there are none."""
    taken = {row.id for row in rows}
    return [clash for row in rows if (clash := _clash(row, taken)) is not None]


def _clash(row: Row, taken: set[str]) -> str | None:
    """Why `row` cannot take its new id, or None when it can (or was not renamed)."""
    new = _RENAMED.get(row.id)
    if new is None or new not in taken:
        return None
    return (
        f"row {row.id!r} is now {new!r}, and this layer has a {new!r} row too: fold what "
        f"{row.id!r} sets into {new!r} and delete {row.id!r}"
    )


def _merged_change(row: Row) -> str:
    """What becomes of a status-bar row that is now part of `status`."""
    config = _status_config(row.config) if row.config is not None else None
    moved = f"; its config moves there as {_inline(config)}" if config else ""
    off = (
        f"; it was disabled, but {_STATUS!r} cannot turn off one part, so the status bar stays "
        f"on: to turn off both its fields (session and model), give {_STATUS!r} `disabled = true`"
        if row.disabled
        else ""
    )
    return f"row {row.id!r} is now part of {_STATUS!r}, the status bar's one row{moved}{off}"


def _inline(config: Mapping[str, Any]) -> str:
    """`config` as a layer file writes it, as TOML someone can paste: `config = { default = "fake" }`,
    a nested table as an inline table (`extra = { "qwen3" = { provider = "openai", ... } }`)."""
    return f"config = {_toml(config)}"


def _toml(value: object) -> str:
    """One TOML value, inline: a key that isn't bare (`qwen2.5:7b`) quoted, a string as JSON's
    (a valid TOML basic string)."""
    match value:
        case bool():
            return "true" if value else "false"
        case int() | float():
            return repr(value)
        case Mapping():
            pairs = (f"{_key(str(k))} = {_toml(v)}" for k, v in value.items())
            return "{ " + ", ".join(pairs) + " }"
        case list() | tuple():
            return "[" + ", ".join(_toml(v) for v in value) + "]"
    return json.dumps(str(value))


def _key(key: str) -> str:
    """A TOML key: bare when it can be (`default`), quoted when not (`"qwen2.5:7b"`)."""
    return key if key and all(c.isascii() and (c.isalnum() or c in "_-") for c in key) else json.dumps(key)


def _status(parts: Sequence[Row]) -> Row:
    """The one status row the old status-bar rows (and any `status` row already there) make:
    disabled only as a `status` row already there says, never by an old part's flag."""
    use = _STATUS_USE if any(part.use is not None for part in parts) else None
    configs = [_status_config(part.config) for part in parts if part.config is not None]
    config = {key: value for each in configs for key, value in each.items()} or None
    own = next((part.disabled for part in parts if part.id == _STATUS), None)
    return Row(_STATUS, use, config, own)


def _status_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """An old status-bar row's config under the status row's names, rows renamed too, and
    without the default model it no longer takes."""
    renamed = {
        _STATUS_KEYS.get(key, key): value for key, value in (config or {}).items() if key not in _STATUS_GONE
    }
    return dict(_renamed_rows(renamed))


def _renamed_rows(config: Mapping[str, Any]) -> Mapping[str, Any]:
    """`config` with each renamed row it names renamed: an operator's `clear` the rows' new ids,
    a `model_row` the row that holds the model now."""
    out: dict[str, Any] = dict(config)
    if isinstance(out.get("clear"), list):
        out["clear"] = [_RENAMED.get(name, name) for name in out["clear"]]
    for key in ("model_row", "row"):
        if isinstance(out.get(key), str):
            out[key] = _MODEL_ROWS.get(out[key], out[key])
    return out if out != config else config
