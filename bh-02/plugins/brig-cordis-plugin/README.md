# brig-cordis-plugin

A `jail` from [brig](../../../libs/brig), and the only package in the workspace that imports it (the
gate's `brig-one-adapter`).

| Row | Binds | Consumes |
|---|---|---|
| `brig:jail` | `jail` over brig's `scratch_darwin()`; config: `write` (default `["."]`), `deny`, `allow` (names taken off brig's self-modification list; default `["CLAUDE.md", "AGENTS.md"]`), `hide` (default `["local.env"]`), `env` (the names that survive the scrub) | `layers` |

`spec_for` is the policy, as a pure function:

- **writes**: the project root and a scratch directory of the jail's own (`TMPDIR`), except
  the composition's layer files (`layers`), every path the host imports code from that sits
  under a writable root (`sys.path` entries, the interpreter's prefix), brig's
  self-modification list (`.git/hooks`, `.git/config`, `.claude`, shell rc files, editor
  settings, ...: what can run code outside the jail later) minus what `allow` names, and `deny`.
  `allow` defaults to the project's guidance files (CLAUDE.md, AGENTS.md), which editing is
  ordinary work; a name not on brig's list is a config error, since `write` is for other paths.
  An `allow` in a layer replaces the default, so name every file it should let through;
- **reads**: everything except brig's credential list under `$HOME` (`.ssh`, `.aws`, ...) and
  what `layers` names as `secrets` (bh-02's `local.env`, the sessions' state);
- **network**: none; seatbelt allows only the kernel's own LISTEN socket;
- **env**: scrubbed to `env`.

The grades are brig's own (`fs_read`, `fs_write`, `network`, `env` enforced; `limits`
best-effort), known before anything starts. darwin only here: brig's Linux preset reads by
allowlist and has not been run in this workspace, so on Linux `start` refuses and names
`kernel:unjailed`. `bh-02/app/tests/test_python_repl.py` runs real inputs in this jail.

One known gap: under `python -m bh_02` the project root is itself on `sys.path`. Denying it would
make the project read-only, so it is left writable, and a module an input writes at the root
could shadow one the host has not imported yet. The `bh-02` console script never puts the root
on `sys.path`, so run `bh-02`, not `python -m bh_02`, when that matters.
