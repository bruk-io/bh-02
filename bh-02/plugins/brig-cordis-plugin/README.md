# brig-cordis-plugin

A `jail` from [brig](../../../libs/brig), and the only package in the workspace that imports it (the
gate's `brig-one-adapter`).

| Row | Binds | Consumes |
|---|---|---|
| `brig:jail` | `jail` over brig's `scratch_darwin()` (darwin) or `strict_linux()` (Linux); config: `write` (default `["."]`), `deny`, `allow` (names taken off brig's self-modification list; default `["CLAUDE.md", "AGENTS.md"]`), `hide` (default `["local.env"]`), `env` (the names that survive the scrub) | `layers` |

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
- **network**: none; the kernel's own LISTEN socket is the one way in or out;
- **env**: scrubbed to `env`.

One policy, two stacks (`stack_for`):

- **darwin**: brig's `scratch_darwin()` (seatbelt), which reads by denylist: `spec_for` as it is.
- **Linux**: brig's `strict_linux()` (bubblewrap), which reads by allowlist. `allowlisted` names
  what is readable: `SYSTEM_READABLE` (`/usr`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/etc`, those
  that exist), the interpreter (`sys.base_prefix`, `sys.prefix`, and every symlinked directory
  on the way to the executable: a uv venv's `python` goes through `cpython-3.15-...`), the
  directory of each absolute path the command names (the worker's), and the writable roots.
  Nothing else exists in the jail, the home directory included, so a cell that reads a file
  outside the project gets `No such file or directory`. The policy's read denies are brig's
  carve-outs inside that tree: the project's `local.env`, if it exists, is masked (reads fail
  with EACCES); if it doesn't, `fs_read` grades `best_effort` naming it, because a file created
  there after the jail started would be readable. bubblewrap makes each absent write-denied path
  under the project (`.envrc`, `.vscode`, `.git/config`, ...) an empty directory on the host to
  mount over, for as long as the kernel runs; the jail removes the ones it made once brig has
  verified the worker is gone. Without `/usr/bin/bwrap`, `start` says to install `bubblewrap`
  or use `kernel:unjailed`.

Anywhere else, `start` refuses and names `kernel:unjailed`. The grades are brig's own, known
before anything starts: `fs_write`, `network` and `env` enforced, `limits` best-effort, `fs_read`
enforced (on Linux, best-effort while a hidden path is absent). `bh-02/app/tests/test_python_cells.py`
runs real cells in this jail: on darwin in `scripts/check`, on Linux in `scripts/linux-jail-check`.

Known gaps on Linux, beyond darwin's:

- While a kernel runs, the empty placeholder directories are real on the host: `git init` in a
  project that is not a repository fails meanwhile (`.git/config` is a directory), and so does
  creating `.envrc` by hand. Removing one while the kernel runs reopens the path inside the jail
  (brig SPEC.md, decision-164), so nothing here does.
- A secret created after the kernel started, at a path inside the project, is readable until
  the kernel restarts; the `fs_read` grade names each such path.

One known gap: under `python -m bh_02` the project root is itself on `sys.path`. Denying it would
make the project read-only, so it is left writable, and a module a cell writes at the root
could shadow one the host has not imported yet. The `bh-02` console script never puts the root
on `sys.path`, so run `bh-02`, not `python -m bh_02`, when that matters.
