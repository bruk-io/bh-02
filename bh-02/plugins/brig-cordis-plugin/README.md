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
  host imports code from) is left to the outer one (`uncovered`). Without `/usr/bin/bwrap`,
  `start` says to install `bubblewrap` or use `kernel:unjailed`.

**Placeholders (Linux).** bubblewrap holds a write-denied path that doesn't exist with an empty,
read-only directory mounted there, and the mount point is a real directory it makes on the host:
a placeholder. So while a kernel runs, `.envrc/`, `.vscode/`, `.idea/`, `.claude/`, an absent
`local.env/` where bh-02 looks for its credential, and in a project that is not a repository
`.git/`, are empty directories in the project on the host. Where a denied path's parent is
absent too (`.git/config` with no `.git`), the topmost absent one is held instead (`mountable`),
so the host's `git init` works while the kernel runs: it fills the empty `.git/` on the host,
while inside the jail `.git` stays an empty read-only directory until the next kernel start. What a placeholder gets in the way
of, while it is there: creating that path as a file by hand (`.envrc`, your credential in
`local.env`: stop bh-02 first). **Removing one while the kernel runs lifts its deny**: the
mount is detached inside the jail, and a cell can then create and write the path (brig SPEC.md,
decision-164; `test_a_linux_jail_s_hold_on_a_secret_ends_when_the_host_replaces_or_removes_it`),
so nothing here removes one early, and neither should you.

When they go: the jail removes the ones it made once brig has verified the worker is gone and
no other bh-02 jail of the same user is running (a shared `flock` on
`/tmp/bh-02-jails-<uid>.lock`, held by every running jail and taken exclusively to clean up: a
second session in the same project binds the first one's placeholders read-only, and removing
them would detach those binds). Each jail records what it made before bubblewrap makes it, in
bh-02's state directory (`$XDG_STATE_HOME/bh-02/jails/`, else `~/.local/state/bh-02/jails/`,
one file per jail). Once bubblewrap is started the record names its process group, and once the
jail is up the jail marks each placeholder as its own (an extended attribute,
`user.bh-02.placeholder`, holding the jail's id; where the filesystem takes none, the record
keeps the directory's inode and change time instead). A session that crashed, or stopped while
another ran, leaves its record, and the next bh-02 jail to start with none running removes what
it names: only an empty directory still marked as that jail's, never one the person has put
something in or made again since. A record whose process group still runs is left alone,
placeholders and all, until it has ended (removing one would detach that jail's mount; the
moment between a killed bh-02 and its jail ending, below, is such a time:
`test_the_sweep_leaves_a_record_whose_process_group_still_runs`).

**The jail ends with bh-02.** Each jail is launched tethered (brig SPEC.md section 8,
decision-167): bh-02 holds the write end of a pipe nothing else holds, and brig's watcher, in the
jail's process group, kills that group once the pipe closes. bh-02 closes it after stopping the
jail; when bh-02 dies, however it dies (a crash, `kill -9`), the kernel closes it. So a program a
cell left running in the background goes with bh-02 instead of keeping its write access to the
project. On Linux that is the whole jail, a program in a session of its own included: killing
the group ends bubblewrap's pid namespace, and every process in it
(`test_a_killed_bh_02_s_jail_ends_with_it_and_the_next_jail_removes_what_it_left`, which then
shows the next jail's sweep removing what the killed one left). On darwin, see the gap below.

On any other platform, `start` refuses and names `kernel:unjailed`. The grades are brig's own, known
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

- Placeholders (above) are real on the host while a kernel runs, and stay until a bh-02 jail
  starts or stops with no other running. A crash in the moment between writing the record and
  starting bubblewrap, or before the placeholders are marked, leaves a record by path alone,
  which removes any empty directory there (and trusts that no jail of it runs). Without extended
  attributes, a placeholder is known by inode and change time, which is as fine as the kernel's
  clock tick, and one something was made and removed under since is kept.
- In a git worktree or submodule `.git` is a file, and nothing can be mounted under it, so the
  jail denies writing the `.git` file itself (`mountable`); on darwin only `.git/hooks` and
  `.git/config` are denied, which cannot exist under a file anyway.
- There is no home directory in the jail (at most the path to an interpreter installed under
  it), so `~/.gitconfig` isn't read. The person's `user.name` and `user.email`, as git resolves
  them on the host for the project, are set in the worker's environment as `GIT_AUTHOR_*` and
  `GIT_COMMITTER_*` (`git_author`), so a jailed `git commit` is theirs; nothing else of their git
  config (aliases, credential helpers, includes) reaches the jail, and a cell can read the two
  values from its environment, as it could from any commit. Chosen over a generated
  `HOME/.gitconfig` in the jail's scratch: no file, and a repository's own identity still wins
  (the host resolved it). The model is told what the jail reads (`reads()`, which
  `context:project` puts in the prompt) and that the home directory is not there.

Known gap on darwin, beyond Linux's: seatbelt has no process namespace, so the jail's processes
are known by their process group alone. A program a cell starts in a session of its own
(`subprocess.Popen(..., start_new_session=True)`, `setsid`, a daemon that double-forks) leaves
that group, and neither stopping the kernel (`/restart kernel`, quitting) nor bh-02 dying ends
it: it keeps running, still under seatbelt and its write denies, with write access to the
project, until it ends or you end it
(`test_a_killed_bh_02_s_seatbelt_jail_ends_with_it_but_not_a_program_that_left_its_group`).
A program left in the group (`Popen` as it comes, a shell's `&`, `nohup`) ends with the jail.

One known gap: under `python -m bh_02` the project root is itself on `sys.path`. Denying it would
make the project read-only, so it is left writable, and a module a cell writes at the root
could shadow one the host has not imported yet. The `bh-02` console script never puts the root
on `sys.path`, so run `bh-02`, not `python -m bh_02`, when that matters.
