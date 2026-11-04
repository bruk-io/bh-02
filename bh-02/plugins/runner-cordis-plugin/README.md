# runner-cordis-plugin

What runs the model's code: the `runner`, which starts each program (the Python process, the
extensions process) in a jail from [brig](https://github.com/bruk-io/brig), or in none; the `approval` rule
over it; and `/release`. The only package in the workspace that imports brig (the gate's
`brig-one-adapter`), which it takes from bruk-io/brig at the commit pinned in its `pyproject.toml`.

| Row | Binds | Consumes |
|---|---|---|
| `runner:confined` | `runner` over a brig jail (bruk-io/brig's `create_bwrap_jail`, bubblewrap: Linux only for now, darwin, or Linux with no `bwrap`, reports every grade `unenforced` from the start and says before the first input to use `runner:unconfined`, and refuses each start), a jail per start; config: `write` (default `["."]`), `deny`, `hide` (files in the project inputs may not read; none by default), `env` (the names that survive the scrub; unset, they are the baseline `PATH`, `HOME`, `LANG`, `LC_ALL`, `TERM` plus the names in the person's `runner.toml`, below) | `host`, `models` (`key_envs()`, below) |
| `runner:unconfined` | `runner`: each program as a plain subprocess (`--no-jail`), every axis reported `unenforced`, its environment without `CLAUDE*` (`CLAUDE_CODE_OAUTH_TOKEN`, and what a Claude Code that launched bh-02 leaves, a messaging token among them), `ANTHROPIC_*`, `TMUX` or `TMUX_PANE` (hygiene, not a boundary: an input without a jail can find the tmux socket itself; the confined runner's `env` allowlist never passes them, `tests/test_runner_tmux.py` shows both) | |
| `runner:approval` | `approval`: `confined` (whether the runner confines what runs in it), `unasked(question) -> bool` (whether it runs without asking the person) | `runner` (`report`) |
| `runner:grants` | `grants`: the broker of what the person granted the jail (`need`, `ask`, `granted`, `on_change`, `serve`, `list`, `revoke`) | `host` |
| `runner:grant_prompt` | (nothing: serves the grants prompt, tells the model each answer through an aside, and registers `/grants`, which lists and revokes) | `grants` (`serve`, `list`, `revoke`), `output` (`choose`), `asides` (`add`), `commands` (`register`) |
| `runner:release` | (nothing: registers `/release`) | `runner` (`release`), `commands` (`register`) |

`runner.py`'s `Runner` is the `runner` value both rows bind, over a mechanism (`BrigJail` in
`jail.py`, `Unjailed` in `unconfined.py`): what is the same whichever starts the program.
- `start(argv_for, *, cwd) -> started`: the mechanism chooses the program's socket (`endpoint`: a
  short path, since a socket path must fit in ~100 bytes, in a directory of its own that only this
  start's program sees: the channel directory brig reserves and binds into the jail, or for an
  unconfined start one under `/tmp`), builds the command with `argv_for(endpoint)`, starts it listening there and
  waits until it accepts, and hands the owner the connection it made then
  (`started.connection`, a connected socket: brig's verified one for a jail; the owner opens its
  streams over it and never dials `started.endpoint`, which is for argv alone, because a jailed
  program can swap its socket for a link; `stop` closes it and removes the directory). The owner chooses nothing: a mechanism that has the jail reserve the channel (brig's
  `reserve_channels`) changes no owner. Each watcher (`on_start(watch) -> remover`) is told of it after, so the status bar's jail
  field (`tui:grades`) follows a Python process started again in place. What one start is stays
  with it (`started.report()`, `notice()`, `reads()`, `writes()`): the Python process and the
  extensions process each start from a command of their own. `report()` and `notice()` are the
  last start's (before any, the mechanism's grades and "").
- **Each owner stops its own program.** A row that starts something registers its stop
  (`on_release(stop) -> remover`, `stop: async () -> str`): the python row its Python process,
  the extensions row the extensions process. `release()` asks each in turn, then has the mechanism let go of
  what it holds on the host (nothing now: brig removes the placeholders it made when the last jail
  holding them ends, below), and joins what each said
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
`Nothing runs in the runner, and it holds nothing.`. It says something only when a program still runs.

`approval.py` is the rule, written once: `is_confined(report)` (the runner enforces `fs_write`
and `network`), and `Approval`, the `approval` value over the runner: `confined` (read from its
`report()` each time) and `unasked(question)` (it is the memory tool, `runs` `"memory"`, whatever
the runner confines; or it runs in the runner, `runs` `"jail"` when the question says nothing, or is
bh-02's own tool bounded to the session's jail and bh-02's own state, `runs` `"harness"`, and the
runner confines it). Asking is not the rule's: the loop puts each call the rule does not let run
unasked to the person (`{"name", "input", "runs", "title", "lines", ...}`: a call to a tool that
runs in bh-02's own process, `runs = "host"`, is put to the person however confined the runner; a
`"harness"` one only when the runner does not confine), and the extensions row each extension it
loads, each through `output.confirm`; the python row's `confined`, what the model is told, is the
rule's.

**The memory tool runs outside the jail and is never asked.** The memory plugin's `memory` tool
(`runs` `"memory"`) runs in bh-02's own process, not in the jail, and writes files there. That is
on purpose, and safe for one reason: the code that writes is bh-02's, not the model's, and
it writes only beneath `host.auto_memory`, the project's auto memory directory, through no link
(`host_paths.write_beneath`: a link or a second name the model planted there is refused, never
followed), and the jailed model can already write that directory without being asked (the jail's
`writes`, below), so asking would protect nothing, jailed or under `--no-jail`. It is also why
the tool is not run in the jail: a jailed program per save would be a whole process for a small
file write. Every other call that runs in bh-02's own process (`"host"`) is still asked, and a
tool takes the value only in a layer's row (an extension's tool is always `"jail"`). The rule
does not check that a tool keeps to that directory; keeping to it is the tool's and
`host_paths`' to prove, so a new tool never gets the value for convenience.
Its row depends on `runner` alone, so `/clear` (a new Python process) and a new ui leave it up,
and the rows that depend on it. It is a capability, bound by one row: two rows' answers could
not be combined, so it is not a broker. It runs in bh-02's own process, so only a layer
replaces it; an extension has no way to bind or reach it. It answers about code bh-02 is about
to hand to the runner, not about each effect a component yields (that is cordis's planned
policy seam, not this).

`runner:confined`'s mechanism, `BrigJail`, compiles a jail for each start from one policy.
The modules:
- `policy.py`: `Policy`, bh-02's own frozen intent (writable roots, write denies, read model and
  readable roots, masks, the environment allowlist and the variables set), and the pure functions
  that make it (`spec_for`, `allowlisted`, `link_directories`, `readable_roots`, `told_reads`,
  `git_author`). No brig.
- `mounts.py`: what a Linux jail does with mounts, as decisions on a `Policy` (`mountable`, `tripwired`,
  the notice). No brig. `facts.py`: what the host is (one walk of the links on the way
  to the interpreter, the git identity). No brig.
- `brig_spec.py`: `to_brig`, the one function from a `Policy` to brig's `FsPolicy`, `EnvPolicy`
  and `Stdio` (and the candidate environment), and `report_of`, brig's report as the runner's.
- `jail.py`: the shell (`BrigJail`, the launch, `_Jailed`). With `brig_spec.py`, the only modules
  that import brig, and they import only what `brig` exports.

`spec_for` is the policy, as a pure function:

- **writes**: the project root, a scratch directory of the jail's own (`TMPDIR`), and the
  project's auto memory directory (`host.auto_memory`, outside the project: the model keeps its
  memories there across sessions, and only the memory rows read it, through no link), except
  the composition's layer files (`host.paths`), every path the host imports code from that sits
  under a writable root (`sys.path` entries, the interpreter's prefix), the
  self-modification list (`SELF_MODIFYING`: `.git/hooks`, `.git/config`, `.claude`, shell rc files, editor
  settings, ...: what can run code outside the jail later) minus the paths a write grant names
  exactly, and `deny`. The project's guidance files (`GUIDANCE`: CLAUDE.md, AGENTS.md), which editing
  is ordinary work, are not on the list. There is no `allow`: a layer naming it fails at boot with the
  loader's error (`invalid config for BrigConfig`), and a self-modifying path is writable only by a
  write grant on that exact path (decision-0012 item 10; a grant on its parent lifts nothing). Nor
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
  package's own directory), which would leave the project read-only.
  Nor the interpreter bh-02 itself runs on, where its file lies under a writable root (a project
  opened at the home directory holds the uv-managed Python): the next bh-02 start on the host
  would run what an input wrote there, outside any jail. `host` holds the standard library and
  the venv's prefix, and with no venv the whole prefix; in a venv layout the base's binary is on
  neither, so `BrigJail` hands `spec_for` the files that `sys.executable` and
  `<sys.base_prefix>/bin/python3` lead to, every link followed, and one strictly under a writable
  root is denied (as for `host`: a root itself would leave the project read-only). The files, not
  the names that lead to them: bubblewrap's mount on a link lands on the file, so the file is what
  holds (measured: a write to the file and one through the link both fail, while the link's own
  entry can be renamed), and a deny on a link that dangles in the jail fails the launch
  (`test_the_interpreter_bh_02_runs_on_is_denied_where_an_input_could_write_it`, the compile of a
  planted venv layout, and in a real jail
  `test_a_linux_jail_refuses_an_input_that_writes_the_interpreter_bh_02_runs_on`: a write, a write
  through the link, a rename and a removal are refused). A mount on the file holds the file, not
  the links that lead to it, and **the directory that holds each link on the way to it is denied
  too** (the owner's rule, TASK-0127). The entry of a link in a writable directory can be renamed,
  and a Python of the input's own planted at its name: uv's `cpython-3.15-linux-x86_64-gnu`, the
  link to the versioned directory that a venv's `python` goes through, lies in
  `~/.local/share/uv/python`, and the next `uv run` on the host would execute what was planted
  there. So for every link from `sys.executable` (and from `<sys.base_prefix>/bin/python3`) to the
  interpreter's file, the directory that holds the link is denied whenever it lies strictly under
  a root the jail may write (generic: uv, pyenv, a venv's own `bin`). The decision is a pure
  function beside `spec_for`, `link_directories(links, writable)`, which takes the chain as the
  host found it; the shell, `facts.links_on_the_way`, only walks it, one path component at a time, so a
  link is found in the directory that physically holds it (a link reached through a link to a
  directory is that directory's). What it denies in the common layouts:
  - bh-02 run from its own checkout (`uv run bh-02`), the project the checkout: its `.venv/bin`
    holds the `python` link; it is bh-02's own code, which `sys.prefix` denied already, and uv's
    Python directory is not under the checkout. Nothing is new.
  - `uv tool install`, the project elsewhere: nothing, none of the chain is under it (the tool's
    venv under `~/.local/share/uv/tools` is denied as `sys.prefix` where a project reaches it).
  - A project that is the home directory (the checkout's or the tool's venv, and uv's Python,
    all under it): uv's Python directory, `~/.local/share/uv/python`, read-only to inputs (the
    versioned directory with it; a mount lands on the same files, so the interpreter still runs
    there), and the venv's `bin` where the venv is bh-02's own; everything else in the home
    directory stays writable (measured in a real jail: the worker ran on the uv Python, a file
    created in that directory failed with `Read-only file system`, one beside it was written).
  - A plain project with a `.venv` of its own on some other Python: not on the way from bh-02's
    interpreter to its file, so not denied; an input may still install into that venv or replace
    its links.

  When the directory that holds a link is a writable root itself (the project is a venv's `bin`,
  or uv's Python directory), it is not denied, as `host`, `trusted` and `code` above are not: a
  root that is also a deny is a read-only project, and every write of the session would fail. The
  person opened the project there to let the model write it; what stays is that an input can rename
  that link, in that one directory. A directory below the root that holds a link is denied as any.
  The tests: `test_the_directory_of_each_link_on_the_way_to_the_interpreter_is_denied_where_it_is_writable`
  (the decision, the root and the roots it leaves out), the compile of a planted uv layout
  (`test_a_jail_denies_the_directory_of_each_link_from_the_interpreter_bh_02_runs_on_to_its_file`,
  with a project's own venv left alone) and, in a real jail,
  `test_a_linux_jail_refuses_an_input_that_changes_a_link_on_the_way_to_the_interpreter_bh_02_runs_on`
  (every link renamed, removed or replaced is refused).

  A started program's `writes()` names the roots its inputs may write (the
  python row reads nothing on the host whose way passes through one);
- **grants store**: `host.grants` (`$XDG_STATE_HOME/bh-02/projects/<project>/grants/`) holds
  `grants.toml`, the always-grants of the project (decision-0012: `grants.py` is the values, their
  validation and the never-grantable floor, `store.py` the file, read and written only through
  `host_paths` at 0600). `spec_for` masks the directory from reads and, where a writable root holds
  it (bh-02 run from the home directory), denies writing it; the command line makes it at 0700
  before any jail starts, so brig holds no placeholder there.
- **reads**: everything except the credential paths under `$HOME` (`CREDENTIALS`: `.ssh`, `.aws`, ...) and
  what `host` names as `secrets`: the sessions' state directories, this run's
  (`$XDG_STATE_HOME/bh-02/sessions`) and the default one (`~/.local/state/bh-02/sessions`),
  where each session's `claude/` holds its Claude Code child's config and messaging peer token.
  A third, of a run with another `XDG_STATE_HOME`, is not known to this one and is not hidden;
- **network**: none, enforced: every start passes brig an `EgressPolicy` (empty until something is
  granted), so the jail has loopback only, a proxy on the host is its one route out and it
  refuses everything, and a program that ignores the proxy settings reaches nothing (the jail has
  no interface). brig sets the proxy variables itself, so a `runner.toml` or layer `env` naming
  `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` or `NO_PROXY` (either case) is refused (`allowlist.effective`).
  The program's own socket is the one way in or out otherwise. It is a channel brig
  reserves (`reserve_channels`, one named `program`), its endpoint is handed to the owner's command
  (`argv_for`) before anything starts, and the runner waits for it with brig's verified check
  (`await_channel_ready`: the listener must be in the jail's own PID namespace). brig binds the
  channel directory into the jail and removes it at the jail's end; no jail sees another's. The
  runner starts two programs, each with a jail of its own made from this one policy: the Python
  process (`python:tool`), and the extensions process (`extensions:process`), where the model's own
  plugins run;
- **env**: scrubbed to `env`. The person's standing list is `~/.config/bh-02/runner.toml`
  (`$XDG_CONFIG_HOME/bh-02/runner.toml`), `env = ["NAME", ...]` and nothing else (decision-0010;
  `allowlist.py`). The row reads it when it starts (`/restart runner` after an edit), through
  `host_paths.passes` as the models file is: a file in the project or reached through a link into it
  is not read and the jail's first `notice()` says where to put it (a narrower list, never a wider);
  one that can't be read or is malformed stops the row with a message saying what to fix. A layer's
  `config` that sets `env` replaces the file's names (and the baseline: a layer's list is the
  whole list) and the `notice()` says so; one that omits it takes baseline plus the file. The row
  refuses a list (the file's or the layer's) that names a variable an endpoint's
  `key = { env = ... }` reads, naming the variable, the endpoint and the list: at startup, and again
  at each program it starts, since a layer can point the model row at another models file or add an
  endpoint without the runner row reloading. The endpoints are every one the model row can reach (its
  models file's and its `extra`), asked of the `models` value (`key_envs()`, read fresh; it
  depends on the loader alone, so the runner gains no reload from it); a models file in the project adds
  nothing (its `extra` still counts). `--no-jail` (`runner:unconfined`) never reads the file. The model cannot
  write it: `host.trusted` is not writable in the jail.

Without the jail (`runner:unconfined`, `--no-jail`) none of this holds but the scrub of
`CLAUDE*` and `ANTHROPIC_*` (and tmux's): every axis is `unenforced`, so the `approval` rule asks
about every input and extension, its code shown, and one the person approves runs with their
permissions. **Every other variable of bh-02's environment reaches the program, a model's provider
key (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`) among them**, so the model's code can read it
(`tests/test_runner_tmux.py` shows it passed, and the Claude token not). It could also read the
environment of any process the person owns (the Claude Code child's, which holds the token), or
rewrite bh-02's config directory or its own code.

One policy, one platform for now. **Linux**: brig's bubblewrap jail, which reads by allowlist.
`allowlisted` names what is readable: `SYSTEM_READABLE` (`/usr`, `/bin`, `/sbin`, `/lib`, `/lib64`,
`/etc`, those that exist), the interpreter (`sys.base_prefix`, `sys.prefix`, and every symlinked
directory on the way to the executable: a uv venv's `python` goes through `cpython-3.15-...`; brig
runs its supervisor, the jail's PID 1, under bh-02's own interpreter and refuses a policy that does
not mount it, `PolicyInterpreterUnreachable`), the directory of each absolute path the command
names (the program's own `worker.py`), bh-02's own code (`host.code`, read-only), and the roots it
may write. Everything else is not in the jail, the home directory included. A path outside every
root is not read-only there but absent: a write to it lands in the jail's own scratch and is gone
with it, and a masked directory is an empty one. **darwin**: brig has no jail type for it yet, so
`runner:confined` refuses to start a program there, saying so and naming `runner:unconfined`; before any start its report is `unenforced` throughout (so
`approval` never says confined) and its notice says the same (`tui:grades` shows it as a note)
(TASK-0176.05 is the seatbelt jail); this is what keeps the swap from landing before it does.

**Placeholders.** bubblewrap holds a write-denied or masked path that doesn't exist with an empty
directory, which brig makes on the host (`.envrc/`, `.vscode/`, `.idea/`, `.claude/`, and in a
project that is not a repository `.git/`, held whole: `mountable` maps a deny under an absent parent
to that parent, or to the `.git` file of a worktree) and removes when the last jail holding it ends;
brig records them under its state directory (`BRIG_HOME`, `~/.brig`) with a lock, marks each as its
own, and a jail that starts after a crashed one removes what it left. bh-02 keeps none of that. So
you can't create an `.envrc` while a jail runs; `/release` stops what each owner runs, and with
it the hold, until the next input.

**The jail ends with bh-02.** bubblewrap runs with `--die-with-parent`: when bh-02 ends, however
it ends, the jail's namespace goes with it, a program in a session of its own included.

**The tripwire (Linux).** bubblewrap holds each denied or masked path with a mount on the host's
directory entry, and the kernel detaches that mount inside the jail when the host replaces the
entry (a `git config` renames a new `.git/config` over the old one; editors save by rename), renames
it away or removes it. From then on an input could write or read the path. bh-02 watches every path
the jail holds,
read off the mounts brig made (`Jail.mounts`, `mounts.tripwired`, `tripwire.Tripwire`: inotify,
armed once brig has made the jail): every read-only mount beneath a writable one, and every pin (a
directory brig binds writable over itself between a root and a deny, so the command can't rename
it; the host renaming one takes the mounts beneath it)
and, at the first such change, ends the jail with brig's `destroy_jail`; the next input's jail holds
the path again and the input says why (`ended()`). A program already running can get one write or
read in before it ends, so brig grades `fs_write` `best_effort` while the jail holds such a path
(and `fs_read` when it masks one that is there), and `approval` counts best-effort writes as
confined only with bh-02's own report axis `host_undo: tripwired` (`jail.HOST_UNDO`), which the
confined runner sets on each start that arms the tripwire and brig does not grade (`is_confined`).
`notice()` names the secrets held. A host change in the moments between bubblewrap mounting a path and the watch
being set is not seen.

**The grades** are brig's: each start's `report()` is `report_of(jail.report)` (`fs_read`,
`fs_write`, `network`, `env`, `channel_exclusivity`, lower case) and bh-02's `host_undo`
(`tripwired`) and `egress` (`proxied`: the start passed an egress policy, `jail.EGRESS`).
brig grades `network` `best_effort` whenever the jail sees any host root, and `violated` where it
sees a place hosts keep sockets; `approval` counts `best_effort` as confined only with
`egress: proxied`, and `violated` never. So a root (the project, a write root, the scratch or memory
directory) at or under `/tmp`, `/var/tmp`, `/run`, `/var/run`, `/dev/shm` or `$XDG_RUNTIME_DIR` is
refused at start (`policy.socket_refusal`), with why and what to do. Before anything starts, `report()` is `PLANNED`, no stronger than any start can
earn. `channel_exclusivity` is `violated` when the jail can write a host path that is not a declared
channel, which brig counts any writable root as (so for any project), or can see where the host
keeps sockets (`/run`, `/tmp` and the like); the status bar shows it `!`.

**Known gap**: darwin has no jail (above).

## Grants in the policy

`spec_for` and `brig_spec.to_brig` take `grants.Grants`, a frozen collection of `Grant`s (decision-0012
items 1, 5 and 10). The floor comes first: `policy.admitted` resolves each path grant (`Path.resolve`,
and the floor's paths too, so a link to a floor path is refused as what it leads to) and asks
`grants.refusal` with the floor `spec_for` builds from its own arguments (`secrets`, `store`, the
credentials under `home`, `layers`, `code`, `trusted`, `interpreters`, the directories of `links`, and
`key_envs`). A refused grant is never used: `Policy.refused` holds the words, and a read grant for a
path that is not there is left out the same way.

| Grant | Becomes |
|---|---|
| `read` | a root in `Policy.readable` (kept by `allowlisted`; the policy's masks inside it are still carved out) |
| `write` | a root in `Policy.writable`; a directory beyond the project also gets the self-modification list and the `trusted` and `code` denies a root has; one on exactly a self-modifying path lifts that deny |
| `env` | a name in `Policy.env_allow` |
| `net` | a `Destination` in the `EgressPolicy` of `Brigged.egress`, which `create_bwrap_jail` is given; empty when none is granted, because every start enforces egress |

Where a refusal is reported: for now in the start's `notice()` (`BrigJail` appends `Policy.refused`),
since nothing asks yet; the broker that asks (TASK-0181.05) refuses a request at the moment it is
made, with the same `grants.refusal` words, before the person is asked.

Where the grants come from: `BrigJail` asks its `grants` (the broker, below) for `granted()` at each
start. A store that is wrong (`store.Refused`) grants nothing and does not fail the start: the start's
`notice()` carries the words (`Broker.problem()`). `BrigJail(egress_hosts=...)` is brig's table the
egress proxy resolves names from instead of the host's resolver; only tests pass it.

## The grants broker

`broker.py`'s `Broker` is the `grants` value, a plain value (no cordis) that `runner:grants` binds once
(decision-0012 items 2 and 7). It holds:

- **the project's always-grants**, in the store, read fresh at each `granted()` off the event loop, so an
  `always` or a revoke from another process (or `bh-02 grants revoke`) counts at the next start;
- **the session's answers**: `once` (applied while it was asked for with `ask`, or while some row holds a
  `need` for it, and remembered after the row leaves so a remounted row is not asked again) and `no`
  (remembered, not asked again).

Rows ask with `need(request)` (acquired, so it leaves with the row), anything else with `await ask(request)`.
Questions go one at a time through the prompt `serve` was given, and two for one grant are one question; with
no prompt served `ask` answers `no`, and held needs are asked the moment one is. A prompt that returns None
(Ctrl-C) records nothing. An `always` is written by reading the store fresh and writing it whole
(`store.write`); a store that is refused is never written over, the grant is then kept for the session and
`problem()` says why. Two processes writing `grants.toml` can lose an update (the next `always` reads again).
Whether a request is already inside the current policy (decision-0012 item 5's `standing`) is TASK-0181.08's:
here `standing` means already granted.

Why `approval` depends on neither `grants` nor a requester: what reloads is what depends. The broker row
depends on `host`, which the shell pins, so it never reloads, and a grant changes the value's contents and not
its binding; `runner:confined` depends on it and reads `granted()` at each start. `approval` depends on
`runner` alone, so a grant, an `always`, a requester's remount and a requester leaving all leave the rule
up (`test_runner_grants_wiring.py` watches the loader for it).

### The prompt

`runner:grant_prompt` serves the broker (`Broker.serve`) a prompt that asks the person through
`output.choose`. The words are one pure function, `prompting.question`: a title, four lines in
order (what is asked for; who asks, and why, in the asker's words; when it applies; what it does to
the grades), a `warning` ('' for none) and the choices `o` once (for this session), `a` always (for
this project) and `n` no, Escape answering no. "When it applies" is `prompting.applies`, the one
place that says what this build does: a path or environment grant from the program's next start
(`/clear` starts the Python process again), a destination likewise until egress goes live. A `net`
grant adds a destination and leaves the network proxied; `env` lets the variable's value reach the
program; `read` and `write` change no grade, unless the path is, holds or lies under a place hosts
keep sockets (`policy.SOCKET_PLACES`, the ones a root is refused under, and `$XDG_RUNTIME_DIR`): then
the warning says the jail's network would be violated and approval would stop counting it as
confined. A `write` on a path `SELF_MODIFYING` names (a git hook, `.envrc`, a shell rc file) warns that
it can run code outside the jail later. Ctrl-C answers '' and the broker records nothing, so the
question is asked again next time; the answer is kept as decided (once for the session, always in the
store, no for the session). An aside tells the model, on the next call's result, each answer decided
since the last call (never one for a grant that was `standing`, which is not asked).

`approval` and `runner` do not reload with `grant-prompt`: it depends on `grants`, `output`, `asides`
and `commands`, and neither of them depends on it (`test_runner_grants_wiring.py` watches the loader
for it). When the prompt's row reloads or leaves, its question under way is withdrawn as a no for its
asker, and the next prompt asks what rows still need.

`/grants` (`runner:grant_prompt`) lists one line each (id, kind, target, answer and scope, who asked and
why) and `/grants revoke ID` takes one back. `bh-02 grants` and `bh-02 grants revoke ID` do the same outside a
session: the command line boots the `host` and `grants` rows alone, by name, and reads the value through a
Protocol of its own (`bh_02.granting`), since the app imports no plugin. An id is the first 8 hex digits of the
SHA-256 of the grant's text, so the two agree. A sub-agent's realm reads `grants` from outside (its rows
ask the one broker).
