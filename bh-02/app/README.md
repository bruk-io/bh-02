# bh-02

The coding harness in a terminal app: a model (Claude through Claude Code, with a subscription
token or a company gateway, or any OpenAI-compatible model you name, driven by bh-02's own loop) acts in
Python, through the tools rows register (the shipped one, `python`, runs in a jailed Python
process), inside a Textual TUI (`tui:ui`), with every part of the program a plugin that can be
replaced while it runs. `bh_02` is the shell: `cli.py` (the `bh-02` command), `bootstrap.py`
(`run()`: read every layer, boot, follow the chat row's `done`, unwind; its own `shell`, `host`
and `session` rows), `sessions.py` (a session is `$XDG_STATE_HOME/bh-02/sessions/<id>/`, which holds `rows.jsonl`: the rows that
reloaded or failed, which the shell hears and queues to a thread),
`watching.py` and `trajectory.py` with `viewing.py` (`bh-02 watch` and `bh-02 trajectory`, which read a session's files),
the layer file (`bh-02.toml`) and `testing.py` (fake models). Every capability is a `*-cordis-plugin` workspace member
(`../plugins/`) that a layer names by string; no package imports another, and they agree on the
names and shapes in [`CONTRACTS.md`](../CONTRACTS.md). The words used here are in
[`GLOSSARY.md`](../GLOSSARY.md).

```
uv run bh-02                                       # a new session
uv run bh-02 --resume [ID]                         # continue this directory's newest session (or ID: all of it, its start, or its last part)
uv run bh-02 sessions                              # list them
uv run bh-02 trajectory [ID] [--follow]             # a session laid out in time: replies, steps, calls, sub-agents
uv run bh-02 check-examples FILE...                # a startup file's docstring examples, with no session (exit 1 on a finding)
uv run bh-02 --no-jail | --model NAME | --patch mine.toml | --trace trace.log
uv tool install --editable ./bh-02/app --reinstall # an installed bh-02, after a pull that adds or renames a plugin
```

[Get started](../../docs/bh-02/get-started.md) sets it up (the credential included), and
[Command line](../../docs/bh-02/reference/command-line.md) has every option and exit code. The
rest of the user guide is on the docs site: [Sessions](../../docs/bh-02/using/sessions.md),
[Commands](../../docs/bh-02/using/commands.md), [Models](../../docs/bh-02/using/models.md),
[Memory](../../docs/bh-02/using/memory.md), [The jail](../../docs/bh-02/using/jail.md) and
[Layers](../../docs/bh-02/using/layers.md) (patches, and what a layer that names something bh-02
doesn't have gets).

## The compositions

`bh-02.toml` is the harness; every other file is a layer over it: the session's own layer
(`sessions.session_layer`), and `--patch`.

| Row | `bh-02.toml` | a session's layer |
|---|---|---|
| `loop` | `agent:loop` | |
| `tools` | `agent:tools` | |
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
| `conversation` | `agent:conversation` (`timeout`: 300; `clear`: `loop`, `transcript`, `python`, `agents`) | |
| `shell-command` | `commands:shell_command` | |
| `status` | `tui:status` | |
| `grades` | `tui:grades` | |
| `palette` | `tui:palette` | |
| `model` | `models:model` (`default`: none, so the models file's `default`, else no model) | `default` (with `--model`, and as `/model` sets it); `state` (the session's `claude/`: Claude Code's own session, which a resume continues) |
| `models` | `models:catalog` | |
| `transcript` | `agent:transcript` | `path` (the session's `transcript.jsonl`) |
| `asides` | `agent:asides` | |
| `access` | `agent:access` | |
| `executor` | `agent:executor` | |
| `memory` | `memory:files` | |
| `on-touch` | `memory:on_touch` | |
| `memory-auto` | `memory:auto` | |
| `extensions` | `extensions:process` | |
| `agents` | `subagents:parent` (`rows`: the parent's rows a child is made of; `tools`: those a type may grant, `["python"]`; `start`: 30; `max_running`: 4; `session_agents`: 16) | |
| `agents-status` | `subagents:status` | |

`run()` adds three rows of its own after every layer, pinned on (`disabled = false`) so no layer
can remove them: `host` (what the host is: the layer files as `paths`, where the credential is
looked for as `credentials`, what no input may read as `secrets`, bh-02's config directories as
`trusted`, its own code as `code`, and the project's auto memory directory as `auto_memory`;
[`CONTRACTS.md`](../CONTRACTS.md) has each field, and the runner plugin's README what the jail
does with them), `session` (the running session, whose id the status bar shows) and `shell`
(which follows the chat row's `done`, across a restart of the chat row).

A row's `id` is its role; `use` is `plugin:component`, a `cordis.plugins` entry point, or
`module:attribute`. Order in a file means nothing; dependencies decide what starts when. The
layer files are live: [Layers](../../docs/bh-02/using/layers.md) has how, and the runner
plugin's README ("When the host undoes a mount") what a save does to a jail on Linux.

A layer (the shipped one, a session's or a `--patch` file) that names a row or a `use` bh-02 no
longer has fails at boot: bh-02 renames its own and translates nothing, so it exits with code 1
and the loader's error, which names the row, the `use` it wrote and the plugins installed, and
the layer is the one to change. After a pull that renames a plugin, install again with
`--reinstall`, since plugins are read from what is installed.

`run()` says that before it mounts a row, because the ui row depends on nothing and would draw the
app first: it reads the layers, refuses a row with no `use` that no layer below it added (a
`LayerError` naming the file, the row and what to add; cordis's `compose` would raise a
ValueError), and resolves every enabled row's `use` (a `NotStarted`, in the words the loader gives
an unresolved row). A row that is waiting on a key no row binds, or whose component fails, is
known only by starting rows, so the ui may draw before that error: holding the ui until the chat
row's dependencies are active would make it depend on them, and a `/model` switch would reload it
with them. A resumed session that does not come up is kept and not offered a resume (it would fail
the same way): the command line says it did not start and where its own layer is.

`main` holds the session for the whole run (`sessions.held`, entered in `cli._session`): an exclusive
`flock` on `running.lock` in the session's directory, with the process's pid written there, taken
for a new session right after it is made and for a resumed one before its layer is read or `--model`
rewrites it. A second run of the same session finds it taken and is refused (`sessions.Held`, said
as `error: ...`, exit code 1) before any row starts, naming the pid. The operating system drops the
lock with the process, so a crash leaves nothing to clear, and the descriptor is not inherited, so
no child outlives the run holding it. The commands that only read a session (`sessions`,
`trajectory`, `watch`) never take it; `watch` asks `sessions.running`, which reads the pid in the file
and whether that process is alive (a lock tried and let go at once would make a bh-02 starting then find
the session held), and ends its follow, saying so, when the run is gone and the agent's log has no end.

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
agent:asides            binds Asides                       depends on nothing
agent:access            binds Access                       depends on nothing
agent:executor          binds Executor                     depends on nothing
agent:tools             binds Tools                        depends on nothing
agent:loop              binds Loop                         depends on Model, Tools, Transcript, System, Approval, Output, Asides, Executor
agent:conversation      registers /clear, /compact         depends on Model, Tools, Loader, Commands, Output, Jobs (the transcript row's file, not Transcript)
memory:files            binds Memory, registers /memory    depends on System, Commands, Host
memory:on_touch         adds memory loaded on demand       depends on Memory, Asides, Transcript, Access
memory:auto             adds auto memory to System, registers the memory tool  depends on System, Host, Transcript, Tools
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
extensions:process   loads the model's own plugins      depends on Runner, Commands, Frame, System, Tools, Approval, Output
subagents:status        pushes the agents field            depends on Roster, Frame
subagents:parent        binds Asker, Roster, registers agent tools depends on Tools, System, Output, Loader, Host, Commands, Model (each call mounts a child; /agents; a Model reload ends them; see below)
```

A sub-agent (`agent`, the agents row) is not a row of these layers: each call mounts one child
under the agents row, a sealed cordis realm whose own loader runs copies of `loop`, `tools`,
`transcript`, `model`, `system`, `asides`, `access`, `memory`, `on-touch`, `executor` and `python` as the
parent's loader mounted them, each under `agents/NAME/` (its transcript in the session's
`agents/NAME/`), plus a `commands:registry` of its own (for `memory`), `subagents:output` (its `output`: a
`confirm` over `asker`, labelled) and `subagents:child` (its type's section of the prompt); never
`memory-auto`; of the tool rows a type may grant, only its type's. Its type is data: shipped (`explore`, `general`) or the person's, `agents/NAME.toml` in
bh-02's config directory (`host.trusted`). From outside it reads only `runner`, `approval`,
`host` and `asker`. It runs in the foreground, or in the background for `agent_wait`, at most
`max_running` at once, until its type's step limit; past `session_agents`, or naming a model
other than its type's, its start is asked first. It is retired when it answers, when the call is
stopped (Ctrl-C; a background child is not), by `agent_stop` or `/agents stop`, or with the agents row (a `/clear`, a `/model` switch or a restart of it), and what it used joins
the session's totals; the ui shows none of its rows' lifecycle, and `--trace` keeps them. Its events go to the session's `agents/NAME/events.jsonl` (0600, under `host.secrets`), which `bh-02 watch SESSION NAME` follows read-only and `/agents watch NAME` names the command for; the status bar's `agents: N running` field is the `subagents:status` row's ([subagents-cordis-plugin](../plugins/subagents-cordis-plugin/README.md)).

So a new model or ui keeps the Python process and its namespace (the python row depends on the
runner and brokers that never reload), a new runner starts a new one, and a `/model` switch
keeps the conversation (`transcript` is a row of its own) and reloads neither `/model` nor the
status bar (they depend on `models`, not `model`).
[Rows and layers](../../docs/bh-02/how-it-works/rows-and-layers.md) says why each row is cut
where it is.

## Reading a session: `bh-02 trajectory`

A session's trajectory is its record laid out in time, and it is stored nowhere: the transcript's
entries carry when they came, how long each step and call took, who answered a call's question, what
a step cost and which sub-agent a call started (decision-0009; [`CONTRACTS.md`](../CONTRACTS.md),
step record and call record), and `bh-02 trajectory [ID]` reads them back. It is split like the loop
is, a pure core and a thin shell:

- `trajectory.py` is pure. `trajectory(conversations, rows)` takes the bytes of the transcript files
  (the session's own, and each sub-agent's) and of the session's `rows.jsonl` and returns frozen
  dataclasses: a session's conversations
  in order (the live `transcript.jsonl` last, the backups `/clear` and `/compact` kept before it by their
  first `at`, else their modification time), each with its replies, their steps and calls, and
  each sub-agent under the call that started it, or after the conversations by its own times when no
  call names it, and its row reloads by time, each marked `first` when its row id is not in the records
  before it (cordis has no first-load event, so a row's first load is recorded as a `reload`). `rendered`
  lays it out as lines, in local time, with every control character stripped, each row reload a line of
  its own before the first line that came after it, among the lines of the writer whose row it is (the
  session's, or the sub-agent's for `agents/NAME/...`), except that first loads which follow one another
  there, with no reload, failure or line of that writer's between, are one line (`row first load`, how
  many rows and the time from the first to the last): the session's boot, and a sub-agent's rows coming
  up, under its `sub-agent` line. While following, a run of them at the very end waits for something
  after it, so it is printed once with its final count.
  `bh_02` imports no plugin (`plugin-layering`), so it reads the entries as TypedDicts of its own; a
  test holds them to what the agent plugin's loop writes (`test_trajectory_records.py`). A line that is
  not a JSON object (the loop's half-written last line) is skipped, a field that is missing or of the
  wrong type is left out.
- `viewing.py` is the shell: it lists a session's directory and reads each file, `rows.jsonl` included, through
  `host_paths` (`directory_beneath`, `read_beneath`: beneath the sessions' state, through no link, with a
  cap), takes a sub-agent only from the names in `agents/` that `bh-02 watch` would accept, and runs the
  `--follow` loop. A follow re-reads every file by its path every second and prints the lines whose
  `Line.key` it has not printed, so a `/clear` or `/compact` that replaced the live file is simply new;
  no offset into a file is kept. A call whose result is not written yet is held back while following (it
  may be running).
- `cli.py` finds the session as `--resume` does (`sessions.find`, `sessions.chosen`) and prints.

What it does not show yet: the raw request, which needs the agent plugin's pure projection functions
in a library both may import.

The row reloads are kept by the shell, not read from the transcript: `run()` appends a listener to the
runtime beside `--trace`'s (`_row_log`), which hears every row's lifecycle event, sub-agents' rows
(`agents/NAME/...`) included, and for the two that count queues a line to `host_paths.Appender`, which
writes it on a thread at 0600, so the event loop never waits on a disk. `reload` is a row's setup
beginning (it came up, was restarted, or a dependency was replaced) and `failed` its setup raising,
with the error; cordis emits no `restart`, a restarted row's old fiber ends `unloading` and `inactive`
and the new one begins with a `reload`; so does a row's first load, which the file does not mark, and
the trajectory tells it by the row id (a row's first record in the file). A write that fails ends the
log and not the run, and the shell says so once after the app has exited: the file, when its first
write failed (the appender keeps that time), and the error. `--trace FILE` is the same stream in full, untimed and written on the
loop, and stays as it was.

## The plugins

Each depends on the libraries (`cordis`, `cordis-helpers` for the patterns, `host-paths` for
where a file is and how it is reached) and on no other plugin; the gate proves it. Each README
has its rows' config and the keys' methods each one uses.

| Package | Binds / registers | Consumes |
|---|---|---|
| [`agent-cordis-plugin`](../plugins/agent-cordis-plugin/README.md) | `loop`, `tools`, `transcript`, `system`, `asides`, `access`, `executor`; `/clear` and `/compact` (`agent:conversation`) | `model`, `tools`, `transcript`, `system`, `approval`, `output`, `asides`, `executor`, `loader`, `commands`, `jobs` |
| [`subagents-cordis-plugin`](../plugins/subagents-cordis-plugin/README.md) | `asker`, the `agent`, `agent_wait`, `agent_send` and `agent_stop` tools and `/agents` (`subagents:parent`); inside a child's realm, its `output` (`subagents:output`) and its type's section (`subagents:child`) | `tools`, `system`, `output`, `loader`, `host`, `commands`, `model`; in a child, `asker`, `loop`, `system` |
| [`chat-cordis-plugin`](../plugins/chat-cordis-plugin/README.md) | `done` (`chat:converse`, the chat itself) | `loop`, `input`, `output`, `commands`, `jobs` |
| [`commands-cordis-plugin`](../plugins/commands-cordis-plugin/README.md) | `commands` (the broker), `jobs`; `/rows`, `/explain`, `/restart` (`commands:operator`); the `!` prefix (`commands:shell_command`) | `output`, `commands`, `loader`, `jobs` |
| [`extensions-cordis-plugin`](../plugins/extensions-cordis-plugin/README.md) | nothing: loads the model's own plugins into the extensions process, whose additions go into `commands`, `frame`, `system` and `tools` | `runner`, `commands`, `frame`, `system`, `tools`, `approval`, `output` |
| [`memory-cordis-plugin`](../plugins/memory-cordis-plugin/README.md) | `memory` and `/memory` (`memory:files`); auto memory and its `memory` tool (`memory:auto`) and memory loaded on demand (`memory:on_touch`) | `system`, `commands`, `host`, `transcript`, `tools`, `memory`, `asides`, `access` |
| [`models-cordis-plugin`](../plugins/models-cordis-plugin/README.md) | `model` (`models:model`: named models over the `claude-code` and `openai` providers), `models` (`models:catalog`), `/model` (`models:switch`) | `host`, `loader`, `commands`, `models`, `jobs` |
| [`python-cordis-plugin`](../plugins/python-cordis-plugin/README.md) | nothing: registers the `python` tool and its `system` section, over a persistent Python process in the runner (`python:tool`) | `runner`, `approval`, `tools`, `system`, `access` |
| [`runner-cordis-plugin`](../plugins/runner-cordis-plugin/README.md) | `runner` (`runner:confined`, a brig jail per start, or `runner:unconfined`), `approval` (`runner:approval`), `/release` (`runner:release`) | `host`, `runner`, `commands` |
| [`tui-cordis-plugin`](../plugins/tui-cordis-plugin/README.md) | `input`, `output`, `frame` (`tui:ui`); the status bar's fields (`tui:status`, `tui:grades`) and the palette (`tui:palette`) | `loader`, `models`, `session`, `runner`, `approval`, `commands`, `frame`, `output` |

## Where the rest is

- How it works: [the loop](../../docs/bh-02/how-it-works/loop.md) (every model under one loop,
  steps classified), [the python tool](../../docs/bh-02/how-it-works/python-tool.md) (CodeAct,
  the namespace, startup files), [the prompt and asides](../../docs/bh-02/how-it-works/prompt-and-asides.md),
  [the jail and approval](../../docs/bh-02/how-it-works/jail-and-approval.md).
- [The model's extensions](../../docs/bh-02/extending/extensions.md): the plugins the model
  writes to `.bh-02/plugins/` while bh-02 runs.
- [Writing a plugin](../../docs/bh-02/extending/plugins.md): the shape, a component, and the fake
  models in `bh_02.testing` for a launch without a login; `../CLAUDE.md` has the rules a plugin
  in this repository keeps.
- The credential's rules: the [models plugin's README](../plugins/models-cordis-plugin/README.md);
  the jail's policy: the [runner plugin's](../plugins/runner-cordis-plugin/README.md).
