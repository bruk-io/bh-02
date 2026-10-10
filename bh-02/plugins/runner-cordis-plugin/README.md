# runner-cordis-plugin

What runs the model's code: the `runner`, which starts each program (the Python process, the
extensions process) in a jail from [brig](../../../libs/brig), or in none; the `approval` rule
over it; and `/release`. The only package in the workspace that imports brig (the gate's
`brig-one-adapter`).

| Row | Binds | Consumes |
|---|---|---|
| `runner:confined` | `runner` over brig's `scratch_darwin()` (darwin) or `strict_linux()` (Linux), a jail per start; config: `write` (default `["."]`), `deny`, `allow` (names taken off brig's self-modification list; default `["CLAUDE.md", "AGENTS.md"]`), `hide` (default `["local.env"]`), `env` (the names that survive the scrub) | `host` |
| `runner:unconfined` | `runner`: each program as a plain subprocess (`--no-jail`), every axis reported `unenforced`, its environment without `CLAUDE*` (`CLAUDE_CODE_OAUTH_TOKEN`, and what a Claude Code that launched bh-02 leaves, a messaging token among them) or `ANTHROPIC_*` | |
| `runner:approval` | `approval`: `confined` (whether the runner confines what runs in it), `unasked(request) -> bool` (whether it runs without asking the person) | `runner` (`report`) |
| `runner:release` | (nothing: registers `/release`) | `runner` (`release`), `commands` (`register`) |

`runner.py`'s `Runner` is the `runner` value both rows bind, over a mechanism (`BrigJail` in
`jail.py`, `Unjailed` in `unconfined.py`): what is the same whichever starts the program.
- `start(argv, *, cwd, endpoint) -> started`: the mechanism starts it, listening on `endpoint`,
  and each watcher (`on_start(watch) -> remover`) is told of it after, so the status bar's jail
  field (`tui:grades`) follows a Python process started again in place. What one start is stays
  with it (`started.report()`, `notice()`, `reads()`, `writes()`): the Python process and the
  extensions process each start from a command of their own. `report()` and `notice()` are the
  last start's (before any, the mechanism's grades and "").
- **Each owner stops its own program.** A row that starts something registers its stop
  (`on_release(stop) -> remover`, `stop: async () -> str`): the python row its Python process,
  the extensions row the extensions process. `release()` asks each in turn, then has the mechanism let go of
  what it holds on the host (on Linux, the placeholders where bh-02 looks for its credential,
  below), and joins what each said
  (`test_release_asks_each_owner_to_stop_its_own_then_the_mechanism_and_says_what_each_said`).
  The runner never stops a row's program itself (`test_the_runner_stops_no_program_itself`): a
  program its owner did not stop keeps running, its jail keeps what it holds, and `/release`
  says so (`A program this runner started still runs (its row did not stop it on /release), and
  its jail holds what it holds: /rows shows the rows; /restart one, then /release again.`).
- `released()` is true from `release()` until the next start, whoever starts: an owner that
  would start only to keep something warm (the extensions process) waits while it is, asking
  with nothing awaited between the question and the start, and one the person asked for (the
  next input's Python process, a changed extension) starts, and so ends it.
- The runner knows nothing of inputs, or of which program is the Python process: what a start
  is (`report()`, `notice()`, `reads()`, `writes()`) is all it says, and each owner asks it
  of its own start.

`/release` (`runner:release`) is `release()` as a command; with nothing to say, it answers
`Nothing runs in the runner, and it holds nothing.`

`approval.py` is the rule, written once: `is_confined(report)` (the runner enforces `fs_write`
and `network`), and `Approval`, the `approval` value over the runner: `confined` (read from its
`report()` each time) and `unasked(request)` (it runs in the runner, `runs` `"jail"` when the
request says nothing, and the runner confines it). Asking is not the rule's: the loop puts each
call the rule does not let run unasked to the person (`{"name", "input", "runs", "title",
"lines", ...}`: a call to a tool that runs in bh-02's own process, `runs = "host"`, is put to
the person however confined the runner), and the extensions row each extension it loads, each
through `output.confirm`; the python row's `confined`, what the model is told, is the rule's.
Its row depends on `runner` alone, so `/clear` (a new Python process) and a new ui leave it up,
and the rows that depend on it. It is a capability, bound by one row: two rows' answers could
not be combined, so it is not a broker. It runs in bh-02's own process, so only a layer
replaces it; an extension has no way to bind or reach it. It answers about code bh-02 is about
to hand to the runner, not about each effect a component yields (that is cordis's planned
policy seam, not this).

`runner:confined`'s mechanism, `BrigJail`, compiles a jail for each start from one policy.
`spec_for` is the policy, as a pure function:

- **writes**: the project root, a scratch directory of the jail's own (`TMPDIR`), and the
  project's auto memory directory (`host.auto_memory`, outside the project: the model keeps its
  memories there across sessions, and only the memory rows read it, through no link), except
  the composition's layer files (`host.paths`), every path the host imports code from that sits
  under a writable root (`sys.path` entries, the interpreter's prefix), brig's
  self-modification list (`.git/hooks`, `.git/config`, `.claude`, shell rc files, editor
  settings, ...: what can run code outside the jail later) minus what `allow` names, and `deny`.
  `allow` defaults to the project's guidance files (CLAUDE.md, AGENTS.md), which editing is
  ordinary work; a name not on brig's list is a config error, since `write` is for other paths.
  An `allow` in a layer replaces the default, so name every file it should let through. Nor
  bh-02's configuration directories (`host.trusted`: `$XDG_CONFIG_HOME/bh-02` and
  `~/.config/bh-02`, as named and as resolved) where one is under a writable root, as when bh-02
  runs from the home directory: the host reads the models file and the person's startup file
  there and trusts them, so an input there could choose what every later
  session reads (a startup file made a link to a key the jail hides, which a session in another
  project would read on the host and hand to its model;
  `test_a_session_run_from_home_can_t_choose_what_a_later_session_reads_as_the_person_s`). On
  Linux it is held as any write deny there is (an existing directory bound read-only over
  itself, an absent one a placeholder, the directories above it pinned, a host change ending the
  jail). Not when the project is that directory or inside it: the deny would leave the project
  read-only, so bh-02 run in its own config lets the model write there, as in any project.
  Nor bh-02's own code (`host.code`: the directory of every package bh-02 runs, its own,
  cordis's, cordis_helpers's, brig's, host_paths's and each installed plugin's, as installed, as
  named and as resolved, found by name with `importlib.util.find_spec`, which imports nothing)
  where one is under a writable root: bh-02 working on its own checkout (`uv run` in
  it, `uv tool install --editable`), or run from a home the checkout is in. bh-02 imports
  those modules in its own process (a plugin a layer names later, say), so an input that rewrote
  one, or wrote a module beside one, would choose code bh-02 runs
  (`test_a_jailed_input_can_t_write_bh_02_s_own_code_when_the_project_is_its_checkout`). By
  package, whatever `sys.path` holds: a package an import hook finds is on no `sys.path`, and a
  `src` directory that is the project itself is not denied as a host import path (the test runs
  there too). Held on Linux as any write deny there is. Not one the project is (bh-02 run in a
  package's own directory), which would leave the project read-only. A started program's `writes()` names the roots its inputs may write (the
  python row reads nothing on the host whose way passes through one);
- **reads**: everything except brig's credential list under `$HOME` (`.ssh`, `.aws`, ...) and
  what `host` names as `secrets`: every place the model rows look for `local.env`
  (`host.credentials`, so the workspace's own is hidden whatever directory bh-02 runs in), the
  `local.env` beside and above the project, and the sessions' state directories, this run's
  (`$XDG_STATE_HOME/bh-02/sessions`) and the default one (`~/.local/state/bh-02/sessions`),
  where each session's `claude/` holds its Claude Code child's config and messaging peer token.
  A third, of a run with another `XDG_STATE_HOME`, is not known to this one and is not hidden;
- **network**: none; the program's own LISTEN socket is the one way in or out. The runner
  starts two programs, each with a jail of its own compiled from this one policy: the Python
  process (`python:tool`), and the extensions process (`extensions:extensions`), where the
  model's own plugins run;
- **env**: scrubbed to `env`.

Without the jail (`runner:unconfined`, `--no-jail`) none of this holds but the scrub of
`CLAUDE*` and `ANTHROPIC_*`: every axis is `unenforced`, so the `approval` rule asks about every
input and extension, its code shown, and one the person approves runs with their permissions. It
could open `local.env` itself, read the environment of any process the person owns (the Claude
Code child's, which holds the token), or rewrite bh-02's config directory or its own code.

One policy, two stacks (`stack_for`):

- **darwin**: brig's `scratch_darwin()` (seatbelt), which reads by denylist: `spec_for` as it is.
- **Linux**: brig's `strict_linux()` (bubblewrap), which reads by allowlist. `allowlisted` names
  what is readable: `SYSTEM_READABLE` (`/usr`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/etc`, those
  that exist), the interpreter (`sys.base_prefix`, `sys.prefix`, and every symlinked directory
  on the way to the executable: a uv venv's `python` goes through `cpython-3.15-...`), the
  directory of each absolute path the command names (the program's own `worker.py`), bh-02's own code
  (`host.code`, read-only: with an editable install the environment's `.pth` files name the
  workspace's `src` directories, outside the interpreter's trees, and the extensions process
  imports cordis from there; without them it never listened and no extension loaded:
  `test_on_linux_the_extensions_worker_imports_cordis_from_an_editable_install`; the package
  directories, never the workspace, whose `local.env` stays out), and the writable roots.
  Nothing else exists in the jail, the home directory included, so an input that reads a file
  outside the project gets `No such file or directory`. What a started program can read is its
  `reads()`, each tree once and none inside another (`told_reads`), which the python row names to
  the model. The policy's read denies are brig's
  carve-outs inside that tree. A secret under the project (its `local.env`, and when bh-02 runs
  inside its own workspace every place the model row looks for one: `host.secrets` names
  them) is held in place by a mount on its path: one that exists is masked (reads fail with
  EACCES, and so do writes, removal and a rename over it). One that doesn't exist has nothing to
  mask. Where the model row looks for its credential (`host.credentials`) it is write-denied,
  an empty read-only directory, so an input can create nothing there (a planted `local.env` would
  be read by the next launch, handing its conversations to someone else's account; the lookup
  takes only a regular file, so the directory never hides
  the real one). Anywhere else (the project's own absent `local.env`, which nothing of bh-02's
  reads) it is left alone, and `fs_read` names it: a file created there later is readable.
  A write deny inside another (an absent secret in a directory the
  host imports code from) is left to the outer one (`uncovered`). Without `/usr/bin/bwrap`,
  `start` says to install `bubblewrap` or use `runner:unconfined`.

**Placeholders (Linux).** bubblewrap holds a write-denied path that doesn't exist with an empty,
read-only directory mounted there, and the mount point is a real directory on the host, which
the jail makes for it: a placeholder. So while a jail runs, `.envrc/`, `.vscode/`, `.idea/`, `.claude/`, an absent
`local.env/` where bh-02 looks for its credential, and in a project that is not a repository
`.git/`, are empty directories in the project on the host. Where a denied path's parent is
absent too (`.git/config` with no `.git`), the topmost absent one is held instead (`mountable`),
so the host's `git init` works while a jail runs: it fills the empty `.git/` on the host,
while inside the jail `.git` stays an empty read-only directory until the next start. What a placeholder gets in the way
of, while it is there: creating that path as a file by hand (`.envrc`, your credential in
`local.env`: `/release` first, below). **Removing one while its jail runs ends the jail**: the
mount is detached inside the jail (brig SPEC.md, decision-164), so the jail ends itself and the
next input's holds the path again (below, "When the host undoes a mount"); nothing here removes
one early, and neither should you.

**Adding your credential mid-session (`/release`).** Where bh-02 looks for its credential and
there is none, the jail holds the path with a placeholder, so you can't create `local.env` there
while a jail runs. `/release` (the `runner:release` row) asks each owner to stop its own program
(above): the python row ends the Python process and its jail, and the extensions row the
extensions process and its jail, which holds the same placeholders and a share of the jail lock, so while it
ran nothing could be freed
(`test_release_frees_what_the_programs_held_once_each_owner_stopped_its_own`,
`test_on_linux_release_frees_the_credential_path_while_the_extensions_worker_runs`). Each jail's
stop removes its placeholders (when no other bh-02 jail of yours runs); then `BrigJail`'s
`release()` waits for a start under way, sweeps what jails that are gone left, and says which of
those paths are free (`Nothing holds PATH until something starts in the runner again: create
your local.env there now, then send your message. ...`), which another session's jail still
holds, and whether a program it started still runs, its owner not having stopped it
(`test_release_never_stops_a_program_its_owner_did_not_and_says_it_still_holds`,
`test_release_waits_for_a_start_under_way_and_says_it_still_runs`). The runner is then
`released()` until its next start, which is the next input's Python process, or the extensions
process, for an extension that changed: the extensions row starts none while it is released and
nothing changed, and once it is not, loads every extension again in a new one, so they are back within
half a second of the next input starting the Python process. Create the file then, and send
your message: the model row reads it at its next start (with no credential, every step starts
afresh, so the next one does; a model already running keeps the one it started with until
`/restart model`). The next
input starts a new jail, which masks the file (`/dev/null` over it): no input reads or rewrites
it. No input gets a window: none runs while the path is free, and an input that runs before you
create the file starts a jail that holds it again (`/release` again), as does an extension that
changes meanwhile. `/restart python` is not the step:
it stops and starts the Python process and its jail at once, holding the path again before you could create anything
(`test_on_linux_release_frees_where_the_model_row_looks_until_the_next_input`).

When they go: the jail removes the ones it made once brig has verified the program it ran is gone and
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

On any other platform, `start` refuses and names `runner:unconfined`. The grades are brig's own, known
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
writable root, and each secret it holds there, `held`: one that is there, masked, and an absent
one no input can create, under a write deny), with inotify from bh-02, set up after its placeholders are
made and before bubblewrap mounts over them (`tripwire.py`). At the first such change it kills
the jail's process group, a running input and anything an input left in the background with
it. The next input starts a new jail, which holds the path again, and its answer, which the
person sees in the conversation, starts `(the REPL was started again, because something on the
host replaced or removed .../.git/config (a `git config`, an editor's save), which lifts the
jail's hold on it, so bh-02 ended the jail; the next one holds it again; what earlier inputs
defined is gone)`. An input that was running ends with `the REPL's process ended during this
input because ...`. The cost: the Python process's variables, at every such host change while it runs.
`/release` first (no jail runs until the next start) costs the same and leaves no window.

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

Not watched: an absent secret nothing holds (the project's own `local.env` where bh-02 does not
look for its credential). An input may create it, and the tripwire can't tell an input's
creation from the host's, so watching it would end the jail mid-input and blame the host
(`test_an_input_creating_the_project_s_own_absent_local_env_leaves_the_jail_running`). A file
the host creates there is readable in the jail, as brig's `fs_read` grade says.

What was tried and could not hold the path instead: binding the parent read-only with writable
carve-outs (a jailed `git commit` then fails: it creates `.git/index.lock`; measured), and
putting the mount back from outside (entering the jail's mount namespace is refused, `EPERM`,
because bubblewrap nests it in a user namespace bh-02 has no capabilities in; measured).

**`fs_write` is graded `enforced` on Linux** (a decision, 2026-09-30): it grades what an input can
do on its own, and `best_effort` would mark the jail unconfined, so every input would ask. A host
change ends the jail rather than lowering the grade; the window above is what remains. `fs_read`
stays best-effort while a secret is held under a writable root (`held`), and the jail names
those paths when the Python process comes up (its start's `notice()`, which `tui:grades`
shows once as a note). brig's
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

- Placeholders (above) are real on the host while a jail runs, and stay until a bh-02 jail
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
- There is no home directory in the jail (at most the paths to an interpreter and to bh-02's own
  code installed under it), so `~/.gitconfig` isn't read. The person's `user.name` and `user.email`, as git resolves
  them on the host for the project, are set in the jailed program's environment as `GIT_AUTHOR_*` and
  `GIT_COMMITTER_*` (`git_author`), so a jailed `git commit` is theirs; nothing else of their git
  config (aliases, credential helpers, includes) reaches the jail, and an input can read the two
  values from its environment, as it could from any commit. Chosen over a generated
  `HOME/.gitconfig` in the jail's scratch: no file, and a repository's own identity still wins
  (the host resolved it). The model is told what the jail reads (the Python process's
  `reads()`, which the python row's section names) and that the home directory is not there.

Known gap on darwin, beyond Linux's: seatbelt has no process namespace, so the jail's processes
are known by their process group alone. A program an input starts in a session of its own
(`subprocess.Popen(..., start_new_session=True)`, `setsid`, a daemon that double-forks) leaves
that group, and neither stopping the Python process (`/restart python`, `/release`, quitting) nor bh-02 dying ends
it: it keeps running, still under seatbelt and its write denies, with write access to the
project, until it ends or you end it
(`test_a_killed_bh_02_s_seatbelt_jail_ends_with_it_but_not_a_program_that_left_its_group`).
A program left in the group (`Popen` as it comes, a shell's `&`, `nohup`) ends with the jail.

One known gap: under `python -m bh_02` the project root is itself on `sys.path`. Denying it would
make the project read-only, so it is left writable, and a module an input writes at the root
could shadow one the host has not imported yet. The `bh-02` console script never puts the root
on `sys.path`, so run `bh-02`, not `python -m bh_02`, when that matters.
