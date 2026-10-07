# bh-02 and its plugins

bh-02 is the coding harness: a shell (the app) over a family of cordis plugins in `plugins/`.
`CONTRACTS.md` here is the keys a layer wires and the shapes of the values bound under them, for
this family only. Change it when a shape changes; it is the only thing the plugins share.
`app/README.md` is how the app runs and the map of the compositions, the rows and the plugins.
[`GLOSSARY.md`](GLOSSARY.md) is every term a bh-02 user meets, one line each: cordis's words as
cordis defines them, then bh-02's. A new term in these docs goes there, or is plain English.

## Adding a plugin

Copy the shape of `plugins/context-cordis-plugin`: a `pyproject.toml` with
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

No package imports another (`plugin-layering`; the units are every package under a gated `src/`,
the libraries `cordis` and `cordis_helpers` are what all may import). Agreement is by name and
shape, in `CONTRACTS.md`:

- **A consumer declares what it needs** as a `runtime_checkable` Protocol of its own, on the
  parameter: `session(*, loop: Loop, ...)` keys on `"loop"` and cordis checks the bound value
  against `chat`'s `Loop` before `session` runs. The loop's `Python` asks the `kernel` for
  `spec`, `instructions`, `run` and `touched`; `tui:status`'s `Confinement` asks the same
  value for `confined`, `report` and `notice`. Two consumers, two contracts.
- **A provider just has the methods.** `ClaudeCodeModel.complete`, `OpenAIModel.complete`, `Kernel.run`, nothing to
  import. Data crosses as dicts (`{"type": "text", ...}`, a tool spec, a message); a package
  types the part it reads with a `TypedDict` or `Mapping`.
- **Errors are a shape too**: a recoverable `loop` failure is any exception with `kind` and
  `message` (`Recoverable` in `chat` and in the shell's bootstrap). Anything else is a bug.
- **Two halves per plugin**: the value (`loop.py`, `client.py`, `jail.py`, `named.py`,
  `python.py`) is a plain library that must not import cordis
  (`cordis-in-wiring-only`); `wiring.py` is the components, which `bind` a value or `acquire` a
  registration.
- A plugin's tests use fakes from a package's own `testing` module (`chat_cordis_plugin.testing`, `bh_02.testing`), never another package's tests.

**The model has one tool, and it carries code.** The kernel is the tool: `kernel:kernel` binds
`kernel`, a persistent Python namespace whose `spec` is `python(code)`, and `agent:loop` offers
that one spec through the provider's standard tool calling and runs every call as an input to it
(`kernel.run`). To the model the kernel is a Python REPL of its own that persists: the namespace
holds what its inputs put there, and nothing an input does reaches back into bh-02 but the
extensions it writes (below); an input reads and writes files with `open`/`pathlib` and runs
programs with `subprocess`, and the jail decides what it may touch.
Replacing a binding reloads every dependent (cordis's rule, and why history lives in
`transcript`, a row of its own).

**The broker pattern is the paper's (section 6.2).** `commands` (slash commands), `frame`
(the app's frame), `system` (its sections) and `memory` (what the model is told with an input's
result) are brokers: one row binds the key, contributors depend on it and `acquire` a
registration whose return value is its remover, so adding or retiring a command reloads
nothing. Keep registrations commutative: each takes its own entry, never an ordered chain.

## The running harness

The shell's base layer is the whole harness (CodeAct always); each later file (the session's
own `session.toml`, `--patch`) is a patch over it. The loader watches every layer
file: editing one, by hand or by `/model`, reshapes the running composition (a jailed input
can't write one: the jail denies them, and on Linux a save by rename ends the jail so the next
input's holds the new file). The layer files are the only way the composition's
*shape* changes durably; the loader's `restart(row)` (`/restart`, `/clear`) gives a row a fresh
fiber, and can't outlive the session. The shell pins three rows of its own after every layer
(`disabled = false`, so no layer can remove them): `layers`, `sessions` (the running session,
whose id the status bar shows) and `harness`.
A session is a directory under `$XDG_STATE_HOME/bh-02/sessions/` whose `session.toml` carries
every per-run choice, so a resume is booting with it again. An
override's `config` replaces the row's, it doesn't merge. The bootstrap follows the chat row's
`done` across a restart of the chat row, so a session survives `/model`.

**What the model sees and how a turn looks.** `loop.reply` yields events (text, thinking,
tool_call, tool_result, usage, stop, note). `approval.approve` decides whether the model's code
runs (unjailed, by asking through `output.confirm`);
`input.interrupted()` is Ctrl-C, which `chat:session` races against the reply. `system`
(`context:project`) is organised as Claude Code's is: who the model is (the model in bh-02, not
Claude Code) and what bh-02 is made of, then the project context: the working directory and
branch, what the context files say, and the sections rows add (`system.add`: the extensions
row's is how to extend bh-02 and the part of cordis that takes). A context file is TOML, a list
of `[[section]]`s, each `files` (patterns) and `function` (a full module path given the files
that match, returning text): bh-02's own (`context_cordis_plugin/context.toml`: the guidance
files, AGENTS.md and CLAUDE.md, yours and the project's, and rule files, each read by a function
in `context_cordis_plugin.sections`), then yours (`$XDG_CONFIG_HOME/bh-02/context.toml`, else
`~/.config/bh-02/context.toml`), then the project's
`.bh-02/context.toml`, which the model can write and so may name only bh-02's own functions and
non-hidden files in the project; nothing is read through any section that the jail keeps from the
model (a link out of the project, a `local.env`). The loop follows it with `kernel.instructions()`: that `python` is the
CodeAct tool bh-02 ships, a Python REPL of the model's own that persists for this run of bh-02,
and how to use it (work in Python, not through a shell, with an example input; build up state;
capture a program's output, which otherwise never reaches the model; give it a timeout; it is
plain Python, not IPython), and under a Linux jail what its code can read (`kernel.reads()`:
the system, the interpreter, the project; no home directory). After each input, the loop asks
`memory` (`agent:memory`, a broker) what to tell the model with its result: each function rows
add there gets the input's code, its
result and `kernel.touched()` (the project files Python in the input opened, heard by an audit
hook in the worker; a shell command's own reads are not heard) and may add a note, never change
the result. `kernel:shell_hints` tells the first input that runs `cat`, `sed`, `ls` or the like
through a shell, once for each kind of work, how Python does it (`shell_note`);
`context:on_touch` gives the context files' `on_touch` sections, so a subdirectory's AGENTS.md
or CLAUDE.md, or a rule for some files, arrives whole with the first input that opens a file it
covers (Claude Code's on-demand loading); it has no config of its own and asks the `system`
value (`system.touched(paths)`), so the context files, and the caches of what was read and
searched, are `context:project`'s alone. Both depend on `transcript`, so `/clear` starts them
afresh, and read its `messages` once, at their first input, so a resumed session is not told a
note its transcript holds after a result; only layer rows add to `memory`, since its functions
run in bh-02's process. The loop reads the prompt before each message the model reads but sends
the one the conversation began with (the transcript's first `system` entry): a prompt that changes (an extension loaded, a branch
switched, CLAUDE.md edited) is told as a note on that message (`prompt.changes`), because a
model server reuses its work on a conversation only up to the first token that differs, and a
changed start costs a local model minutes of prompt processing (it looks frozen) and Claude
a restart of Claude Code and its cache. The transcript keeps a change as the edits from the
reading before it (`prompt.edits`), not a whole copy, and the loop applies them in turn to
know what it last told (`prompt.latest`); a transcript that kept whole copies reads the same.
The date is not in the prompt, or every midnight would be such a change: the loop tells it
first on the person's message, the first of a conversation and of each day
(`(Today's date: ...)`, the entry's `today` field saying which it told, so a resume does not
tell it again and `/clear` does). So the prompt reads the same from day to day,
and a local model server that keeps its prompt cache can reuse a new session's start. The
prompt is read, and `memory` asked, in a thread of the loop's own, never on the event loop the
TUI shares: a section function may read many files and search the project, and must not need the
event loop. One runs at a time: nothing stops one part-way, so a reading a stopped reply left
running is waited for before the next begins (Ctrl-C after Ctrl-C leaves at most one in flight),
and the thread is a daemon's, not the default executor's, which `asyncio.run` and the
interpreter join as they end, so one left running never holds bh-02 open. The claude-code provider
adds a note that Claude Code's own opening line and its `mcp__bh__` tool names don't mean the
model is in Claude Code.
The ui `observe`s lifecycle events (cordis's seventh effect) to show rows reloading.
`agent:loop` classifies each turn (`stops.classify`, after ../harness/ARCHITECTURE.MD) and replays
a provider's message as it came.

**The TUI.** `tui:app` runs a Textual app on cordis's own event loop and binds `input`, `output`
and `frame` (the app's frame: status fields and commands, each pushed with a remover).
It depends on its config alone, so it never reloads with anything else. The app owns the
terminal: a child process that inherits fd 2 paints over it, so every child's stderr goes to
a file (the kernel's and brig's do), `--trace` takes a file, and anything
the shell must say waits until the app has exited. A row that shows something in the frame
depends on `frame` and `acquire`s an entry (`tui:status` is the pattern). The approval
modal is `push_screen` with a callback, because `confirm()` is called from cordis's coroutines,
not Textual workers. Real-launch tests (`bh-02/app/tests/test_real_launch.py`) start the
installed script in a pty with a fake model from `bh_02.testing`: `run_test()` alone misses
what only a real launch does.

**CodeAct, the kernel and the jail.** The kernel (`kernel:kernel`) is a stdlib-only worker
(`worker.py`, run by path, its one channel a Unix socket that carries an input in and its output
back; `worker-stdlib-only`) started by the `jail` row (`brig:jail`, or `kernel:unjailed`).
Approval is one rule in one row, `kernel:approval` (key `approval`, a capability, not a broker):
confined (the jail enforces writes and network), the model's code runs without asking;
unconfined (`--no-jail`), it is put to the person through `output.confirm` (the approval modal,
showing the code) and runs only on a yes. `agent:loop` asks it about every input and
`extensions:extensions` about every load; neither keeps a copy of the rule, and the kernel's own
`confined` (what the model is told) reads the same function, `kernel_cordis_plugin.is_confined`.
It depends on `jail` and `output`, not `kernel`, so `/clear` leaves it up; only a layer replaces
it (it runs in bh-02's process; an extension can't reach it). The kernel depends on its jail
alone, so a new ui or model keeps the namespace. Only `brig_cordis_plugin` imports brig
(`brig-one-adapter`). darwin is jailed by seatbelt (reads by denylist), Linux by bubblewrap
(reads by allowlist: the system, the interpreter, the project; the policy, `spec_for`, is the
same). The Linux jail's tests skip on darwin; `scripts/linux-jail-check` runs them in a
container with bubblewrap.

**The model's own plugins.** `extensions:extensions` loads the cordis components the model
writes to `.bh-02/plugins/NAME.py` while bh-02 runs (looked at every half second; changed,
loaded afresh; deleted, unloaded), so the model can evolve the harness without anyone editing
a layer. They run in a second worker the `jail` row starts (`extensions_cordis_plugin.worker`,
a cordis runtime of its own, listed in `cordis-in-wiring-only`'s `shell`), never in bh-02's
process: each load goes through `approval` with its source, as an input does (jailed, without
asking; unjailed, the person decides). An extension reaches bh-02 only through three keys bound in
that worker, each of which only adds (`commands.register`, `frame.status`, `system.add`); the
host registers what arrives into the real keys and keeps the removers. Its own `system` section
tells the model how, and `.bh-02/plugins/status.json` tells it how each load went. Don't give an
extension a key that replaces or reaches the composition (the loader, `jail`, `model`): the
worker's process boundary is what keeps a model's plugin as contained as its inputs.

**The model, by name.** The model row is `models:model` (`models_cordis_plugin`): named models
over their providers, the one its config's `default` names (`sonnet` unless a layer says
another; `--model` at launch, `/model NAME` mid-session, which edits the session layer's model
row). The built-ins are `sonnet`, `opus` and `haiku` on the `claude-code` provider; the models
file (`$XDG_CONFIG_HOME/bh-02/models.toml`, else `~/.config/bh-02/models.toml`) and the row's
`extra` add more, one table each: `provider`, `id`, and for `openai` (any OpenAI-compatible
`/chat/completions`: OpenAI, OpenRouter, Groq, Ollama's `/v1`, ...) `base_url` and an optional
`key`, the name of a `local.env` line the provider reads per request and sends only as the
`Authorization` header (never `CLAUDE_CODE_OAUTH_TOKEN`: a model whose key names it is refused,
and so is its request). The models file is trusted whole (a `module:attribute` provider runs in
bh-02's process; a key goes to its `base_url`), so one in the project (the working directory,
and the model row's `cwd` if set), as named or anywhere its links lead, is not read: the
model's code can write there (bh-02 run from the home directory, `$XDG_CONFIG_HOME` in the
project, a link into it). The built-ins and `extra` still work, and `models.problem`, `/model`
and the error of a name only that file could name say why and where the file must be instead.
A model that can't be used binds anyway and each step says what is wrong. `models:catalog`
binds `models` (the models there are, and which one the row names), depending on the loader
and `layers` alone, so `/model` (the operator) and the status bar depend on it and never reload
with a switch. The models plugin's README has the providers' details.

**The Claude provider.** Claude is the `claude-code` provider (`models_cordis_plugin.claude_code`):
Claude through Claude Code (the Claude Agent SDK), which is the subscription's sanctioned route.
It is a `model` under bh-02's own `agent:loop`, the same shape as the `openai` provider, and pi's
shape (`pi-claude-agent-sdk`): every model step reaches the loop as one step. The loop
classifies it, nudges, runs every call as an input in the kernel (asking the person first when it is
unjailed) and keeps the transcript (a session's `transcript.jsonl`). So approval is in one place
for every provider, and nothing about the loop depends on which one runs.

Why this shape, and not Claude Code's own loop (the first stack), or the plain Messages API with
the subscription token (the second, which only Haiku answered):
- The subscription reaches every model only through Claude Code.
- Claude Code's own loop would own the conversation, the approvals and the tool.

Claude Code is kept to carrying steps:
- It runs no built-in tool, loads no settings, CLAUDE.md or claude.ai connector, and does not
  compact.
- bh-02's one tool, `python`, is only *declared* to it, through an in-process MCP server, and
  never runs there. A call parks until the loop's next request brings its result, paired by the
  tool_use id Claude Code puts in the MCP request's `_meta`. Anything but `mcp__bh__python` is
  denied without asking.
- A step that ends any way but asking for tools or answering is interrupted at once, so Claude
  Code's own recoveries (it continued a truncated step three times, measured) never run instead
  of the loop's nudges.

One Claude Code process holds a conversation, and its session is checked against every request.
When they differ (`/clear`, a failed step), the transcript is written as a new Claude Code
session and resumed. Its state is the session's `claude/` directory (the `model` row's
`state`, from the session layer): an isolated `CLAUDE_CONFIG_DIR`, the saved session (so
`--resume` continues it) and the CLI's stderr. The plugin's README has the measurements and the
undocumented Claude Code internals it pins.

**The credential** is `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token` makes one), in the
git-ignored `local.env` at the repository root, so `uv run bh-02` needs no `--env-file`.
- The row reads that file itself and passes the token only in the Claude Code child's `env`:
  never into bh-02's own `os.environ`, never on a command line.
- The CLI starts through `claude-code-detached`, which leaves the terminal's process group and
  drops every `ANTHROPIC_*` and `CLAUDE_*` (Bedrock, Vertex, limits) from the child's
  environment but the few the SDK and the options set.
- **Never set or read `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`, and never print, log or
  commit the token.**

The kernel never gets it:
- `kernel:unjailed` drops every `CLAUDE*` (`CLAUDE_CODE_OAUTH_TOKEN`, and what a launching
  Claude Code leaves) and `ANTHROPIC_*` from the worker's environment.
- `brig:jail` scrubs the environment, and denies reading `local.env`: the project's, and every
  place the model rows look for it (`layers.credentials`: above bh-02's install and environment,
  from `bh_02.cli.credential_search`, the one definition of that search; `layers.secrets` names
  them all). So the workspace's own is hidden from whatever directory bh-02 runs in, and an input
  can't create or replace one where the model row looks (a planted `local.env` would hand the
  next launch's conversations to someone else's account). On Linux the jail holds each of these
  under the project with a mount the host can undo (an editor's save renames over the file), and
  says so as a note when the kernel comes up. The same is true of every write deny there
  (`.git/config`, a layer file): when the host undoes one, the jail ends itself at once and the
  next input's jail holds it again (a few milliseconds' window, measured in the brig plugin's
  README); `/release` (`kernel:release`) stops the kernel until
  the next input, which frees them so the person can add a credential mid-session: the brig
  plugin's README has the details. `secrets` also names the
  sessions' state directory: each session's `claude/` holds the Claude Code child's config and
  its messaging peer token. That is this run's (`$XDG_STATE_HOME/bh-02/sessions`) and the
  default one (`~/.local/state/bh-02/sessions`); a third, of a run with another
  `XDG_STATE_HOME`, is not known to this one and is not hidden.
- An approved `--no-jail` input runs with the person's permissions and could open `local.env`
  itself; only its environment is scrubbed.

Without a token the row still binds, and each step answers with an `authentication_failed` error
naming the variable, `local.env` and `claude setup-token`.

Ctrl-C closes the reply, and the loop closes its model step. The claude-code provider interrupts Claude
Code and reads it to the end of its query (the openai provider closes its HTTP stream), so nothing runs on after a stop. The CLI is in a
session of its own, so the terminal's SIGINT never reaches it. The loop answers the stopped
message in the transcript (what the step said, then that it was stopped, or that it failed), so
the next message does not redo it.

## Gate rules that are about this family

In the root gate (`pypeeker_rules/apps.py`, options in the root `pyproject.toml`):
`terminal-io` and `print-input` (only the modules their `allowed` lists name touch the
terminal, so the interface stays swappable; anything the user sees during a run goes through the
`ui` (its `output`); names in `sys` that are not terminal I/O, such as `argv`, `executable`, `path`, may be
imported by name anywhere; the kernel's worker is exempt from `print-input` because its stdout is
what an input printed), `cordis-in-wiring-only` (`*.wiring` plus the `shell` list),
`worker-stdlib-only`, `brig-one-adapter`.
