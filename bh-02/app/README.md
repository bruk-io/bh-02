# bh-02

The coding harness in a terminal app: a model (Claude through Claude Code on the Claude
subscription, or any OpenAI-compatible model you name, driven by bh-02's own loop) acts in
Python, through the tools rows register (the shipped one, `python`, runs in a jailed Python
process), inside a Textual TUI (`tui:ui`), with every part of the program a plugin that can be
replaced while it runs. `bh_02` is the shell: `cli.py` (the `bh-02` command), `bootstrap.py`
(`run()`: read every layer, boot, follow the chat row's `done`, unwind; its own `shell`, `host`
and `session` rows), `sessions.py` (a session is `$XDG_STATE_HOME/bh-02/sessions/<id>/`),
`outdated.py` (an earlier bh-02's layers in today's names), the layer file (`bh-02.toml`) and
`testing.py` (fake models). Every capability is a `*-cordis-plugin` workspace member
(`../plugins/`) that a layer names by string; no package imports another, and they agree on the
names and shapes in [`CONTRACTS.md`](../CONTRACTS.md). The words used here are in
[`GLOSSARY.md`](../GLOSSARY.md).

```
uv run bh-02                                       # a new session
uv run bh-02 --resume [ID]                         # continue this directory's newest session (or ID: all of it, its start, or its last part)
uv run bh-02 sessions                              # list them
uv run bh-02 --no-jail | --model NAME | --patch mine.toml | --trace trace.log
uv run bh-02 update-layer mine.toml                # rewrite a layer in today's row names (keeps mine.toml.bak)
```

[Get started](../../docs/bh-02/get-started.md) sets it up (the credential included), and
[Command line](../../docs/bh-02/reference/command-line.md) has every option and exit code. The
rest of the user guide is on the docs site: [Sessions](../../docs/bh-02/using/sessions.md),
[Commands](../../docs/bh-02/using/commands.md), [Models](../../docs/bh-02/using/models.md),
[Memory](../../docs/bh-02/using/memory.md), [The jail](../../docs/bh-02/using/jail.md) and
[Layers](../../docs/bh-02/using/layers.md) (patches, and layer files from an earlier bh-02).

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
| `conversation` | `agent:conversation` (`timeout`: 300) | |
| `shell-command` | `commands:shell_command` | |
| `status` | `tui:status` | |
| `grades` | `tui:grades` | |
| `palette` | `tui:palette` | |
| `model` | `models:model` (`default`: `sonnet`) | `default` (with `--model`, and as `/model` sets it); `state` (the session's `claude/`: Claude Code's own session, which a resume continues) |
| `models` | `models:catalog` | |
| `transcript` | `agent:transcript` | `path` (the session's `transcript.jsonl`) |
| `notes` | `agent:notes` | |
| `access` | `agent:access` | |
| `executor` | `agent:executor` | |
| `memory` | `memory:files` | |
| `on-touch` | `memory:on_touch` | |
| `memory-auto` | `memory:auto` | |
| `extensions` | `extensions:extensions` | |

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

So a new model or ui keeps the Python process and its namespace (the python row depends on the
runner and brokers that never reload), a new runner starts a new one, and a `/model` switch
keeps the conversation (`transcript` is a row of its own) and reloads neither `/model` nor the
status bar (they depend on `models`, not `model`).
[Rows and layers](../../docs/bh-02/how-it-works/rows-and-layers.md) says why each row is cut
where it is.

## The plugins

Each depends on the libraries (`cordis`, `cordis-helpers` for the patterns, `host-paths` for
where a file is and how it is reached) and on no other plugin; the gate proves it. Each README
has its rows' config and the keys' methods each one uses.

| Package | Binds / registers | Consumes |
|---|---|---|
| [`agent-cordis-plugin`](../plugins/agent-cordis-plugin/README.md) | `loop`, `tools`, `transcript`, `system`, `notes`, `access`, `executor`; `/clear` and `/compact` (`agent:conversation`) | `model`, `tools`, `transcript`, `system`, `approval`, `output`, `notes`, `executor`, `loader`, `commands`, `jobs` |
| [`chat-cordis-plugin`](../plugins/chat-cordis-plugin/README.md) | `done` (`chat:converse`, the chat itself) | `loop`, `input`, `output`, `commands`, `jobs` |
| [`commands-cordis-plugin`](../plugins/commands-cordis-plugin/README.md) | `commands` (the broker), `jobs`; `/rows`, `/explain`, `/restart` (`commands:operator`); the `!` prefix (`commands:shell_command`) | `output`, `commands`, `loader`, `jobs` |
| [`extensions-cordis-plugin`](../plugins/extensions-cordis-plugin/README.md) | nothing: loads the model's own plugins into the extensions process, whose additions go into `commands`, `frame`, `system` and `tools` | `runner`, `commands`, `frame`, `system`, `tools`, `approval`, `output` |
| [`memory-cordis-plugin`](../plugins/memory-cordis-plugin/README.md) | `memory` and `/memory` (`memory:files`); auto memory (`memory:auto`) and memory loaded on demand (`memory:on_touch`) | `system`, `commands`, `host`, `transcript`, `memory`, `notes`, `access` |
| [`models-cordis-plugin`](../plugins/models-cordis-plugin/README.md) | `model` (`models:model`: named models over the `claude-code` and `openai` providers), `models` (`models:catalog`), `/model` (`models:switch`) | `host`, `loader`, `commands`, `models`, `jobs` |
| [`python-cordis-plugin`](../plugins/python-cordis-plugin/README.md) | nothing: registers the `python` tool and its `system` section, over a persistent Python process in the runner (`python:tool`) | `runner`, `approval`, `tools`, `system`, `access` |
| [`runner-cordis-plugin`](../plugins/runner-cordis-plugin/README.md) | `runner` (`runner:confined`, a brig jail per start, or `runner:unconfined`), `approval` (`runner:approval`), `/release` (`runner:release`) | `host`, `runner`, `commands` |
| [`tui-cordis-plugin`](../plugins/tui-cordis-plugin/README.md) | `input`, `output`, `frame` (`tui:ui`); the status bar's fields (`tui:status`, `tui:grades`) and the palette (`tui:palette`) | `loader`, `models`, `session`, `runner`, `approval`, `commands`, `frame`, `output` |

## Where the rest is

- How it works: [the loop](../../docs/bh-02/how-it-works/loop.md) (every model under one loop,
  steps classified), [the python tool](../../docs/bh-02/how-it-works/python-tool.md) (CodeAct,
  the namespace, startup files), [the prompt and notes](../../docs/bh-02/how-it-works/prompt-and-notes.md),
  [the jail and approval](../../docs/bh-02/how-it-works/jail-and-approval.md).
- [The model's extensions](../../docs/bh-02/extending/extensions.md): the plugins the model
  writes to `.bh-02/plugins/` while bh-02 runs.
- [Writing a plugin](../../docs/bh-02/extending/plugins.md): the shape, a component, and the fake
  models in `bh_02.testing` for a launch without a login; `../CLAUDE.md` has the rules a plugin
  in this repository keeps.
- The credential's rules: the [models plugin's README](../plugins/models-cordis-plugin/README.md);
  the jail's policy: the [runner plugin's](../plugins/runner-cordis-plugin/README.md).
