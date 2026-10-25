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
[the prompt and asides](../docs/bh-02/how-it-works/prompt-and-asides.md),
[the python tool](../docs/bh-02/how-it-works/python-tool.md),
[the jail and approval](../docs/bh-02/how-it-works/jail-and-approval.md)).

## Keys

| Key | Value | Bound by | Read by |
|---|---|---|---|
| `loop` | a conversation: `reply(message: str) -> AsyncIterator[event]`, one reply's events in order; a failure the person can recover from raises as Errors says | `agent:loop`, `bh_02.testing:*` (fakes) | `chat:converse` |
| `input` | `read() -> str \| None` (`None`: no more input); `interrupted()` returns when the person asks to stop the running reply (a stop asked for after a line was read and before `interrupted()` is called is held for it; the next `read()` drops one still held); `closed()` returns once no more lines will come (the person left, or the ui crashed): a command running then is cancelled, since nobody is left to read its answer. Ends with the ui (below) | `tui:ui` | `chat:converse` |
| `output` | `show(events: AsyncIterator[event])`, `notice(message: str)`, `confirm(question) -> bool`. Not part of the shape: `lifecycle(event)` (a cordis `Event`: `kind`, `fiber`, `error`), which the ui row `observe`s itself to show rows reloading; no consumer calls it, and it shows nothing of a sub-agent's rows (a `fiber` under `agents/`), which `--trace` keeps, and the session's `rows.jsonl` (the shell's, not the ui's: a line for each `reload` and `failed` event, a sub-agent's rows included, after a `{at, kind: "run"}` line the shell writes when it opens the log to mark the run's start, read by `bh-02 trajectory`). Ends with the ui (below). Inside a sub-agent's realm, `output` is `subagents:output`'s: `confirm` alone, each question labelled with the agent (`agent`) and put through `asker` | `tui:ui`; in a sub-agent's realm, `subagents:output` | `chat:converse`; `agent:loop` and `extensions:process` (`confirm`: what the `approval` rule does not let run unasked); `subagents:parent` (the parent's: `confirm`, behind `asker`, and a sub-agent's start past the session's budget or naming a model other than its type's, unlabelled since the parent's reply asks it; `show`: a note that a sub-agent waits for a slot, a note that a sub-agent's event log stopped being written (once, as its run ends, before its usage), and each sub-agent's usage when it ends, one `usage` event after a `note`, so it joins the session's totals); `tui:grades` (`show`: a start's notice, as a `note`); `agent:conversation` (`show`: a `note` as `/compact`'s step begins); `commands:jobs` (`notice`: a queued restart that failed, as its command words it) |
| `frame` | the app's frame, a broker (below): `status(field: str, text: str, *shorter: str) -> remover` (`shorter`: shorter forms of `text`, each shorter than the last, shown when the line is too narrow); `commands(specs) -> remover` (`specs: () -> Sequence[spec]`, a spec: `name`, `help`, `usage`, `choices`?: `() -> Sequence[{args, help}]`, arguments offered as entries of their own, `/model claude/haiku`; both read when the palette is searched (each time it opens, and per key) and when the composer's list of commands opens (once per opening), so what is registered or added later is offered) | `tui:ui` | `tui:status`, `tui:grades` (`status`); `tui:palette` (`commands`); `extensions:process` (`status`: each extension's fields under its name, and its own `extensions` field); `subagents:status` (`status`: the `agents` field) |
| `system` | the system prompt, a broker: `text() -> str` (bh-02's own, then the directory and its git branch, `.git/HEAD` read through no link, then the sections rows add; never the date), `add(name, section) -> remover` (`section: () -> str`, read with the rest each time `text()` is). Sections are told sorted by `name`, two of one name by their text, never in the order rows added them, so a row that adds its section again after a restart keeps its place. `text()` is read on `executor`, one call at a time, so a section must not need the event loop. Names no tool: a tool's row tells the model of it in a section. Depends on its config (`root`) alone. Why it is sent unchanged: [the prompt and asides](../docs/bh-02/how-it-works/prompt-and-asides.md#why-the-prompt-stays-fixed-for-a-conversation) | `agent:system` | `agent:loop` (`text`); `add`: `python:tool` (`python`), `subagents:parent` (`agents`), `subagents:child` (`agent`, in a sub-agent's realm), `memory:files` (`memory`), `memory:auto` (`memory: auto`), `extensions:process` (`extensions`, and `extensions: NAME` for each) |
| `model` | one model step: `complete(messages, tools) -> AsyncIterator[chunk]`; closing the iterator stops the step and releases what it holds. `messages` is always the whole conversation: a provider may keep its own copy across calls (the claude-code provider keeps a Claude Code session, checked against each request and rebuilt from `messages` when they differ) but assumes nothing the messages don't say. `tools`: the specs the loop offers, in name order, as `tool_changes` asks. Optional attribute `tool_changes`: `"fixed"` (the default when absent: the list the conversation began with, for its life) or `"listed"` (the list as the transcript last recorded it); a change is told as an aside either way, and both shipped providers say `fixed` (why: the prompt and asides). Optional attribute `settings`: a mapping of what its steps are made with, `model` (the named model, `ENDPOINT/MODEL`), `provider`, and the `max_tokens` and `temperature` it sends, each left out when it sends none (claude-code sends neither); the loop reads it as it reads `tool_changes` and records it on a conversation's first step and on any step where it differs from the last recorded (`step record`, Shapes). A `usage` chunk may carry `model`, the id that answered (claude-code's from `message_start`, openai's from the response), which the loop records on the step. A model that can't be used binds too, and each step raises what is wrong | `models:model` (the model its config's `default` names, on its provider: `claude-code`, `openai`, or a `module:attribute` factory; [models-cordis-plugin](plugins/models-cordis-plugin/README.md)), `bh_02.testing:echo_model`, `slow_model`, `repl_model` (fakes) | `agent:loop`; `agent:conversation` (one step, `/compact`'s summary, asked as the loop's next request would be with `tools.specs()` offered; a call it makes never runs); `subagents:parent` (for its lifetime alone: a model switch reloads it, ending the sub-agents) |
| `models` | the models there are, read fresh each time (the model row's config from the loader's entries, and the models file): `listed() -> Sequence[{name, provider, id, current: bool, default?, where?, problem?}]` (each endpoint's models, the models file's endpoints then the row's `extra`, in that order; there are no built-in models; an endpoint is a table of the models file or of `extra`, and its models are named `ENDPOINT/MODEL`, split at the first `/`: the ones its `models` names, in order, then, for one with `discover = true` (models file only), the ones its server listed when `refresh` last asked (in its `include`, at most 200), and the model row's and the default's when they are of it and named by id; `default`: on the model a new session starts on when no layer names one (the models file's `default`), where that came from, `the models file`; `where`: a model's `base_url`, when it has one; `problem`: what is wrong and what to do; a models file that is in the project, can't be read or is not TOML is not read and lists none, the row's `extra` stays, and `listed` never raises for it), `endpoints() -> Sequence[{name, where, notes: [str]}]` (each endpoint with something to say besides its models, one line each: its table's problem, or, for one that discovers, why it listed none or what its list leaves out; read from what `refresh` kept), `async refresh() -> None` (asks each discovering endpoint `GET <base_url>/models` unless it listed within 30 s: awaited by `/model` listing alone, never raises for a server; `listed`, `endpoints` and `current` only read what it kept, so `/model`'s choices, the composer's completion and the status bar never ask), `current() -> {name, provider, unusable?}` (the model the row names now, `ENDPOINT/MODEL` included, with no network; `provider` empty when that is no usable model, and then `unusable` says why, which the status bar shows as `NAME (unusable)`; `name` is a default's own text when it is a name, else `default`, so it is never blank; never raises), `check(name) -> str \| None` (why the row can't switch to `name`, or None), `path: str` (the models file), `problem: str \| None` (why the models file is not read and where it must be instead: it is in the project, or it can't be read or is not TOML, then only the row's `extra` is offered; None when it is read, there or not), `default_problem: str \| None` (why the models file's `default` is refused, as the model row says it with what to write: no name, no model, or a model whose table has a problem; None when it is fine, absent, or the file is not read). Depends on `loader` alone, so a switch never reloads it | `models:catalog` | `models:switch` (`/model`), `tui:status` (`current`) |
| `transcript` | `messages: Sequence[message]` (property), `append(message)`; optionally `async flush()`, a capability only a transcript that writes behind the loop has (`FileTranscript`: `append` commits in memory and queues the line to `host_paths.Appender`, so the event loop never waits on a disk), which the loop checks for and awaits at the end of every reply, however it ends: `MemoryTranscript` has none and is asked for none, and no consumer's Protocol changes; and optionally `async check()`, which only a transcript whose file can be replaced under it has (`FileTranscript`): it returns once the writing thread has looked at the file and found it the one it writes to, and raises `TranscriptReplaced` if not, which the loop awaits first in every reply, before it appends anything, so a reply over a replaced file is refused before the model is asked (the look is the thread's one stat: no flush, no write waited for). A command runs only after the reply before it, so `/clear` and `/compact` find every entry in the file; a line that can't be written (a full disk) is raised by the next `append`, `check` and `flush` and by the row's leaving, never dropped, as `TranscriptWriteFailed`, a recoverable failure (Errors) whose message names the file, the error and `/restart transcript` (free space first), and nothing after the failed line is written; and a file replaced under it (`/clear` or `/compact` replaced it and the restart failed) is refused the same way, as `TranscriptReplaced`, a recoverable failure (Errors) whose message names `/restart transcript`, so the old conversation is never written into the new file. A file that ends in a write cut short (a last line with no newline that is not JSON) is read without that line, which is kept beside it at 0600 (`transcript.jsonl.torn`, then `.torn.2`, ...) before the file is cut to its last whole line, so the next entry starts a line of its own; a line that is not JSON anywhere else stops the row with a `ValueError` naming the file and the line, the file untouched. Besides the conversation it keeps `system entry`s and `tools entry`s (Shapes), each change told as an aside on the message after it, which a request never sends as messages (`request_for`); the dates told, as `today` on a person's message; when a message came, as `at` on it; each step's timing, answering model, usage and settings, as `step` on its assistant entry (`step record`, Shapes); the asides told with each result, as `asides` on its `tool` entry; and each call's answer, waits, run time, sub-agent and nested calls, as `call` on that entry (`call record`, Shapes). A record is appended once and never changed, a field is left out only where there is nothing to record (step record, call record), and no provider sends one. `bh-02 trajectory` reads them back from the files with TypedDicts of its own (`bh_02.trajectory`, which imports no plugin), so a change to a record's shape is a change there. `agent:transcript` keeps it in its config's `path` (a session's `transcript.jsonl`, made 0600), which `/clear` and `/compact` replace whole, the old file kept, both at 0600 ([agent-cordis-plugin](plugins/agent-cordis-plugin/README.md)) | `agent:transcript` | `agent:loop`; `memory:auto` (its lifetime: a new conversation reads the auto memory index afresh); `memory:on_touch` (its lifetime, and `messages`, read once: what a resumed conversation was told, [memory-cordis-plugin](plugins/memory-cordis-plugin/README.md#what-loads-on-demand)); `agent:conversation` depends on the row's file, not the key (`loader.rows`), since it restarts the row |
| `tools` | the tools the model is offered, a broker: `register(spec, run, *, runs="jail", show=None) -> remover` (`spec`: a tool spec, one name one tool: a second registration of it raises; `run: async (input) -> tool result`: what it raises, or an answer of another shape, is told to the model as an error naming the tool, never the reply's failure; `runs`: `"jail"`, the runner's, put to the person only when the `approval` rule says the runner does not confine it, `"harness"`, bh-02's own process acting only on the session's jail and bh-02's own state (a sub-agent tool), unasked exactly when the runner confines and asked otherwise (`--no-jail`), the same as `"jail"` for approval and only a layer's row may declare it, `"memory"`, the memory tool alone: it runs in bh-02's own process, outside the jail, and writes only beneath `host.auto_memory`, through no link (`host_paths.write_beneath`), which the jailed model can already write without being asked, so it is never asked, jailed or under `--no-jail`, and only a layer's row may declare it, or `"host"`, bh-02's own process, always asked; `show: (input) -> {"title", "lines", "language"?}`, how a call is put to the person, else the tool's name and its input as JSON), `specs()` (every spec, in name order, so a row registering again after a restart gives the same list), `get(name)` (the registration, or None), `await ready(names, timeout)` (the names still unregistered once all are or `timeout` seconds pass), `serve(call) -> remover` (`call: async (name, input) -> {"content", "failed"}`, the loop row's, one at a time: a second raises), `await call(name, input) -> {"content": str, "failed": bool}` (a call a tool's own call makes, run by what `serve` gave; with nothing serving, failed, saying so). A row `acquire`s its registration. Depends on nothing, so a tool's row coming, going or restarting reloads neither the loop nor another tool's row | `agent:tools` | `agent:loop` (`specs` once, at a conversation's first request, after its config's `requires` are `ready`, waiting `wait` seconds, 30; `get` for each call; `serve`: an input's calls, run as the model's own are, put to `approval`, then to `asides`), `agent:conversation` (`specs`), `python:tool` (`register`: `python`; `specs` and `call`: `tools.NAME(...)` in an input), `extensions:process` (`register`: the extensions' tools; `specs`: the names that are bh-02's own), `subagents:parent` (`register`: `agent`, `agent_wait`, `agent_send` and `agent_stop`, `runs="harness"`), `memory:auto` (`register`: `memory`, `runs="memory"`: save, read or delete an auto memory by name, from bh-02's own process, outside the jail) |
| `asides` | what the model is told beside a call's result, a broker: `add(fn) -> remover`, iterable for the functions added. `fn(call) -> str`: `call` is `{"name", "input", "result", "touched"}` (the tool's name, the call's input, its result as the model reads it, the files it opened as its tool answered); it returns an aside to follow the result ('' for none). A function adds an aside and never changes the result; the loop sorts the asides, so any set of them composes in any order, and keeps them on the call's `tool` entry; one that raises or returns something other than text is told as one line naming it, and the rest still say theirs. Called on `executor`, after every call that ran, one call's at a time and never beside a reading of the prompt (a stop waits for them): it may read files and must not need the event loop. Only rows in a layer add to it (it runs in bh-02's process; an extension's code runs in the jail). A contributor keeps what it told as its own state, which a new conversation starts afresh, and reads what was told before it began from `transcript`, so an aside is told once a conversation, a resumed one too | `agent:asides` | `agent:loop` (iterates), `memory:on_touch` (`add`), `subagents:child` (`add`, in a sub-agent's realm: what `agent_send` left for the child, framed as from its parent) |
| `access` | what is asked before a file is read or written, a broker: `before_read(fn)` and `before_write(fn)`, each returning a remover (`fn(path) -> str \| None`: None lets the file be opened, text refuses it and says why); `asking()` (the kinds some function asks about, `"read"`, `"write"`: a tool need not ask about the others); `refusal(kind, path) -> str \| None` (every refusal, sorted, joined by a blank line; None when all let it go ahead; a function that raises refuses, saying so: a check that could not be made is not a yes). Called off bh-02's event loop (a function may read files) while a call runs, one question at a time; a refusal reaches the model with the call's result. It hears only what a tool reports, so it says something first and the jail is the wall ([what it doesn't hear](../docs/bh-02/how-it-works/prompt-and-asides.md#asked-before-a-file-is-written)). Depends on nothing | `agent:access` | `python:tool` (`asking`, `refusal`: before an input's own Python opens a project file), `memory:on_touch` (`before_write`: the first write to a file whose on-demand instructions have not been told) |
| `memory` | Claude Code's memory: `text() -> str` (what loads at launch, in the order [memory-cordis-plugin](plugins/memory-cordis-plugin/README.md#what-loads-at-launch) gives; '' when nothing loads), the memory row's section of `system`, read on `executor` with the rest of the prompt; `touched(paths: Sequence[str]) -> Sequence[(file, text)]` (what loads on demand for the absolute files an input opened, broadest first), called on `executor` through an `asides` function; `listed() -> [Entry]` (every memory file and how it loads, for `/memory`, the auto memory index among them); `places() -> (root, home)`. Every file is read through no link the model could have made, and a file in the project imports nothing outside it. It keeps nothing, so `/memory` on the event loop and the prompt in the worker thread may ask at once. A sub-agent's realm binds a `memory` of its own, copied from the parent's row with its config, so its prompt has the project's guidance and `memory:on_touch` there tells its inputs what loads on demand; never `memory:auto` in a child, so never the `memory` tool (it is that row's) | `memory:files` | `memory:on_touch` (`touched`) |
| `executor` | where `agent:loop` runs what may block, off bh-02's event loop: `await run(fn)` (`fn()`, given nothing, in a daemon thread, once the call before it has ended; its result, or what it raised). A caller cancelled while it waits stops waiting and nothing else: the call runs to its end, its outcome dropped, and the next waits for it, so one runs at a time however often a reply is stopped. A daemon's thread, not the default executor's, so a call left running never holds bh-02 open. Depends on nothing, so `/clear` and `/model`, which reload the loop, keep it and the call in flight; a new one (its row restarted, or replaced by a layer) knows nothing of a call the last one left running | `agent:executor` | `agent:loop` (`run`: each reading of the prompt, and each call's `asides` functions) |
| `runner` | what starts the programs that run the model's code, over a mechanism (a brig jail, or none): `await start(argv, *, cwd, endpoint) -> started` (a program listening on the Unix socket `endpoint`); `started.interrupt() -> bool`, `await started.stop()`, `started.ended() -> str` (why the jail ended the program itself, for the person, or ""), and what this start is, kept with it whatever else the runner starts: `started.report() -> report` (Shapes), `started.notice() -> str` (what the person should know of the jail it runs in; "" for nothing), `started.reads() -> tuple[str, ...]` (the trees it can read when that is all it can read, each once and none inside another; empty when it reads everything but what it hides, or is no jail), `started.writes() -> tuple[str, ...]` (the directories it may write but a scratch directory of its own: the project root and what the row's `write` adds; empty when it confines no writes). `report()` and `notice()` (the last start's; before any, the mechanism's grades and ""); `on_start(watch) -> remover` (`watch(started)`, after each start); `on_release(stop) -> remover` (`stop: async () -> str`: an owner stops its own program on `/release` and says what it stopped, "" for nothing); `await release() -> str` (each owner's `stop`, then the mechanism lets go of the placeholders it holds on the host, and what each said); `released() -> bool` (`/release` ran and nothing has started since: any start ends it; an owner that would start only to keep something warm waits while it holds, asking with nothing awaited between the question and the start). It never stops a row's program itself, and knows nothing of inputs or of which program is the Python process. What a jail allows: [runner-cordis-plugin](plugins/runner-cordis-plugin/README.md) | `runner:confined` (a brig jail per start), `runner:unconfined` (`--no-jail`: a plain subprocess, every grade `unenforced`, its environment without `CLAUDE*` or `ANTHROPIC_*`) | `python:tool` (`start`, and its start's `report`, `notice`, `reads`, `writes`; `on_release`: its Python process's stop), `extensions:process` (`start`: the extensions process; `released`; `on_release`: its stop), `runner:approval` (`report`), `tui:grades` (`report`, `on_start`), `runner:release` (`release`) |
| `approval` | the rule for whether what the model asked for runs without asking the person: `confined: bool` (the runner enforces `fs_write` and `network`; read from its `report()` each time), `unasked(question) -> bool` (it is the memory tool (`runs` `"memory"`): it runs in bh-02's own process, outside the jail, but writes only beneath `host.auto_memory` through no link, which the jailed model can already write unasked, so it is unasked whether the runner confines or not; or it runs in the runner (`runs` `"jail"`, when the question says nothing) or is bh-02's own tool acting only on the session's jail and bh-02's own state (`runs` `"harness"`), and the runner confines it; every other `"host"` call is never unasked). Asking is not the rule's: each asker puts what is not unasked to the person through `output.confirm(question)`, runs it only on a yes, and keeps no copy of the rule. A capability, bound by one row, not a broker: the rule has exactly one author. Depends on `runner` alone, so `/clear` and a new ui leave it up; only a layer replaces it ([why](plugins/runner-cordis-plugin/README.md)) | `runner:approval` | `agent:loop` (`unasked`: each call), `extensions:process` (`confined`: what the model is told; `unasked`: each extension to load), `python:tool` (`confined`: what the model is told, and whether the startup files run unasked), `tui:grades` (`confined`: `jailed` or `unjailed`) |
| `host` | what the host is, for the rows that keep the model's code from it and those that read its files: `paths`, `secrets`, `trusted` and `code`, each a `tuple[str, ...]` of absolute paths, and `auto_memory: str`, `key_envs: Mapping[str, tuple[str, ...]]` and `models_file: str`. `paths` (the layer files the loader watches); `secrets` (what no jailed input may read: the sessions' state directories, this run's and the default; bh-02 reads no credential file, so no such file is among them); `trusted` (bh-02's config directories, this run's and the default `~/.config/bh-02`, as named and as resolved, whose files the host reads and trusts: `bh_02.bootstrap.config_directories`); `code` (where bh-02 runs its own code from: the directory of every package a layer may name as installed, `bh_02`, `cordis`, `cordis_helpers`, `brig`, `host_paths` and each `cordis.plugins` entry point's top-level package, a single module's file, as named and as resolved, found by name, importing nothing: `bh_02.bootstrap.code_directories`); `auto_memory` (the project's auto memory directory, `$XDG_STATE_HOME/bh-02/projects/<project>/memory`, which the command line makes; '' for none: `bh_02.bootstrap.memory_directory`); `key_envs` (each variable an endpoint of the models file reads as its `key = { env = ... }`, to those endpoints, and `models_file`, the file read: `bh_02.bootstrap.models_keys`; empty when there is none or it is in the project; `runner:confined` refuses an environment list naming one, and `commands:shell_command` leaves them out of a `!` command's environment). What the jail does with each: [runner-cordis-plugin](plugins/runner-cordis-plugin/README.md) | `bh_02.bootstrap:host` (mounted by its `run()`) | `runner:confined` (every field: what an input may not read, write or create, and `auto_memory` a root it may write), `commands:shell_command` (`key_envs`), `subagents:parent` (`trusted`: the only places agent type files are read, `agents/NAME.toml`, and never one whose reading passes through the project, nor one read through a link: `host_paths.read_beneath`), `memory:files` and `memory:auto` (`auto_memory`: the index read through no link, and the `memory` tool writing it from bh-02's own process, outside the jail) |
| `commands` | the command broker: `register(spec, run) -> remover` (`spec`: `name`, `help`, `usage`, `choices`?; `run: async (args: str) -> answer`), `claim(prefix, spec, run) -> remover` (every line that starts with `prefix`, one character that is no letter, digit, space or `/`, goes to `run` with the rest of the line; a prefix is one row's, so a second claim raises; `/help` lists it, the palette doesn't), `specs()` (the slash commands), `claims(line) -> bool` (whether a line is the harness's rather than the model's: `/name` then whitespace or the end, a known command or not, or a claimed prefix), `run(line) -> answer` (text, shown as one `note`, or a sequence of events shown as they come), `take_for_model() -> list[str]` (what commands left for the model since it was last asked, in the order they ran; taking it empties it), `on_stop(note) -> remover` (`note: () -> str`, a line for the stop notice, '' for none) and `stop_notes() -> list[str]` (every row's line, sorted, a note that raises told as one line; the chat row shows them as notes right after the `stop` of a reply the person interrupted: `subagents:parent` says how many background agents still run and that `/agents stop` ends them). It holds an answer's `for_model` events instead of answering them; a `cleared` drops what it holds, and a note says so, unless it is `compacted`. It holds them in memory and depends on nothing, so a restart of the chat row keeps them and a resumed session starts without. A sub-agent's realm reads no `commands` from outside, so beside its `memory` row it mounts a `commands:registry` of its own (`agents/NAME/commands`), which only that row registers with. Each command's answer is its owner's: `/clear`, `/compact` (agent), `/model` (models), `/agents` (agents), `!COMMAND` ([commands-cordis-plugin](plugins/commands-cordis-plugin/README.md)) | `commands:registry` | `chat:converse` (`claims`, `run`, `take_for_model`, `stop_notes`), `commands:operator`, `models:switch` (`/model`), `runner:release` (`/release`), `agent:conversation` (`/clear`, `/compact`), `memory:files` (`register`: `/memory`), `subagents:parent` (`register`: `/agents`; `on_stop`), `extensions:process` (`register`; never `claim`), `commands:shell_command` (`claim`: `!`), `tui:palette` (`specs`) |
| `jobs` | the restarts commands ask for, a capability: `put(job, failed)` (`job`: an async function of nothing, run after those put before it, one at a time, in the row's own work, never in the caller's task, which a restart could cancel half-way; `failed(why) -> str`: what the person is told through `output.notice` if it raises, `why` one line naming the error), `pending() -> bool`, `settled()` (returns once none is queued or running). Depends on `output` alone, so no restart it runs reloads it | `commands:jobs` | `commands:operator` (`put`: `/restart`), `agent:conversation` (`put`: `/clear`, `/compact`), `models:switch` (`put`: `/model NAME`'s reload), `chat:converse` (`settled`: before each read) |
| `session` | the running session: `current: str` (its id, empty when the composition runs without a session), `resumed: bool` (whether it was continued with `--resume`) | `bh_02.bootstrap:session` (mounted by its `run()`) | `tui:status` (`current`, `resumed`: the status bar's session id) |
| `loader` | cordis's loader handle: `status()`, `rows` (each row as it was mounted, with its `entry`), `entries()`, `restart(*rows)` (together: a row depending on several reloads once), `reload()` (read the layer files again now, rather than at the watcher's next look), `explain(row)`, `config.layers` | the loader itself (cordis) | `commands:operator` (`status`, `restart`), `models:switch` (`reload`, `status`; `config.layers`: whether a layer after the session's sets the model row's config), `agent:conversation` (`status`, `restart`; `rows`: the transcript row's `use` and `path`, as it runs), `tui:status` (`entries`: whether the layers still name the model row; `status`: whether it is up when the field is first pushed), `models:catalog` (`entries`: the model row's config), `subagents:parent` (`rows`: the rows a sub-agent's conversation is copied from, as they were mounted) |
| `asker` | a confirm-only view of the parent's `output` for sub-agents: `confirm(question) -> bool`, only for a question that says which agent asks (`agent`, a name and a type; any other is a no, never put to the person). With `runner`, `approval` and `host`, the only key a sub-agent's sealed realm reads from outside (`use(cordis.loader:loader, config=LoaderConfig(overrides=..., watch=None), expose=...)`); every key its rows bind is its own, and they run under ids prefixed `agents/NAME/`. What the agents row starts: a child of an agent type, which is data (a prompt section, a model, a step limit, the tool rows of its `tools` it grants; shipped `explore` and `general`, the person's from `host.trusted`'s `agents/NAME.toml`), in the foreground or in the background (`agent_wait`), at most `max_running` at once, each ended by its type's step limit, its start asked past `session_agents` or for a model other than its type's ([subagents-cordis-plugin](plugins/subagents-cordis-plugin/README.md)). Each child's events also go to `<session>/agents/NAME/events.jsonl`, created 0600 by the agents row alone (under the sessions' state directory, in `host.secrets`, so no jailed input reads or forges it): one JSON object a line, `{"at": ISO time, "event": ...}`, the first `{"type": "agent_start", "name", "agent_type", "prompt", "background"}`, then each event of its reply as the loop yielded it, the last `{"type": "agent_end", "report"}`; `bh-02 watch SESSION AGENT` renders it read-only. A log whose write fails (a full disk, the file removed or replaced) stops, writing no `agent_end`, and the child goes on; when its run ends one `note` through `output.show` names the file, when the write failed, the error, and that `bh-02 watch` shows nothing after it and never sees the agent end: it ends when the session is no longer running, or on Ctrl-C | `subagents:parent` | `subagents:output` (in each sub-agent's realm) |
| `roster` | how many sub-agents run now, read-only: `running() -> int` (a child waiting for a slot counts; one being stopped does not) and `watch(hear) -> remover` (`hear()`, called on the event loop after each start, stop and end of a child). It starts and stops nothing | `subagents:parent` | `subagents:status` (the status bar's `agents` field: `agents: N running`, `N running` then `N` as shorter forms, taken down at none) |
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
and a line typed meanwhile reaches the new loop: never the old one, never dropped, never a reply
the restart stops. How the ui shows rows coming back up: [tui-cordis-plugin](plugins/tui-cordis-plugin/README.md).

**Brokers** (`commands`, `frame`, `system`, `tools`, `asides`, `access`; the paper's, section
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
the same way. The loop records each call on its `tool` entry (call record, Shapes): when it
reached approval, what approval made of it (`unasked`, `yes` or `no`: a `no` never runs), how long
the person took and the tool ran, and the sub-agent it started; the calls an input made are
listed in the `nested` of the call that made them. A tool's row tells the model about its tool in a `system` section of its own, never
in the spec's description, which a model server caches with the list. A reply the person stops
still answers every call it made: [the loop](../docs/bh-02/how-it-works/loop.md). A process that
dies mid-call answers none, since the step's entry is appended before its calls run; the next reply
answers each call of the last step that no `tool` entry follows, before anything else, so a resumed
conversation is whole before its first request (call record, Shapes).

**The model's extensions** reach bh-02 only through four keys, bound in the extensions process,
each of which only adds: `commands.register` (never `commands.claim`: there it raises),
`frame.status` (pushed under `NAME:field`), `system.add(text)` (text, not a function: it
crosses a socket) and `tools.register` (registered with `runs = "jail"` whatever it says, never `"harness"`, `"memory"` or `"host"`, and never under one of
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
tool result {"content": str, "touched"?: [str, ...], "child"?: str}   a tool's answer to a call: what
            the model reads, and the files the call opened (absolute), as the tool says it opened
            them: match them against files you chose, never open one because it is named here.
            `child`: the sub-agent the call started (the `agent` tool's, foreground or background;
            absent when it started none); the loop keeps it on the call's record (call record), as
            it keeps `touched` for the asides, and drops anything but a non-empty string
question    {"name": str, "input": Mapping, "runs"?: "jail" | "harness" | "memory" | "host", "title"?: str,
             "lines"?: [str, ...], "language"?: str,
             "agent"?: {"name": str, "type": str}}   put to `approval.unasked`, and when that
            says no, to the person by `output.confirm`: a call (its tool's name, its input, where
            it runs, and how it is shown: its tool's `show`, which may give only `title`,
            `lines` and `language` (never `name`, `input`, `runs` or `agent`: the loop and the
            asker set those), the python tool's `title` and its code as `lines`, else its input
            as JSON), or an extension to load (`"name":
            "extension"`, its own `title`, its source as `input.code`), or a sub-agent's start
            the agents row asks about (`"name": "agent"`, its `title` saying why, the prompt as
            `lines`). `agent`: the sub-agent that asks, which its `output` (`subagents:output`) sets
            over whatever the question carried; the approval modal says who asks, and Ctrl-C never
            answers it (the reply it stops withdraws its foreground child's; a background
            child's stays queued)
report      Mapping[axis, grade]   a start's, per axis (`fs_read`, `fs_write`, `network`, `limits`,
            `env`, ...): `enforced`, `best_effort`, `cooperative` or `unenforced`, as brig grades
            them; what runs there is `confined` when `fs_write` and `network` are enforced
message     {"role": "user" | "assistant" | "tool", "content": str,
             "tool_calls"?: [tool call, ...]   (assistant),
             "provider"?: Mapping  (assistant: the provider's own message, replayed as received),
             "call_id"?: str       (tool: the call it answers; its content is the call's result,
                                    then each aside told with it and any change in the
                                    instructions, each after a blank line),
             "asides"?: [str, ...] (tool: the asides its content tells, sorted; `[]` for none, and
                                    for a call that never ran. Every `tool` entry the loop writes
                                    has it),
             "feedback"?: str      (user: the loop telling the model why its last step didn't count),
             "today"?: str         (user: the date told with it, `2026-10-07`; its content then
                                    starts `(Today's date: 2026-10-07.)` and a blank line, before
                                    any change in the instructions and the person's words),
             "at"?: str            (user: when the message came, UTC ISO-8601 to the millisecond
                                    with `Z`, `2026-10-18T03:47:12.345Z`, so it sorts as text; on
                                    `feedback` and an unanswered message too, and on a seed's),
             "seed"?: {"keep": str}  (user: the first entry of a conversation `/compact` began,
                                    bh-02 saying it carries on from an earlier one: `keep` is the
                                    text the person gave `/compact WHAT TO KEEP` for the summary
                                    to keep, `""` for none, so a reader never matches the seed's
                                    wording; the summary follows as an assistant entry whose
                                    `step` is the summary step's),
             "step"?: step record  (assistant: the step that made the entry, on every one the
                                    loop writes from a model step, `STOPPED` and `FAILED` ones
                                    too; not on the entry that answers a message the model was
                                    never asked, which is no step),
             "call"?: call record  (tool: the call it answers, on every `tool` entry the loop
                                    writes, the `_NOT_RUN` and interrupted ones too, and the
                                    answer given a call a crash left unanswered)}
                                   `asides`, `today`, `at`, `seed`, `step` and `call` are the loop's own: a provider sends `content` alone
step record {"at": str, "first_chunk"?: float, "took"?: float, "model"?: str, "usage"?: usage total,
             "settings"?: settings, "tool_changes"?: "listed"}
                        a closed TypedDict (`agent_cordis_plugin.records`). `at`: when the request
                        was handed to `complete`. `first_chunk`: seconds to the first chunk of any
                        kind, a Claude Code start or rebuild and the provider's own retry included;
                        `took`: seconds to the last chunk (both rounded to the millisecond, from a
                        monotonic clock; neither when the step ended before any chunk). `model`: the
                        id the `usage` chunk named (absent when no provider reported one). `usage`:
                        the step's `usage` chunks summed (absent when it sent none). `settings`: only
                        on a conversation's first step and on any step whose settings differ from the
                        last recorded in it. `tool_changes`: only when the model's is `listed`;
                        absent means `fixed`. `/compact`'s summary step is recorded the same way, by
                        the same code over the same clock, on the assistant entry of the seed (its
                        `settings` always, being its conversation's first step)
call record {"at": str, "answer"?: "unasked" | "yes" | "no", "waited"?: float, "took"?: float,
             "child"?: str, "nested"?: [nested record, ...]}
                        a closed TypedDict (`agent_cordis_plugin.records`). `at`: when the call
                        reached approval, or was refused before it (a name it was not offered, an
                        input that does not fit the spec, a tool not running). `answer`: what
                        approval made of it (`Answer`, a StrEnum written as its word): `unasked`
                        (`approval.unasked` let it run), `yes` or `no` (the person was asked; `no`
                        also covers a question the app closing withdrew, and a `no` call never runs);
                        absent for a call refused before approval, or never reached (the reply was
                        stopped before it started, or while its question was open: `at` alone;
                        so too a call a crash left unanswered, which the next reply answered
                        with `interrupted: bh-02 stopped before this call finished; it may have
                        partly run`: its `at` is when that reply began, and no answer, wait or run
                        time was recorded, since the process that had them died with them).
                        `waited`: seconds from the question put to its answer, the time queued
                        behind another question included (the ui shows one at a time); only when
                        the person was asked. `took`: seconds the tool ran, a question the tool puts
                        during its own run inside it (a call the stop interrupted: up to the stop);
                        absent when it did not run. `child`: the sub-agent the call started (the
                        `agent` tool's result names it, `tool result`). `nested`: the calls its
                        input made through `tools`, in the order they ended, each a nested record
                        (`child` and a refusal included); absent when it made none. Durations are
                        rounded to the millisecond, from the monotonic clock
nested record
            {"name": str, "at": str, "answer"?: ..., "waited"?: float, "took"?: float, "child"?: str}
                        a closed TypedDict: a call record with its tool's `name`, and no `nested`
                        (a call a nested call made is listed beside it, in its call's `nested`)
settings    {"model": str, "provider": str, "max_tokens"?: int, "temperature"?: float}
                        a closed TypedDict: the model's `settings` attribute (above), as recorded
usage total {"input_tokens": int, "output_tokens": int, "cache_read_input_tokens": int,
             "cache_creation_input_tokens": int, "cost_usd"?: float, "partial"?: true}
                        a closed TypedDict: a step's `usage` chunks added up by the one function
                        `/compact` sums its own with (`records.summed`); `partial` when its last part is
system entry
            {"role": "system", "content": str}
                        a prompt told whole: a transcript's first, the one every request begins
                        with
            {"role": "system", "edits": [{"at": int, "drop": int, "add": [str, ...]}, ...]}
                        a later prompt, as what turns the one before it into this one, by
                        paragraph (split at every blank line, exactly): from paragraph `at`, `drop`
                        give way to `add` (`prompt.edits`; `prompt.latest` applies them in turn,
                        passing over one `edits` could not have made). The loop's own: a request
                        carries the first alone, so a provider never sees `edits`
tools entry {"role": "tools", "tools": [tool spec, ...]}   the list a conversation began with
            {"role": "tools", "added"?: [tool spec, ...], "removed"?: [str, ...],
             "redefined"?: [tool spec, ...]}   a later change, each in name order, only those
                        there are. The loop's own
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
             "partial"?: true, "model"?: str}
                        one step's usage, not a running total: a ui sums them (a provider that
                        reports running totals sends differences; one step may send several,
                        which a ui shows as one line). `input_tokens` is everything the model
                        read, cached or not; the cache fields say how much of it was read from,
                        or written to, the provider's prompt cache. `partial`: a part sent before
                        the provider's output count, which a later part carries. `model`: the id
                        that answered, which the loop records on the step and a ui ignores
            {"type": "stop", "reason": str}              the loop's classification of a step (below)
            {"type": "note", "text": str}                 a line shown to the person, never the model: the
                                                          shell speaking (a command's answer); from the
                                                          loop, what it told the model as an aside (its
                                                          instructions changed; an aside from `asides`,
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

A reply is a stream of events: everything the person might want to see of it, in order.
`text` is the reply itself; the rest describe the work around it. A consumer that shows only
text keeps `text` and may drop the rest; one that shows more matches on `type` and ignores types
it doesn't know, so a provider can add one.
