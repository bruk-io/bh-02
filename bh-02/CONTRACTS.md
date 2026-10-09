# Contracts

No plugin in this workspace imports another. They agree on **names** (the keys a layer wires)
and **shapes** (what a value bound under a name looks like), written down here and nowhere
else. A consumer states the shape it needs as a `runtime_checkable` Protocol of its own; cordis
checks the value against it when the dependency is committed, before the consumer's first
effect. A provider imports nothing to satisfy a contract; it just has the methods.

Data crosses plugins as plain dicts, the way it crosses a wire. A package that reads a shape
declares a `TypedDict` or `Mapping` for the part it reads; TypedDicts are structural, so two
packages' declarations of one shape type-check against each other without sharing a line.

## Keys

| Key | Value | Bound by | Read by |
|---|---|---|---|
| `loop` | a conversation: `reply(message: str) -> AsyncIterator[event]` | `agent:loop`, `bh_02.testing:*` (fakes) | `chat:session` |
| `input` | `read() -> str \| None` (`None` means no more input); `interrupted()` returns when the person asks to stop the running turn (a stop asked for after a line was read and before `interrupted()` is called is held for it; the next `read()` drops one still held); `closed()` returns once no more lines will come (the person left, or the ui crashed): a command running then is cancelled, since nobody is left to read its answer | `tui:app` | `chat:session` |
| `output` | `show(events: AsyncIterator[event])`, `notice(message: str)`, `confirm(request) -> bool`. Not part of the key's shape: `lifecycle(event)` (a cordis `Event`: `kind`, `fiber`, `error`), which the ui row itself `observe`s to show rows reloading; no consumer of `output` calls it | `tui:app` | `chat:session`, `kernel:approval` (`confirm`: the model's code, unjailed), `tui:status` (`show`: the jail's notice, as a `note`), `agent:compact` (`show`: a `note` as the summary step begins; `notice`: a restart it queued that failed, after the new conversation was written), `commands:operator` (`notice`: a restart `/clear`, `/model` or `/restart` queued that failed, after the command answered) |
| `frame` | the app's frame, which rows push into: `status(field: str, text: str, *shorter: str) -> remover` (`shorter`: shorter forms of `text`, each shorter than the last, which the status bar shows instead when its line is too narrow), `commands(specs) -> remover` (`specs: () -> Sequence[spec]`, a spec: name, help, usage, and `choices`?: `() -> Sequence[{args, help}]`, the arguments the palette offers as entries of their own, `/model haiku`; both read each time the palette opens, so commands registered later, and models added since, are offered) | `tui:app` | `tui:status` (`status`), `tui:palette` (`commands`), `extensions:extensions` (`status`: the extensions' fields, each under its extension's name, and its own `extensions` field) |
| `system` | the system prompt: `text() -> str`: who the model is and where it is working (bh-02's own, then the directory and the git branch, read from `.git/HEAD` through no link), then the sections rows add; not the date, which `agent:loop` tells with the person's message. Read fresh, on `executor`, off the event loop (the loop calls it there, one call at a time, so a section must not need the event loop); `add(name, section) -> remover` (`section: () -> str`, read with the rest each time `text()` is, in that thread, so a row with something to tell the model `acquire`s one and it leaves with the row; sections are told sorted by `name`, two of one name by their text, never in the order rows added them, so a row that adds its section again after a restart keeps its place and the prompt does not read as changed: `extensions`, `extensions: NAME` (an extension's own), `memory`, `memory: auto`, `python`). A broker, depending on its config (`root`) alone; the prompt names no tool (a tool's row says what the model should know of it, in a section) | `agent:system` | `agent:loop` (`text`), `kernel:kernel` (`add`: `python`, what the model is told about the python tool, its REPL and its jail, read per request), `memory:memory` (`add`: what loads at launch), `memory:auto` (`add`: auto memory, how to keep it and its index, read once a conversation), `extensions:extensions` (`add`: how to extend bh-02, and the sections extensions add) |
| `model` | one model step: `complete(messages, tools) -> AsyncIterator[chunk]` (`tools`: the tool specs offered through standard tool calling, from `agent:loop` the specs `tools` held at the loop's first request, in name order, the same list every step of that loop; closing it stops the step and releases what it holds). `messages` is always the whole conversation; a provider may keep its own copy across calls (the claude-code provider keeps one Claude Code session per conversation, checks each request against it and rebuilds it from `messages` when they differ), so it must not assume anything the messages do not say. `models:model` binds the model its config's `default` names, on that model's provider: `claude-code` (Claude through Claude Code), `openai` (any OpenAI-compatible `/chat/completions`), or a `module:attribute` factory given the model's table (bh-02's fakes); one it can't use binds too, and each step raises what is wrong | `models:model`, `bh_02.testing:echo_model`, `bh_02.testing:slow_model`, `bh_02.testing:repl_model` (fakes) | `agent:loop`, `agent:compact` (one step: `/compact`'s summary, asked as the loop's next request would be, with `tools.specs()` offered; any call it makes is never run) |
| `models` | the models there are, read fresh (the model row's config from the loader's entries, and the models file) each time: `listed() -> Sequence[{name, provider, id, current: bool, where?, problem?, shadows?}]` (in order: the built-ins, the models file's, the model row's `extra`; `where`: an openai model's `base_url`; `problem`: what is wrong with its table and what to do; `shadows`: a user's model named like a built-in; a models file that can't be read raises; one in the project is not read, and lists none), `current() -> {name, provider}` (the model the model row names now; `provider` empty when the name is no usable model; never raises), `check(name) -> str \| None` (why the model row can't switch to `name`, or None), `path: str` (the models file), `problem: str \| None` (why the models file is not read and where it must be instead: it is in the project, which the model's code can write; None when it is outside, there or not). Depends on `loader` and `layers` (where a key's `local.env` is looked for), neither of which a switch replaces, so a switch never reloads it or what depends on it | `models:catalog` | `commands:operator` (`/model`), `tui:status` (`current`) |
| `transcript` | `messages: Sequence[message]` (property), `append(message)`; besides the conversation, it keeps the system prompts the model was told as `{"role": "system"}` entries (`system entry`, below): the first, whole, is the one every request begins with; a later one is a change told as a note on the message after it, kept as the edits from the reading before it rather than a whole copy (a transcript kept before the loop kept edits has each reading whole, and resumes as it is); the dates it was told, each as `today` on the person's message that told it; and the `notes` told with each input's result, as `notes` on its `tool` entry (`message`, below). `agent:transcript` keeps it in its config's `path` (a session's `transcript.jsonl`), which `/compact` replaces whole with a new conversation, its first two messages bh-02's note and the summary (the old file kept beside it, under the first of `.bak`, `.bak.2`, ... not taken), then restarts the row | `agent:transcript` | `agent:loop`; `memory:auto` (its lifetime alone: a new conversation reads the auto memory index afresh); `memory:on_touch` (`messages`, read once, at the first input that opens a file: a note in a `tool` entry's `notes` was told before it began, wherever it sorted among the others and whatever the result printed; on-touch's own note joins its texts with a blank line, so it ends one where the next begins, as memory begins one (`From FILE, instructions ...` or `From FILE, a rule for ...`; a file a text imports is part of it): a text another note's follows is told again after a resume. An entry from before the loop kept `notes` is searched instead: a note it holds whole, after a blank line and up to another note or the entry's end, though not one the entry starts with; where the result ends is not marked there, so one an input printed that way counts too. It shares its lifetime, so a new conversation (`/clear`, `/compact`) starts it afresh); `agent:compact` depends on the row's file, not the key (the `path` of the row as the loader mounted it, `loader.rows`, when it is a running `agent:transcript` row), since it restarts the row |
| `tools` | the tools the model is offered, a broker: `register(spec, run, *, runs="jail", show=None) -> remover` (`spec`: a tool spec, Shapes, named by its `name`, which is one tool's: a second registration of it raises; `run: async (input) -> tool result`, Shapes: what it raises, or an answer of another shape, is told to the model as an error naming the tool, never the reply's failure; `runs`: where a call runs, `"jail"` (the jail row's jail: `approval` asks only when that does not confine it) or `"host"` (bh-02's own process: always asked); `show: (input) -> {"title", "lines", "language"?}`, how a call is put to the person, else the tool's name and its input as JSON), `specs()` (every registered spec, in name order, so a row registering again after a restart gives the same list), `get(name)` (the registration, or None), `await ready(names, timeout)` (the names still unregistered once they all are or `timeout` seconds pass). A row `acquire`s its registration, so the tool leaves with it. Depends on nothing, so a tool's row coming, going or restarting (the kernel's, on `/clear`) reloads neither the loop nor another tool's row | `agent:tools` | `agent:loop` (`specs` once, at its first request, after its config's `requires` are `ready`, waiting `wait` seconds, 30; `get` for each call), `agent:compact` (`specs`: offered with the summary request), `kernel:kernel` (`register`: `python`) |
| `notes` | what the model is told with a call's result, a broker: `add(fn) -> remover`, iterable for the functions added. `fn(call) -> str`: `call` is `{"name", "input", "result", "touched"}` (the tool's name, the call's input, its result as the model reads it, and the files it opened, as its tool answered: the python tool's are what the input's own Python code opened); it returns a note to go after the result ('' for none). A function adds a note and never changes the result, and the loop sorts the notes, so any set of them composes in any order, and keeps them on the call's `tool` entry as `notes` (`message`, below); one that raises or returns something other than text is told as one line naming it, and the rest still say theirs. Called on `executor`, off bh-02's event loop, after every call that ran, one call's at a time and never beside a reading of the prompt (a stop waits for them), so it may read files but must not need the event loop; only rows in a layer add to it (it runs in bh-02's process; an extension's code runs in the jail). Its contributors keep what they have told as their own state, which a new conversation (`/clear`) starts afresh; what was told before they began (a resumed session's, or before a row reloaded) they read from `transcript` (its `tool` entries' `notes`), so a note is told once a conversation, a resumed one too | `agent:notes` | `agent:loop` (iterates), `memory:on_touch` (`add`) |
| `access` | what is asked before a file is read or written, a broker: `before_read(fn)` and `before_write(fn)` each return a remover (`fn(path) -> str | None`: None lets the file be opened, text refuses it and says why), `asking()` (the kinds some function is asked about, `"read"`, `"write"`: a tool need not ask about the others), `refusal(kind, path) -> str | None` (every refusal, sorted, joined by a blank line; None when all let it go ahead; a function that raises refuses, saying so: a check that could not be made is not a yes). Called off bh-02's event loop (a function may read files), while a call runs, one question at a time. The model reads nothing while a call runs, so a question only matters because it can stop the open: a refusal reaches the model with the call's result. It hears what the tools report and nothing else (below: **Asking before a file is opened**). Depends on nothing | `agent:access` | `kernel:kernel` (`asking`, `refusal`: before an input's own Python opens a project file), `memory:on_touch` (`before_write`: the first write to a file whose on-demand instructions have not been told) |
| `memory` | Claude Code's memory (its docs' "How Claude remembers your project"): `text() -> str` (what loads at launch: the managed policy's CLAUDE.md; `~/.claude/CLAUDE.md` and `~/.claude/rules/` without `paths`; each directory's `CLAUDE.md`, `.claude/CLAUDE.md` and `CLAUDE.local.md` from the filesystem's root down to the project's, the project's `.claude/rules/` without `paths` among them; `AGENTS.md` as `instruction_files` says; each file's block-level HTML comments out and its `@path` imports after it, up to four hops; '' when nothing loads), the memory row's section of `system`, read on `executor` with the rest of the prompt; `touched(paths: Sequence[str]) -> Sequence[(file, text)]` (what loads on demand for the absolute files an input opened: a subdirectory's CLAUDE.md files and `.claude/rules/`, every rule whose `paths` match; broadest first), called on `executor` through a `notes` function; `listed() -> [Entry]` (every memory file and how it loads, for `/memory`, the auto memory index among them); `places() -> (root, home)`. Every file is read through no link the model could have made, and a file in the project imports nothing outside it. It keeps nothing, so `/memory` on the event loop and the prompt in the worker thread may ask at once | `memory:memory` | `memory:on_touch` (`touched`) |
| `executor` | where `agent:loop` runs what may block, off bh-02's event loop: `await run(fn)` (`fn()`, given nothing, in a daemon thread, once the call before it has ended; its result, or what it raised). A caller cancelled while it waits (a stopped reply) stops waiting and nothing else: the call runs to its end, its outcome dropped (what it raised is logged nowhere), and the next call waits for it, so one runs at a time however often a reply is stopped. A daemon's thread, not the default executor's, which `asyncio.run` and the interpreter join as they end, so a call left running never holds bh-02 open. Depends on nothing, so `/clear` and `/model`, which reload the loop, keep it and the call in flight; a new one (its row restarted, or replaced by a layer) knows nothing of a call the last one left running | `agent:executor` | `agent:loop` (`run`: each reading of the prompt, `system.text()` then `kernel.instructions()`, and each input's `notes` functions) |
| `jail` | `start(argv, *, cwd, endpoint) -> started` (a program listening on the Unix socket `endpoint`; `started.interrupt() -> bool`, `await started.stop()`, `started.ended() -> str`: why the jail ended the program itself, for the person, or "": a Linux `brig:jail` ends itself when the host undoes one of its mounts; and what this start is, kept with it whatever else the jail starts (the `jail` row starts the Python process and the extensions process, each from a command of its own): `started.report() -> Mapping[axis, grade]` (its grades), `started.notice() -> str` (what the person should know about the jail it runs in: `brig:jail` on Linux names the secrets it holds with a mount the host can undo; empty when there is nothing to say), `started.reads() -> tuple[str, ...]` (the trees it can read when that is all it can read: a Linux `brig:jail`'s allowlist, which names the program's own directory and bh-02's own code (`layers.code`), and writable roots, each once and none inside another; empty when it reads everything but what it hides, as darwin's does, or is no jail), `started.writes() -> tuple[str, ...]` (the directories it may write, but a scratch directory of its own: `brig:jail`'s project root and what its `write` adds; empty when it confines no writes, as `kernel:unjailed`)), `report() -> Mapping[axis, grade]` (the grades, known before anything starts; no start changes them), `await release() -> str` (`/release`, called once the `kernel` row has stopped the Python process: what that freed on the host, for the person; a Linux `brig:jail` first stops every other process it started that still runs, the extensions process, whose jail holds the same paths (a start under way is waited for and stopped too), then names where bh-02 looks for its credential and nothing holds now, or what another session's jail still holds, and says the extensions process stopped; empty when there is nothing to say), `released() -> bool` (whether `release` stopped its programs and none has started since: the next start ends it, which is the next input's Python process; a row other than `kernel` (the extensions row) starts none while it holds, asking with nothing awaited between the question and the start, or its jail would hold again what the release freed before the person could use it; never for one whose `release` stops nothing, as `kernel:unjailed` and darwin's `brig:jail`) | `brig:jail`, `kernel:unjailed` | `kernel:kernel` (`start`, and its Python process's `report`, `notice`, `reads` and `writes`, the last where the person's startup file is not read on the host; `report`, for `confined`; `release`), `extensions:extensions` (`start`: a second process, the extensions process; `released`: it starts none while the jail is released, then loads every extension again in a new one), `kernel:approval` (`report`) |
| `kernel` | bh-02's handle on the Python process (the process the jail started that runs inputs and keeps the namespace for the run; the key's name is older than the term), and the `python(code)` tool, which its row registers with `tools` (spec `PYTHON`, run `call`, shown as its code) and tells the model about in the `system` section `python`: `call(input) -> tool result` (`input["code"]` run as an input, answered with `run`'s text and the files `touched()` names; an input with no `code` string runs nothing and says why), `instructions() -> str` (what the model is told about it, the `python` section, read per request on `executor`; under a jail that reads by allowlist, it names the trees `reads()` gives and says nothing else exists there; confined, it names where its code may write: the project, and any directory outside it its worker's jail lets it write, as the auto memory directory, from that start's `writes()`), `run(code: str) -> str` (one input, as the model reads it; every failure it knows of, a Python process that died, an answer it can't read, one the jail won't start again, is the input's text, not an exception; a new Python process's first input starts with a parenthesised note when there is one: it was started again (and why, when its jail ended the last one), or what the startup files did, the person's own `$XDG_CONFIG_HOME/bh-02/kernel.py` (else `~/.config/bh-02/kernel.py`; read by the host, since a Linux jail has no home in it, unless it is in the project or another root its Python process's `writes()` names, or its way passes through one: then read in the jail, and if that fails the note says why) and then the project's `.bh-02/kernel.py` (read in the jail), the only one `instructions()` says is the model's to edit; a startup file that ended the Python process is passed over by the ones after it, until `/restart kernel`, and said to be, and one Ctrl-C stopped is not run again in that process, the next input saying so; either way what the note had to tell before it, the restart and why among it, is still told: the input it cut short says it before which file ended the process, and the next input after a stop says it with what was stopped), `confined: bool` (whether its jail confines its inputs, by `approval`'s rule: what `instructions()` tells the model, and whether the startup files run unasked), `report()`, `notice()` and `reads()` (its Python process's jail's: what the Python process it last started is, kept once that stops, never another process's of the same jail; before any, the jail's `report()`), `await release() -> str` (ends the Python process and its jail now, then its jail's `release()`, which on Linux stops the extensions process too; the next input starts a new Python process, told its variables are gone, and the extensions load again; an input running is left alone and the answer says so), `touched() -> tuple[str, ...]` (the files under its `root` the last input opened, read or written, absolute and each once, at most 1,000: what the input's own Python code opened with `open` or `pathlib`, heard by an audit hook in the Python process, not an `os.open` (`shutil.rmtree`'s, `Path.touch`), a directory it listed, a module it imported, a source file its traceback was formatted from or a file a program it ran opened; empty before any input and after one that did not finish. The Python process runs the model's code, so these are what it says it opened: match them against files you chose, never open a file because it is named here). Before an input's own Python opens a file under its `root` to read or write it, for the kinds `access.asking()` names, its Python process asks `access.refusal(kind, path)` (once per file and kind an input) and a refusal stops the open with a PermissionError; every refusal ends the input's text as a line in brackets (`(bh-02 refused to let this input write PATH: ...)`), so it is told even when the input's code caught the error, and the refused file is in `touched`. Depends on `jail`, `tools`, `system` and `access` (the three brokers, which never reload), so a new ui or model keeps the namespace | `kernel:kernel` | `tui:status` (`confined`, `report`, `notice`: shown as a note each time the `kernel` row comes up), `kernel:release` (`release`: `/release`); its tool reaches the loop and `/compact` through `tools` (`/compact` never restarts the `kernel` row, whose Python process keeps the namespace the summary names) |
| `approval` | whether what the model asked for may run: `confined: bool` (whether the jail confines what runs in it, so nothing is asked; read from the jail each time), `approve(request) -> bool` (async; `request` as in Shapes: yes at once when it runs in the jail (`runs`, the jail when it says nothing) and that confines it; otherwise the person's answer through `output.confirm(request)`, and no when there is nobody to ask). A capability, bound by one row: whether the model's code runs unasked is a rule with exactly one author, which is the point of it, so it is not a broker (guards rows add would compose, but then no one row could say what the rule is). Depends on `jail` and `output`, not `kernel`, so `/clear` leaves it up | `kernel:approval` | `agent:loop` (`approve`: each call), `extensions:extensions` (`confined`: what the model is told; `approve`: each extension to load) |
| `layers` | `paths: tuple[str, ...]`: the layer files the loader is watching, which no jailed input may write; `credentials: tuple[str, ...]`: where the model rows look for bh-02's credential file (`local.env` above bh-02's install and its environment, nearest first; the first that is a regular file is read, unless the row names an `env_file`), the one definition of that search; `secrets: tuple[str, ...]`: absolute paths no jailed input may read: every one of `credentials`, the `local.env` beside and above the project, and the sessions' state directories, this run's and the default one (each session's `claude/`: Claude Code's config and its messaging peer token). A secret under a root an input may write it may not write or create either; `trusted: tuple[str, ...]`: bh-02's configuration directories of the person's, this run's (`$XDG_CONFIG_HOME/bh-02`, else `~/.config/bh-02`) and the default one (`~/.config/bh-02`), each as named and as it resolves (`bh_02.bootstrap.config_directories`), whose files the host reads and trusts (the models file and the person's startup file): no jailed input may write in one that is under a root it may write (bh-02 run from the home directory), or a session could choose what a later one reads there; `code: tuple[str, ...]`: where bh-02 runs its own code from, the directory of every package a layer may name as installed (`bh_02`, `cordis`, `cordis_helpers`, `brig` and each `cordis.plugins` entry point's top-level package; a single module's file), each as named and as it resolves, found by name with `importlib.util.find_spec`, which imports nothing (`bh_02.bootstrap.code_directories`). With an editable install (`uv run` in the checkout, `uv tool install --editable`) these are the workspace's `src/<package>` directories, whose modules bh-02 imports in its own process, and the extensions' worker imports cordis from one. Every jail reads them, and no jailed input may write in one that is under a root it may write (bh-02 working on its own checkout, or run from a home the checkout is in), or it could choose code bh-02 runs; `memory: str`: the project's auto memory directory (`$XDG_STATE_HOME/bh-02/projects/<project>/memory`, else under `~/.local/state`, `<project>` the git repository's root, a worktree's main one, named as Claude Code names it: `bh_02.bootstrap.memory_directory`), which the command line makes and a jailed input may write ('' for none) | `bh_02.bootstrap:layer_files` (mounted by its `run()`) | `brig:jail` (`paths`, `secrets`, `trusted`, `code`: write-denied under a writable root, and on Linux in the read allowlist, read-only; `memory`: a root an input may write, and `credentials`: one that does not exist yet stays denied, so no input can plant it, and `/release` names those it frees), `models:model` and `models:catalog` (`credentials`), `memory:memory` and `memory:auto` (`memory`) |
| `commands` | the command broker: `register(spec, run) -> remover` (`spec`: name, help, usage; `run: async (args: str) -> answer`), `claim(prefix, spec, run) -> remover` (every line that starts with `prefix`, one character that is no letter, digit, space or `/`, goes to `run` with the rest of the line; a prefix is one row's, so a second claim raises; `/help` lists it as the prefix and `spec`'s usage, the palette doesn't), `specs()` (the slash commands), `claims(line) -> bool` (whether a line is the harness's rather than the model's: `/name` then whitespace or the end, a known command or not, or a line starting with a claimed prefix), `run(line) -> answer` (what to show the person: text, which `chat:session` shows as one `note`, or a sequence of events it shows as they are; a command's own answer may also carry `for_model`, which the value holds instead of answering, and a `cleared` in it drops what is held and adds a note saying so, unless it is `compacted` (`/compact`'s), which keeps it: `/clear` answers `cleared`, a `note`, then `restarting`; `/model` lists the models, the current one marked, then where to add models or why the models file is not read; `/model NAME` a `note` then `restarting`, or text saying why NAME can't be switched to; `/model`'s spec has `choices`, one per usable model; `/compact` `cleared` (`compacted`), a `note` carrying the summary, the summary step's `usage` as one event, then `restarting`, or why nothing changed (text, or a `note` then the step's `usage`), having shown a `note` itself (`output.show`) as the step began; `!COMMAND` a `note`, what it printed and how it ended, then `for_model`, the same for the model, or text saying why it didn't run and what to set), `take_for_model() -> list[str]` (what commands left for the model since it was last asked, in the order they ran; taking it empties it: the chat row puts it in front of the person's next message. The value depends on nothing, so a restart of the chat row keeps it) | `commands:registry` | `chat:session` (`claims`, `run`, `take_for_model`), `commands:operator` (`register`), `commands:shell_command` (`claim`: `!`), `extensions:extensions` (`register`: the extensions' commands; never `claim`), `kernel:release` (`register`: `/release`), `agent:compact` (`register`: `/compact`), `tui:palette` (`specs`) |
| `sessions` | the running session: `current: str` (its id, empty when the composition runs without a session), `resumed: bool` (whether it was continued with `--resume`) | `bh_02.bootstrap:session_list` (mounted by its `run()`) | `tui:status` (`current`, `resumed`: the status bar's session id) |
| `loader` | cordis's loader handle: `status()`, `rows` (each row as it was mounted, with its `entry`), `entries()`, `restart(*rows)` (together: a row depending on several reloads once; `/clear` restarts its rows so), `reload()` (read the layer files again now, rather than at the watcher's next look), `explain(row)` | the loader itself (cordis) | `commands:operator` (`restart`, `reload`: /model reloads at once; `config.layers`: the layer files after the session's, which `/model` checks for one that sets the model row's config), `agent:compact` (`status`, `restart`: the loop and its transcript, together; `rows`: the transcript row's `use` and `path`, as it runs), `tui:status` (`entries`: whether the layers still name the model row; `status`: whether that row is up when the model field is first pushed), `models:catalog` (`entries`: the model row's config) |
| `done` | an awaitable (the `asyncio.Task` `background(...)` returned) that resolves when the chat row's own run ends | `chat:session` | `bh_02.bootstrap:harness` |

**The ui's `input` and `output` end with the ui.** Whatever ends the app (Ctrl-Q, `/exit` or `/quit`, a
crash) settles everything waiting on it: a pending `input.read()` returns `None`, every
`interrupted()` and `closed()` returns (so a command running, a `!` one that would take
minutes, is cancelled, and bh-02 leaves at once), a pending `output.confirm` is a no. After a crash, `read()` raises
instead of returning `None`: the failure is shaped like a recoverable one (`kind =
"ui_crashed"`, `message`), and it reaches the command line through the chat row's `done` (a
teardown error would not).

**The ui row's config.** `tui:app` takes `history` (a JSON-lines file the ui owns: it appends
what the transcript draws, draws its last `replay` entries again when it starts, and trims it
once it grows; a session's layer points it at the session's `events.jsonl`; a `cleared` event is
recorded like any other and a replay starts after the last one, so a resume shows the
conversation since the last `/clear` or `/compact` (from the note carrying the summary); a
session made before `cleared` existed still lists the file in `commands:operator`'s `forget`,
and the ui's next write after it is emptied puts a `carried` entry first, so the usage forgotten
entries added up to is kept) and `replay` (how many entries to draw again, 400). The status
bar's `usage` field is the ui's own, pushed by `tui:app`'s output: the session's running totals
of usage events (a resumed session's history included, and not reset by `/clear`: `cleared`
starts a new conversation, not a new session, and what the session spent stays spent), not a
row's. Once a turn has ended with its usage still `partial` (stopped before the provider counted
its output), the output and cost totals are lower bounds and end in `+`.

**Rows coming back up.** `/model` restarts the model row (`model`), `/clear` the loop,
its transcript and the kernel row (a new Python process), `/compact` the loop and its transcript, and the chat row reloads
with them. The ui hears it through the lifecycle events it
already `observe`s: `tui:status` shows `model: NAME (PROVIDER, starting…)` from the row's `unloading` (or
`reload`) until it is `active`, and a line typed while no turn is running and rows are coming
up is kept for the chat row's next `read()` and noted as waiting (`⧗ waiting for loop to
start; ...`), never dropped. The note names only rows that bind a key, which is all the chat
row depends on: a status-bar row reloading with them (`status` after `kernel` restarts) is
not waited on. A restarted row's old fiber ends `inactive` before its new one's
`reload`; a line kept in that moment says it waits at the `reload`. The restart begins a
moment after the command answers (a job queued for the row's own work: the operator's `/clear`
restarts the rows and `/model` reloads the layers it edited, the compact row's `/compact`
restarts its rows), while the chat row is still up and reading again; so each answer ends with
`restarting` (event), naming the rows it restarts. From that event
until each of those rows is `active` again (through the `inactive` inside its restart), the
ui hands no line to the chat row: a line typed right after the command waits for the new
model and says so, rather than going to the old one or starting a turn the restart stops. A
line typed while a command runs waits for it and names no row, unless the command's answer
then announces a restart. A row announced that has not begun two seconds later (nothing
restarted: a layer the loader could not read) is no longer waited on. `/model NAME` with the
model already NAME changes nothing and announces nothing; `/restart ROW` announces nothing
either, so a line typed right after `/restart loop` can still start a turn the restart stops.

**A line the harness takes.** Which lines are the harness's, not the model's, is the
`commands` value's to say (`claims`), and `chat:session` asks it: a slash command, or a line
starting with a prefix a row claimed. Only a row in a layer claims one (the shipped layer's
`shell-command`, `commands:shell_command`, claims `!`): a prefix takes every line the person
starts with it, and `!` runs that line in the person's shell, so an extension can't (its
`commands.claim` raises, and its host passes on nothing but a command, a field and a section). `!COMMAND` runs as the
person: not in the jail and not put to `approval` (the person typed it), in the project,
through their `$SHELL -c`, in bh-02's environment less `ANTHROPIC_*` and `CLAUDE*`. The app
owns the terminal, so the command's stdin is empty, its output captured, and it has no
controlling terminal; Ctrl-C doesn't stop a command (a Ctrl-C while one runs is held, then
dropped by the next `read()`, and the ui says so), so it has a `timeout` (120 s), at which its
process group is ended. The person leaving (`input.closed()`) ends it too: `chat:session`
cancels the command, and its process group is ended before bh-02 exits. Its output is shown,
with nothing a terminal acts on left in it (escapes, control characters), and reaches the
model with the person's next message (its `for_model` event, which the `commands` value holds
and `chat:session` takes, `take_for_model`, and puts in front of that message), never during a
turn: the chat row reads one line at a time, so a `!` line typed during a turn runs after it.
`commands` depends on nothing, so a restart of the chat row (`/model` reloads the loop, and
the chat row with it) keeps what is held; `cleared` (`/clear`) drops it, and a note says so,
but `/compact`'s (`compacted`) keeps it: the summary is written from what the model read, which
never held it, and it still goes with the person's next message.
It is held in memory, so a session left and resumed before the next message starts without
it.

**`frame` is a broker of the same shape as `commands`.** A row that shows something in the
app's frame depends on what it reports on and on `frame`, and `acquire`s an entry: `yield
acquire(frame.status, "jail", summary)`. The entry leaves with the row, so a volatile key
(`kernel`, restarted by `/clear`) reloads that small row and never the app. Two rows pushing
the same status field: the later push shows until it is removed. A status field removed while
rows are coming back up keeps its last text until it is pushed again (its row is most likely
one of them) or every row has stayed up for a moment, so `/clear` (which reloads `status`
with `kernel`) does not blank the session, model and jail fields for the second it takes. A ui with no frame binds no
`frame`, and a layer that uses one disables the rows over it (the shipped `status` and
`palette`). A frame that has `status` but not `commands` is not a `frame` either: `palette`
would never start.

**The tools.** The model is offered the tools rows register with `tools` (a broker), through
its provider's standard tool calling; CodeAct's `python(code)`, the kernel row's, is the shipped
default, not a requirement, and the loop knows of no tool by name. The loop reads the list
(`tools.specs()`, in name order) at its first request, once the tools its config `requires`
have registered (the shipped layer: `["python"]`; a message typed meanwhile, right after
`/clear`, says it waits; one that never registers within `wait` seconds fails the message with
`tools_missing`, below), and offers that list for its life, so the start of what a model server
caches never changes under it (telling a running conversation of a change is TASK-0057's). It
runs each call through the tool its name has now (one restarting, the kernel's on `/restart
kernel`, is waited for `wait` seconds), after `approval` says yes, and answers a name it did
not offer, or an input that does not fit the spec (a `required` property missing, one not of its
schema's simple type), with text saying so, never running it or asking anyone. A turn the person
stops answers every call it made: the one running in its tool with `interrupted: ... it may have
partly run`, one that already had its result (the stop came while its notes were made or the
prompt read) with that result, the rest (one waiting for approval included) with `not run:
...`. A tool's row tells the model about its tool as a `system` section of its own (the python
tool's: its REPL and its jail, read per request), never in the spec's description, which a model
server caches with the list. The loop reads the prompt before each message the model reads (on
`executor`, off the event loop), and sends the prompt the conversation began with: what reads
differently from what it last told is told on that message (`agent_cordis_plugin.changes`) and
kept in the transcript as the edits from that reading (`system entry`, below), so the start of
a conversation never changes under a model server's cache, and the transcript holds the prompt
once however often it changes. The date is not in the prompt, so it reads the same every day:
the loop tells it first on the person's message when the transcript has told none yet or another
day's. A python input is plain Python: nothing of bh-02's is in the namespace and nothing it
does reaches back into bh-02 but the files it writes (an extension, below, which loads jailed
too); it reads and writes files and runs programs itself, and the jail decides what it may
touch.

**Asking before a file is opened.** Instructions a file is covered by (a subdirectory's
CLAUDE.md, a rule whose `paths` match) arrive with the result of the first call that opens it
(`notes`), so after the call: one input can read a file and write it before they arrive. Claude
Code avoids that by construction (its Edit and Write refuse a file not Read first, and the
instructions come with the Read). bh-02's way is `access`: a tool asks before it opens a file,
and a row may refuse. The shipped one, `memory:on_touch`, refuses the first write to a file whose
on-demand instructions this conversation has not been told; the refused file is among what the
call touched, so they follow as its note, and the next write goes ahead. No shipped row refuses
reads. What it does not do, plainly:
- **It hears what the tool reports, nothing else.** The python tool asks from an audit hook in its
  Python process, so it hears Python's own `open()` and `pathlib` of a file in the project, not a
  program an input runs (`sed -i`, `git apply`, a formatter), not `os.open`, nor a rename, a
  replace or a delete; not a file outside the project. Another tool asks only if its author made
  it ask. The jail is the wall; this is a way to say something first.
- **Mid-call the model is told nothing.** A refusal stops one open: the input runs on (or ends at
  the PermissionError, if its code does not catch it), so it may be half done, and the model learns
  of it with the result. A refusal the code caught still ends the result as a line in brackets.
- **It costs a question.** For each file and kind an input opens, once an input, when some row asks
  about that kind: one round trip to bh-02, whose answer may read rule files. With no row asking
  about reads (the shipped composition), reads are never asked about.

**What the model's extensions reach.** `extensions:extensions` loads the cordis components the
model writes (`.bh-02/plugins/NAME.py` in the project) into the extensions process, a second process the `jail` row
starts, so they run as confined as inputs do, and each load is put to `approval` as an input
is (unconfined, the person decides). An extension reaches bh-02 only through three keys, bound
in that process, each of which only adds: `commands.register(spec, run)` (never
`commands.claim`, a line prefix: the extensions process's `commands` refuses it, and the host adds nothing
an extension sends but these three kinds), `frame.status(field, text, *shorter)` (pushed under
`NAME:field`, so it can't replace another row's field) and `system.add(text)` (text, not a
function: it crosses a socket). The extensions
row registers each into the real key and keeps the remover, so a changed, deleted or failed
extension takes back what it added, and nothing it does can replace a row. The host reads what
the model wrote there following no link: a link, a file with a second name, or a link on the way
(`.bh-02`, the directory itself) is not read, since it could hand the model a file the jail
hides, and status.json says why (for a link on the way, which nothing is written through, the
row's `system` section does). The plugin's README has the extensions process's wire.

**CodeAct, the Python process and the jail.** CodeAct is how the model works here: it acts by
writing code, which the `python` tool carries to the Python process (the loop runs each call
through its registration, `kernel.call`, as one input); the namespace keeps its data between inputs, and only what an input
prints enters the model's context. The namespace lasts the run, not the session: the
transcript is the truth, and the namespace a cache that a resume, `/clear` or a Python process
that died empties. The Python process's socket carries an input in and its output back,
nothing else.

The jail is not part of CodeAct; it is what bh-02 runs it in. A `jail` starts processes (the
Python process and the extensions process) and reports, per axis (`fs_read`, `fs_write`,
`network`, `limits`, `env`, ...), a grade: `enforced`, `best_effort`, `cooperative` or
`unenforced`, as brig grades them. What runs in a jail is `confined` when the jail enforces
`fs_write` and `network` (the status bar's `jailed`).

The concerns: the tool (its spec, `PYTHON`, its call and `instructions()`) is CodeAct's; starting, restarting and
talking to the Python process, its startup files and `touched()` are the `kernel` row's; what
each start is (`report()`, `notice()`, `reads()`, `writes()`) and `release()` are the jail's.
The `kernel` value carries the first two, and passes on the jail's (`confined`, `report()`,
`notice()`, `reads()`, `release()`) to `tui:status` and `/release`. The `kernel` row may ask
the jail what its own start is (`reads()`, to tell the model what it can see; `writes()`, to
read the startup files safely); the jail knows nothing of inputs, or of which process is the
Python process.

**Approval: one rule, one row.** Whether what the model asked for runs unasked is where it runs
and what the confinement there says, and the `approval` row (`kernel:approval`) is the one place that says it; the loop and the
extensions row ask it, and neither keeps a copy of the rule. A call that runs in a jail that confines it runs without
asking (the jail denies writes outside the project, the layer files, bh-02's own code, the
network and the credential files), and so does an extension's load; unconfined
(`kernel:unjailed`), or run in bh-02's own process (a tool registered with `runs = "host"`),
each is put to the person, shown as its tool shows it (`output.confirm`), and runs only on a
yes, since it would run with the person's own permissions. A no to a call is its answer
(`denied: ...`); a no to an extension leaves it unloaded until its file changes.
`kernel.instructions()` tells the model which of the two holds, by the same rule over the same
jail (`kernel.confined`), and the
extensions row by `approval.confined`. Only a layer may replace the `approval` row: it runs in
bh-02's own process, and an extension, which reaches bh-02 only through the three keys that
add (above), has no way to bind or reach it. This is a question about code bh-02 is about to hand
to the jail, not cordis's planned policy seam, which would see each effect a component yields
before the runtime performs it.

`done` is how "the chat is finished" reaches the bootstrap without `Runtime.idle()`, which is
process-wide and would also wait on a provider's *own* background work (a heartbeat, a
reconnect loop) that has nothing to do with the chat row. The shell's bootstrap doesn't read `done`
by reaching into the store by hand: it mounts its own `harness` row that depends on it like
any other component depends on anything, so a chat row must bind it; a composition
whose chat row doesn't is a bootstrap error, not a silent hang.

Row ids in the shipped layers coincide with these keys where a row binds one; a row that
contributes to a broker (`operator`, `palette`, the frame's rows) has an id of its own.
`layers`, `sessions` and `harness` are rows the shell's bootstrap (`bh_02.bootstrap:run`) adds
itself.

Each "Bound by" component declares its keys with `@component(provides=(...))` (cordis
checks this: a fiber that declares a key and does not bind it fails at activation, and
`boot` reports a composition where nothing declares `provides` for a key some row injects).
Adding or removing a binding here means updating that component's `provides=` to match, or
the check starts lying.

## Errors

A `loop` or `model` signals a failure the person should see and can recover from by
raising any exception with two attributes: `kind: str` (a short tag: `authentication_failed`,
`rate_limit`, `connection`, `tools_missing` (a tool the loop requires never registered), ...) and `message: str`, written for the person at the keyboard.
`chat:session` shows it and carries on. Anything else is a bug and propagates.

## Shapes

```
tool spec   {"name": str, "description": str, "parameters": <JSON Schema object>}
tool result {"content": str, "touched"?: [str, ...]}   what a tool's `run` answers a call with:
            what the model reads, and the files the call opened (absolute)
request     {"name": str, "input": Mapping, "runs"?: "jail" | "host", "title"?: str,
             "lines"?: [str, ...], "language"?: str}   put to `approval.approve`, and through it,
            when asked, to the person by `output.confirm`: a call (its tool's name, its input,
            where it runs, and how it is shown: the python tool's `title` and its code as
            `lines`; another tool's its own `show`, else its input as JSON), or (with
            `"name": "extension"`, its own `title` and its source as `input.code`) an extension
            to load
message     {"role": "user" | "assistant" | "tool", "content": str,
             "tool_calls"?: [tool call, ...]   (assistant),
             "call_id"?: str       (tool: the call it answers; its content is the call's result,
                                    then each note told with it (`notes`) and any change in the
                                    instructions, each after a blank line),
             "notes"?: [str, ...]  (tool: the `notes` its content tells, as it has them,
                                    sorted; `[]` for none, and for a call that never ran. Every
                                    `tool` entry the loop writes has it, so one without it is from
                                    before the loop kept them, and its notes are only in `content`.
                                    The loop's own: a provider sends `content` alone),
             "provider"?: Mapping  (assistant: the provider's own message, replayed as received),
             "feedback"?: str      (user: the loop telling the model why its last turn didn't count),
             "today"?: str         (user: the date the loop told with this message, `2026-10-07`; its
                                    content then starts `(Today's date: 2026-10-07.)` and a blank
                                    line, before any change in the instructions and the person's
                                    words. The loop's own: a provider sends `content` alone)}
system entry
            {"role": "system", "content": str}
                        a prompt the model was told, whole: a transcript's first, the one every
                        request begins with (and each later one, in a transcript kept before the
                        loop kept edits)
            {"role": "system", "edits": [{"at": int, "drop": int, "add": [str, ...]}, ...]}
                        a later prompt, as what turns the one before it into this one, by
                        paragraph (split at every blank line, exactly): from paragraph `at` of the
                        one before, `drop` of them give way to `add` (`agent_cordis_plugin.edits`;
                        `latest` applies a transcript's entries in turn, giving what the model was
                        last told, and passes over one whose edits `edits` could not have made, a
                        damaged file's). The loop's own: a request carries the first alone, as
                        `{"role": "system", "content": str}`, so a provider never sees `edits`
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
                                                          one turn's usage, not a running total: the ui sums them
                                                          (a provider that reports running totals sends differences;
                                                          one turn may send several, which a ui shows as one line);
                                                          `input_tokens` is everything the model read, cached or not,
                                                          and the cache fields say how much of it was read from, or
                                                          written to, the provider's prompt cache;
                                                          `partial`: a part sent before the provider's
                                                          output count, which a later part carries (a
                                                          turn stopped before it has output not counted)
            {"type": "stop", "reason": str}
            {"type": "note", "text": str}                 the shell speaking (a command's answer); from the
                                                          loop, what it told the model besides a result
                                                          (its instructions changed; a note from `notes`,
                                                          by its first line)
            {"type": "cleared", "compacted"?: true}       the conversation starts afresh (`/clear`, or
                                                          `/compact`, its note carrying the summary): a
                                                          ui drops what it shows of the conversation so far
                                                          (a line typed after `/clear` and not read yet
                                                          belongs to the new one, and stays) and keeps
                                                          the session's usage totals; a note
                                                          saying so follows, so a ui that ignores the
                                                          type still says what happened. `compacted`:
                                                          the new one carries on from a summary
                                                          (`/compact`), so what `commands` holds for
                                                          the model (`for_model`) is kept
            {"type": "for_model", "text": str}           a command's answer: text for the model, not the
                                                          person (`!COMMAND`'s output): the `commands`
                                                          value holds it instead of answering it, and
                                                          `chat:session` takes it (`take_for_model`)
                                                          and puts it in front of the person's next
                                                          message, a paragraph of its own (several, in
                                                          the order they came); `cleared` drops what
                                                          is held, unless `compacted`
            {"type": "restarting", "rows": [str, ...]}   a command's answer: these rows restart now
                                                          (`/model`, `/clear`, `/compact`); a ui holds a
                                                          line typed from here until they are `active`
                                                          again, rather than hand it to the chat row still
                                                          reading (see Rows coming back up). Shows nothing
```

A model streams chunks for one assistant turn and ends with its own `stop` (why the
provider stopped) and `message` (what it sent, for replay). A `tool_call` whose arguments did
not decode carries `error` instead of being dropped. The loop classifies each step:
`act` (calls to run), `answered` (the only real done), `truncated`
(hit the output limit, possibly mid-call), `silent` (said nothing), `undecodable` (a call it
made could not be read). Only `act` runs calls; a turn that is neither `act` nor `answered`
is fed back to the model as a `feedback` message, a bounded number of times, and never read
as the answer. A turn the provider refused (`refusal`) is `refused`: never run, never fed
back, and it ends the reply. The `stop` event a reply ends with carries that classification.
A reply the person stops while a turn streams (Ctrl-C closes it) still answers its message
in the transcript: what the turn said so far, then `[the person stopped this reply here]`, so
the next request does not ask the stopped message again; a model step that raises (a 429, a
dropped connection) is answered the same way, with `[this reply failed here; ...]`.

Which reasons each provider can produce: Claude (the claude-code provider, which passes on the
Messages API's own) reports `end_turn`, `tool_use`, `max_tokens`, `stop_sequence`, `refusal` and
`model_context_window_exceeded` (the last is truncated, like `max_tokens`); it also has
`pause_turn`, but only for a request with server tools, which bh-02 never sends, so the loop has
no case for it. It streams a call's arguments as JSON, so a call can be `undecodable`. Claude
Code has recoveries of its own for most of these (it continues a truncated step, retries a
silent one); the claude-code provider interrupts it at any end but `tool_use` and an answer, so
the loop's classification decides. An OpenAI-compatible model (the openai provider) reports the
API's `finish_reason` in the loop's words: `stop`, `length` (truncated), `tool_calls` (the
legacy `function_call` too) and `content_filter`, which it passes on as `refusal`; it streams a
call's arguments as JSON text in pieces, so a call can be `undecodable`, and a stream that ends
with neither a `finish_reason` nor `[DONE]` raises rather than stopping silently.

A reply is a stream of events: everything the person might want to see of a turn, in order.
`text` is the reply itself; the rest describe the work around it. A consumer that shows only
text keeps `text` and may drop the rest; one that shows more
matches on `type` and ignores types it doesn't know, so a provider can add one.
