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
| `input` | `read() -> str \| None` (`None` means no more input); `interrupted()` returns when the person asks to stop the running turn (a stop asked for after a line was read and before `interrupted()` is called is held for it; the next `read()` drops one still held) | `tui:app` | `chat:session` |
| `output` | `show(events: AsyncIterator[event])`, `notice(message: str)`, `confirm(request) -> bool`. Not part of the key's shape: `lifecycle(event)` (a cordis `Event`: `kind`, `fiber`, `error`), which the ui row itself `observe`s to show rows reloading; no consumer of `output` calls it | `tui:app` | `chat:session`, `kernel:approval` (`confirm`: the model's code, unjailed), `tui:status` (`show`: the jail's notice, as a `note`) |
| `frame` | the app's frame, which rows push into: `status(field: str, text: str, *shorter: str) -> remover` (`shorter`: shorter forms of `text`, each shorter than the last, which the status bar shows instead when its line is too narrow), `commands(specs) -> remover` (`specs: () -> Sequence[spec]`, a spec: name, help, usage, and `choices`?: `() -> Sequence[{args, help}]`, the arguments the palette offers as entries of their own, `/model haiku`; both read each time the palette opens, so commands registered later, and models added since, are offered) | `tui:app` | `tui:status` (`status`), `tui:palette` (`commands`), `extensions:extensions` (`status`: the extensions' fields, each under its extension's name, and its own `extensions` field) |
| `system` | `text() -> str`: what the model is told about who and where it is (bh-02's own, then the project context: where it is working, what the context files' sections' `function`s say, and what rows add; not the date, which `agent:loop` tells with the person's message), read fresh, in a worker thread (the loop calls it there, one call at a time, so it must not need the event loop); `add(section) -> remover` (`section: () -> str`, read with the rest each time `text()` is, in that thread, so a row with something to tell the model `acquire`s one and it leaves with the row); `touched(paths: Sequence[str]) -> Sequence[(file, text)]` (what the context files' `on_touch` sections say about `paths`, the absolute files an input opened, in the order of the sections; read fresh from the same context files as `text()`, so the `system` row's config is theirs too, and called in the loop's worker thread through a `memory` function, one call at a time with `text()`) | `context:project` | `agent:loop` (`text`), `extensions:extensions` (`add`: how to extend bh-02, and the sections extensions add), `context:on_touch` (`touched`) |
| `model` | one model step: `complete(messages, tools) -> AsyncIterator[chunk]` (`tools`: the tool specs offered through standard tool calling, from `agent:loop` always the kernel's one; closing it stops the step and releases what it holds). `messages` is always the whole conversation; a provider may keep its own copy across calls (the claude-code provider keeps one Claude Code session per conversation, checks each request against it and rebuilds it from `messages` when they differ), so it must not assume anything the messages do not say. `models:model` binds the model its config's `default` names, on that model's provider: `claude-code` (Claude through Claude Code), `openai` (any OpenAI-compatible `/chat/completions`), or a `module:attribute` factory given the model's table (bh-02's fakes); one it can't use binds too, and each step raises what is wrong | `models:model`, `bh_02.testing:echo_model`, `bh_02.testing:slow_model`, `bh_02.testing:repl_model` (fakes) | `agent:loop` |
| `models` | the models there are, read fresh (the model row's config from the loader's entries, and the models file) each time: `listed() -> Sequence[{name, provider, id, current: bool, where?, problem?, shadows?}]` (in order: the built-ins, the models file's, the model row's `extra`; `where`: an openai model's `base_url`; `problem`: what is wrong with its table and what to do; `shadows`: a user's model named like a built-in; a models file that can't be read raises; one in the project is not read, and lists none), `current() -> {name, provider}` (the model the model row names now; `provider` empty when the name is no usable model; never raises), `check(name) -> str \| None` (why the model row can't switch to `name`, or None), `path: str` (the models file), `problem: str \| None` (why the models file is not read and where it must be instead: it is in the project, which the model's code can write; None when it is outside, there or not). Depends on `loader` and `layers` (where a key's `local.env` is looked for), neither of which a switch replaces, so a switch never reloads it or what depends on it | `models:catalog` | `commands:operator` (`/model`), `tui:status` (`current`) |
| `transcript` | `messages: Sequence[message]` (property), `append(message)`; besides the conversation, it keeps the system prompts the model was told as `{"role": "system"}` entries (`system entry`, below): the first, whole, is the one every request begins with; a later one is a change told as a note on the message after it, kept as the edits from the reading before it rather than a whole copy (a transcript kept before the loop kept edits has each reading whole, and resumes as it is); and the dates it was told, each as `today` on the person's message that told it (`message`, below) | `agent:transcript` | `agent:loop`; `kernel:shell_hints` and `context:on_touch` (`messages`, read once, at the first input that may need them: a note a `tool` entry holds whole after its result was told before they began; and they share its lifetime, so a new conversation (`/clear`) starts them afresh) |
| `memory` | what the model is told with an input's result, a broker: `add(fn) -> remover`, iterable for the functions added. `fn(input) -> str`: `input` is `{"code", "result", "touched"}` (the input's code, its result as the model reads it, and `kernel.touched()`); it returns a note to go after the result ('' for none). A function adds a note and never changes the result, and the loop sorts the notes, so any set of them composes in any order; one that raises or returns something other than text is told as one line naming it, and the rest still say theirs. Called in a worker thread, off bh-02's event loop, after every input that ran, one input's at a time (the loop awaits them), so it may read files but must not need the event loop; only rows in a layer add to it (it runs in bh-02's process; an extension's code runs in the jail). Its contributors keep what they have told as their own state, which a new conversation (`/clear`) starts afresh; what was told before they began (a resumed session's, or before a row reloaded) they read from `transcript`, so a note is told once a conversation, a resumed one too | `agent:memory` | `agent:loop` (iterates), `kernel:shell_hints` and `context:on_touch` (`add`) |
| `jail` | `start(argv, *, cwd, endpoint) -> started` (a program listening on the Unix socket `endpoint`; `started.interrupt() -> bool`, `await started.stop()`, `started.ended() -> str`: why the jail ended the program itself, for the person, or "": a Linux `brig:jail` ends itself when the host undoes one of its mounts), `report() -> Mapping[axis, grade]`, `notice() -> str` (what the person should know about the jail the program runs in, read once it has started: `brig:jail` on Linux names the secrets it holds with a mount the host can undo; empty when there is nothing to say), `reads() -> tuple[str, ...]` (once it has started, the trees a program in it can read when that is all it can read: a Linux `brig:jail`'s allowlist and writable roots; empty when it reads everything but what it hides, as darwin's does, or is no jail), `await release() -> str` (called with no program of it running: what that freed on the host, for the person; a Linux `brig:jail` names where bh-02 looks for its credential and nothing holds now, or what another session's jail still holds; empty when nothing was held) | `brig:jail`, `kernel:unjailed` | `kernel:kernel`, `extensions:extensions` (`start`: a second program, the extensions' worker), `kernel:approval` (`report`) |
| `kernel` | a persistent Python namespace, and the model's one tool: `spec` (the tool spec of `python(code)`), `instructions() -> str` (what the model is told about it, read per request, with `system.text()` in the loop's worker thread; under a jail that reads by allowlist, it names the trees `reads()` gives and says nothing else exists there), `run(code: str) -> str` (one input, as the model reads it; every failure the kernel knows of, a worker that died, an answer it can't read, a worker the jail won't start again, is the input's text, not an exception; a new kernel's first input starts with a parenthesised note when there is one: it was started again (and why, when its jail ended the last one), or what the project's startup file `.bh-02/kernel.py` did), `confined: bool` (whether its jail confines its inputs, by `approval`'s rule: what `instructions()` tells the model, and whether the startup file runs unasked), `report()`, `notice()` and `reads()` (its jail's), `await release() -> str` (ends the worker and its jail now, then its jail's `release()`; the next input starts a new worker, told its variables are gone; an input running is left alone and the answer says so), `touched() -> tuple[str, ...]` (the files under the kernel's root the last input opened, read or written, absolute and each once, at most 1,000: what the input's own Python code opened with `open` or `pathlib`, heard by an audit hook in the worker, not an `os.open` (`shutil.rmtree`'s, `Path.touch`), a directory it listed, a module it imported, a source file its traceback was formatted from or a file a program it ran opened; empty before any input and after one that did not finish. The worker is the model's process, so these are what it says it opened: match them against files you chose, never open a file because it is named here). Depends on `jail` alone, so a new ui or model keeps the namespace | `kernel:kernel` | `agent:loop` (`spec`, `instructions`, `run`, `touched`), `tui:status` (`confined`, `report`, `notice`: shown as a note each time a kernel comes up), `kernel:release` (`release`: `/release`) |
| `approval` | whether the model's code may run: `confined: bool` (whether the jail confines what runs in it, so nothing is asked; read from the jail each time), `approve(request) -> bool` (async; `request` as in Shapes: yes at once when confined; otherwise the person's answer through `output.confirm(request)`, and no when there is nobody to ask). A capability, bound by one row: whether the model's code runs unasked is a rule with exactly one author, which is the point of it, so it is not a broker (guards rows add would compose, but then no one row could say what the rule is). Depends on `jail` and `output`, not `kernel`, so `/clear` leaves it up | `kernel:approval` | `agent:loop` (`approve`: each input), `extensions:extensions` (`confined`: what the model is told; `approve`: each extension to load) |
| `layers` | `paths: tuple[str, ...]`: the layer files the loader is watching, which no jailed input may write; `credentials: tuple[str, ...]`: where the model rows look for bh-02's credential file (`local.env` above bh-02's install and its environment, nearest first; the first that is a regular file is read, unless the row names an `env_file`), the one definition of that search; `secrets: tuple[str, ...]`: absolute paths no jailed input may read: every one of `credentials`, the `local.env` beside and above the project, and the sessions' state directories, this run's and the default one (each session's `claude/`: Claude Code's config and its messaging peer token). A secret under a root an input may write it may not write or create either | `bh_02.bootstrap:layer_files` (mounted by its `run()`) | `brig:jail` (`paths`, `secrets`, and `credentials`: one that does not exist yet stays denied, so no input can plant it, and `/release` names those it frees), `models:model` and `models:catalog` (`credentials`) |
| `commands` | the slash-command broker: `register(spec, run) -> remover` (`spec`: name, help, usage; `run: async (args: str) -> answer`), `specs()`, `run(line) -> answer` (an answer: text, which `chat:session` shows as one `note`, or a sequence of events it shows as they are: `/clear` answers `cleared`, a `note`, then `restarting`; `/model` lists the models, the current one marked, then where to add models or why the models file is not read; `/model NAME` a `note` then `restarting`, or text saying why NAME can't be switched to; `/model`'s spec has `choices`, one per usable model) | `commands:registry` | `chat:session` (`run`), `commands:operator` (`register`), `extensions:extensions` (`register`: the extensions' commands), `kernel:release` (`register`: `/release`), `tui:palette` (`specs`) |
| `sessions` | the running session: `current: str` (its id, empty when the composition runs without a session), `resumed: bool` (whether it was continued with `--resume`) | `bh_02.bootstrap:session_list` (mounted by its `run()`) | `tui:status` (`current`, `resumed`: the status bar's session id) |
| `loader` | cordis's loader handle: `status()`, `entries()`, `restart(*rows)` (together: a row depending on several reloads once; `/clear` restarts its rows so), `reload()` (read the layer files again now, rather than at the watcher's next look), `explain(row)` | the loader itself (cordis) | `commands:operator` (`restart`, `reload`: /model reloads at once; `config.layers`: the layer files after the session's, which `/model` checks for one that sets the model row's config), `tui:status` (`entries`: whether the layers still name the model row; `status`: whether that row is up when the model field is first pushed), `models:catalog` (`entries`: the model row's config) |
| `done` | an awaitable (the `asyncio.Task` `background(...)` returned) that resolves when the chat row's own run ends | `chat:session` | `bh_02.bootstrap:harness` |

**The ui's `input` and `output` end with the ui.** Whatever ends the app (Ctrl-Q, `/exit` or `/quit`, a
crash) settles everything waiting on it: a pending `input.read()` returns `None`, every
`interrupted()` returns, a pending `output.confirm` is a no. After a crash, `read()` raises
instead of returning `None`: the failure is shaped like a recoverable one (`kind =
"ui_crashed"`, `message`), and it reaches the command line through the chat row's `done` (a
teardown error would not).

**The ui row's config.** `tui:app` takes `history` (a JSON-lines file the ui owns: it appends
what the transcript draws, draws its last `replay` entries again when it starts, and trims it
once it grows; a session's layer points it at the session's `events.jsonl`; a `cleared` event
is recorded like any other and a replay starts after the last one, so a resume shows the
conversation since the last `/clear`; a session made before `cleared` existed still lists the
file in `commands:operator`'s `forget`, and the ui's next write after it is emptied puts a
`carried` entry first, so the usage forgotten entries added up to is kept) and `replay` (how
many entries to draw again, 400). The status bar's `usage` field is the ui's own, pushed by
`tui:app`'s output: the session's running totals of usage events (a resumed session's history
included, and not reset by `/clear`: `cleared` starts a new conversation, not a new session,
and what the session spent stays spent), not a row's. Once a turn has ended with its usage
still `partial` (stopped before the provider counted its output), the output and cost totals
are lower bounds and end in `+`.

**Rows coming back up.** `/model` restarts the model row (`model`), `/clear` the loop,
its transcript and the kernel, and the chat row reloads with them. The ui hears it through the lifecycle events it
already `observe`s: `tui:status` shows `model: NAME (PROVIDER, starting…)` from the row's `unloading` (or
`reload`) until it is `active`, and a line typed while no turn is running and rows are coming
up is kept for the chat row's next `read()` and noted as waiting (`⧗ waiting for loop to
start; ...`), never dropped. The note names only rows that bind a key, which is all the chat
row depends on: a status-bar row reloading with them (`status` after a new kernel) is
not waited on. A restarted row's old fiber ends `inactive` before its new one's
`reload`; a line kept in that moment says it waits at the `reload`. The restart begins a
moment after the command answers (the operator's queued job: `/clear` restarts the rows,
`/model` reloads the layers it edited), while the chat row is still up and reading again; so
both answers end with `restarting` (event), naming the rows they restart. From that event
until each of those rows is `active` again (through the `inactive` inside its restart), the
ui hands no line to the chat row: a line typed right after the command waits for the new
model and says so, rather than going to the old one or starting a turn the restart stops. A
line typed while a command runs waits for it and names no row, unless the command's answer
then announces a restart. A row announced that has not begun two seconds later (nothing
restarted: a layer the loader could not read) is no longer waited on. `/model NAME` with the
model already NAME changes nothing and announces nothing; `/restart ROW` announces nothing
either, so a line typed right after `/restart loop` can still start a turn the restart stops.

**`frame` is a broker of the same shape as `commands`.** A row that shows something in the
app's frame depends on what it reports on and on `frame`, and `acquire`s an entry: `yield
acquire(frame.status, "jail", summary)`. The entry leaves with the row, so a volatile key
(`kernel`, restarted by `/clear`) reloads that small row and never the app. Two rows pushing
the same status field: the later push shows until it is removed. A status field removed while
rows are coming back up keeps its last text until it is pushed again (its row is most likely
one of them) or every row has stayed up for a moment, so `/clear` (which reloads `status`
with the kernel) does not blank the session, model and jail fields for the second it takes. A ui with no frame binds no
`frame`, and a layer that uses one disables the rows over it (the shipped `status` and
`palette`). A frame that has `status` but not `commands` is not a `frame` either: `palette`
would never start.

**The one tool.** The model is offered exactly one tool, the kernel's `spec`
(`python(code)`), through its provider's standard tool calling. The loop runs each call as
`kernel.run(code)` and answers a call to any other name, or one without a `code` string, with
text saying so, never running it. A turn the person stops answers every call it made: the one
running in the kernel with `interrupted: ... it may have partly run`, one that already had its
result (the stop came while its `memory` notes were made or the prompt read) with that result,
the rest (one waiting for approval included) with `not run: ...`. `kernel.instructions()` is what the model is told about the
tool and where its code runs; the loop puts it in the system prompt after `system.text()`, reads
the two before each message the model reads (in a worker thread, off the event loop), and sends
the prompt the conversation began with: what reads differently from what it last told is told
on that message (`agent_cordis_plugin.changes`) and kept in the transcript as the edits from
that reading (`system entry`, below), so the start of a conversation never changes under a
model server's cache, and the transcript holds the prompt once however often it changes. The
date is not in the prompt, so it reads the same every day: the loop tells it first on the
person's message when the transcript has told none yet or another day's. A
input is plain Python: nothing of bh-02's is in its namespace and nothing it does reaches back
into bh-02 but the files it writes (an extension, below, which loads jailed too); it reads and
writes files and runs programs itself, and the jail decides what it may touch.

**What the model's extensions reach.** `extensions:extensions` loads the cordis components the
model writes (`.bh-02/plugins/NAME.py` in the project) into a second program the `jail` row
starts, so they run as confined as inputs do, and each load is put to `approval` as an input
is (unconfined, the person decides). An extension reaches bh-02 only through three keys, bound
in that program, each of which only adds: `commands.register(spec, run)`,
`frame.status(field, text, *shorter)` (pushed under `NAME:field`, so it can't replace another
row's field) and `system.add(text)` (text, not a function: it crosses a socket). The extensions
row registers each into the real key and keeps the remover, so a changed, deleted or failed
extension takes back what it added, and nothing it does can replace a row. The plugin's README
has the worker's wire.

**The jail and the kernel.** A `jail` starts one program and reports, per axis (`fs_read`,
`fs_write`, `network`, `limits`, `env`, ...), a grade: `enforced`, `best_effort`,
`cooperative` or `unenforced`, as brig grades them. What runs in a jail is `confined` when the
jail enforces `fs_write` and `network`. The worker's socket carries an input in and its output
back, nothing else.

**Approval: one rule, one row.** Whether the model's code runs unasked is where the confinement
says, and the `approval` row (`kernel:approval`) is the one place that says it; the loop and the
extensions row ask it, and neither keeps a copy of the rule. Confined, an input runs without
asking (the jail denies writes outside the project, the layer files, the network and the
credential files), and so does an extension's load; unconfined (`kernel:unjailed`), each is put
to the person with its code (`output.confirm`) and runs only on a yes, since it would run with the
person's own permissions. A no to an input is the call's answer (`denied: ...`); a no to an
extension leaves it unloaded until its file changes. The kernel tells the model which of the two
holds (`instructions()`) by the same rule over the same jail (`kernel.confined`), and the
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
`rate_limit`, `connection`, ...) and `message: str`, written for the person at the keyboard.
`chat:session` shows it and carries on. Anything else is a bug and propagates.

## Shapes

```
tool spec   {"name": str, "description": str, "parameters": <JSON Schema object>}
request     {"name": "python", "input": {"code": str}, "title"?: str}   code put to `approval.approve`,
            and through it, unconfined, to the person by `output.confirm`: an input, or (with
            `"name": "extension"` and its own `title`) an extension to load
message     {"role": "user" | "assistant" | "tool", "content": str,
             "tool_calls"?: [tool call, ...]   (assistant),
             "call_id"?: str       (tool: the call it answers; its content is the input's result,
                                    then each `memory` note told with it and any change in the
                                    instructions, each after a blank line),
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
                        `latest` applies a transcript's entries in turn to what the model was last
                        told). The loop's own: a request carries the first alone, as
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
                                                          (its instructions changed; a `memory` note,
                                                          by its first line)
            {"type": "cleared"}                           the conversation starts afresh (`/clear`): a ui
                                                          drops what it shows of the conversation so far
                                                          (a line typed after `/clear` and not read yet
                                                          belongs to the new one, and stays) and keeps
                                                          the session's usage totals; a note
                                                          saying so follows, so a ui that ignores the
                                                          type still says what happened
            {"type": "restarting", "rows": [str, ...]}   a command's answer: these rows restart now
                                                          (`/model`, `/clear`); a ui holds a line typed
                                                          from here until they are `active` again,
                                                          rather than hand it to the chat row still
                                                          reading (see Rows coming back up). Shows nothing
```

A model streams chunks for one assistant turn and ends with its own `stop` (why the
provider stopped) and `message` (what it sent, for replay). A `tool_call` whose arguments did
not decode carries `error` instead of being dropped. The loop classifies each turn after
../harness/ARCHITECTURE.MD: `act` (calls to run), `answered` (the only real done), `truncated`
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
