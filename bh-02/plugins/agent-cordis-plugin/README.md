# agent-cordis-plugin

A harness-owned agent loop, the transcript it reads, `tools`, the tools it offers the model,
`system`, the system prompt it sends, `notes`, what it tells the model with a call's result,
`access`, what is asked before a file is read or written, `executor`, where it reads the prompt
and asks `notes`, and `/compact`, which begins a new conversation from the model's summary.

| Row | Binds | Consumes |
|---|---|---|
| `agent:loop` | `loop`; config: `max_nudges` (default 2), `requires` (the tools a conversation can't begin without; the shipped layer: `["python"]`), `wait` (how long it waits for them, and for a tool restarting; 30 s) | `model` (`complete`, `tool_changes`), `tools` (`specs`, `get`, `ready`, `serve`), `transcript` (`messages`, `append`), `system` (`text`), `approval` (`unasked`), `output` (`confirm`), `notes` (iterated), `executor` (`run`) |
| `agent:tools` | `tools`: a `ToolBroker`, the tools rows `acquire` with `register(spec, run, *, runs, show)`, offered in name order | |
| `agent:transcript` | `transcript`; config: `path` (a JSON-lines file), in memory when unset | |
| `agent:system` | `system`: the system prompt (`text()`: who the model is, the working directory and branch (its `.git/HEAD`, read from the root through no link), then the sections rows add, sorted by name); a broker, `add(name, section)`; config: `root` (default `.`) | |
| `agent:notes` | `notes`: a `Hooks` (cordis-helpers) of functions rows `acquire` with `add(fn)` | |
| `agent:access` | `access`: an `Access`, the functions rows `acquire` with `before_read(fn)` and `before_write(fn)`, which a tool asks before it opens a file (`refusal(kind, path)`) | |
| `agent:executor` | `executor`: a `OneAtATime`, which runs a call off the event loop once the one before it has ended | |
| `agent:conversation` | registers `/clear` and `/compact [WHAT TO KEEP]`, each restart queued in `jobs`; config: `timeout` (seconds, 300: /compact's summary), `loop` and `transcript` (the rows /compact restarts), `clear` (the rows /clear restarts: `loop`, `transcript`, `python`) | `model` (`complete`), `tools` (`specs`), `loader` (`status`, `rows`, `restart`), `commands` (`register`), `output` (`show`), `jobs` (`put`) |

A turn is the reply to one message: a model step, the calls it asked for, and again, until a
step asks for none. The model is
offered the tools rows register with `tools` (`agent:tools`, a broker; CodeAct's `python(code)`
is the python row's registration, and the loop knows of no tool by name), through the
provider's standard tool calling. The loop reads the list at a conversation's first request
(`tools.specs()`, in name order, so a row registering again after a restart changes nothing),
after the tools its config `requires` have registered: a message typed while one has not (right
after `/clear`, which restarts the python row with the loop) shows a `note` that it waits, `wait`
seconds at most, and one that never registers fails the message (`Unstarted`, `kind`
`tools_missing`, the message kept and answered `FAILED`). It keeps that list in the transcript
as a `tools` entry, since the list is the start of what a model server caches (`toolset.py`).
Before each message the model reads it reads the list again; a tool added, removed or redefined
since is kept as another `tools` entry (`changed`) and told on that message, as a changed prompt
is (`told`: each tool by name, the start of its description and its input's names), and the
person sees `told the model its tools changed since the conversation began`. A tool the
conversation has that is missing for less than `wait` seconds is taken for restarting, not
removed. What each request offers is the model's to choose (`tool_changes`): `fixed`, the
default and both shipped providers', offers the list the conversation began with for its life
(an added tool comes with the next conversation, `/clear` or `/compact`, and a call naming it
now says so; a call to a removed one answers that it was removed); `listed` offers the list as
the transcript last recorded it. A resumed session reads the lists from its transcript, so it
sends the same requests. Each call runs through the tool its
name has now (`called`: a tool that raises, or answers with something other than `{"content":
str, ...}`, answers with an error the model reads), one restarting waited for `wait` seconds,
and only once it may (`Asked`): at once when the `approval` rule says it runs unasked
(`approval.unasked({"name", "input", "runs", "title", "lines", ...})`, `shown`: the tool's own
`show(input)`, else its input as JSON; it runs in a runner that confines it), else on the
person's yes, which the loop asks itself (`output.confirm`, the approval modal). A no is its
answer (`DECLINED`: `denied: ...`), so approval is one rule for any model provider and any tool,
and the loop
keeps no copy of it. A call to a name it did not offer (`refusal`), or one whose input doesn't
fit the spec (`malformed`: a `required` property missing, one not of its schema's simple type),
is answered with text saying so, runs nothing, and is put to nobody. A turn stopped part-way
still answers every call: the one with its tool when the stop came with `interrupted: ... it may
have partly run`, one that had its result (the stop came while its notes were made or the prompt
read) with that result, the rest (the one at the approval question included) with `not run:
...`. A call a tool's own call makes (an input's `tools.NAME(...)`) runs the same way: the loop
row serves it through the `tools` broker (`tools.serve(loop.nested)`, `tools.call`), so it is put
to the rule and the person as the model's own would be, run through the tool its name has now,
and given to `notes`, whose notes go with the result of the call that made it (`_nested`); it
answers `{"content", "failed"}`, `failed` when it did not run (no such tool, its input malformed,
a no) or the tool failed. The transcript and the tools are rows of their own, so the history and
the namespace outlive the loop: replace `model` (or the ui) and the loop reloads while the conversation
carries on.

After each call that ran, the loop calls every function in `notes` with
`{"name", "input", "result", "touched"}` (`touched`: the files the call opened, as its tool
answered; the python tool's are its Python process's `touched()`) and puts what they return after the result
(`noted`, sorted, so the order rows added them in means nothing; one that fails says so in one line). The `tool` entry keeps them as
a list too (`notes`, `[]` for none and for a call that never ran), beside the text the model
reads (the result, then each note, then any change in the instructions, each after a blank
line), so what was told is read back whole, never searched for in a text the result and the
other notes share. The person sees the call's own result, and a `note` for each
of those notes, by its first line. `notes` is a row of its own, depending on nothing, so neither
the loop nor a row adding to it reloads the other; a row that adds to it (`memory:on_touch`)
depends on `transcript`, so `/clear` starts it afresh and it tells a new conversation again; it
reads its `messages` too, so a resumed one is not told again a note a `tool` entry's `notes`
hold (an entry from before the loop kept them is searched; CONTRACTS.md: transcript).

Each model step is classified by `stops.classify` (pure; the table is in its docstring): only
`act` runs calls, only `answered` ends the reply, and a
truncated, silent or undecodable step is fed back with harness's own wording up to
`max_nudges` times per reply. A step that did not act keeps no calls on its transcript
entry, so nothing is left for a result to answer. A reply the person stops while a step streams
(Ctrl-C closes it) still answers its message in the transcript: what the step said so far, then
`[the person stopped this reply here]` (`STOPPED`), so the next request does not ask the stopped
message again; a model step that raises (a 429, a dropped connection) is answered the same way,
with `[this reply failed here; the person saw the error]` (`FAILED`). A provider's assistant
message rides on its
entry as `provider`, for the model to replay unchanged.

Every request begins with the system prompt the conversation began with (`system.text()`, the
python tool's section among the rest), kept in the transcript as its first `{"role": "system"}` entry
([why](../../../docs/bh-02/how-it-works/prompt-and-notes.md#why-the-prompt-stays-fixed-for-a-conversation)). The loop still reads
the prompt before each message the model reads (the person's message, an input's result, a
nudge); when it reads differently from what the model was last told, what changed
(`prompt.changes`, pure: each part, a paragraph, that is new or reads differently, whole, and
the first line of each that is gone) goes with that message, while the person sees a `note`.

The new reading is kept as another `system` entry, but not whole: as the edits that turn the
last reading into it (`prompt.edits`, pure: for each run of paragraphs that reads differently,
where it starts, how many are gone and what stands there now, `{"at", "drop", "add"}`), so a
session where extensions load, the branch switches or CLAUDE.md is edited keeps the prompt in its
transcript once, not once per change. What the model was last told is the first entry with
each later one's edits applied in turn (`prompt.latest`, pure), which the loop works out when it
meets a transcript it has not read and then keeps up itself. A transcript from before the loop
kept edits has every reading whole; `latest` takes those as they are, so it resumes unchanged
and its next change is kept as edits from its last whole reading. An entry whose edits `edits`
could not have made (a transcript edited by hand or damaged) is passed over, the reading before
it standing, so the session still answers and its next change is kept as edits from that one. Only the first entry reaches a
model, as `{"role": "system", "content"}`; the edits are the loop's own. A loop that reloads (a
new model, a new ui), or one over a resumed session, carries on from what the transcript says
the model was told; `/clear` empties it, so the next conversation begins with the prompt as it
reads then.

The date is not in the prompt, which would then read differently every midnight. The loop tells it with the person's message instead (`reply`), when the transcript has told no
date yet or the last one it told is another day's: the entry's content starts
`(Today's date: 2026-10-07.)` and the entry carries the date as `"today"`, which is how the loop
finds the last one told. So a resumed session (the transcript is a file) does not tell it again
the same day, and `/clear` (an empty transcript) does. A message that also tells a change in the
instructions has the date first, then the change, then the person's words. The clock is
`LoopModel`'s `today` (the real date in the `agent:loop` row; a test gives its own). The providers send
`content` alone, so `today` never reaches a model.

Reading the prompt (`system.text()`, whose sections may read many files: memory's reads every
CLAUDE.md, the python tool's asks its jail what it reads) and asking `notes` (memory's on-touch function reads rule
files) run on `executor` (`executor.OneAtATime`, in a thread), not on the event loop, which
cordis and the TUI share, so a slow section function never freezes the app. The transcript is
changed only once each is done, so a reply stopped meanwhile leaves it whole (stopped while the
person's message was being dated and the prompt read, the message is kept and answered as
stopped, as one stopped in its first model step is). What runs there must not need the event
loop: a section function and a `notes` function each read and return text.

One runs at a time, and nothing stops one part-way: a stop ends the reply's wait (but for the
`notes` call, which a stop waits for, so its notes are told), and the reading finishes in its
thread, unused: what it returned or raised goes nowhere, logged by no one. `executor` keeps the
call in flight, and the next waits for it before it begins, so stopping reply after reply while
a slow prompt is read leaves one reading running, not one per stop. `executor` is a row of its
own (`agent:executor`) that depends on nothing, like `notes`: `/model` and `/clear` reload the
loop, a new `LoopModel`, but not `system`, whose caches take no lock, nor `executor`, so the new
loop's first reading waits for the one the last loop left running too, and `system`'s sections'
caches are used by one thread at a time. Only a new `executor` (its row restarted, or replaced
by a layer) knows nothing of a call the last one left running, and may start one beside it. A
`LoopModel` built without one (a test, direct use) makes its own. Each call's thread is a daemon's, not the
default executor's (`asyncio.to_thread`'s): `asyncio.run` joins those as bh-02 ends, and the
interpreter at exit, so a reading left running would hold bh-02 open until it finished; a
daemon's is left to the end of the process, and its answer to an event loop that has closed
goes nowhere.

`/compact` (`agent:conversation`, `conversation.py`) is for a conversation grown long: a local model
processes more prompt before each first token, and any model nears its context window. It asks
the model for a summary in one step: the request is the loop's own (`loop.request_for`: the
prompt the conversation began with, then the conversation) with the registered tools offered
as with every step (`tools.specs()`), so a model server reuses its work on the conversation, then bh-02's message
asking for the summary in plain text, for the model itself to carry on from, naming what its
Python namespace holds (`asked`; `/compact WHAT TO KEEP` adds what the person wants kept). A
call the step makes is never run, and a step that calls, is cut off, says nothing or refuses
gives no summary (`stops.classify`): the answer says why (and what the step cost, as one
`usage` event, which still counts) and nothing changes. A conversation that is only the last
summary, nothing said since, is not compacted again. A command runs in the chat row's task and
Ctrl-C stops only a turn, so the step has `timeout` seconds, and a note says so as it begins
(the row shows it itself, `output.show`, since the chat row shows a command's answer only once
it has one); past them it is closed (its provider stops) and nothing changes. The person
leaving cancels the command (`chat:converse` races it against `input.closed()`): the step is
closed and nothing has been written. The summary then begins the new conversation (`seeded`:
bh-02's note that the conversation carries on from an earlier one, as the person's message,
then the summary as the model's answer, so the roles alternate; the note stays at the
conversation's start, a resume's too, so it says the namespace was kept at the compaction and
empties as the python tool's instructions say), written over the transcript row's file in one step
(`transcript.rewrite`: written whole beside it, then renamed over it, the old file kept under
the first of `.bak`, `.bak.2`, ... not taken, so no compaction's backup replaces another's),
and the loop and the transcript restart, together. The new conversation holds no `system`
entry and no date, so the loop reads the prompt afresh for its first message (folding in
whatever changed since the old one began, with no note of a change) and tells the date. The
python row is not restarted: the summary names what its Python process's namespace holds. The answer is `cleared`
(`compacted`: what `commands` holds for the model's next message, `!`'s output, is kept, since
the summary was written from what the model read, which never held it), a note carrying the
summary, the step's usage as one event (counted in the session's totals), then `restarting`
the two rows, so the ui drops the old conversation and a resume's replay starts at the summary.
The restart is queued before the chat row shows the answer, and stops the chat row: the note
comes second whatever the provider sent, as `/clear`'s does, so it is shown before then.

`/clear` (the same row) is that rewrite with an empty conversation: written over the
transcript row's file in one step, the old kept as `.bak` (`.bak.2`, ...), so a cleared
conversation is never lost, and the rows in `clear` restart together (the loop, the transcript
and the python row, so the namespace empties with the conversation). A transcript with nothing in
it yet, one kept in memory, or a row another component fills is not written: its restart is the
new conversation. The answer is `cleared` (not `compacted`, so what `commands` holds for the
model is dropped), a note saying so and where the old conversation is kept, then
`restarting`.

The conversation row depends on `model`, `tools` (only its `specs`), the loader, `commands`,
`output` and `jobs`, and on neither `loop` nor `transcript`: a restart of them reloads what depends on them,
which would cancel the row's own work half-way. It finds the conversation's file from the
transcript row as the loader mounted it (`loader.rows`: a running `agent:transcript` row's
`path`, whatever the layer files say now), so it needs a session's transcript (one kept in
memory, or a row another component fills, can't begin again from a summary, and /compact says
so). Both commands' restarts are queued in `jobs` (CONTRACTS.md: jobs), never run in the chat
row's task, which they reload; the chat row reads its next line once they are done. A restart
that fails is told to the person (the jobs row's `output.notice`), since the new conversation
is written by then. Both are one row's, beside the transcript they rewrite, rather than the operator's:
the operator keeps not depending on the model, and nothing outside the row (once the
operator's `forget`) has to be kept in step with the transcript row's file.
