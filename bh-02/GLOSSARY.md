# Glossary

The words you meet using or changing bh-02, one line each. bh-02 is built on cordis and keeps
cordis's words as cordis defines them; the rest are bh-02's own. [`CONTRACTS.md`](CONTRACTS.md)
has the exact shapes, [`app/README.md`](app/README.md) the rows as shipped, and the page a line
links to the detail.

## cordis's words

As [cordis's README](../libs/cordis/README.md) defines them (its "Concepts").

- **plugin**: a package that ships components, found through its `cordis.plugins` entry point (`tui`, `agent`, `python`, `runner`, ...).
- **component**: a recipe for one part of the program: what it needs, and the effects it yields; a layer names one as `plugin:component` (`agent:loop`).
- **row**: one entry of a composition: `id` (its role), `use` (which component fills it), `config`, `disabled`.
- **layer**: a TOML file of rows, as `[[plugin]]` tables, applied in order over the layers before it ([Layers](../docs/bh-02/using/layers.md)).
- **loader**: the part of cordis that reads the layers, starts the rows, and swaps only what changed when a layer file is edited; its handle is bound as `loader`.
- **key**: the name a value is bound under, and the name of the parameter a component reads it by; two plugins agree on a key by name, never by importing each other.
- **binding** (`bind`): a value held under a key, for as long as the row that bound it is up.
- **dependency**: a key a component needs: it runs only while every one is bound, and reloads when one is replaced.
- **provider**, **consumer**: the row that binds a key, and a row that depends on it (not a **model provider**, below).
- **contract**: the shape a component asks of a dependency: a Protocol of its own, checked when the value arrives.
- **effect**: one step a component yields, with its undo: `bind`, `acquire`, `enter`, `use`, `background`, `performer`, `observe`.
- **undo**: the other half of an effect, which reverses its step (unbinds the key, calls the remover, exits the context); a row's undos run in reverse order when it goes.
- **provides=**: the keys a component declares it binds (`@component(provides=(...))`), checked, not inferred.
- **unresolved** (row): a row whose plugin's module failed to import; it is reported, never fatal to the rest.
- **acquire**: an effect that calls a registration and keeps the **remover** it returns (the function that takes the entry back out), called when the row goes.
- **broker**: one row binds a registry; others register into it with `acquire`, and leave without reloading anyone (`commands`, `frame`, `tools`).
- **fiber**: a component running as a row, with a state: loading, active, unloading, inactive, failed.
- **lifecycle event**: what a fiber just did (`reload`, `bind`, `active`, `unloading`, `inactive`, `failed`); `observe` hears them, `--trace` writes them.
- **reload** and **restart**: a row started again because its layer changed or a dependency was replaced (reload), or because an operator asked (`restart`, as `/clear` does).

## bh-02's words

- **bh-02**: the coding harness: a terminal app where a model works by writing Python.
- **harness**: a program around a model that runs its loop and its tools and decides what it may do; bh-02 is one, built on cordis.
- **harness** (the project): a separate project of the repository's owner whose `ARCHITECTURE.MD` gave bh-02 CodeAct and its step table: "harness's rule", never read a truncated or silent step as the answer (`stops.classify`).
- **DeepSeek Harness**: the agent harness built on the paper cordis realises (cordis's README); its account of tool registries, tool changes and model-written plugins informed bh-02's designs.
- **the harness's** (a line): bh-02's rather than the model's: a slash command, or a line with a prefix a row claimed, as `commands` decides (`claims`).
- **harness** (row): the shell's pinned row before it was `shell` (`bh_02.bootstrap:harness`); `update-layer` renames it.
- **harness** (in brig's docs and tests): the program that starts the jails, such as bh-02; in brig's tests, the test run itself (`harness_pid`).
- **the shell**: `bh_02` (`app/`): the `bh-02` command, which reads the layers, boots them and waits for the chat to end.
- **layer files**: `bh-02.toml` (the whole harness), a session's `session.toml`, and your `--patch` files, applied in that order.
- **stack** (a session's): the model a session started on, kept in its `meta.json` and listed by `bh-02 sessions` (an earlier bh-02's session: `claude` or `ollama`); not always the model that answered.
- **stack** (brig's): the mechanisms brig composes into one jail; bh-02's runner uses `scratch_darwin()` (Seatbelt) on macOS and `strict_linux()` (bubblewrap) on Linux (`stack_for`).
- **first stack**, **second stack**, **Ollama stack**: how an earlier bh-02 reached a model: Claude Code's own loop through the Claude Agent SDK, the Messages API with the subscription token (`anthropic:completion`, which only Haiku answered), and Ollama's own row (`--ollama`) ([Sessions](../docs/bh-02/using/sessions.md#resuming)).
- **stack** (a fiber's, in cordis): the undos a fiber has recorded, run last first when it unloads.
- **loop** (row and key): the agent loop, `agent:loop`: sends the conversation to the model, runs each call it asks for through its tool, and nudges a step that didn't count ([The loop](../docs/bh-02/how-it-works/loop.md)).
- **model** (row and key), **the model row**: the model itself, one step at a time (`models:model`), the one its `default` names, chosen by `--model NAME` or `/model NAME` (an earlier bh-02's `completion` row).
- **named model**: a name the model row can take, with its provider and id: the built-ins `sonnet`, `opus` and `haiku`, and yours in the models file.
- **model provider** (a model's `provider` field): what reaches a model: `claude-code` (Claude through Claude Code, on the subscription) or `openai` (any OpenAI-compatible endpoint).
- **models file**: `~/.config/bh-02/models.toml` (`$XDG_CONFIG_HOME/bh-02/models.toml`): your models, one table each, read only from outside the project ([Models](../docs/bh-02/using/models.md#adding-your-own-the-models-file)).
- **models** (row and key): `models:catalog`: the models there are and which one the model row names, for `/model` and the status bar.
- **step**: one call to the model: it answers, or asks for calls to run.
- **nudge**: the loop telling the model why its last step didn't count (cut off, silent, unreadable), a bounded number of times.
- **transcript** (row and key): the conversation the model is sent again each step, kept in the session's `transcript.jsonl`.
- **the model's context**: what the model reads each step: the system prompt and the transcript, never the namespace.
- **chat** (row): `chat:converse`: reads your messages, shows the replies, runs the lines `commands` claims (slash commands, `!`), and binds `done`, which ends when you leave.
- **turn**: one reply to one message, however many model steps and inputs it takes.
- **event**: one thing that happened in a turn, a dict with a `type` (`text`, `thinking`, `tool_call`, `tool_result`, `usage`, `stop`, `note`, `cleared`, `restarting`) that the ui draws; [`CONTRACTS.md`](CONTRACTS.md) has each shape.
- **note**: a line shown to you, never to the model: in the app, the `note` event (a command's answer, a row reloading, or what the loop told the model as an aside, by its first line); from the command line, a line it prints starting `note:`. In bh-02 a note means only this.
- **aside**: text bh-02 tells the model beside what it reads, never a message of its own: with a call's result, what rows add to `asides` (memory that loads on demand) and the python tool's own before an input's output (what its startup files did); with the next message the model reads, a change in its instructions or its tools. The transcript keeps each, so a resumed conversation knows what it was told ([The prompt and asides](../docs/bh-02/how-it-works/prompt-and-asides.md)).
- **chunk**: an event from one model step.
- **`for_model`**: what a command's answer leaves for the model (`!COMMAND`'s output), which `commands` holds, never shown, until your next message.
- **CodeAct**: how the model works in bh-02: it acts by writing Python, which the `python` tool carries to the Python process, and only what an input prints enters its context ([The python tool](../docs/bh-02/how-it-works/python-tool.md)).
- **tool**: what the model may call through its provider's standard tool calling: a spec (name, description, parameters) a row registers with `tools`, and the function that runs a call.
- **call**: one use of a tool, answered with its result.
- **tools** (row and key): `agent:tools`, the broker tools register with; the loop offers what is registered.
- **tool list**: the tools a conversation is offered: the ones it began with, read at its first request and kept in its transcript ([The loop](../docs/bh-02/how-it-works/loop.md)).
- **tool change**: a tool added, removed or redefined mid-conversation, told to the model as an aside on its next message; an added one is offered from the next conversation.
- **python** (the tool): `python(code)`, the tool bh-02 ships: each call runs its code as an input in the Python process, and what the input printed is the result.
- **tools** (in an input): the namespace's view of bh-02's other tools, each a function, `tools.NAME(arg=...)`, whose call runs as the model's own would.
- **input**: one `python` call: the code the model sent the Python process and what it printed (not a cell: there is no notebook; not the `input` key, below).
- **Python process**: the process the runner starts to run inputs and keep the namespace for the run; to the model, a Python REPL of its own that persists.
- **namespace**: what the inputs have defined in the Python process (variables, functions, imports): the model's working state for the run, and a cache, since the transcript is the record.
- **python** (row): `python:tool`, bh-02's handle on the Python process, which registers the `python` tool; its class is still `Kernel`, an older name (not Jupyter's kernel, which is the process itself).
- **extensions process**: the process the model's extensions run in, the second one the runner starts.
- **worker**: an older word, still in some messages and in the code (`worker.py`), for a process the jail started: the Python process or the extensions process.
- **startup file**: Python a new, confined Python process runs before its first input: yours (`$XDG_CONFIG_HOME/bh-02/kernel.py`, else `~/.config/bh-02/kernel.py`), then the project's `.bh-02/kernel.py` ([The python tool](../docs/bh-02/how-it-works/python-tool.md)).
- **runner** (row and key): what starts the Python process and the extensions process, each in a brig jail (`runner:confined`) or in none (`runner:unconfined`, `--no-jail`); not part of CodeAct, but what bh-02 runs it in.
- **jail**: brig's sandbox around one program the confined runner started; its grades say what it enforces.
- **confined**, **unconfined**: whether the runner enforces writes and network, so the model's code runs without asking (`jailed` in the status bar), or not, so each input is put to you first (`unjailed`).
- **grades**: how well each part of the jail holds (`enforced`, `best_effort`, `cooperative`, `unenforced`), shown in the status bar as ✓, ~, ? and ✗.
- **placeholder** (Linux): an empty directory the jail makes in the project to hold a path an input may not create (`.envrc/`, `.claude/`), removed when the jail ends ([The jail](../docs/bh-02/using/jail.md#on-linux)).
- **tripwire** (Linux): the jail ending itself at once when the host replaces, moves or removes a path it holds with a mount ([The jail](../docs/bh-02/using/jail.md#on-linux)).
- **release** (row): `runner:release`: `/release`, which stops the Python process and the extensions process until the next input and frees what their jails held.
- **approval** (row and key): `runner:approval`, the one rule for whether what the model asked for runs unasked; what it doesn't let run is put to you ([The jail and approval](../docs/bh-02/how-it-works/jail-and-approval.md)).
- **the modal**: the question the model's code is put to you in when it is unjailed: `y` runs it, `n` or Esc doesn't.
- **host**: the side outside the jail: bh-02's own process and brig's host process, whose import paths, environment and files a jailed input can't reach.
- **composer**: the box along the bottom of the app where you type a message or a command.
- **ui** (row): `tui:ui`, the Textual app: it binds `input`, `output` and `frame`, and depends on nothing, so it never reloads.
- **input**, **output** (keys): what the chat reads your lines from and shows replies, notes and questions through; the ui binds both.
- **port**: a word in the tui plugin's code (`ports.py`): the values the ui binds for other rows, `input`, `output` and `frame`.
- **frame** (key): the app around the conversation, a broker rows push status bar fields and palette commands into.
- **status** (row): `tui:status`: the status bar's session id and model (the `usage` field is the ui's own).
- **grades** (row): `tui:grades`: the status bar's `jail` field, the grades of the runner's last start, `jailed` or `unjailed` by the approval rule.
- **status bar**: the line along the bottom: session, model, jail, usage; narrower forms when the terminal is narrow.
- **palette** (row): `tui:palette`: the commands, offered in the command palette (Ctrl-P).
- **commands** (row and key): the command broker: the slash commands rows register and the line prefixes rows in a layer claim (`!`); it says which lines are commands ([Commands](../docs/bh-02/using/commands.md)).
- **prefix**: a character a row in a layer claims in `commands`, so every line you start with it is that row's, never a message to the model (`!`).
- **`!COMMAND`**, **shell command** (row `shell-command`): `commands:shell_command`: a line starting with `!` runs in your shell, as you, not in the jail, and the model reads its output with your next message ([Commands](../docs/bh-02/using/commands.md#shell-commands-command)).
- **operator** (row): `commands:operator`: the commands that act on the running program through the loader.
- **jobs** (row and key): `commands:jobs`: the restarts commands ask for (`/clear`, `/compact`, `/model NAME`, `/restart`), run one at a time after the command answers.
- **switch** (row): `models:switch`: `/model`, which lists the models and switches by name in the session's layer.
- **system** (row and key): `agent:system`: the system prompt, a broker of the sections rows add ([The prompt and asides](../docs/bh-02/how-it-works/prompt-and-asides.md)).
- **memory** (row and key): `memory:files`: Claude Code's memory files, read as Claude Code reads them, as a section of the system prompt; `/memory` lists them ([Memory](../docs/bh-02/using/memory.md)).
- **auto memory** (row `memory-auto`): `memory:auto`: memories the model keeps for itself across conversations (a `MEMORY.md` index and a file per memory), as Claude Code's auto memory, outside the repository ([Memory](../docs/bh-02/using/memory.md#auto-memory)).
- **conversation** (row): `agent:conversation`: `/clear` and `/compact`, each a new conversation written over the transcript's file ([agent-cordis-plugin](plugins/agent-cordis-plugin/README.md)).
- **asides** (row and key): `agent:asides`: a broker of functions rows add, each of which may add an aside to a call's result.
- **notes** (row): the asides broker before it was `asides` (`agent:notes`); `update-layer` renames it.
- **access** (row and key): `agent:access`: a broker of functions rows add that a tool asks before it opens a file, each answering go ahead or why not.
- **executor** (row and key): `agent:executor`: where the loop reads the prompt and asks `asides`, in a thread off the app's event loop, one call at a time.
- **touched**: the files a call opened, as its tool answers (an input's: what its own Python code opened, `touched()`).
- **on-touch** (row): `memory:on_touch`: memory that loads on demand (a subdirectory's CLAUDE.md, a rule whose `paths` match), told whole as an aside to the first input in a conversation that opens a file it covers.
- **extension**: a plugin the model writes itself, `.bh-02/plugins/NAME.py` in the project, which bh-02 loads while it runs ([The model's extensions](../docs/bh-02/extending/extensions.md)).
- **extensions** (row): `extensions:extensions`, which loads the extensions into the extensions process.
- **run**: one launch of bh-02, from start to leaving; the Python process and its namespace last one run.
- **session**: what a run keeps under `$XDG_STATE_HOME/bh-02/sessions/<id>/` (its layer, transcript and history, not the namespace), so `--resume` continues it in a later run.
- **pinned** (row): one of the three rows the shell adds itself after every layer (`session`, `host`, `shell`), `disabled = false`, so no layer can remove it.
- **session** (row and key): `bh_02.bootstrap:session`, pinned: the running session, its id (`current`), which the status bar shows, and whether it was resumed (`resumed`).
- **host** (row and key): `bh_02.bootstrap:host`, pinned: what the host is: `paths`, `trusted` and `code` (no input may write them), `credentials` and `secrets` (no input may read them), and `auto_memory` (an input may write it).
- **shell** (row): `bh_02.bootstrap:shell`, pinned: the shell's wait for the chat's `done`, declared as a dependency so cordis checks it like any other.
- **done** (key): what the chat binds; the shell waits on it, and follows it across a restart of the chat row.
- **usage**: tokens and cost, per model step and summed for the session, in the status bar.
- **credential**: `CLAUDE_CODE_OAUTH_TOKEN` in `local.env` at the repository root, read by the model row alone ([models-cordis-plugin](plugins/models-cordis-plugin/README.md)).
- **fakes**: stand-in models in `bh_02.testing` that a `--patch` or a models file names, to run bh-02 without a login ([Writing a plugin](../docs/bh-02/extending/plugins.md#trying-it-without-a-login-fake-models)).
- **update-layer**: `bh-02 update-layer FILE`: rewrites a layer that names rows or components bh-02 renamed, merged or dropped, keeping `FILE.bak` ([Layers](../docs/bh-02/using/layers.md#layers-from-an-earlier-bh-02)).
- **gate**: the architecture check (pypeeker) that `scripts/check` runs: which packages may import which, and what must stay pure.
- **value half**, **wiring**: a plugin's two parts: the plain library (no cordis), and `wiring.py`, the components that bind it.
