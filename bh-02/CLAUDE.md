# bh-02 and its plugins

bh-02 is the coding harness: a shell (`app/`) over a family of cordis plugins (`plugins/`, one
member each). [`CONTRACTS.md`](CONTRACTS.md) is the keys a layer wires, the shapes bound under
them and what each promises, for this family only: the one thing the plugins share, changed when
a shape changes. [`app/README.md`](app/README.md) is how the app runs and the map of its
compositions, rows and plugins; each plugin's `README.md` is its rows and why they work as they
do; [`GLOSSARY.md`](GLOSSARY.md) is every term a bh-02 user meets, one line each, cordis's then
bh-02's (a new term goes there, or is plain English); `docs/bh-02/` is the docs site.

## Adding a plugin

Copy the shape of `plugins/memory-cordis-plugin`: a `pyproject.toml` with
`[project.entry-points."cordis.plugins"] <name> = "<name>_cordis_plugin"` and workspace sources
for the libraries it uses, `src/<name>_cordis_plugin/` with a `wiring.py` and `py.typed`, a
`README.md`, a `tests/` dir. The workspace's member list, testpaths, mypy files, ruff `src` and
the gate's units are globs over the directories, so nothing else needs registering. Two things
are judgement and stay by hand in the root `pyproject.toml`: purity-budget entries
(`no-impure-functions`) and any `over-exposed-module-symbol` allow entries beyond
`*_cordis_plugin.wiring:*`. A plugin the shipped layer names also goes in the app's own
`dependencies` and `[tool.uv.sources]` (`app/pyproject.toml`): `uv sync --all-packages` installs
every member either way, but `uv tool install ./bh-02/app` installs only what the app depends on
(`test_booting.py` checks every plugin the layer names is there). Then `uv sync --all-packages`:
entry points are read from installed metadata, and a stale one shows up as an unresolved row,
not an import error.

## How the family stays apart

No package imports another (`plugin-layering`: the units are every package under a gated `src/`;
`cordis`, `cordis_helpers` and `host_paths` are what all may import). They agree by name and shape:
- **A consumer declares what it needs** as a `runtime_checkable` Protocol of its own on the
  parameter (`converse(*, loop: Loop)`), which cordis checks the bound value against before it
  runs: two consumers of one key, two contracts (the loop's `Tools`, `/compact`'s `Offered`).
- **A provider just has the methods** (`ClaudeCodeModel.complete`, `OpenAIModel.complete`,
  `Kernel.run`), nothing to import. Data crosses as dicts, typed by its reader (`TypedDict`).
- **Errors are a shape**: a recoverable `loop` failure is any exception with `kind` and `message`
  (`Recoverable` in `chat` and the shell's bootstrap). Anything else is a bug.
- **Two halves per plugin**: the value (`loop.py`, `client.py`, `jail.py`, `named.py`,
  `python.py`) is a plain library that doesn't import cordis (`cordis-in-wiring-only`);
  `wiring.py` is the components, which `bind` a value or `acquire` a registration.
- **Brokers stay commutative** (`commands`, `frame`, `system`, `tools`, `asides`, `access`, the
  paper's section 6.2): one row binds the key; each contributor `acquire`s an entry of its own,
  which leaves with it, never a place in an ordered chain.
- **What every package must compute alike is a library function, not a key**: in `host_paths`,
  where config and state are (`config_home`, `state_home`), every place reading a file goes
  through (`walked`, `passes`), and the opener beneath a root through no link (`read_beneath`,
  `directory_beneath`). A copy per plugin that drifted would be a hole, and a key would add
  reloads to rows that must not reload (the python row, `system`): the walk is code, not a value.
- **Fakes come from a package's own `testing` module** (`chat_cordis_plugin.testing`,
  `bh_02.testing`), never from another package's tests.

## The running harness

What to keep when changing it; the detail is where each line points.
- **Layers are the composition**: `app/src/bh_02/bh-02.toml`, then the session's `session.toml`
  (every per-run choice: a resume boots with it again) and `--patch`, each a patch (an override's
  `config` replaces the row's), then the shell's pinned `host`, `session` and `shell`. The loader
  watches every layer file, the only durable way the shape changes (`restart(row)` can't outlive
  the session). The shell follows the chat row's `done` across its restart, so a session survives
  `/model` (`app/README.md`).
- **What reloads is what depends** (cordis's rule), so what must outlive a reload is a row that
  depends on little: the conversation in `transcript`, the reading in flight in `executor`, held
  output in `commands`, queued restarts in `jobs`, the rule in `approval`. Check a new dependency
  against what it would reload ([rows and layers](../docs/bh-02/how-it-works/rows-and-layers.md)).
- **The loop knows no tool by name**: a tool is a `tools` registration (CodeAct's `python` is the
  default, not a requirement), and tells the model of itself in a `system` section, never in its
  spec's description.
- **What a conversation began with is sent unchanged**, the prompt and the tool list: a change is
  told as an aside, the date on the person's message
  ([why](../docs/bh-02/how-it-works/prompt-and-asides.md#why-the-prompt-stays-fixed-for-a-conversation)).
- **Nothing blocks the event loop the TUI shares**: the prompt is read and `asides` asked on
  `executor`, one call at a time, and must not need the event loop (agent plugin's README).
- **Approval is one rule in one row** (`runner:approval`): its askers put what it doesn't let run
  to the person themselves and keep no copy of it; only a layer replaces it (runner plugin).
- **No command restarts rows in the chat row's task**: it queues them in `jobs`, and the chat row
  reads its next line only once `jobs.settled()`.
- **Only a layer's rows act in bh-02's process**: only they add to `asides` or claim a line prefix
  (`!` runs in the person's shell). An extension gets four keys that only add, never one that
  replaces or reaches the composition (the loader, `runner`, `model`) (extensions plugin).
- **Never read on the host a file the model can write, or follow a link it could make, and hand
  its text to the model**: read it through `host_paths`, or in the jail.
- **What the host trusts, the jail keeps from the model**: a file the host reads and trusts, or
  code it imports, is in `host` and `runner:confined` denies writing it; a secret is in
  `host.secrets`. The policy is one pure function, `spec_for`
  ([runner plugin's README](plugins/runner-cordis-plugin/README.md)).
- **Each owner stops its own program** on `/release`; the runner never stops a row's program.
- **Claude Code only carries steps**: no built-in tool, settings, CLAUDE.md or compaction; bh-02's
  tools are only declared to it, and any end but tools or an answer is interrupted, so the loop
  decides. The SDK is pinned for the internals it leans on (models plugin).
- **The app owns the terminal**: no child inherits fd 2, `--trace` takes a file, and the shell
  speaks once the app has exited. `confirm()` runs in cordis's coroutines, not Textual workers,
  so the approval modal is `push_screen` with a callback (tui plugin).
- **Test a real launch**: `app/tests/test_real_launch.py` starts the installed script in a pty
  with a fake model from `bh_02.testing`, since `run_test()` misses what only a real launch does.
  The Linux jail's tests skip on darwin; `scripts/linux-jail-check` runs them with bubblewrap.

## The credential

`CLAUDE_CODE_OAUTH_TOKEN`, in the git-ignored `local.env`, goes only from the model row to the
Claude Code CLI, never to a program the runner starts. Never set or read `ANTHROPIC_API_KEY`;
never print, log or commit the token ([the rules](plugins/models-cordis-plugin/README.md#the-credential)).

## Gate rules that are about this family

In the root gate (`pypeeker_rules/apps.py`, options in the root `pyproject.toml`):
- `terminal-io`, `print-input`: only the modules their `allowed` lists name touch the terminal (so
  the interface stays swappable: what the user sees goes through the ui's `output`); names in
  `sys` that are not terminal I/O (`argv`, `executable`, `path`) may be imported anywhere, and
  `python_cordis_plugin.worker` is exempt from `print-input` (its stdout is what an input printed).
- `cordis-in-wiring-only`: `*.wiring`, plus the `shell` list (the extensions process's
  `extensions_cordis_plugin.worker`, a cordis runtime of its own, among them).
- `worker-stdlib-only`: the Python process imports the standard library only.
- `brig-one-adapter`: only `runner_cordis_plugin` imports brig.
