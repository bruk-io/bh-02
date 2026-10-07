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
- **network**: none; the program's own LISTEN socket is the one way in or out. The `jail` row
  starts two programs, each with a jail of its own compiled from this one policy: the kernel's
  worker, and the extensions' worker (`extensions:extensions`), where the model's own plugins
  run;
- **env**: scrubbed to `env`.

One policy, two stacks (`stack_for`):

- **darwin**: brig's `scratch_darwin()` (seatbelt), which reads by denylist: `spec_for` as it is.
- **Linux**: brig's `strict_linux()` (bubblewrap), which reads by allowlist. `allowlisted` names
  what is readable: `SYSTEM_READABLE` (`/usr`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/etc`, those
  that exist), the interpreter (`sys.base_prefix`, `sys.prefix`, and every symlinked directory
  on the way to the executable: a uv venv's `python` goes through `cpython-3.15-...`), the
  directory of each absolute path the command names (the worker's), and the writable roots.
  Nothing else exists in the jail, the home directory included, so an input that reads a file
  outside the project gets `No such file or directory`. The policy's read denies are brig's
  carve-outs inside that tree. A secret under the project (its `local.env`, and when bh-02 runs
  inside its own workspace every place the model row looks for one: `layers.secrets` names
  them) is held in place by a mount on its path: one that exists is masked (reads fail with
  EACCES, and so do writes, removal and a rename over it). One that doesn't exist has nothing to
  mask. Where the model row looks for its credential (`layers.credentials`) it is write-denied,
  an empty read-only directory, so an input can create nothing there (a planted `local.env` would
  be read by the next launch; the lookup takes only a regular file, so the directory never hides
  the real one). Anywhere else (the project's own absent `local.env`, which nothing of bh-02's
  reads) it is left alone, and `fs_read` names it: a file created there later is readable.
  A write deny inside another (an absent secret in a directory the
  host imports code from) is left to the outer one (`uncovered`). Without `/usr/bin/bwrap`,
  `start` says to install `bubblewrap` or use `kernel:unjailed`.

**Placeholders (Linux).** bubblewrap holds a write-denied path that doesn't exist with an empty,
read-only directory mounted there, and the mount point is a real directory on the host, which
the jail makes for it: a placeholder. So while a kernel runs, `.envrc/`, `.vscode/`, `.idea/`, `.claude/`, an absent
`local.env/` where bh-02 looks for its credential, and in a project that is not a repository
`.git/`, are empty directories in the project on the host. Where a denied path's parent is
absent too (`.git/config` with no `.git`), the topmost absent one is held instead (`mountable`),
so the host's `git init` works while the kernel runs: it fills the empty `.git/` on the host,
while inside the jail `.git` stays an empty read-only directory until the next kernel start. What a placeholder gets in the way
of, while it is there: creating that path as a file by hand (`.envrc`, your credential in
`local.env`: `/release` first, below). **Removing one while the kernel runs ends the jail**: the
mount is detached inside the jail (brig SPEC.md, decision-164), so the jail ends itself and the
next input's holds the path again (below, "When the host undoes a mount"); nothing here removes
one early, and neither should you.

**Adding your credential mid-session (`/release`).** Where bh-02 looks for its credential and
there is none, the jail holds the path with a placeholder, so you can't create `local.env` there
while the kernel runs. `/release` (the `kernel:release` row) ends the kernel's worker and its
jail now; the jail's stop removes its placeholders (when no other bh-02 jail of yours runs), and
`release()` sweeps what jails that are gone left, then says which of those paths are free and
which another session's jail still holds. Create the file then, and send your message: the model
row reads it at its next start (with no credential, every step starts afresh, so the next one
does; a model already running keeps the one it started with until `/restart model`). The next
input starts a new jail, which masks the file (`/dev/null` over it): no input reads or rewrites
it. No input gets a window: none runs while the path is free, and an input that runs before you
create the file starts a jail that holds it again (`/release` again). `/restart kernel` is not the step:
it stops and starts the jail at once, holding the path again before you could create anything
(`test_on_linux_release_frees_where_the_model_row_looks_until_the_next_input`).

When they go: the jail removes the ones it made once brig has verified the worker is gone and
no other bh-02 jail of the same user is running (a shared `flock` on
`/tmp/bh-02-jails-<uid>.lock`, held by every running jail and taken exclusively to clean up: a
second session in the same project binds the first one's placeholders read-only, and removing
them would detach those binds). The jail makes its placeholders itself, before bubblewrap
starts (which then mounts over them as it would over directories it made): first it records
them, in bh-02's state directory (`$XDG_STATE_HOME/bh-02/jails/`, else
`~/.local/state/bh-02/jails/`, one file per jail), then makes each and at once marks it as its
own (an extended attribute, `user.bh-02.placeholder`, holding the jail's id; where the
filesystem takes none, the record keeps the directory's inode and change time instead). Once
bubblewrap is started the record names its process group. A session that crashed, or stopped
while another ran, leaves its record, and the next bh-02 jail to start with none running removes
what it names: only an empty directory still marked as that jail's, never one the person has
put something in or made again since, and nothing a record names by path alone (an empty
directory there may be the person's: `test_a_record_with_unmarked_paths_removes_nothing_it_can_t_prove`). A record whose process group still runs is left alone,
placeholders and all, until it has ended (removing one would detach that jail's mount; the
moment between a killed bh-02 and its jail ending, below, is such a time:
`test_the_sweep_leaves_a_record_whose_process_group_still_runs`).

**The jail ends with bh-02.** Each jail is launched tethered (brig SPEC.md section 8,
decision-167): bh-02 holds the write end of a pipe nothing else holds, and brig's watcher, in the
jail's process group, kills that group once the pipe closes. bh-02 closes it after stopping the
jail; when bh-02 dies, however it dies (a crash, `kill -9`), the kernel closes it. So a program
an input left running in the background goes with bh-02 instead of keeping its write access to the
project. On Linux that is the whole jail, a program in a session of its own included: killing
the group ends bubblewrap's pid namespace, and every process in it
(`test_a_killed_bh_02_s_jail_ends_with_it_and_the_next_jail_removes_what_it_left`, which then
shows the next jail's sweep removing what the killed one left). On darwin, see the gap below.

On any other platform, `start` refuses and names `kernel:unjailed`. The grades are brig's own, known
before anything starts: `fs_write`, `network` and `env` enforced, `limits` best-effort, `fs_read`
enforced, but on Linux best-effort whenever the jail holds a secret under a writable root
(`graded`, below). `bh-02/app/tests/test_python_repl.py`
runs real inputs in this jail: on darwin in `scripts/check`, on Linux in `scripts/linux-jail-check`
(which CI runs on every push, `.github/workflows/linux-jail.yml`).

**When the host undoes a mount (Linux): the jail ends.** Every hold is a mount on the host's
directory entry: a write deny an existing path bound read-only over itself (`.git/config`,
`.git/hooks`, a layer file, a host import path) or a placeholder (above), a secret a
`/dev/null` over the file. When the host replaces that entry (`git config`, `git remote add`,
`git push -u` and anything else that sets a value write `.git/config.lock` and rename it over
`.git/config`; editors and `sed -i` save a layer file or `local.env` by renaming a new file over
it), renames it away, removes it (a placeholder) or creates it (an absent secret), the kernel
detaches the mount inside the jail, and from then on an input could write, read or create that
path (measured before this existed: an input wrote `.git/config` after a host `git config`, for the
rest of the session). A held *directory* is not affected by what happens inside it: saving
`.vscode/settings.json` by rename leaves the hold on `.vscode` in place.

So the jail watches the directory of every path it holds (`tripwired`: each write deny under a
writable root, and each held secret), with inotify from bh-02, set up after its placeholders are
made and before bubblewrap mounts over them (`tripwire.py`). At the first such change it kills
the jail's process group, a running input and anything an input left in the background with
it. The next input starts a new jail, which holds the path again, and its answer, which the
person sees in the conversation, starts `(the REPL was started again, because something on the
host replaced or removed .../.git/config (a `git config`, an editor's save), which lifts the
jail's hold on it, so bh-02 ended the jail; the next one holds it again; what earlier inputs
defined is gone)`. An input that was running ends with `the REPL's process ended during this
input because ...`. The cost: the kernel's variables, at every such host change while it runs.
`/release` first (no jail runs until the next input) costs the same and leaves no window.

The window, measured in `scripts/linux-jail-check`'s container (aarch64, bubblewrap 0.9), from
the host's rename (or the start of a host `git config`) to the jail's process group being gone,
over two runs of 20 each: a median of 0.9 to 2.3 ms and a worst of 1.4 to 10 ms with bh-02's
process otherwise idle; a median of 20 to 72 ms and a worst of 35 to 186 ms with another thread
in bh-02's process busy on the CPU (the watcher thread needs the interpreter lock; the figure
also includes the measuring loop waiting for it, so it is an upper bound). In that window, a
program an input left running that tries the path in a tight loop gets its write in: 19 or 20
times in 20, both over a renamed-over `.git/config` and into `.git/config.lock` while a host
`git config` writes it (the
lock is an ordinary new file in `.git`, which an input may write, and git renames it into place:
no mount can hold a file that doesn't exist yet). An input that is not running at that moment
never gets in: the next one finds the path held
(`test_on_linux_a_host_rename_over_a_denied_path_ends_the_jail_and_the_next_holds_it`,
`test_on_linux_a_layer_file_saved_by_rename_reloads_and_no_later_input_rewrites_it`: your own
save of a layer file still reloads). So before you run a host git command that writes
`.git/config`, or save a layer file, while an input's background program runs, stop the reply,
or `/release`.

What was tried and could not hold the path instead: binding the parent read-only with writable
carve-outs (a jailed `git commit` then fails: it creates `.git/index.lock`; measured), and
putting the mount back from outside (entering the jail's mount namespace is refused, `EPERM`,
because bubblewrap nests it in a user namespace bh-02 has no capabilities in; measured).

**`fs_write` is graded `enforced` on Linux** (a decision, 2026-09-30): it grades what an input can
do on its own, and `best_effort` would mark the jail unconfined, so every input would ask. A host
change ends the jail rather than lowering the grade; the window above is what remains. `fs_read`
stays best-effort while a secret is held under a writable root (`held`), and the jail names
those paths when the kernel comes up (`notice()`, which `tui:status` shows as a note). brig's
SPEC.md (section 6, bwrap) says what its own grade covers. darwin's seatbelt matches paths, not
directory entries, and has no such gap: a host `git config` there changes nothing for the jail
(`test_on_darwin_a_host_rename_over_a_denied_path_lifts_nothing`).

**The directory a denied path is in stays put (Linux).** `.git/config` is held by a mount, but
`.git` is writable (a jailed `git commit` writes in it), and an input could rename `.git` away,
taking the mount with it, and make a new `.git/config` of its own, `core.hooksPath` and all
(measured). brig now binds every existing directory between the project and a denied path over
itself (brig SPEC.md section 6, decision-168), so `.git` (and a layer file's directory, and a
host import path's) can't be renamed or removed by an input, and is as writable as before
(`test_an_input_can_t_put_its_own_git_config_in_place_by_moving_the_directory_it_is_in`). What
it costs: `os.rename` between such a directory and the rest of the project fails with `EXDEV`
(`mv` and `shutil.move` copy instead). On darwin an input can rename `.git` away, which
displaces the repository but plants nothing: seatbelt denies `.git/config` and `.git/hooks`
by path, wherever the directory came from.

Known gaps on Linux, beyond darwin's:

- Placeholders (above) are real on the host while a kernel runs, and stay until a bh-02 jail
  starts or stops with no other running. One can stay for good: if bh-02 dies in the instant
  between making a placeholder and marking it (two system calls apart; on a filesystem without
  extended attributes, between making it and rewriting the record), it is an empty directory
  nothing can prove a jail made, so no sweep removes it; remove it by hand (`.envrc/`,
  `.vscode/`, ...: empty, and while no bh-02 runs). Removing an unproven one could remove the
  person's own, which is worse. A crash anywhere else leaves only what the next sweep removes
  (`test_a_placeholder_is_made_and_marked_before_bubblewrap_starts`). Without extended
  attributes, a placeholder is known by inode and change time, which is as fine as the kernel's
  clock tick, and one something was made and removed under since is kept.
- In a git worktree or submodule `.git` is a file, and nothing can be mounted under it, so the
  jail denies writing the `.git` file itself (`mountable`); on darwin only `.git/hooks` and
  `.git/config` are denied, which cannot exist under a file anyway.
- There is no home directory in the jail (at most the path to an interpreter installed under
  it), so `~/.gitconfig` isn't read. The person's `user.name` and `user.email`, as git resolves
  them on the host for the project, are set in the worker's environment as `GIT_AUTHOR_*` and
  `GIT_COMMITTER_*` (`git_author`), so a jailed `git commit` is theirs; nothing else of their git
  config (aliases, credential helpers, includes) reaches the jail, and an input can read the two
  values from its environment, as it could from any commit. Chosen over a generated
  `HOME/.gitconfig` in the jail's scratch: no file, and a repository's own identity still wins
  (the host resolved it). The model is told what the jail reads (`reads()`, which the kernel's
  instructions name) and that the home directory is not there.

Known gap on darwin, beyond Linux's: seatbelt has no process namespace, so the jail's processes
are known by their process group alone. A program an input starts in a session of its own
(`subprocess.Popen(..., start_new_session=True)`, `setsid`, a daemon that double-forks) leaves
that group, and neither stopping the kernel (`/restart kernel`, quitting) nor bh-02 dying ends
it: it keeps running, still under seatbelt and its write denies, with write access to the
project, until it ends or you end it
(`test_a_killed_bh_02_s_seatbelt_jail_ends_with_it_but_not_a_program_that_left_its_group`).
A program left in the group (`Popen` as it comes, a shell's `&`, `nohup`) ends with the jail.

One known gap: under `python -m bh_02` the project root is itself on `sys.path`. Denying it would
make the project read-only, so it is left writable, and a module an input writes at the root
could shadow one the host has not imported yet. The `bh-02` console script never puts the root
on `sys.path`, so run `bh-02`, not `python -m bh_02`, when that matters.
