# bh-02

The coding harness in a terminal app: a model (Claude through Claude Code on the Claude
subscription, or any OpenAI-compatible model you name, driven by bh-02's own loop) acts in Python, its one tool, in a jailed kernel, inside a Textual TUI (`tui:app`), with every part of the program a plugin that can be replaced while it
runs. `bh_02` is the shell: `cli.py` (the `bh-02` command), `bootstrap.py` (`run()`: read
every layer, boot, follow the chat row's `done`, unwind; its own `harness`, `layers` and `sessions`
rows), `sessions.py` (a session is `$XDG_STATE_HOME/bh-02/sessions/<id>/`), the
layer file (`bh-02.toml`) and `testing.py`. Every capability is a
`*-cordis-plugin` workspace member (`../plugins/`) that a layer names by string; no package
imports another, and they agree on the names and shapes in [`CONTRACTS.md`](../CONTRACTS.md).
The words used here (row, layer, loop, model, provider, frame, ...) are in
[`GLOSSARY.md`](../GLOSSARY.md).

```
uv run bh-02                                       # a new session
uv run bh-02 --resume [ID]                         # continue this directory's newest session (or ID: all of it, its start, or its last part)
uv run bh-02 sessions                              # list them
uv run bh-02 --no-jail | --model NAME | --patch mine.toml | --trace trace.log
uv run bh-02 update-layer mine.toml                # rewrite a layer in today's row names (keeps mine.toml.bak)
```

**Layer files from an earlier bh-02.** Some of bh-02's rows were renamed (`llm` is `loop`,
`mode` is `chat`), the three status-bar rows (`jail_status`, `model_status`, a session's
`session`) are one `status` row, and the rows from before the one tool (`tools`, `fs`,
`approve`, `actions`, `guard`) are gone, as is the sidebar's (`sidebar`, or any row using
`tui:sessions`; `bh-02 sessions` lists the sessions). A session's own layer is brought up to date on
`--resume`, silently. A `--patch` file is yours, so a run naming old rows stops before the app
starts (exit code 1, no session made), listing each row and what to change
(`mine.toml: row 'llm' is now 'loop'; rename its id`) and the command that does it: `bh-02
update-layer mine.toml` rewrites the file in today's names, keeps the original as
`mine.toml.bak` (the rewrite drops comments; the copy keeps them) and prints what it changed.
Run again, it says the file is up to date and writes nothing. A file it can't read is one line
saying what is wrong, exit code 1, and nothing written. Two cases are yours to settle: a file
with both an old row and its new name (`llm` and `loop`) is refused, unchanged, since which
one's settings win is your call (a resumed session whose `session.toml` has both is refused the
same way); and an old status-bar row that was `disabled` is not carried over: `status` can't turn
off one part, so the bar stays on, and the change line says to give `status` `disabled = true` to
turn off all of it. An old
`model_status` naming `llm` names `model`, the row that holds the model now. The model row was
`completion`, filled by a provider's own row: `claude-code:completion` (its `model` is the
model row's `default` now; an id that is no built-in name becomes an `extra` model of the
row's own) or `ollama:completion` (an `extra` OpenAI-compatible model at its host's `/v1`,
named as its model and chosen); a session started with `--ollama` is given that model on
`--resume`. A status row's `default_model` is gone: the status bar asks the `models` row.

**The credential.** Claude is reached through Claude Code (the Claude Agent SDK) on the Claude
subscription, with a Claude Code OAuth token (`claude setup-token` makes one) kept in
`local.env` at the repository root (git-ignored; `CLAUDE_CODE_OAUTH_TOKEN=...`, one line). The
model row (its claude-code provider) reads that file itself and passes the token only to the Claude Code
CLI it starts, never into bh-02's own environment. The kernel's inputs never get it: the jail
scrubs the environment and denies reading `local.env`, and `--no-jail` drops
`CLAUDE_CODE_OAUTH_TOKEN`, every other `CLAUDE*` variable (a Claude Code that launched bh-02
leaves its own, a messaging token among them) and `ANTHROPIC_*` from the worker's environment. But an unjailed input
runs with your permissions, so one you approve could still open `local.env` itself, or read
the environment of any process you own, the Claude Code child's (which holds the token)
included: read an input before you answer `y`. Without the token, bh-02 starts anyway and each message answers with an
error saying where to put one. A session started on
Anthropic's Messages API (`anthropic:completion`) resumes on Claude Code, from its transcript. A
session started on the first Claude Agent SDK stack, where Claude Code ran its own loop, can't
be resumed: `--resume` says so in one line; start a new one.

**Models, by name.** The model defaults to `sonnet`. `--model NAME` starts on another and
`/model NAME` switches to one mid-session, across providers, the conversation carried on:
`sonnet`, `opus` and `haiku` are built in (Claude through Claude Code), and the models file,
`~/.config/bh-02/models.toml` (`$XDG_CONFIG_HOME/bh-02/models.toml`), adds your own, one table
each:

```toml
[llama]                                   # Ollama serves the OpenAI API at /v1
provider = "openai"
id = "llama3.2"
base_url = "http://localhost:11434/v1"

[router]                                  # any OpenAI-compatible endpoint: OpenRouter, Groq, ...
provider = "openai"
id = "anthropic/claude-sonnet-4"
base_url = "https://openrouter.ai/api/v1"
key = "OPENROUTER_API_KEY"                # a line of local.env: OPENROUTER_API_KEY=sk-...
```

`/model` lists them, the current one marked, and the palette offers `/model NAME` for each;
the status bar shows `model: NAME (provider)`. A model's `key` is read from `local.env` by the
model row itself and sent only as the request's `Authorization` header; a jailed input can't
read the file, and no key may name `CLAUDE_CODE_OAUTH_TOKEN`. The models file must be outside
the project (and not a link into it), where a jailed input can't write it: one in it is not
read, and `/model` says why (run from your home directory, `~/.config` is in the project). A
name that is no model, or a table with a problem, is a message saying what to fix (`/model`
refuses to switch to it; one chosen at launch answers each message with it). A
`--patch` that sets the model row's config replaces the session's whole, so it chooses the
model: `--model` with it is refused, and `/model` says it can't switch (set `default` in the
patch, or run without it; `bh-02 update-layer` says so when the patch it writes is one). The
models plugin's README has every setting.

In a session: `/help` lists the commands (Ctrl-P opens them as a palette). `/rows` shows the
running composition, `/explain ROW` what cordis knows about a row, `/restart ROW` starts one
afresh, `/clear` starts a new conversation and an empty kernel (and clears the screen, leaving
one note; the usage totals are the session's and stay), `/model [NAME]` lists the models or
switches to one, `/release` stops the kernel until the next input (on Linux, the way to add
your credential mid-session: the jail frees where bh-02 looks for it). A command never reaches
the model; a line like `/tmp/app.py is broken` is not a command. Ctrl-C stops a reply, Ctrl-Q
(or `/exit`) quits.

The app owns the terminal while it runs, so nothing else writes there: `--trace FILE` appends
lifecycle lines to a file, a layer file that could not be reloaded is reported after the app
exits, and the kernel's and brig's children log to files. The session's id is in the status
bar, and `bh-02 sessions` lists this directory's sessions, newest first. A narrow status bar
shows the id's last part (`58d9`), which `--resume` takes as well. A session is labelled with its stack,
the model it started on (`sonnet`; an earlier bh-02's session: `claude` or `ollama`), and the names of any
`--patch` files it started with (`patched: echo.toml`): the stack is not always the model that
answered, since `/model` switches and a patch can replace the `loop` row, and a resume with
other patches keeps the label it started with. A layer file that can't be
parsed at launch is one line naming it, exit code 1 (a `--patch` path that doesn't exist is
a usage error from click, exit code 2), and no session is made for the run; a new
run whose composition never starts (`could not start`) leaves no session either, while a
resumed one that can't start is kept. A session record whose `meta.json` can't be read (not
JSON, a key missing, a value of the wrong type) is skipped, never fatal: `bh-02 sessions`
names it on stderr, and `--resume` passes over it (and says what is wrong if you name it). On
exit bh-02 prints the session's id and how to continue it: `bh-02 --resume` when it is the
newest here, else `bh-02 --resume <id>`.

**Fake models for real launches.** `bh_02.testing` (a shell module in the gate, so it may know
cordis without putting test rows into a plugin) has `echo`, `repl_model` (each message is a
python call under the shipped loop, run as an input in the kernel, so `--no-jail` asks about it in
the modal), `bomb` (crashes the app), `slow_start` (`echo`, taking 3 s to start every time) and `showcase` (one of every kind of event
the transcript draws, usage and an unusual stop included; `lines N` streams N lines all at
once, a burst that never waits; `slow N` streams N lines 50 ms apart, so a Ctrl-C can land
mid-reply), named by a patch layer:

```toml
[[plugin]]
id = "loop"
use = "bh_02.testing:echo"
```

Two more replace only the `model` row, so the shipped loop, its transcript and the session's
layer run as they do with Claude: `echo_model` (each turn echoes the last message and
says which user message of the conversation it was, `(message 2)`, so a screen shows whether
`/clear` forgot the transcript and a resume restored it) and `slow_model` (the same, taking 3 s
to start). And three are providers a models file names for a model of its own, under the
shipped `models:model` row, so `--model` picks one and `/model` switches between them (or to
an OpenAI-compatible model) as between Claude and any other: `echo_provider` (`echo_model`'s
turn, said as `[ID] echo: ...`, so a screen shows which model answered), `slow_provider` (the
same, taking 3 s to start: what the status bar and a message typed meanwhile say while
`/model` restarts the model) and `repl_provider` (`repl_model`'s):

```toml
[fake]
provider = "bh_02.testing:echo_provider"
id = "fake"
```

`tests/test_real_launch.py` starts the installed `bh-02` in a pseudo-terminal with those, in a
models file of its own, and an OpenAI-compatible model on `models_cordis_plugin.openai.testing`'s
stand-in server (`-m "not real_launch"` deselects it).

## The compositions

`bh-02.toml` is the harness; every other file is a layer over it: the session's own layer
(`sessions.session_layer`), and `--patch`.

| Row | `bh-02.toml` | a session's layer |
|---|---|---|
| `loop` | `agent:loop` | |
| `ui` | `tui:app` | `history` (the session's `events.jsonl`) |
| `chat` | `chat:session` | |
| `kernel` | `kernel:kernel` | |
| `jail` | `brig:jail` | `kernel:unjailed` with `--no-jail` |
| `approval` | `kernel:approval` | |
| `release` | `kernel:release` | |
| `system` | `context:project` | |
| `commands` | `commands:registry` | |
| `operator` | `commands:operator` | `layer`, `model_row` (`model`), `forget` (the transcript) |
| `status` | `tui:status` | |
| `palette` | `tui:palette` | |
| `model` | `models:model` (`default`: `sonnet`) | `default` (with `--model`, and as `/model` sets it); `state` (the session's `claude/`: Claude Code's own session, which a resume continues) |
| `models` | `models:catalog` | |
| `transcript` | `agent:transcript` | `path` (the session's `transcript.jsonl`) |
| `memory` | `agent:memory` | |
| `shell-hints` | `kernel:shell_hints` | |
| `on-touch` | `context:on_touch` | |
| `extensions` | `extensions:extensions` | |

`run()` adds three rows of its own after every layer, pinned on so no layer can remove them:
`layers` (the files above, as paths, so the jail can keep an input from rewriting them;
`credentials`: where the model rows look for `local.env`, above bh-02's install and environment,
nearest first; and `secrets`: every one of those, the `local.env` beside and above the project,
and the sessions' state directory, this run's and the default `~/.local/state/bh-02/sessions`
(Claude Code's own config and tokens), which a jailed input can't read; with `--no-jail` an input runs with your permissions, so one you
approve could open them: only its environment is scrubbed), `sessions` (the running session,
whose id the status bar shows) and `harness` (which follows the chat row's `done`, across a
restart of the chat row).

A row's `id` is its role; `use` is `plugin:component`, a `cordis.plugins` entry point, or
`module:attribute`. Order in a file means nothing; dependencies decide what starts when. Entry
points come from installed metadata, so a new plugin needs `uv sync` before a layer can name
it. The layer files are live: edit one (by hand, or by `/model`; a jailed input can't write
one) and the rows that changed are swapped, their dependents reloaded in place,
everything else left alone; a bad edit is reported and changes nothing. On Linux, saving a
layer file inside the project by rename (most editors do) ends the kernel's jail, because the
rename lifts the jail's hold on it; the next input's jail holds the new file, and the input
says why its variables are gone. A program an input left running can get a write in during the
few milliseconds that takes: stop the reply (or `/release`) before editing a layer while one runs
(brig-cordis-plugin's README, "When the host undoes a mount").

What the rows depend on, which is what decides what reloads when:

```
commands:registry       binds Commands                     depends on nothing
commands:operator       registers /rows ... /model         depends on Commands, Loader, Models
context:project         binds System                       depends on nothing
models:model            binds Model                        depends on Layers (where the credential is looked for; its config, the models file as it starts, the credential at the first step)
models:catalog          binds Models                       depends on Loader, Layers
agent:transcript        binds Transcript                   depends on nothing
agent:memory            binds Memory                       depends on nothing
agent:loop              binds Loop                         depends on Model, Kernel, Transcript, System, Approval, Memory
kernel:shell_hints      adds the shell hints to Memory     depends on Memory, Transcript
context:on_touch        adds the on-touch sections         depends on System, Memory, Transcript
brig:jail               binds Jail                         depends on Layers
kernel:unjailed         binds Jail                         depends on nothing
kernel:kernel           binds Kernel (the one tool)        depends on Jail
kernel:approval         binds Approval                     depends on Jail, Output
kernel:release          registers /release                 depends on Kernel, Commands
tui:app                 binds Input, Output, Frame         depends on nothing (its config)
tui:status              pushes the status bar's fields     depends on Kernel, Loader, Models, Sessions, Frame, Output
tui:palette             pushes the palette's commands      depends on Commands, Frame
chat:session            runs the chat, binds Done          depends on Loop, Input, Output, Commands
extensions:extensions   loads the model's own plugins      depends on Jail, Commands, Frame, System, Approval
```

Swap the model or the ui and the kernel keeps its namespace, because the kernel depends on the
jail alone; swap the jail and a new worker starts. `approval` is the one place that decides
whether the model's code runs unasked (an input, an extension's load), and depends on the jail
and the ui, not the kernel, so `/clear` leaves it up; only a layer replaces it. Retire a
command and it leaves the `commands` broker: that is the paper's service broker, one row binds
the key, the contributors
register through an effect whose undo is their removal. Switch the model (`/model NAME`, which
names it as the model row's `default` in the session's layer) and the model row reloads on the
new model's provider, the loop against it, while `transcript`, a row of its own, keeps the
conversation. `/model` and the status bar depend on `models`, not `model`, so a switch reloads
neither. A patch that gives the `model` row a `config` replaces the session layer's (its
`state`, and the `default` `/model` writes, which then changes nothing): name a model with
`--model` instead, or put it in the models file.

## The plugins

Each depends on the libraries (`cordis`, and `cordis-helpers` for the patterns) and on no
other plugin; the gate proves it.

| Package | Binds / registers | Consumes |
|---|---|---|
| `tui-cordis-plugin` | `ui`: `input`, `output` (whose `confirm` asks in a modal), `frame` (the Textual app); the frame's rows (`status`: session, model and provider, jail; `palette`) | `frame` and what each row reports on |
| `models-cordis-plugin` | `model`: named models over their providers (`models:model`): `claude-code`, Claude through Claude Code (the Claude Agent SDK) on the subscription (one model step per call, the loop's one tool, `python`, only declared to it through an in-process MCP server whose calls wait for the loop's results, any other tool denied; one Claude Code process per conversation, its session checked against the transcript and rebuilt from it when they differ), and `openai`, any OpenAI-compatible `/chat/completions` (streamed, a call's arguments assembled from their deltas, a key from `local.env` in its header); each streams text, thinking and tool calls, usage, the API's stop reason and its message for replay. `models` (`models:catalog`): the models there are | `layers` (`credentials`: where both look for `local.env`), `loader` (catalog) |
| `agent-cordis-plugin` | `loop` (`agent:loop`: turns classified after harness, bounded nudges, each call an input, run only on `approval`'s yes, its result followed by what `memory`'s functions add), `transcript` (`agent:transcript`), `memory` (`agent:memory`: the broker of what the model is told with an input's result) | the loop: `model` (`complete`), `kernel` (`spec`, `instructions`, `run`, `touched`), `transcript` (`messages`, `append`), `system` (`text`), `approval` (`approve`), `memory` (its functions, after each input) |
| `chat-cordis-plugin` | runs `session` (a turn interruptible) and binds `done` | `loop`, `input`, `output`, `commands` |
| `context-cordis-plugin` | `system` (`context:project`): who the model is (the model in bh-02, not Claude Code) and what bh-02 is made of, then the project context: the working directory and branch, what the context files' sections say (guidance and rule files, each read by a function), read fresh; a broker other rows add sections to; and what the context files' `on_touch` sections say about the files an input opened (`touched`). `context:on_touch` adds to `memory` that guidance and those rules, each told once a conversation with the result of the first input that opens a file they cover | on-touch: `system` (`touched`), `memory` (`add`), `transcript` (its lifetime only) |
| `extensions-cordis-plugin` | nothing: loads the cordis components the model writes to `.bh-02/plugins/` while bh-02 runs, into a worker the `jail` row starts; what they add (commands, status fields, prompt sections) goes into `commands`, `frame` and `system`; each load on `approval`'s yes | `jail`, `commands`, `frame`, `system`, `approval` |
| `kernel-cordis-plugin` | `kernel` (`kernel:kernel`): a persistent Python worker behind a Unix socket, and the model's one tool, `python(code)` (its spec, its instructions, whether it is confined, an input run, the files it opened); `approval` (`kernel:approval`): whether the model's code runs, at once when the jail confines it, else on the person's yes; `jail` (`kernel:unjailed`); `kernel:shell_hints` adds to `memory` how Python does what an input ran through a shell (`cat`, `sed`, `ls`), once for each kind of work a conversation; `kernel:release` registers `/release`, which stops the kernel and its jail until the next input | kernel: `jail` (`start`, `report`, `notice`, `reads`, `release`); approval: `jail` (`report`), `output` (`confirm`); shell hints: `memory` (`add`), `transcript` (its lifetime only); release: `kernel` (`release`), `commands` (`register`) |
| `brig-cordis-plugin` | `jail`: brig's `scratch_darwin()` on darwin, `strict_linux()` on Linux; the only importer of brig | `layers` |
| `commands-cordis-plugin` | `commands` (the broker); the operator's commands over the loader | `commands`, `loader`, `models` (operator) |

Every model runs in the same composition: `agent:loop` offers the kernel's one tool on every
request, runs every call as an input, and classifies every turn (harness's rule: never read a
truncated or silent turn as the answer); only the model row's provider differs.

## CodeAct

bh-02 offers the model exactly one tool, `python(code)`, over the provider's standard tool
calling (../harness/ARCHITECTURE.MD: "one tool, and it carries code"). To the model it is a
Python REPL of its own that persists, and each call is one input to it: plain Python (not IPython),
with nothing of bh-02's in the namespace, and nothing an input does calls back into bh-02. An input reads and edits files with `open` or `pathlib` and runs programs (`python`, `git`,
a test runner) with `subprocess`, in the project directory. The model is told to work in Python
rather than through a shell, and an input that runs `cat`, `sed` or `ls` through one is told how
Python does that, once for each kind of work a conversation. The namespace outlives a model
swap; Ctrl-C interrupts the running input and keeps the namespace.

After each input, the loop asks `memory` what to tell the model with its result (in a worker
thread, as it reads the prompt, so neither freezes the app): the functions
rows add there are given the input's code, its result and the project files it opened (the
worker hears each `open` with an audit hook, so `kernel.touched()` is what Python in the input
read or wrote, not what a shell command did). `kernel:shell_hints` adds the shell hint above;
`context:on_touch` adds the context files' `on_touch` sections, so a subdirectory's AGENTS.md
or CLAUDE.md, or a rule for some files, arrives whole with the result of the first input that
opens a file it covers, as Claude Code's do when its Read, Write or Edit touches one. It asks
the `system` value (`touched`), so the context files are the ones the `system` row's config
names (`root`, `home`, `files`), read and searched once for the prompt and for this. Both
depend on `transcript`, so after `/clear` they tell the new conversation again.

The kernel is a worker process started by the `jail` row. `brig:jail` confines it: writes
only inside the project (and never to the layer files, the host's import paths, `.git/hooks`,
`.git/config`, CLAUDE.md, ...), no network, credentials unreadable, and an environment
scrubbed to a short allowlist; the programs an input starts are inside the same jail. A confined
input runs without asking. brig's host process, which starts the worker from outside the
jail, keeps the environment bh-02 was launched with (brig's launcher passes it on, and bh-02
never puts its own token there); a jailed input can't read it. `--no-jail` uses
`kernel:unjailed`: an input runs with your permissions, so every input is shown to you, code and
all, and runs only if you say `y`. For a moment after it comes up (0.4 s, its keys dimmed) the
question ignores keys, so the rest of a message you were typing can't answer it; those keys are
dropped. Only the worker's environment is scrubbed of `CLAUDE*` and
`ANTHROPIC_*`: an approved input can still read `local.env`, or the environment of any process
you own, the Claude Code child's included.

## The model's own plugins

The model can extend bh-02 itself, while it runs: it writes a module of cordis components to
`.bh-02/plugins/NAME.py` in the project, and the `extensions` row loads it within half a second,
again whenever it changes, and unloads it when it is deleted. An extension can add a slash
command for you, a status-bar field, or text in the model's own prompt, and nothing else: it
runs in a worker the `jail` row starts, as confined as an input, and reaches bh-02 only through
those three keys, each of which only adds. Jailed, it loads without asking, as an input runs
without asking; with `--no-jail` each one is put to you first, with its source. The status bar's
`ext:` field lists them (`ext: todo ✓`), and `.bh-02/plugins/status.json` is what the model
reads to see whether one loaded. The plugin's README has the details.

## Writing a plugin

`../CLAUDE.md` has the package shape. A provider is a value with the methods `CONTRACTS.md`
lists and a component that binds it. A contributor to a broker (a slash command into
`commands`, a status field into `frame`) is a component that registers into it. Neither
imports the plugin it sits beside, nor the broker: it says what it needs of one.

```python
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from cordis import Effects, acquire, component


@runtime_checkable
class Commands(Protocol):
    def register(
        self, spec: Mapping[str, Any], run: Callable[[str], Awaitable[str]]
    ) -> Callable[[], None]: ...


@component
async def git(*, commands: Commands) -> Effects:
    yield acquire(commands.register, {"name": "status", "help": "...", "usage": "/status"}, status)
```

Bind the wrong thing under `commands` and this row fails at load with "git: commands is bound
to a X, which is missing register". Declare the package's entry point
(`[project.entry-points."cordis.plugins"] git = "git_cordis_plugin"`), `uv sync
--all-packages`, and a layer can say `use = "git:git"`.
