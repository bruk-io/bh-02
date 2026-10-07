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
- **chat** (row): `chat:session`: reads your messages, shows the replies, runs the lines `commands` claims (slash commands, `!`); it binds `done`, which ends when you leave.
- **turn**: one reply to one message, however many model steps and inputs it takes.
- **event**: one thing that happened in a turn, a dict with a `type` (`text`, `thinking`, `tool_call`, `tool_result`, `usage`, `stop`, `note`, `cleared`, `restarting`), which the ui draws; a **chunk** is the same from one model step. A command's answer may also carry `for_model` (`!COMMAND`'s output), which `commands` holds, never shown, until the chat puts it in front of your next message to the model. [`CONTRACTS.md`](CONTRACTS.md) has each shape.
- **python**, **the one tool**: the only tool the model is offered, `python(code)`: each call is one input to the model's REPL, the kernel.
- **CodeAct**: working that way: the model acts by writing code, not by calling many tools.
- **kernel** (row and key), **the REPL**: a Python process, started inside the jail, that keeps what each input defines for the rest of the run; the model is told of it as a Python REPL of its own that persists.
- **worker**: the kernel's process, the one that runs inputs; the `jail` row starts it, and a new jail starts a new worker.
- **input** (to the REPL): one piece of code the model sent the kernel, one `python` call, and its output (not the `input` key, below).
- **jail** (row and key): what the kernel runs in: `brig:jail` confines it (no writes outside the project, no network, no credentials); `kernel:unjailed` (`--no-jail`) does not.
- **confined**: the jail enforces writes and network, so an input (or an extension's load) runs without asking; unconfined, each is put to you first.
- **grades**: how well each part of the jail holds (`enforced`, `best_effort`, `cooperative`, `unenforced`), shown in the status bar as ✓ and ✗.
- **placeholder** (Linux): an empty directory the jail makes in the project, on the host, to hold a path an input may not create (`.envrc/`, `.claude/`, `.git/` in a project that is no repository) for as long as the kernel runs; removed after. Removing one yourself meanwhile ends the jail (see **tripwire**).
- **tripwire** (Linux): the jail watching every path it holds with a mount; when the host replaces, moves or removes one (a host `git config` rewrites `.git/config` that way; editors save by rename), which lifts that hold, the jail ends itself at once and the next input's jail holds the path again, telling you why the kernel's variables are gone.
- **release** (row): `kernel:release`: `/release` stops the kernel until the next input, and with it the jail, which frees its placeholders: on Linux, how you add your credential (`local.env`) mid-session where the jail holds that path.
- **approval** (row and key): `kernel:approval`, the one place that decides whether the model's code runs: an input (the loop asks) or an extension to load (the extensions row asks). Confined, at once; unconfined, it asks you in the modal. Only a layer replaces it.
- **the modal**: the question the model's code is put to you in when it is unjailed: `y` runs it, `n` or Esc doesn't. It ignores keys for its first 0.4 s, so typing can't answer it.
- **host**: the side outside the jail: bh-02's own process (and brig's host process, which starts the worker), whose import paths, environment and files a jailed input can't reach; the kernel's `client.py` is its end of the socket.
- **composer**: the box along the bottom of the app where you type a message or a command; the palette puts a command that takes arguments there to finish.
- **ui** (row): `tui:app`, the Textual app. It binds `input`, `output` and `frame`, and depends on nothing, so it never reloads.
- **input**, **output** (keys): what the chat reads your lines from and shows replies, notes and questions through; the ui binds both.
- **port**: a word in the tui plugin's code (`ports.py`): the values the ui binds for other rows, `input`, `output` and `frame`.
- **frame** (key): the app around the conversation, which rows push into: status bar fields and palette commands. A broker.
- **status** (row): `tui:status`: the status bar's session id, model and jail grades. The `usage` field is the ui's own.
- **status bar**: the line along the bottom: session, model, jail, usage; narrower forms when the terminal is narrow.
- **palette** (row): `tui:palette`: the commands, offered in the command palette (Ctrl-P).
- **commands** (row and key): the command broker: `/help`, `/rows`, `/explain`, `/restart`, `/clear`, `/model`, any a row registers (`/release`), and the prefixes rows in a layer claim (`!`); it says which lines are commands.
- **prefix**: a character a row in a layer claims in `commands`, so every line you start with it is that row's, never a message to the model (`!`); one row each, and never an extension.
- **`!COMMAND`**, **shell command** (row `shell-command`): `commands:shell_command`: a line starting with `!` runs in your shell, as you (not in the jail), in the project; what it printed is shown, and the model reads it with your next message (`commands` holds it meanwhile, so a `/model` switch keeps it; `/clear` drops it). Ctrl-C doesn't stop it, and says so; its timeout (120 s) does, and so does leaving bh-02.
- **operator** (row): `commands:operator`: the commands that act on the running program through the loader.
- **system** (row and key): `context:project`: what the model is told about where it is working (that it is the model in bh-02, not Claude Code; the directory, its branch), and the sections other rows add to it.
- **context file**: TOML listing the project context's `[[section]]`s, each `files` (patterns) and `function` (a module path given the files that match), and optionally `on_touch` (one given them with the files an input opened): bh-02's own, then yours (`$XDG_CONFIG_HOME/bh-02/context.toml`, else `~/.config/bh-02/context.toml`), then the project's `.bh-02/context.toml` (bh-02's own functions and the project's non-hidden files only); read again when it changes.
- **memory** (row and key): `agent:memory`, what the model is told with an input's result: a broker of functions rows add, each given the input's code, result and touched files, each adding a note or nothing.
- **touched**: the project files an input opened, read or written (`kernel.touched()`), heard by an audit hook in the worker; not what a shell command it ran opened.
- **on-touch** (row): `context:on_touch`: the guidance or rule for a file, given whole the first time an input opens it in a conversation; it reads the context files through the `system` row (`touched`), so it has no config of its own.
- **shell hints** (row): `kernel:shell_hints`: an input that ran `cat`, `sed` or `ls` through a shell is told how Python does that, once per kind of work in a conversation.
- **extension**: a plugin the model writes itself, `.bh-02/plugins/NAME.py` in the project: cordis components bh-02 loads while it runs, jailed, which can add a command, a status field or prompt text and nothing else. **extensions** (row): `extensions:extensions`, which loads them.
- **session**: one run and everything it keeps, under `$XDG_STATE_HOME/bh-02/sessions/<id>/`, so `--resume` continues it.
- **sessions** (key), **layers** (key), **harness** (row): rows the shell adds itself, **pinned** after every layer so no layer can remove them: the running session, whose id the status bar shows; the layer files and the paths no input may read; the wait for the chat's `done`.
- **done** (key): what the chat binds; the shell waits on it, and follows it across a restart of the chat row.
- **usage**: tokens and cost, per turn and summed for the session, in the status bar.
- **credential**: `CLAUDE_CODE_OAUTH_TOKEN` in `local.env` at the repository root, read by the model row alone; an OpenAI-compatible model's `key` names another line of the same file.
- **fakes**: stand-in models in `bh_02.testing` (`echo`, `repl_model`, ...) that a `--patch` names, or (`echo_provider`, ...) a models file's model names as its provider, for tests without a login.
- **update-layer**: `bh-02 update-layer FILE`: rewrites a layer that names rows bh-02 renamed (`llm`, `mode`, `completion`) or merged (`jail_status`, `model_status`) or dropped (`tools`, `sidebar`, ...), keeping `FILE.bak`.
- **gate**: the architecture check (pypeeker) that `scripts/check` runs: which packages may import which, and what must stay pure.
- **value half**, **wiring**: a plugin's two parts: the plain library (no cordis), and `wiring.py`, the components that bind it.
