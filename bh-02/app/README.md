# bh-02

The coding harness in a terminal app: a model (Claude through Claude Code on the Claude
subscription, or any OpenAI-compatible model you name, driven by bh-02's own loop) acts in Python, through the tools rows register (the shipped one, `python`, runs in a jailed Python process), inside a Textual TUI (`tui:ui`), with every part of the program a plugin that can be replaced while it
runs. `bh_02` is the shell: `cli.py` (the `bh-02` command), `bootstrap.py` (`run()`: read
every layer, boot, follow the chat row's `done`, unwind; its own `shell`, `host` and `session`
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
`mode` is `chat`, `jail_status` is `grades`; the shell's own `harness` is `shell`, `layers` is
`host` and `sessions` is `session`), and so were some components (`chat:session` is
`chat:converse`, `tui:app` is `tui:ui`; the shell's `bh_02.bootstrap:harness`, `layer_files` and
`session_list` are `bh_02.bootstrap:shell`, `host` and `session`). The status-bar rows
(`model_status`, and the `session` row an earlier session's layer filled with `tui:status`) are
one `status` row, and the tool rows from before CodeAct (`fs`, `approve`,
`actions`, `guard`, and any row using the old `tools:` plugin; a `tools` row naming no plugin is
today's broker, `agent:tools`) are gone, as is the sidebar's (`sidebar`, or any row using
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
CLI it starts, never into bh-02's own environment. The Python process's inputs never get it: the jail
scrubs the environment and denies reading `local.env`, and `--no-jail` drops
`CLAUDE_CODE_OAUTH_TOKEN`, every other `CLAUDE*` variable (a Claude Code that launched bh-02
leaves its own, a messaging token among them) and `ANTHROPIC_*` from the Python process's environment. But an unjailed input
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
afresh, `/clear` starts a new conversation and a new Python process (the old conversation kept as
the session's `transcript.jsonl.bak`; it clears the screen, leaving one note; the usage totals
are the session's and stay), `/compact [WHAT TO KEEP]` asks the model
to summarise the conversation and carries on in a new one from the summary, keeping the Python
process and its variables (the screen keeps only the note carrying the summary, and the old transcript
is kept as the session's `transcript.jsonl.bak`, a later /compact's as `.bak.2`, and so on; the
model has 300 seconds, the `conversation` row's `timeout`, since Ctrl-C doesn't stop a command, and a
note says so as it begins; quitting stops it and changes nothing), `/model [NAME]` lists the models or switches
to one, `/release` stops the Python process and the extensions process until the next input
(on Linux, the way to add your credential mid-session: each row stops its own, then the runner
frees where bh-02 looks for it; the extensions load again once the next input has started the
Python process). A command never reaches the
model; a line like `/tmp/app.py is broken` is not a command. `!COMMAND` runs COMMAND in your
shell, as you (not in the jail), in the project: what it printed is shown, and the model reads
it with your next message, never mid-turn (a `/model` switch or a `/compact` in between keeps it;
`/clear` drops it). Its output is captured, since the app owns the terminal (a program that wants the terminal,
a password prompt, fails), and Ctrl-C can't stop it (pressed while one runs, it says so): it is
stopped at its timeout (120 s; the `shell-command` row's `timeout`), or when you quit. Ctrl-C
stops a reply, Ctrl-Q (or `/exit`) quits.

The app owns the terminal while it runs, so nothing else writes there: `--trace FILE` appends
lifecycle lines to a file, a layer file that could not be reloaded is reported after the app
exits, and the Python process's and brig's children log to files. The session's id is in the status
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
python call under the shipped loop, run as an input in the Python process, so `--no-jail` asks about it in
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
layer run as they do with Claude: `echo_model` (each step echoes the last message and
says which user message of the conversation it was, `(message 2)`, so a screen shows whether
`/clear` forgot the transcript and a resume restored it) and `slow_model` (the same, taking 3 s
to start). And three are providers a models file names for a model of its own, under the
shipped `models:model` row, so `--model` picks one and `/model` switches between them (or to
an OpenAI-compatible model) as between Claude and any other: `echo_provider` (`echo_model`'s
step, said as `[ID] echo: ...`, so a screen shows which model answered), `slow_provider` (the
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
| `ui` | `tui:ui` | `history` (the session's `events.jsonl`) |
| `chat` | `chat:converse` | |
| `python` | `python:tool` | |
| `runner` | `runner:confined` | `runner:unconfined` with `--no-jail` |
| `approval` | `runner:approval` | |
| `release` | `runner:release` | |
| `system` | `agent:system` | |
| `commands` | `commands:registry` | |
| `operator` | `commands:operator` | |
| `jobs` | `commands:jobs` | |
| `switch` | `models:switch` | `layer` (the session's), `model_row` (`model`) |
| `conversation` | `agent:conversation` (`timeout`: 300) | |
| `shell-command` | `commands:shell_command` | |
| `status` | `tui:status` | |
| `grades` | `tui:grades` | |
| `palette` | `tui:palette` | |
| `model` | `models:model` (`default`: `sonnet`) | `default` (with `--model`, and as `/model` sets it); `state` (the session's `claude/`: Claude Code's own session, which a resume continues) |
| `models` | `models:catalog` | |
| `transcript` | `agent:transcript` | `path` (the session's `transcript.jsonl`) |
| `notes` | `agent:notes` | |
| `executor` | `agent:executor` | |
| `memory` | `memory:files` | |
| `on-touch` | `memory:on_touch` | |
| `memory-auto` | `memory:auto` | |
| `extensions` | `extensions:extensions` | |

`run()` adds three rows of its own after every layer, pinned on so no layer can remove them:
`host` (`paths`: the files above, as paths, so the jail can keep an input from rewriting them;
`credentials`: where the model rows look for `local.env`, above bh-02's install and environment,
nearest first; and `secrets`: every one of those, the `local.env` beside and above the project,
and the sessions' state directory, this run's and the default `~/.local/state/bh-02/sessions`
(Claude Code's own config and tokens), which a jailed input can't read; `trusted`: bh-02's
config directory, this run's `$XDG_CONFIG_HOME/bh-02` and the default `~/.config/bh-02`, as
named and as resolved, where your models file and startup file are, which bh-02
reads and trusts, so a jailed input can't write there when it is in the project (bh-02 run from
your home directory); `code`: where bh-02 runs its own code from, the directory of every
package a layer may name (`bh_02`, cordis, cordis_helpers, brig, host_paths, each installed
plugin's) as installed, as named and as resolved (`code_directories`), which every jail reads (with an
editable install, `uv run` here or `uv tool install --editable`, the extensions process imports
cordis from the workspace) and a jailed input can't write when it is in the project (bh-02
working on its own checkout: bh-02 imports its modules from there); with `--no-jail` an input
runs with your permissions, so one you approve could open or write them: only its environment
is scrubbed; and `auto_memory`: the project's auto memory directory,
`$XDG_STATE_HOME/bh-02/projects/<project>/memory`, which the command line makes and a jailed
input may write), `session` (the running session,
whose id the status bar shows) and `shell` (which follows the chat row's `done`, across a
restart of the chat row).

A row's `id` is its role; `use` is `plugin:component`, a `cordis.plugins` entry point, or
`module:attribute`. Order in a file means nothing; dependencies decide what starts when. Entry
points come from installed metadata, so a new plugin needs `uv sync` before a layer can name
it. The layer files are live: edit one (by hand, or by `/model`; a jailed input can't write
one) and the rows that changed are swapped, their dependents reloaded in place,
everything else left alone; a bad edit is reported and changes nothing. On Linux, saving a
layer file inside the project by rename (most editors do) ends the Python process's jail, because the
rename lifts the jail's hold on it; the next input's jail holds the new file, and the input
says why its variables are gone. A program an input left running can get a write in during the
few milliseconds that takes: stop the reply (or `/release`) before editing a layer while one runs
(runner-cordis-plugin's README, "When the host undoes a mount").

What the rows depend on, which is what decides what reloads when:

```
commands:registry       binds Commands                     depends on nothing
commands:jobs           binds Jobs                         depends on Output
commands:operator       registers /rows ... /restart       depends on Commands, Loader, Jobs
commands:shell_command  claims ! (a shell command)         depends on Commands
models:model            binds Model                        depends on Host (where the credential is looked for; its config, the models file as it starts, the credential at the first step)
models:catalog          binds Models                       depends on Loader, Host
models:switch           registers /model                   depends on Commands, Loader, Models, Jobs
agent:transcript        binds Transcript                   depends on nothing
agent:system            binds System                       depends on nothing (its config)
agent:notes             binds Notes                        depends on nothing
agent:access            binds Access                       depends on nothing
agent:executor          binds Executor                     depends on nothing
agent:tools             binds Tools                        depends on nothing
agent:loop              binds Loop                         depends on Model, Tools, Transcript, System, Approval, Output, Notes, Executor
agent:conversation      registers /clear, /compact         depends on Model, Tools, Loader, Commands, Output, Jobs (the transcript row's file, not Transcript)
memory:files            binds Memory, registers /memory    depends on System, Commands, Host
memory:on_touch         adds memory loaded on demand       depends on Memory, Notes, Transcript, Access
memory:auto             adds auto memory to System         depends on System, Host, Transcript
runner:confined         binds Runner                       depends on Host
runner:unconfined       binds Runner                       depends on nothing
runner:approval         binds Approval                     depends on Runner
runner:release          registers /release                 depends on Runner, Commands
python:tool             registers python, its stop         depends on Runner, Approval, Tools, System, Access
tui:ui                  binds Input, Output, Frame         depends on nothing (its config)
tui:status              pushes session and model fields    depends on Loader, Models, Session, Frame
tui:grades              pushes the jail field              depends on Runner, Approval, Frame, Output
tui:palette             pushes the palette's commands      depends on Commands, Frame
chat:converse           runs the chat, binds Done          depends on Loop, Input, Output, Commands, Jobs
extensions:extensions   loads the model's own plugins      depends on Runner, Commands, Frame, System, Tools, Approval, Output
```

Swap the model or the ui and the Python process keeps its namespace, because the python row
depends on the runner and brokers that never reload; swap the runner and a new process starts.
`approval` is the one place that decides whether the model's code runs unasked (an input, an
extension's load; what it does not let run, the asker puts to you), and depends on the runner
alone, so `/clear` and a new ui leave it up; only a layer replaces it. Retire a
command and it leaves the `commands` broker: that is the paper's service broker, one row binds
the key, the contributors
register through an effect whose undo is their removal. Switch the model (`/model NAME`, which
names it as the model row's `default` in the session's layer) and the model row reloads on the
new model's provider, the loop against it, while `transcript`, a row of its own, keeps the
conversation, and `executor` the reading of the prompt a stopped reply left running, which the
new loop waits for (so does one `/clear` restarts). `/model` and the status bar depend on `models`, not `model`, so a switch reloads
neither. A patch that gives the `model` row a `config` replaces the session layer's (its
`state`, and the `default` `/model` writes, which then changes nothing): name a model with
`--model` instead, or put it in the models file.

## The plugins

Each depends on the libraries (`cordis`, `cordis-helpers` for the patterns, `host-paths` for
where a file is and how it is reached) and on no other plugin; the gate proves it.

| Package | Binds / registers | Consumes |
|---|---|---|
| `tui-cordis-plugin` | `ui`: `input`, `output` (whose `confirm` asks in a modal), `frame` (the Textual app); the frame's rows (`status`: session, model and provider, jail; `palette`) | `frame` and what each row reports on |
| `models-cordis-plugin` | `model`: named models over their providers (`models:model`): `claude-code`, Claude through Claude Code (the Claude Agent SDK) on the subscription (one model step per call, the loop's tools only declared to it through an in-process MCP server whose calls wait for the loop's results, any other tool denied; one Claude Code process per conversation, its session checked against the transcript and rebuilt from it when they differ), and `openai`, any OpenAI-compatible `/chat/completions` (streamed, a call's arguments assembled from their deltas, a key from `local.env` in its header); each streams text, thinking and tool calls, usage, the API's stop reason and its message for replay. `models` (`models:catalog`): the models there are; `/model` (`models:switch`), which lists them and switches by name | `host` (`credentials`: where both look for `local.env`), `loader` (catalog, switch), `commands`, `output` (switch) |
| `agent-cordis-plugin` | `loop` (`agent:loop`: steps classified after harness, bounded nudges, the registered tools offered, read once at the first request after those it `requires`, each call run through its tool at once when the `approval` rule lets it run unasked, else on the person's yes (`output.confirm`), its result followed by what `notes`' functions add), `tools` (`agent:tools`: the broker of the model's tools, offered in name order), `transcript` (`agent:transcript`), `system` (`agent:system`: the system prompt, who the model is and where it is working, then the sections rows add; a broker), `notes` (`agent:notes`: the broker of what the model is told with a call's result), `access` (`agent:access`: the broker of what is asked before a file is read or written), `executor` (`agent:executor`: where the loop reads the prompt and asks `notes`, off the event loop, one call at a time across the loop's reloads); `agent:conversation` registers `/clear` and `/compact`, which begin a new conversation, empty or from the model's summary, over the transcript row's file (the old kept as `.bak`), restarting the loop and the transcript (and for `/clear` the python row) | the loop: `model` (`complete`), `tools` (`specs`, `get`, `ready`), `transcript` (`messages`, `append`), `system` (`text`), `approval` (`unasked`), `output` (`confirm`), `notes` (its functions, after each call), `executor` (`run`); compact: `model` (`complete`), `tools` (`specs`), `loader` (`status`, `rows`, `restart`), `commands` (`register`), `output` (`show`, `notice`) |
| `chat-cordis-plugin` | runs the chat (`chat:converse`: a turn interruptible; a line `commands` claims goes to it, cancelled if the input closes, and what a command left the model, which `commands` holds, goes with the next message) and binds `done` | `loop`, `input`, `output`, `commands` (`claims`, `run`, `take_for_model`), `jobs` (`settled`) |
| `memory-cordis-plugin` | `memory` (`memory:files`): Claude Code's memory, as its docs describe it: the managed policy's CLAUDE.md, yours (`~/.claude/CLAUDE.md`, `~/.claude/rules/`), each directory's CLAUDE.md files from the filesystem's root down to the project's, AGENTS.md where there is none, `@path` imports (four hops) and `.claude/rules/` without `paths`, a section of `system`, read fresh; `/memory` lists them. `memory:auto` adds auto memory: how the model keeps notes of its own in the project's directory outside the repository, and their MEMORY.md index, read once a conversation. `memory:on_touch` adds to `notes` what loads on demand (a subdirectory's CLAUDE.md files and rules, every rule whose `paths` match), each told whole once a conversation, with the result of the first input that opens a file it covers (or of the next, when that one's note was full) | memory: `system` (`add`), `commands` (`register`), `host` (`auto_memory`); auto: `system` (`add`), `host` (`auto_memory`), `transcript` (its lifetime); on-touch: `memory` (`touched`), `notes` (`add`), `transcript` (`messages`: what a resumed conversation was told) |
| `extensions-cordis-plugin` | nothing: loads the cordis components the model writes to `.bh-02/plugins/` while bh-02 runs, into the extensions process, which the runner starts; what they add (commands, status fields, prompt sections, tools whose calls run in that process) goes into `commands`, `frame`, `system` and `tools`; each load at once when the `approval` rule lets it run unasked, else on the person's yes; on `/release` it stops the extensions process, and none starts until something starts in the runner (the next input) or an extension changes, and then every extension loads again | `runner` (`start`, `released`, `on_release`), `commands`, `frame`, `system`, `tools` (`register`, `specs`), `approval` (`confined`, `unasked`), `output` (`confirm`) |
| `python-cordis-plugin` | nothing: `python:tool` starts a persistent Python process in the runner, behind a Unix socket, and registers the `python(code)` tool with `tools` (a call runs as an input and answers with the files it opened), tells the model about it in the `system` section `python`, and stops it on `/release` | `runner` (`start`, and its start's `report`, `notice`, `reads`, `writes`; `report`; `on_release`), `approval` (`confined`), `tools` (`register`), `system` (`add`), `access` (`asking`, `refusal`) |
| `runner-cordis-plugin` | `runner`: what starts the Python process and the extensions process, `runner:confined` (a brig jail per start: `scratch_darwin()` on darwin, `strict_linux()` on Linux; the only importer of brig) or `runner:unconfined` (`--no-jail`); `approval` (`runner:approval`): whether what the model asked for runs unasked, when it runs in a runner that confines it; `runner:release` registers `/release`, which has each row stop its own program, then frees what the jails held | confined: `host`; approval: `runner` (`report`); release: `runner` (`release`), `commands` (`register`) |
| `commands-cordis-plugin` | `commands` (the broker: slash commands, and the line prefixes a layer's rows claim; it says which lines are commands); `jobs` (`commands:jobs`: the restarts commands queue, which the chat waits on); the operator's commands over the loader; `!COMMAND` (`commands:shell_command`): the person's shell command, its output shown and held (in `commands`) for their next message | `commands`, `loader`, `models` (operator); `commands` (`claim`: shell command) |

Every model runs in the same composition: `agent:loop` offers the registered tools on every
request (the python row's `python`, in the shipped layer), runs every call through its tool, and
classifies every step (harness's rule: never read a
truncated or silent step as the answer); only the model row's provider differs.

## CodeAct

bh-02 ships one tool, `python(code)`, offered over the provider's standard tool calling with
whatever tools other rows register with `tools`: one tool, and it carries code. To the model it
is a
Python REPL of its own that persists, and each call is one input to it: plain Python (not IPython),
with nothing of bh-02's in the namespace, and nothing an input does calls back into bh-02. An input reads and edits files with `open` or `pathlib` and runs programs (`python`, `git`,
a test runner) with `subprocess`, in the project directory. The model is told to work in Python
rather than through a shell. The namespace outlives a model
swap; Ctrl-C interrupts the running input and keeps the namespace.

Helpers you want in every project's REPL (a `show`, a `search`) go in your own startup file,
`$XDG_CONFIG_HOME/bh-02/kernel.py` (else `~/.config/bh-02/kernel.py`); the project's
`.bh-02/kernel.py` runs after it, and is the only one the model is told it may edit. A new
Python process runs both before the first input, which is told the names each defined (or its
traceback; one failing doesn't stop the other). bh-02 reads yours itself and sends it in, since
the Linux jail has no home directory in it, so whatever it holds the model can read (in that
jail its helpers run, but its file is not there to open: the model is told `inspect.getsource`
shows one); the project's is read inside the jail, and so is yours when it is somewhere an
input may write, or reached through there. No jailed input may write your config directory, so
a session run from your home directory can't change what a later one runs. One that ends the
REPL is passed over until `/restart python`, and the input it cut short names it, after what
the opening had to tell by then (that the REPL was started again, and why). With `--no-jail` neither runs unasked: the model is told to
run them as inputs of its own, which you are asked about. The python row's `startup` config is
the list.

After each call, the loop asks `notes` what to tell the model with its result (on `executor`,
off the event loop, as it reads the prompt, so neither freezes the app): the functions
rows add there are given the tool's name, the call's input, its result and the files it opened
(for an input, the Python process hears each `open` with an audit hook, so `touched()` is what Python in the input
read or wrote, not what a shell command did). `memory:on_touch` adds memory's on-demand files, so a subdirectory's CLAUDE.md, or a rule whose
`paths` match, arrives whole with the result of the first input that opens a file it covers, as
Claude Code's do when its Read, Write or Edit touches one. It asks the `memory` value
(`touched`), so the memory row's config (`root`, `home`, `instruction_files`, `excludes`) holds
for the prompt and for this. It depends on `transcript`, so after `/clear` or `/compact` it tells
the new conversation again, and reads the notes the loop keeps with each result (`notes` on the
result's entry), so a resumed session (`--resume`) is not told again a note told with an earlier
result.

The Python process is a program the runner starts. `runner:confined` confines it: writes
only inside the project (and never to the layer files, the host's import paths, bh-02's own
code, `.git/hooks`, `.git/config`, `.claude`, bh-02's config directory, ...), no network,
credentials unreadable, and an environment scrubbed to a short allowlist; the programs an input starts are inside the same jail. A confined
input runs without asking. brig's host process, which starts the Python process from outside the
jail, keeps the environment bh-02 was launched with (brig's launcher passes it on, and bh-02
never puts its own token there); a jailed input can't read it. `--no-jail` uses
`runner:unconfined`: an input runs with your permissions, so every input is shown to you, code and
all, and runs only if you say `y`. For a moment after it comes up (0.4 s, its keys dimmed) the
question ignores keys, so the rest of a message you were typing can't answer it; those keys are
dropped. Only the Python process's environment is scrubbed of `CLAUDE*` and
`ANTHROPIC_*`: an approved input can still read `local.env`, or the environment of any process
you own, the Claude Code child's included.

## The model's own plugins

The model can extend bh-02 itself, while it runs: it writes a module of cordis components to
`.bh-02/plugins/NAME.py` in the project, and the `extensions` row loads it within half a second,
again whenever it changes, and unloads it when it is deleted. An extension can add a slash
command for you, a status-bar field, text in the model's own prompt, or a tool the model is
offered, and nothing else: it runs in the extensions process, which the runner starts, as
confined as an input, and reaches bh-02 only through those four keys, each of which only adds (a
call to its tool runs in that process, and with `--no-jail` each call is put to you, shown by its name and arguments). Jailed, it loads without asking, as an input runs
without asking; with `--no-jail` each one is put to you first, with its source. The status bar's
`ext:` field lists them (`ext: todo ✓`), and `.bh-02/plugins/status.json` is what the model
reads to see whether one loaded. bh-02 reads those files with your permissions, so it follows no
link there: a link, a file with a second name (a hard link), or a link on the way (`.bh-02`, the
directory itself) is not read, since it could lead to a file the jail hides from the model, and
status.json (or, for a link on the way, the model's prompt) says what to write instead. The
plugin's README has the details.

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
