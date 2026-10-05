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
| `output` | `show(events: AsyncIterator[event])`, `notice(message: str)`, `confirm(request) -> bool`. Not part of the key's shape: `lifecycle(event)` (a cordis `Event`: `kind`, `fiber`, `error`), which the ui row itself `observe`s to show rows reloading; no consumer of `output` calls it | `tui:app` | `chat:session`, `agent:loop` (`confirm`), `extensions:extensions` (`confirm`: an extension to load, unjailed) |
| `frame` | the app's frame, which rows push into: `status(field: str, text: str, *shorter: str) -> remover` (`shorter`: shorter forms of `text`, each shorter than the last, which the status bar shows instead when its line is too narrow), `commands(specs) -> remover` (`specs: () -> Sequence[spec]`, a spec: name, help, usage, and `choices`?: `() -> Sequence[{args, help}]`, the arguments the palette offers as entries of their own, `/model haiku`; both read each time the palette opens, so commands registered later, and models added since, are offered), `sessions(listed) -> remover` (`listed: () -> Sequence[item]`, read each time the sidebar shows or is focused, so a session started since is listed, and called on a worker thread, not the event loop, so it must not touch event-loop state; an item: `id`, `created`, `stack` (the model it started on), `title`?, `patches`?: the `--patch` files it started with, `current`?: bool, true for the running session; `resume`?: the command that continues it, which choosing it shows (the lister knows what its stack needs, e.g. `local.env`); `retired`?: why it can't be continued and what to do instead, shown in place of `resume`; a session record that can't be read is an item of `id` and `broken`: what is wrong with it and what to do, which choosing it shows) | `tui:app` | `tui:status` (`status`), `tui:palette` (`commands`), `tui:sessions` (`sessions`), `extensions:extensions` (`status`: the extensions' fields, each under its extension's name, and its own `extensions` field) |
| `system` | `text() -> str`: what the model is told about where it is working, read fresh; `add(section) -> remover` (`section: () -> str`, read with the rest each time `text()` is, so a row with something to tell the model `acquire`s one and it leaves with the row) | `context:project` | `agent:loop` (`text`), `extensions:extensions` (`add`: how to extend bh-02, and the sections extensions add) |
| `model` | one model step: `complete(messages, tools) -> AsyncIterator[chunk]` (`tools`: the tool specs offered through standard tool calling, from `agent:loop` always the kernel's one; closing it stops the step and releases what it holds). `messages` is always the whole conversation; a provider may keep its own copy across calls (the claude-code provider keeps one Claude Code session per conversation, checks each request against it and rebuilds it from `messages` when they differ), so it must not assume anything the messages do not say. `models:model` binds the model its config's `default` names, on that model's provider: `claude-code` (Claude through Claude Code), `openai` (any OpenAI-compatible `/chat/completions`), or a `module:attribute` factory given the model's table (bh-02's fakes); one it can't use binds too, and each step raises what is wrong | `models:model`, `bh_02.testing:echo_model`, `bh_02.testing:slow_model`, `bh_02.testing:cells_model` (fakes) | `agent:loop` |
| `models` | the models there are, read fresh (the model row's config from the loader's entries, and the models file) each time: `listed() -> Sequence[{name, provider, id, current: bool, where?, problem?, shadows?}]` (in order: the built-ins, the models file's, the model row's `extra`; `where`: an openai model's `base_url`; `problem`: what is wrong with its table and what to do; `shadows`: a user's model named like a built-in; a models file that can't be read raises), `current() -> {name, provider}` (the model the model row names now; `provider` empty when the name is no usable model; never raises), `check(name) -> str \| None` (why the model row can't switch to `name`, or None), `path: str` (the models file). Depends on `loader` alone, so a switch never reloads it or what depends on it | `models:catalog` | `commands:operator` (`/model`), `tui:status` (`current`) |
| `transcript` | `messages: Sequence[message]` (property), `append(message)` | `agent:transcript` | `agent:loop` |
| `jail` | `start(argv, *, cwd, endpoint) -> started` (a program listening on the Unix socket `endpoint`; `started.interrupt() -> bool`, `await started.stop()`), `report() -> Mapping[axis, grade]` | `brig:jail`, `kernel:unjailed` | `kernel:kernel`, `extensions:extensions` (a second program, the extensions' worker) |
| `kernel` | a persistent Python namespace, and the model's one tool: `spec` (the tool spec of `python(code)`), `instructions() -> str` (what the model is told about it, read per request), `run(code: str) -> str` (one cell, as the model reads it; every failure the kernel knows of, a worker that died, an answer it can't read, a worker the jail won't start again, is the cell's text, not an exception), `confined: bool` (whether the loop may run a cell without asking), `report()`. Depends on `jail` alone, so a new ui or model keeps the namespace | `kernel:kernel` | `agent:loop` (`spec`, `confined`, `instructions`, `run`), `tui:status` (`confined`, `report`) |
| `layers` | `paths: tuple[str, ...]`: the layer files the loader is watching, which no jailed cell may write; `secrets: tuple[str, ...]`: absolute paths no jailed cell may read: where bh-02's credential file (`local.env`) may be, and the sessions' state directories, this run's and the default one (each session's `claude/`: Claude Code's config and its messaging peer token) | `bh_02.bootstrap:layer_files` (mounted by its `run()`) | `brig:jail` |
| `commands` | the slash-command broker: `register(spec, run) -> remover` (`spec`: name, help, usage; `run: async (args: str) -> answer`), `specs()`, `run(line) -> answer` (an answer: text, which `chat:session` shows as one `note`, or a sequence of events it shows as they are: `/clear` answers `cleared`, a `note`, then `restarting`; `/model` lists the models, the current one marked; `/model NAME` a `note` then `restarting`, or text saying why NAME can't be switched to; `/model`'s spec has `choices`, one per usable model) | `commands:registry` | `chat:session` (`run`), `commands:operator` (`register`), `extensions:extensions` (`register`: the extensions' commands), `tui:palette` (`specs`) |
| `sessions` | this directory's sessions: `current: str` (the running one's id, empty when the composition runs without a session), `resumed: bool` (whether it was continued with `--resume`), `listed() -> Sequence[{id, created, stack, title?, patches?}]` (`stack`: the model it was started on, by name, or an earlier bh-02's `claude` or `ollama`; `patches`: the names of the `--patch` files it started with), newest first, read fresh, then one `{id, broken}` per record that can't be read (`broken`: which file, what is wrong, what to do), so one bad `meta.json` is named instead of failing the list | `bh_02.bootstrap:session_list` (mounted by its `run()`) | `tui:sessions`, `tui:status` (`current`, `resumed`: the status bar's session id) |
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
`frame`, and a layer that uses one disables the rows over it (the shipped `status`,
`palette` and `sidebar`). A frame that has `status` but
not `commands` and `sessions` is not a `frame` either: `palette` or `sidebar` would never start.

**The one tool.** The model is offered exactly one tool, the kernel's `spec`
(`python(code)`), through its provider's standard tool calling. The loop runs each call as
`kernel.run(code)` and answers a call to any other name, or one without a `code` string, with
text saying so, never running it. A turn the person stops answers every call it made: the one
running in the kernel with `interrupted: ... it may have partly run`, the rest (one waiting
for approval included) with `not run: ...`. `kernel.instructions()` is what the model is told about the
tool and where its code runs; the loop puts it in the system prompt after `system.text()`. A
cell is plain Python: nothing of bh-02's is in its namespace and nothing it does reaches back
into bh-02 but the files it writes (an extension, below, which loads jailed too); it reads and
writes files and runs programs itself, and the jail decides what it may touch.

**What the model's extensions reach.** `extensions:extensions` loads the cordis components the
model writes (`.bh-02/plugins/NAME.py` in the project) into a second program the `jail` row
starts, so they run as confined as cells do; unconfined, each load is put to the person first,
as a cell is. An extension reaches bh-02 only through three keys, bound in that program, each
of which only adds: `commands.register(spec, run)`, `frame.status(field, text, *shorter)`
(pushed under `NAME:field`, so it can't replace another row's field) and `system.add(text)`
(text, not a function: it crosses a socket). The extensions row registers each into the real
key and keeps the remover, so a changed, deleted or failed extension takes back what it added,
and nothing it does can replace a row. The plugin's README has the worker's wire.

**The jail and the kernel.** A `jail` starts one program and reports, per axis (`fs_read`,
`fs_write`, `network`, `limits`, `env`, ...), a grade: `enforced`, `best_effort`,
`cooperative` or `unenforced`, as brig grades them. The kernel is `confined` when its jail
enforces `fs_write` and `network`. The worker's socket carries a cell in and its output back,
nothing else. Whether a cell is asked about is where the confinement says, and the loop does the asking:
confined, a cell runs without asking (the jail denies writes outside the project, the layer
files, the network and the credential files); unconfined (`kernel:unjailed`), `agent:loop`
puts every cell to the person with its code (`output.confirm`) and runs it only on a yes (a no
is the call's answer, `denied: ...`), since it runs with the person's own permissions.

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
request     {"name": "python", "input": {"code": str}, "title"?: str}   code put to the person by
            `output.confirm`: a cell, or (with its own `title`) an extension to load unjailed
message     {"role": "user" | "assistant" | "tool", "content": str,
             "tool_calls"?: [tool call, ...]   (assistant), "call_id"?: str (tool),
             "provider"?: Mapping  (assistant: the provider's own message, replayed as received),
             "feedback"?: str      (user: the loop telling the model why its last turn didn't count)}
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
            {"type": "note", "text": str}                 the shell speaking (a command's answer)
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
