# warden

A second example app on cordis, unrelated to LLMs: a process supervisor, composed the way bh-02
is (a shell in `app/`, plugins in `plugins/`). `README.md` is its map and `CONTRACTS.md` its own
keys-and-shapes doc. A plugin family agrees on names and shapes among its own members, never
across apps: warden's plugins and bh-02's share nothing.

There is no `pyproject.toml` at this directory: uv resolves a member's workspace sources against
the nearest project, so a project here would hide the workspace from `app/` and `plugins/*`.
warden is policed by the root gate (its shell modules are in the `terminal-io` and
`cordis-in-wiring-only` option lists in the root `pyproject.toml`).
