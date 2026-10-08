# Glossary

The words you meet using or changing bh-02, one line each. bh-02 is built on cordis and keeps
cordis's words as cordis defines them; the rest are bh-02's own. [`CONTRACTS.md`](CONTRACTS.md)
has the exact shapes, [`app/README.md`](app/README.md) the rows as shipped.

## cordis's words

As [cordis's README](../libs/cordis/README.md) defines them (its "Concepts").

- **plugin**: a package that ships components, found through its `cordis.plugins` entry point (`tui`, `agent`, `kernel`, ...).
- **component**: a recipe for one part of the program: what it needs, and the effects it yields. A layer names one as `plugin:component` (`agent:loop`).
- **row**: one entry of a composition: `id` (its role), `use` (which component fills it), `config`, `disabled`.
- **layer**: a TOML file of rows, as `[[plugin]]` tables. Layers apply in order: a new id adds a row, a known id replaces that row's fields (a `config` replaces the whole config, it doesn't merge).
- **loader**: the part of cordis that reads the layers, starts the rows, and swaps only what changed when a layer file is edited. It binds its handle as `loader` (`status()`, `restart()`, `explain()`).
- **key**: the name a value is bound under, and the name of the parameter a component reads it by. Two plugins agree on a key by name, never by importing each other.
- **binding** (`bind`): a value held under a key, for as long as the row that bound it is up.
- **dependency**: a key a component needs. It runs only while every one is bound, and reloads when one is replaced.
- **provider**, **consumer**: the row that binds a key, and a row that depends on it. A provider just has the methods; the consumer states what it needs. (Not a **model provider**, below: what reaches a model.)
- **contract**: the shape a component asks of a dependency: a Protocol of its own, checked when the value arrives.
- **effect**: one step a component yields, with its undo: `bind`, `acquire`, `enter`, `use`, `background`, `performer`, `observe`.
- **undo**: the other half of an effect: what reverses its step (unbinds the key, calls the remover, exits the context). The runtime runs the undos, in reverse order, when the row goes.
- **provides=**: the keys a component declares it binds (`@component(provides=(...))`), checked, not inferred: a row that never binds one fails, and a dependency no row declares is reported before anything starts.
- **unresolved** (row): a row whose plugin's module failed to import; it is reported, never fatal to the rest.
- **acquire**: an effect that calls a registration and keeps the **remover** it returns (the function that takes the entry back out), called when the row goes.
- **broker**: one row binds a registry; others register into it with `acquire`, and leave without reloading anyone (`commands`, `frame`).
- **fiber**: a component running as a row, with a state: loading, active, unloading, inactive, failed.
- **lifecycle event**: what a fiber just did (`reload`, `bind`, `active`, `unloading`, `inactive`, `failed`); `observe` hears them, `--trace` writes them.
- **reload** and **restart**: a row started again because its layer changed or a dependency was replaced (reload), or because an operator asked (`restart`, as `/clear` does).

## bh-02's words

- **bh-02**: the coding harness: a terminal app where a model works by writing Python.
- **the shell**: `bh_02` (`app/`): the `bh-02` command, which reads the layers, boots them and waits for the chat to end.
- **layer files**: `bh-02.toml` (the whole harness), a session's `session.toml`, and your `--patch` files, applied in that order.
- **stack**: what a session started on, as `bh-02 sessions` lists it: the model's name (an earlier bh-02's session: `claude` or `ollama`).
- **loop** (row and key): the agent loop, `agent:loop`: sends the conversation to the model, runs each call it makes as an input, and nudges a turn that didn't count.
- **model** (row and key), **the model row**: the model itself, one step at a time (`models:model`), the one its `default` names. `/model NAME` switches it by name; `--model NAME` picks it at launch. An earlier bh-02 called it `completion`.
- **named model**: a name the model row can take, with its provider and id: the built-ins `sonnet`, `opus` and `haiku`, and yours in the models file.
- **model provider** (a model's `provider` field): what reaches a model: `claude-code` (Claude through Claude Code, on the subscription) or `openai` (any OpenAI-compatible endpoint: OpenAI, OpenRouter, Groq, Ollama's `/v1`, ...). The status bar shows it after the model's name.
- **models file**: `~/.config/bh-02/models.toml` (`$XDG_CONFIG_HOME/bh-02/models.toml`): your models, one table each (`provider`, `id`, `base_url`, and `key`, the name of a `local.env` line other than `CLAUDE_CODE_OAUTH_TOKEN`). `/model` lists them. It must be outside the project (not a link into it): one in it, which the model's code could write, is not read, and `/model` says why.
- **models** (row and key): `models:catalog`: the models there are and which one the model row names, for `/model` and the status bar.
- **step**: one call to the model: it answers, or asks for inputs to run. A turn is one step or more.
- **nudge**: the loop telling the model why its last step didn't count (cut off, silent, unreadable), a bounded number of times.
- **transcript** (row and key): the conversation the model is sent again each step, kept in the session's `transcript.jsonl`.
- **the model's context**: what the model reads each step: the system prompt and the transcript. Not the namespace, which it sees only through what inputs print.
- **chat** (row): `chat:session`: reads your messages, shows the replies, runs the lines `commands` claims (slash commands, `!`); it binds `done`, which ends when you leave.
- **turn**: one reply to one message, however many model steps and inputs it takes.
- **event**: one thing that happened in a turn, a dict with a `type` (`text`, `thinking`, `tool_call`, `tool_result`, `usage`, `stop`, `note`, `cleared`, `restarting`), which the ui draws; a **chunk** is the same from one model step. A command's answer may also carry `for_model` (`!COMMAND`'s output), which `commands` holds, never shown, until the chat puts it in front of your next message to the model. [`CONTRACTS.md`](CONTRACTS.md) has each shape.
- **CodeAct**: how the model works in bh-02. It acts by writing code, which the `python` tool carries to the Python process; the namespace keeps its data between inputs, and only what an input prints enters the model's context. bh-02 runs it inside the jail, and approval decides whether each input runs unasked.
- **python**, **the one tool**: the only tool the model is offered, `python(code)`: a standard tool whose one argument is code. Each call runs as an input in the Python process, which the jail started and which keeps its namespace for the run; what the input printed comes back as the result.
- **input**: one `python` call: the code the model sent the Python process, and what it printed. Not a cell: there is no notebook. (Not the `input` key, below.)
- **Python process**: the process that runs inputs and keeps the namespace for the run; the jail starts it. The model is told of it as a Python REPL of its own that persists. A new one starts empty: at launch and on a resume, after `/clear`, `/release` or `/restart kernel`, and when the last one died or its jail ended it.
- **namespace**: what the inputs have defined in the Python process (variables, functions, imports): the model's working state. It lasts the run, across `/model` and `/compact`, not the session; the model sees none of it but what an input prints, and it is a cache: the transcript is the truth.
- **kernel** (row and key): `kernel:kernel`, bh-02's handle on the Python process: it starts it through the jail, sends it each input, starts it again when it died, and runs the startup files. It also carries the `python` tool's spec and instructions, and passes on its jail's grades and `/release`. The name is older than "Python process" (and is not Jupyter's kernel, which is the process itself).
- **extensions process**: the process the model's extensions run in, the second one the jail starts; `/release` stops it, and they load again after the next input.
- **worker**: an older word, still in some messages and in the code (`worker.py`), for a process the jail started: the Python process or the extensions process.
- **startup file**: Python a new Python process runs before its first input, when it is confined: yours (`$XDG_CONFIG_HOME/bh-02/kernel.py`, else `~/.config/bh-02/kernel.py`), for helpers in every project, then the project's `.bh-02/kernel.py`, the only one the model is told it may edit; unconfined, the model is told to run them as inputs, which you are asked about.
- **jail** (row and key): what starts the Python process and the extensions process: `brig:jail` confines them (no writes outside the project, no network, no credentials); `kernel:unjailed` (`--no-jail`) does not. Not part of CodeAct: what bh-02 runs it in.
- **confined**: the jail enforces writes and network, so an input (or an extension's load) runs without asking; unconfined, each is put to you first. The status bar says `jailed` or `unjailed`.
- **grades**: how well each part of the jail holds (`enforced`, `best_effort`, `cooperative`, `unenforced`), shown in the status bar as ✓ and ✗.
- **placeholder** (Linux): an empty directory the jail makes in the project, on the host, to hold a path an input may not create (`.envrc/`, `.claude/`, `.git/` in a project that is no repository) for as long as the jail runs; removed after. Removing one yourself meanwhile ends the jail (see **tripwire**).
- **tripwire** (Linux): the jail watching every path it holds with a mount; when the host replaces, moves or removes one (a host `git config` rewrites `.git/config` that way; editors save by rename), which lifts that hold, the jail ends itself at once and the next input's jail holds the path again, telling you why the namespace is gone.
- **release** (row): `kernel:release`: `/release` stops the Python process until the next input, and with it the jail, which stops the extensions process too (they load again after that input) and frees its placeholders: on Linux, how you add your credential (`local.env`) mid-session where the jail holds that path.
- **approval** (row and key): `kernel:approval`, the one place that decides whether the model's code runs: an input (the loop asks) or an extension to load (the extensions row asks). Confined, at once; unconfined, it asks you in the modal. Only a layer replaces it.
- **the modal**: the question the model's code is put to you in when it is unjailed: `y` runs it, `n` or Esc doesn't. It ignores keys for its first 0.4 s, so typing can't answer it.
- **host**: the side outside the jail: bh-02's own process (and brig's host process, which starts the Python process and the extensions process), whose import paths, environment and files a jailed input can't reach; the `kernel` row's `client.py` is its end of the Python process's socket.
- **composer**: the box along the bottom of the app where you type a message or a command; the palette puts a command that takes arguments there to finish.
- **ui** (row): `tui:app`, the Textual app. It binds `input`, `output` and `frame`, and depends on nothing, so it never reloads.
- **input**, **output** (keys): what the chat reads your lines from and shows replies, notes and questions through; the ui binds both.
- **port**: a word in the tui plugin's code (`ports.py`): the values the ui binds for other rows, `input`, `output` and `frame`.
- **frame** (key): the app around the conversation, which rows push into: status bar fields and palette commands. A broker.
- **status** (row): `tui:status`: the status bar's session id, model and jail grades. The `usage` field is the ui's own.
- **status bar**: the line along the bottom: session, model, jail, usage; narrower forms when the terminal is narrow.
- **palette** (row): `tui:palette`: the commands, offered in the command palette (Ctrl-P).
- **commands** (row and key): the command broker: `/help`, `/rows`, `/explain`, `/restart`, `/clear`, `/model`, any a row registers (`/release`, `/compact`), and the prefixes rows in a layer claim (`!`); it says which lines are commands.
- **prefix**: a character a row in a layer claims in `commands`, so every line you start with it is that row's, never a message to the model (`!`); one row each, and never an extension.
- **`!COMMAND`**, **shell command** (row `shell-command`): `commands:shell_command`: a line starting with `!` runs in your shell, as you (not in the jail), in the project; what it printed is shown, and the model reads it with your next message (`commands` holds it meanwhile, so a `/model` switch and a `/compact` keep it; `/clear` drops it). Ctrl-C doesn't stop it, and says so; its timeout (120 s) does, and so does leaving bh-02.
- **operator** (row): `commands:operator`: the commands that act on the running program through the loader.
- **system** (row and key): `agent:system`: the system prompt: who the model is (the model in bh-02), where it is working (the directory, its branch), then the sections other rows add to it (memory's, how to extend bh-02).
- **memory** (row and key): `memory:memory`: Claude Code's memory, as Claude Code reads it: the managed policy's CLAUDE.md, yours (`~/.claude/CLAUDE.md`, `~/.claude/rules/`), the CLAUDE.md, `.claude/CLAUDE.md` and CLAUDE.local.md files from the filesystem's root down to the project's, AGENTS.md where there is no CLAUDE.md, the files they import (`@path`) and the project's rules (`.claude/rules/`), a section of the system prompt; `/memory` lists them. A file in the project imports nothing outside it, and no link the model could have made is followed.
- **auto memory** (row `memory-auto`): `memory:auto`: notes the model keeps for itself across conversations, as Claude Code's auto memory: a MEMORY.md index and a topic file per memory, written with whatever tools the model has in the project's own directory outside the repository (`$XDG_STATE_HOME/bh-02/projects/<project>/memory`, which the jail lets an input write); the index's first 200 lines or 25KB are told at the start of each conversation. `disabled = true` on the row turns it off.
- **compact** (row): `agent:compact`: `/compact [WHAT TO KEEP]` asks the model to summarise the conversation and begins a new one from the summary (the old transcript kept as `transcript.jsonl.bak`, a later one's as `.bak.2`, and so on); the loop and the transcript restart, the Python process keeps its namespace. The model has `timeout` seconds (300), since Ctrl-C doesn't stop a command (leaving bh-02 does, and changes nothing).
- **notes** (row and key): `agent:notes`, what the model is told with an input's result: a broker of functions rows add (memory's on-demand files), each given the input's code, result and touched files, each adding a note or nothing.
- **executor** (row and key): `agent:executor`, where the loop reads the prompt and asks `notes`: in a thread off the app's event loop, one call at a time. A reading a stopped reply left running is waited for, not started again beside; a row of its own, so `/clear` and `/model` keep it.
- **touched**: the project files an input opened, read or written (`kernel.touched()`), heard by an audit hook in the Python process; not what a shell command it ran opened.
- **on-touch** (row): `memory:on_touch`: memory that loads on demand (a subdirectory's CLAUDE.md, a rule whose `paths` match), given whole the first time an input opens a file it covers in a conversation (a resumed one's transcript says what it was told); it asks the `memory` row, so it has no config of its own.
- **extension**: a plugin the model writes itself, `.bh-02/plugins/NAME.py` in the project: cordis components bh-02 loads while it runs, into the extensions process, jailed, which can add a command, a status field or prompt text and nothing else. **extensions** (row): `extensions:extensions`, which loads them.
- **run**: one launch of bh-02, from start to leaving. The Python process and its namespace last one run.
- **session**: what a run keeps under `$XDG_STATE_HOME/bh-02/sessions/<id>/` (its layer, transcript and history), so `--resume` continues it in a later run. The namespace is not kept.
- **sessions** (key), **layers** (key), **harness** (row): rows the shell adds itself, **pinned** after every layer so no layer can remove them: the running session, whose id the status bar shows; the layer files, the paths no input may read, and the auto memory directory it may write; the wait for the chat's `done`.
- **done** (key): what the chat binds; the shell waits on it, and follows it across a restart of the chat row.
- **usage**: tokens and cost, per turn and summed for the session, in the status bar.
- **credential**: `CLAUDE_CODE_OAUTH_TOKEN` in `local.env` at the repository root, read by the model row alone; an OpenAI-compatible model's `key` names another line of the same file.
- **fakes**: stand-in models in `bh_02.testing` (`echo`, `repl_model`, ...) that a `--patch` names, or (`echo_provider`, ...) a models file's model names as its provider, for tests without a login.
- **update-layer**: `bh-02 update-layer FILE`: rewrites a layer that names rows bh-02 renamed (`llm`, `mode`, `completion`) or merged (`jail_status`, `model_status`) or dropped (`tools`, `sidebar`, ...), keeping `FILE.bak`.
- **gate**: the architecture check (pypeeker) that `scripts/check` runs: which packages may import which, and what must stay pure.
- **value half**, **wiring**: a plugin's two parts: the plain library (no cordis), and `wiring.py`, the components that bind it.
