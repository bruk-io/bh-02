# Contracts

No plugin in this workspace imports another. They agree on **names** (the keys a layer wires)
and **shapes** (what a value bound under a name looks like), written down here and nowhere
else. A consumer states the shape it needs as a `runtime_checkable` Protocol of its own; cordis
checks the value against it when the dependency is committed, before the consumer's first
effect. A provider imports nothing to satisfy a contract; it just has the methods.

Data crosses plugins as plain dicts, the way it crosses a wire. A package that reads a shape
declares a `TypedDict` or `Mapping` for the part it reads; TypedDicts are structural, so two
packages' declarations of one shape type-check against each other without sharing a line.

This page is each key's signature, what it promises, and who binds and reads it. Why a row works
as it does is its plugin's README; how the parts fit is under How it works
([the loop](../docs/bh-02/how-it-works/loop.md),
[the prompt and notes](../docs/bh-02/how-it-works/prompt-and-notes.md),
[the python tool](../docs/bh-02/how-it-works/python-tool.md),
[the jail and approval](../docs/bh-02/how-it-works/jail-and-approval.md)).

## Keys

| Key | Value | Bound by | Read by |
|---|---|---|---|
| `loop` | a conversation: `reply(message: str) -> AsyncIterator[event]`, one turn's events in order; a failure the person can recover from raises as Errors says | `agent:loop`, `bh_02.testing:*` (fakes) | `chat:converse` |
| `input` | `read() -> str \| None` (`None`: no more input); `interrupted()` returns when the person asks to stop the running turn (a stop asked for after a line was read and before `interrupted()` is called is held for it; the next `read()` drops one still held); `closed()` returns once no more lines will come (the person left, or the ui crashed): a command running then is cancelled, since nobody is left to read its answer. Ends with the ui (below) | `tui:ui` | `chat:converse` |
| `output` | `show(events: AsyncIterator[event])`, `notice(message: str)`, `confirm(request) -> bool`. Not part of the shape: `lifecycle(event)` (a cordis `Event`: `kind`, `fiber`, `error`), which the ui row `observe`s itself to show rows reloading; no consumer calls it. Ends with the ui (below) | `tui:ui` | `chat:converse`; `agent:loop` and `extensions:extensions` (`confirm`: what the `approval` rule does not let run unasked); `tui:grades` (`show`: a start's notice, as a `note`); `agent:conversation` (`show`: a `note` as `/compact`'s step begins); `commands:jobs` (`notice`: a queued restart that failed, as its command words it) |
| `frame` | the app's frame, a broker (below): `status(field: str, text: str, *shorter: str) -> remover` (`shorter`: shorter forms of `text`, each shorter than the last, shown when the line is too narrow); `commands(specs) -> remover` (`specs: () -> Sequence[spec]`, a spec: `name`, `help`, `usage`, `choices`?: `() -> Sequence[{args, help}]`, arguments offered as entries of their own, `/model haiku`; both read each time the palette opens, so what is registered or added later is offered) | `tui:ui` | `tui:status`, `tui:grades` (`status`); `tui:palette` (`commands`); `extensions:extensions` (`status`: each extension's fields under its name, and its own `extensions` field) |
| `system` | the system prompt, a broker: `text() -> str` (bh-02's own, then the directory and its git branch, `.git/HEAD` read through no link, then the sections rows add; never the date), `add(name, section) -> remover` (`section: () -> str`, read with the rest each time `text()` is). Sections are told sorted by `name`, two of one name by their text, never in the order rows added them, so a row that adds its section again after a restart keeps its place. `text()` is read on `executor`, one call at a time, so a section must not need the event loop. Names no tool: a tool's row tells the model of it in a section. Depends on its config (`root`) alone. Why it is sent unchanged: [the prompt and notes](../docs/bh-02/how-it-works/prompt-and-notes.md#why-the-prompt-stays-fixed-for-a-conversation) | `agent:system` | `agent:loop` (`text`); `add`: `python:tool` (`python`), `memory:files` (`memory`), `memory:auto` (`memory: auto`), `extensions:extensions` (`extensions`, and `extensions: NAME` for each) |
| `model` | one model step: `complete(messages, tools) -> AsyncIterator[chunk]`; closing the iterator stops the step and releases what it holds. `messages` is always the whole conversation: a provider may keep its own copy across calls (the claude-code provider keeps a Claude Code session, checked against each request and rebuilt from `messages` when they differ) but assumes nothing the messages don't say. `tools`: the specs the loop offers, in name order, as `tool_changes` asks. Optional attribute `tool_changes`: `"fixed"` (the default when absent: the list the conversation began with, for its life) or `"listed"` (the list as the transcript last recorded it); a change is told as a note either way, and both shipped providers say `fixed` (why: the prompt and notes). A model that can't be used binds too, and each step raises what is wrong | `models:model` (the model its config's `default` names, on its provider: `claude-code`, `openai`, or a `module:attribute` factory; [models-cordis-plugin](plugins/models-cordis-plugin/README.md)), `bh_02.testing:echo_model`, `slow_model`, `repl_model` (fakes) | `agent:loop`; `agent:conversation` (one step, `/compact`'s summary, asked as the loop's next request would be with `tools.specs()` offered; a call it makes never runs) |
| `models` | the models there are, read fresh each time (the model row's config from the loader's entries, and the models file): `listed() -> Sequence[{name, provider, id, current: bool, where?, problem?, shadows?}]` (the built-ins, the models file's, the row's `extra`, in that order; `where`: an openai model's `base_url`; `problem`: what is wrong and what to do; `shadows`: a user's model named like a built-in; a models file that can't be read raises, and one in the project is not read and lists none), `current() -> {name, provider}` (the model the row names now; `provider` empty when that is no usable model; never raises), `check(name) -> str \| None` (why the row can't switch to `name`, or None), `path: str` (the models file), `problem: str \| None` (why the models file is not read and where it must be instead; None when it is outside the project). Depends on `loader` and `host` alone, so a switch never reloads it | `models:catalog` | `models:switch` (`/model`), `tui:status` (`current`) |
| `transcript` | `messages: Sequence[message]` (property), `append(message)`. Besides the conversation it keeps `system entry`s and `tools entry`s (Shapes), each change told as a note on the message after it, which a request never sends as messages (`request_for`); the dates told, as `today` on a person's message; and the notes told with each result, as `notes` on its `tool` entry. `agent:transcript` keeps it in its config's `path` (a session's `transcript.jsonl`), which `/clear` and `/compact` replace whole, the old file kept ([agent-cordis-plugin](plugins/agent-cordis-plugin/README.md)) | `agent:transcript` | `agent:loop`; `memory:auto` (its lifetime: a new conversation reads the auto memory index afresh); `memory:on_touch` (its lifetime, and `messages`, read once: what a resumed conversation was told, [memory-cordis-plugin](plugins/memory-cordis-plugin/README.md#what-loads-on-demand)); `agent:conversation` depends on the row's file, not the key (`loader.rows`), since it restarts the row |
| `tools` | the tools the model is offered, a broker: `register(spec, run, *, runs="jail", show=None) -> remover` (`spec`: a tool spec, one name one tool: a second registration of it raises; `run: async (input) -> tool result`: what it raises, or an answer of another shape, is told to the model as an error naming the tool, never the reply's failure; `runs`: `"jail"`, the runner's, put to the person only when the `approval` rule says the runner does not confine it, or `"host"`, bh-02's own process, always asked; `show: (input) -> {"title", "lines", "language"?}`, how a call is put to the person, else the tool's name and its input as JSON), `specs()` (every spec, in name order, so a row registering again after a restart gives the same list), `get(name)` (the registration, or None), `await ready(names, timeout)` (the names still unregistered once all are or `timeout` seconds pass), `serve(call) -> remover` (`call: async (name, input) -> {"content", "failed"}`, the loop row's, one at a time: a second raises), `await call(name, input) -> {"content": str, "failed": bool}` (a call a tool's own call makes, run by what `serve` gave; with nothing serving, failed, saying so). A row `acquire`s its registration. Depends on nothing, so a tool's row coming, going or restarting reloads neither the loop nor another tool's row | `agent:tools` | `agent:loop` (`specs` once, at a conversation's first request, after its config's `requires` are `ready`, waiting `wait` seconds, 30; `get` for each call; `serve`: an input's calls, run as the model's own are, put to `approval`, then to `notes`), `agent:conversation` (`specs`), `python:tool` (`register`: `python`; `specs` and `call`: `tools.NAME(...)` in an input), `extensions:extensions` (`register`: the extensions' tools; `specs`: the names that are bh-02's own) |
| `notes` | what the model is told with a call's result, a broker: `add(fn) -> remover`, iterable for the functions added. `fn(call) -> str`: `call` is `{"name", "input", "result", "touched"}` (the tool's name, the call's input, its result as the model reads it, the files it opened as its tool answered); it returns a note to follow the result ('' for none). A function adds a note and never changes the result; the loop sorts the notes, so any set of them composes in any order, and keeps them on the call's `tool` entry; one that raises or returns something other than text is told as one line naming it, and the rest still say theirs. Called on `executor`, after every call that ran, one call's at a time and never beside a reading of the prompt (a stop waits for them): it may read files and must not need the event loop. Only rows in a layer add to it (it runs in bh-02's process; an extension's code runs in the jail). A contributor keeps what it told as its own state, which a new conversation starts afresh, and reads what was told before it began from `transcript`, so a note is told once a conversation, a resumed one too | `agent:notes` | `agent:loop` (iterates), `memory:on_touch` (`add`) |
| `access` | what is asked before a file is read or written, a broker: `before_read(fn)` and `before_write(fn)`, each returning a remover (`fn(path) -> str \| None`: None lets the file be opened, text refuses it and says why); `asking()` (the kinds some function asks about, `"read"`, `"write"`: a tool need not ask about the others); `refusal(kind, path) -> str \| None` (every refusal, sorted, joined by a blank line; None when all let it go ahead; a function that raises refuses, saying so: a check that could not be made is not a yes). Called off bh-02's event loop (a function may read files) while a call runs, one question at a time; a refusal reaches the model with the call's result. It hears only what a tool reports, so it says something first and the jail is the wall ([what it doesn't hear](../docs/bh-02/how-it-works/prompt-and-notes.md#asked-before-a-file-is-written)). Depends on nothing | `agent:access` | `python:tool` (`asking`, `refusal`: before an input's own Python opens a project file), `memory:on_touch` (`before_write`: the first write to a file whose on-demand instructions have not been told) |
| `memory` | Claude Code's memory: `text() -> str` (what loads at launch, in the order [memory-cordis-plugin](plugins/memory-cordis-plugin/README.md#what-loads-at-launch) gives; '' when nothing loads), the memory row's section of `system`, read on `executor` with the rest of the prompt; `touched(paths: Sequence[str]) -> Sequence[(file, text)]` (what loads on demand for the absolute files an input opened, broadest first), called on `executor` through a `notes` function; `listed() -> [Entry]` (every memory file and how it loads, for `/memory`, the auto memory index among them); `places() -> (root, home)`. Every file is read through no link the model could have made, and a file in the project imports nothing outside it. It keeps nothing, so `/memory` on the event loop and the prompt in the worker thread may ask at once | `memory:files` | `memory:on_touch` (`touched`) |
| `executor` | where `agent:loop` runs what may block, off bh-02's event loop: `await run(fn)` (`fn()`, given nothing, in a daemon thread, once the call before it has ended; its result, or what it raised). A caller cancelled while it waits stops waiting and nothing else: the call runs to its end, its outcome dropped, and the next waits for it, so one runs at a time however often a reply is stopped. A daemon's thread, not the default executor's, so a call left running never holds bh-02 open. Depends on nothing, so `/clear` and `/model`, which reload the loop, keep it and the call in flight; a new one (its row restarted, or replaced by a layer) knows nothing of a call the last one left running | `agent:executor` | `agent:loop` (`run`: each reading of the prompt, and each call's `notes` functions) |
| `runner` | what starts the programs that run the model's code, over a mechanism (a brig jail, or none): `await start(argv, *, cwd, endpoint) -> started` (a program listening on the Unix socket `endpoint`); `started.interrupt() -> bool`, `await started.stop()`, `started.ended() -> str` (why the jail ended the program itself, for the person, or ""), and what this start is, kept with it whatever else the runner starts: `started.report() -> report` (Shapes), `started.notice() -> str` (what the person should know of the jail it runs in; "" for nothing), `started.reads() -> tuple[str, ...]` (the trees it can read when that is all it can read, each once and none inside another; empty when it reads everything but what it hides, or is no jail), `started.writes() -> tuple[str, ...]` (the directories it may write but a scratch directory of its own: the project root and what the row's `write` adds; empty when it confines no writes). `report()` and `notice()` (the last start's; before any, the mechanism's grades and ""); `on_start(watch) -> remover` (`watch(started)`, after each start); `on_release(stop) -> remover` (`stop: async () -> str`: an owner stops its own program on `/release` and says what it stopped, "" for nothing); `await release() -> str` (each owner's `stop`, then the mechanism lets go of what it holds on the host, and what each said); `released() -> bool` (`/release` ran and nothing has started since: any start ends it; an owner that would start only to keep something warm waits while it holds, asking with nothing awaited between the question and the start). It never stops a row's program itself, and knows nothing of inputs or of which program is the Python process. What a jail allows: [runner-cordis-plugin](plugins/runner-cordis-plugin/README.md) | `runner:confined` (a brig jail per start), `runner:unconfined` (`--no-jail`: a plain subprocess, every grade `unenforced`, its environment without `CLAUDE*` or `ANTHROPIC_*`) | `python:tool` (`start`, and its start's `report`, `notice`, `reads`, `writes`; `on_release`: its Python process's stop), `extensions:extensions` (`start`: the extensions process; `released`; `on_release`: its stop), `runner:approval` (`report`), `tui:grades` (`report`, `on_start`), `runner:release` (`release`) |
| `approval` | the rule for whether what the model asked for runs without asking the person: `confined: bool` (the runner enforces `fs_write` and `network`; read from its `report()` each time), `unasked(request) -> bool` (it runs in the runner, `runs` `"jail"` when the request says nothing, and the runner confines it). Asking is not the rule's: each asker puts what is not unasked to the person through `output.confirm(request)`, runs it only on a yes, and keeps no copy of the rule. A capability, bound by one row, not a broker: the rule has exactly one author. Depends on `runner` alone, so `/clear` and a new ui leave it up; only a layer replaces it ([why](plugins/runner-cordis-plugin/README.md)) | `runner:approval` | `agent:loop` (`unasked`: each call), `extensions:extensions` (`confined`: what the model is told; `unasked`: each extension to load), `python:tool` (`confined`: what the model is told, and whether the startup files run unasked), `tui:grades` (`confined`: `jailed` or `unjailed`) |
| `host` | what the host is, for the rows that keep the model's code from it and those that read its files: `paths`, `credentials`, `secrets`, `trusted` and `code`, each a `tuple[str, ...]` of absolute paths, and `auto_memory: str`. `paths` (the layer files the loader watches); `credentials` (where the model rows look for bh-02's `local.env`, nearest first; the first that is a regular file is read: `bh_02.cli.credential_search`, the one definition of that search); `secrets` (what no jailed input may read: every one of `credentials`, the `local.env` beside and above the project, and the sessions' state directories, this run's and the default); `trusted` (bh-02's config directories, this run's and the default `~/.config/bh-02`, as named and as resolved, whose files the host reads and trusts: `bh_02.bootstrap.config_directories`); `code` (where bh-02 runs its own code from: the directory of every package a layer may name as installed, `bh_02`, `cordis`, `cordis_helpers`, `brig`, `host_paths` and each `cordis.plugins` entry point's top-level package, a single module's file, as named and as resolved, found by name, importing nothing: `bh_02.bootstrap.code_directories`); `auto_memory` (the project's auto memory directory, `$XDG_STATE_HOME/bh-02/projects/<project>/memory`, which the command line makes; '' for none: `bh_02.bootstrap.memory_directory`). What the jail does with each: [runner-cordis-plugin](plugins/runner-cordis-plugin/README.md) | `bh_02.bootstrap:host` (mounted by its `run()`) | `runner:confined` (every field: what an input may not read, write or create, and `auto_memory` a root it may write), `models:model` and `models:catalog` (`credentials`), `memory:files` and `memory:auto` (`auto_memory`) |
| `commands` | the command broker: `register(spec, run) -> remover` (`spec`: `name`, `help`, `usage`, `choices`?; `run: async (args: str) -> answer`), `claim(prefix, spec, run) -> remover` (every line that starts with `prefix`, one character that is no letter, digit, space or `/`, goes to `run` with the rest of the line; a prefix is one row's, so a second claim raises; `/help` lists it, the palette doesn't), `specs()` (the slash commands), `claims(line) -> bool` (whether a line is the harness's rather than the model's: `/name` then whitespace or the end, a known command or not, or a claimed prefix), `run(line) -> answer` (text, shown as one `note`, or a sequence of events shown as they come), `take_for_model() -> list[str]` (what commands left for the model since it was last asked, in the order they ran; taking it empties it). It holds an answer's `for_model` events instead of answering them; a `cleared` drops what it holds, and a note says so, unless it is `compacted`. It holds them in memory and depends on nothing, so a restart of the chat row keeps them and a resumed session starts without. Each command's answer is its owner's: `/clear`, `/compact` (agent), `/model` (models), `!COMMAND` ([commands-cordis-plugin](plugins/commands-cordis-plugin/README.md)) | `commands:registry` | `chat:converse` (`claims`, `run`, `take_for_model`), `commands:operator`, `models:switch` (`/model`), `runner:release` (`/release`), `agent:conversation` (`/clear`, `/compact`), `extensions:extensions` (`register`; never `claim`), `commands:shell_command` (`claim`: `!`), `tui:palette` (`specs`) |
| `jobs` | the restarts commands ask for, a capability: `put(job, failed)` (`job`: an async function of nothing, run after those put before it, one at a time, in the row's own work, never in the caller's task, which a restart could cancel half-way; `failed(why) -> str`: what the person is told through `output.notice` if it raises, `why` one line naming the error), `pending() -> bool`, `settled()` (returns once none is queued or running). Depends on `output` alone, so no restart it runs reloads it | `commands:jobs` | `commands:operator` (`put`: `/restart`), `agent:conversation` (`put`: `/clear`, `/compact`), `models:switch` (`put`: `/model NAME`'s reload), `chat:converse` (`settled`: before each read) |
| `session` | the running session: `current: str` (its id, empty when the composition runs without a session), `resumed: bool` (whether it was continued with `--resume`) | `bh_02.bootstrap:session` (mounted by its `run()`) | `tui:status` (`current`, `resumed`: the status bar's session id) |
| `loader` | cordis's loader handle: `status()`, `rows` (each row as it was mounted, with its `entry`), `entries()`, `restart(*rows)` (together: a row depending on several reloads once), `reload()` (read the layer files again now, rather than at the watcher's next look), `explain(row)`, `config.layers` | the loader itself (cordis) | `commands:operator` (`status`, `restart`), `models:switch` (`reload`, `status`; `config.layers`: whether a layer after the session's sets the model row's config), `agent:conversation` (`status`, `restart`; `rows`: the transcript row's `use` and `path`, as it runs), `tui:status` (`entries`: whether the layers still name the model row; `status`: whether it is up when the field is first pushed), `models:catalog` (`entries`: the model row's config) |
| `done` | an awaitable (the `asyncio.Task` `background(...)` returned) that resolves when the chat row's own run ends; a composition whose chat row doesn't bind it is a bootstrap error, not a silent hang ([why](plugins/chat-cordis-plugin/README.md)) | `chat:converse` | `bh_02.bootstrap:shell` |

**The ui's `input` and `output` end with the ui.** Whatever ends the app (Ctrl-Q, `/exit` or
`/quit`, a crash) settles everything waiting on it: a pending `input.read()` returns `None`,
every `interrupted()` and `closed()` returns (so a command running, a `!` one that would take
minutes, is cancelled, and bh-02 leaves at once), a pending `output.confirm` is a no. After a
crash, `read()` raises instead of returning `None`: a recoverable failure (`kind =
"ui_crashed"`, `message`), which reaches the command line through the chat row's `done` (a
teardown error would not).

**A restart a command asks for.** A command never restarts rows in the chat row's task: it
queues the restart in `jobs` and answers, ending with `restarting` (the rows). `chat:converse`
reads its next line only once `jobs.settled()`, so the restart reloads it while it holds no line,
and a line typed meanwhile reaches the new loop: never the old one, never dropped, never a turn
the restart stops. How the ui shows rows coming back up: [tui-cordis-plugin](plugins/tui-cordis-plugin/README.md).

**Brokers** (`commands`, `frame`, `system`, `tools`, `notes`, `access`; the paper's, section
6.2): one row binds the key, and a contributor depends on it and `acquire`s a registration whose
return value is its remover, so the entry leaves with the row and adding or retiring one reloads
nothing else. Registrations commute: each takes its own entry, never a place in an ordered chain.
Of `frame`: two rows pushing one status field, the later push shows until it is removed, and a
field removed is gone at once. A ui with no frame binds no `frame`, and a layer that uses one
disables the rows over it (the shipped `status`, `grades` and `palette`); a frame that has
`status` but not `commands` is not a `frame` either (`palette` would never start).

**A tool, as the loop runs it.** The loop knows no tool by name: CodeAct's `python` is the
shipped default, not a requirement. It runs a call through the tool its name has now (one
restarting, waited for `wait` seconds) once `approval.unasked` lets it or the person says yes, and
answers a name it did not offer, an input that does not fit the spec (a `required` property
missing, one not of its schema's simple type), or a tool removed since the conversation began
with text saying so, never running it or asking anyone. A call an input makes (`tools.call`) runs
the same way. A tool's row tells the model about its tool in a `system` section of its own, never
in the spec's description, which a model server caches with the list. A turn the person stops
still answers every call it made: [the loop](../docs/bh-02/how-it-works/loop.md).

**The model's extensions** reach bh-02 only through four keys, bound in the extensions process,
each of which only adds: `commands.register` (never `commands.claim`: there it raises),
`frame.status` (pushed under `NAME:field`), `system.add(text)` (text, not a function: it
crosses a socket) and `tools.register` (registered with `runs = "jail"`, never under one of
bh-02's own names). Nothing an extension does can replace a row, or reach the loader, `runner`,
`model` or `approval`. What the host checks:
[extensions-cordis-plugin](plugins/extensions-cordis-plugin/README.md).

Row ids in the shipped layers coincide with these keys where a row binds one; a row that
contributes to a broker (`operator`, `palette`, the frame's rows) has an id of its own.
`shell`, `host` and `session` are rows the shell's bootstrap (`bh_02.bootstrap:run`) adds
itself.

Each "Bound by" component declares its keys with `@component(provides=(...))` (cordis
checks this: a fiber that declares a key and does not bind it fails at activation, and
`boot` reports a composition where nothing declares `provides` for a key some row injects).
Adding or removing a binding here means updating that component's `provides=` to match, or
the check starts lying.

## Errors

A `loop` or `model` signals a failure the person should see and can recover from by raising any
exception with two attributes: `kind: str` (a short tag: `authentication_failed`, `rate_limit`,
`connection`, `tools_missing` (a tool the loop requires never registered), ...) and
`message: str`, written for the person at the keyboard. `chat:converse` shows it and carries on.
Anything else is a bug and propagates.

## Shapes

```
tool spec   {"name": str, "description": str, "parameters": <JSON Schema object>}
tool result {"content": str, "touched"?: [str, ...]}   a tool's answer to a call: what the model
            reads, and the files the call opened (absolute), as the tool says it opened them:
            match them against files you chose, never open one because it is named here
request     {"name": str, "input": Mapping, "runs"?: "jail" | "host", "title"?: str,
             "lines"?: [str, ...], "language"?: str}   put to `approval.unasked`, and when that
            says no, to the person by `output.confirm`: a call (its tool's name, its input, where
            it runs, and how it is shown: its tool's `show`, the python tool's `title` and its
            code as `lines`, else its input as JSON), or an extension to load (`"name":
            "extension"`, its own `title`, its source as `input.code`)
report      Mapping[axis, grade]   a start's, per axis (`fs_read`, `fs_write`, `network`, `limits`,
            `env`, ...): `enforced`, `best_effort`, `cooperative` or `unenforced`, as brig grades
            them; what runs there is `confined` when `fs_write` and `network` are enforced
message     {"role": "user" | "assistant" | "tool", "content": str,
             "tool_calls"?: [tool call, ...]   (assistant),
             "provider"?: Mapping  (assistant: the provider's own message, replayed as received),
             "call_id"?: str       (tool: the call it answers; its content is the call's result,
                                    then each note told with it and any change in the
                                    instructions, each after a blank line),
             "notes"?: [str, ...]  (tool: the notes its content tells, sorted; `[]` for none, and
                                    for a call that never ran. Every `tool` entry the loop writes
                                    has it: one without is from before, its notes only in `content`),
             "feedback"?: str      (user: the loop telling the model why its last step didn't count),
             "today"?: str         (user: the date told with it, `2026-10-07`; its content then
                                    starts `(Today's date: 2026-10-07.)` and a blank line, before
                                    any change in the instructions and the person's words)}
                                   `notes` and `today` are the loop's own: a provider sends `content` alone
system entry
            {"role": "system", "content": str}
                        a prompt told whole: a transcript's first, the one every request begins
                        with (and each later one, in a transcript from before the loop kept edits,
                        which resumes as it is)
            {"role": "system", "edits": [{"at": int, "drop": int, "add": [str, ...]}, ...]}
                        a later prompt, as what turns the one before it into this one, by
                        paragraph (split at every blank line, exactly): from paragraph `at`, `drop`
                        give way to `add` (`prompt.edits`; `prompt.latest` applies them in turn,
                        passing over one `edits` could not have made). The loop's own: a request
                        carries the first alone, so a provider never sees `edits`
tools entry {"role": "tools", "tools": [tool spec, ...]}   the list a conversation began with
            {"role": "tools", "added"?: [tool spec, ...], "removed"?: [str, ...],
             "redefined"?: [tool spec, ...]}   a later change, each in name order, only those
                        there are (a transcript from before the loop kept them begins its list at
                        its next request). The loop's own
tool call   {"id": str, "name": str, "input": Mapping}
chunk       {"type": "text", "text": str}
            {"type": "tool_call", "id": str, "name": str, "input": Mapping, "error"?: str}
            {"type": "stop", "reason": str}              the provider's own finish reason
            {"type": "message", "message": Mapping}      the provider's assistant message, as received
            {"type": "thinking" | "usage", ...}          as in `event`
event       a text, thinking, tool_call or usage chunk, or one of:
            {"type": "thinking", "text": str}
            {"type": "tool_result", "call_id": str, "content": str, "is_error": bool}
            {"type": "usage", "input_tokens": int, "output_tokens": int, "cost_usd"?: float,
             "cache_read_input_tokens"?: int, "cache_creation_input_tokens"?: int,
             "partial"?: true}
                        one step's usage, not a running total: a ui sums them (a provider that
                        reports running totals sends differences; one step may send several,
                        which a ui shows as one line). `input_tokens` is everything the model
                        read, cached or not; the cache fields say how much of it was read from,
                        or written to, the provider's prompt cache. `partial`: a part sent before
                        the provider's output count, which a later part carries
            {"type": "stop", "reason": str}              the loop's classification of a step (below)
            {"type": "note", "text": str}                 the shell speaking (a command's answer); from the
                                                          loop, what it told the model besides a result
                                                          (its instructions changed; a note from `notes`,
                                                          by its first line)
            {"type": "cleared", "compacted"?: true}       the conversation starts afresh (`/clear`, or
                                                          `/compact`, from a summary): a ui drops what it
                                                          shows of the conversation so far (a line typed
                                                          after it and not read yet stays) and keeps the
                                                          session's usage totals; a note saying so follows,
                                                          for a ui that ignores the type. `compacted`: what
                                                          `commands` holds for the model is kept
            {"type": "for_model", "text": str}           a command's answer for the model, not the person
                                                          (`!COMMAND`'s output): `commands` holds it, and
                                                          `chat:converse` puts what it takes in front of
                                                          the person's next message, a paragraph each, in
                                                          the order they came
            {"type": "restarting", "rows": [str, ...]}   a command's answer: these rows restart now,
                                                          queued in `jobs`; a ui names them in what a line
                                                          typed until the chat row reads again says it
                                                          waits for. Shows nothing
```

A model streams chunks for one step and ends with its own `stop` (why the provider stopped) and
`message` (what it sent, for replay). A `tool_call` whose arguments did not decode carries
`error` instead of being dropped. The loop classifies each step (`stops.classify`): `act` (calls
to run), `answered` (the only real done), `truncated` (hit the output limit, possibly mid-call),
`silent` (said nothing), `undecodable` (a call it made could not be read) or `refused` (the
provider's `refusal`). Only `act` runs calls; every other step ends with a `stop` event carrying
its classification; `answered` and `refused` end the reply, and the rest are fed back to the model
as `feedback`, a bounded number of times, never read as the answer. Which reasons each provider
reports: [models-cordis-plugin](plugins/models-cordis-plugin/README.md).

A reply is a stream of events: everything the person might want to see of a turn, in order.
`text` is the reply itself; the rest describe the work around it. A consumer that shows only
text keeps `text` and may drop the rest; one that shows more matches on `type` and ignores types
it doesn't know, so a provider can add one.
