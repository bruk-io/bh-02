---
id: decision-0010
title: >-
  Keep the jail's environment allow-list in ~/.config/bh-02/runner.toml, below
  any layer, and refuse it naming a variable a key reads
date: '2026-10-25 18:04'
status: proposed
---
## Context

TASK-0169 moves provider keys from `local.env` to the process environment. What keeps a key from the model's code is the jail's environment allow-list: `env -i` plus the runner's `env` names (PATH, HOME, LANG, LC_ALL, TERM, by default), as TASK-0169.01 confirmed. That list can only be set in a `--patch` layer today, a `config` there replaces the row's whole config, and a layer can live anywhere, so it is per launch and easy to forget.

The person wants a standing home under `~/.config/bh-02/`, owned by the runner plugin. Precedent: bh-02's configuration directories are `host.trusted`; the jail forbids writing them (`jail.py`), and files in them are read through `host_paths.passes` (the models file by `in_project`, the sub-agent type files by `type_files`). Plugins may not import one another (`plugin-layering`), and the models file is the models plugin's alone.

## Decision

1. **A file of the runner's own: `~/.config/bh-02/runner.toml`** (`$XDG_CONFIG_HOME/bh-02/runner.toml`), one file per owner as `models.toml` is. It holds `env = ["NAME", ...]`, the variables the jail lets through on top of its baseline (the baseline names are not repeated in the file; they are always passed). It is not a section of a shared file, so the models file's trust and the runner's stay separate, and not the models file, which is the models plugin's. Any other key in it is refused with a message naming the keys it takes, so the file's meaning can grow only by a decision.
2. **A layer's runner `config` that sets `env` replaces the file's list; one that omits it takes the file's.** Today a layer's `config` replaces the whole config, so without this a `--patch` that only sets `allow` would silently drop the person's standing list. The layer is explicit and per launch, so it wins; when it does, the jail's start says in one line that the layer's `env` replaced `runner.toml`'s (names, never values).
3. **Startup refuses an allow-list that names a variable a `key = { env = ... }` in the models file reads.** The jail would hand that key to the model's code, which is exactly what the list exists to prevent. The message names the variable, the endpoint that reads it and both files, and says to remove it from one. Because plugins may not import one another, the check lives where both values are visible (the app's composition, or the `host` value), not in either plugin, and covers a layer's `env` as well as the file's. The same variable names are also what the `!COMMAND` task drops from its environment.
4. **The model cannot write the file, and a file the model could have written is not read.** In `host.trusted`, the jail already denies writes; when bh-02 runs from a directory that contains the config directory (the home directory), the existing `trusted` handling applies. The file is read through `host_paths.passes` like the models file: if it is in the project, or reached through a link into it, it is not read and the person is told where to put it. The direction of failure is narrower: an unread file leaves the baseline, never a wider list. A file that is unreadable or malformed is refused with a message that says what to fix, and the jail does not start on it (a typo must not quietly widen or drop the list).

## Consequences

- `BrigConfig.env`'s default stays the baseline; the standing list is the runner's input before layers, so the runner plugin gains a reader for `runner.toml`, and docs/bh-02/using/jail.md and the runner README describe it.
- A person who relied on `--patch` with `env` keeps it working; one who wrote a layer with only `allow` now also gets their file's list, which is the point.
- The refusal in (3) needs a view of both files at startup, so TASK-0169.03 (the `key` object) must expose which variables each endpoint's `key` reads to that place.
- `--no-jail` ignores the file (the unconfined runner passes the host's environment; TASK-0169 documents that).
- Not decided here: other `BrigConfig` settings (`allow`, `write`, `deny`, `hide`) in the file. They widen what the model may do, not just see, and stay layer-only until someone asks.
