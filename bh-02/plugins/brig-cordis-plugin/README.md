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
  carve-outs inside that tree. A secret under the project (its `local.env`, and when bh-02 runs
  inside its own workspace every place the model row looks for one: `layers.secrets` names
  them) is held in place by a mount on its path: one that exists is masked (reads fail with
  EACCES, and so do writes, removal and a rename over it). One that doesn't exist has nothing to
  mask. Where the model row looks for its credential (`layers.credentials`) it is write-denied,
  an empty read-only directory, so a cell can create nothing there (a planted `local.env` would
  be read by the next launch; the lookup takes only a regular file, so the directory never hides
  the real one). Anywhere else (the project's own absent `local.env`, which nothing of bh-02's
  reads) it is left alone, and `fs_read` names it: a file created there later is readable.
  A write deny inside another (an absent secret in a directory the
  host imports code from) is left to the outer one (`uncovered`). bubblewrap makes each absent
  write-denied path under the project (`.envrc`, `.vscode`, `.git/config`, an absent
  `local.env`, ...) an empty directory on the host to mount over, for as long as the kernel
  runs; the jail removes the ones it made once brig has verified the worker is gone. Without
  `/usr/bin/bwrap`, `start` says to install `bubblewrap` or use `kernel:unjailed`.

Anywhere else, `start` refuses and names `kernel:unjailed`. The grades are brig's own, known
before anything starts: `fs_write`, `network` and `env` enforced, `limits` best-effort, `fs_read`
enforced, but on Linux best-effort whenever the jail holds a secret under a writable root
(`graded`, below). `bh-02/app/tests/test_python_cells.py`
runs real cells in this jail: on darwin in `scripts/check`, on Linux in `scripts/linux-jail-check`.

**What the host can undo on Linux.** A mount sits on the host's directory entry. When the host
replaces that entry (an editor saves `local.env` by writing a new file and renaming it over the
old one; `git config` saves `.git/config` the same way) or removes it (the empty directory held
where a secret is absent), the kernel detaches the mount inside the jail, and from then on a
cell can read and rewrite what is at that path, and create the absent one (measured:
`test_a_linux_jail_s_hold_on_a_secret_ends_when_the_host_replaces_or_removes_it`). bubblewrap
can't prevent it, so `fs_read` grades best-effort while any secret is held that way (`held`),
and the jail says which paths when the kernel comes up (`notice()`, which `tui:status` shows
as a note in the conversation): edit them with bh-02 stopped, or `/restart kernel` afterwards,
which puts a new jail over them. The same is true of every write deny the host replaces by
rename (`.git/config` after a host `git config`): the jail holds it again only from the next
kernel start. darwin's seatbelt matches paths, not directory entries, and has no such gap.

Known gaps on Linux, beyond darwin's:

- While a kernel runs, the empty placeholder directories are real on the host: `git init` in a
  project that is not a repository fails meanwhile (`.git/config` is a directory), and so does
  creating `.envrc` by hand, and so does creating your credential in an absent `local.env` the
  jail holds. Removing one while the kernel runs reopens the path inside the jail
  (brig SPEC.md, decision-164), so nothing here does.
- The placeholders are removed only when no other bh-02 jail of the same user is running (a
  shared `flock` on `/tmp/bh-02-jails-<uid>.lock`, held by every running jail and taken
  exclusively to clean up): a second session in the same project binds the first one's
  placeholders read-only, and removing them would detach those binds. So with overlapping
  sessions, and after a crash or `SIGKILL`, empty placeholder directories stay behind.
- In a git worktree or submodule `.git` is a file, and nothing can be mounted under it, so the
  jail denies writing the `.git` file itself (`mountable`); on darwin only `.git/hooks` and
  `.git/config` are denied, which cannot exist under a file anyway.
- There is no home directory in the jail: `~/.gitconfig` isn't read, so a jailed `git commit`
  needs the repository's own `user.name` and `user.email`.

One known gap: under `python -m bh_02` the project root is itself on `sys.path`. Denying it would
make the project read-only, so it is left writable, and a module a cell writes at the root
could shadow one the host has not imported yet. The `bh-02` console script never puts the root
on `sys.path`, so run `bh-02`, not `python -m bh_02`, when that matters.
