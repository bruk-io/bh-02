# agent-cordis-plugin

A harness-owned agent loop, the transcript it reads, and `memory`, what it tells the model with
an input's result.

| Row | Binds | Consumes |
|---|---|---|
| `agent:loop` | `loop`; config: `max_nudges` (default 2) | `model` (`complete`), `kernel` (`spec`, `instructions`, `run`, `touched`), `transcript` (`messages`, `append`), `system` (`text`), `approval` (`approve`), `memory` (iterated) |
| `agent:transcript` | `transcript`; config: `path` (a JSON-lines file), in memory when unset | |
| `agent:memory` | `memory`: a `Hooks` (cordis-helpers) of functions rows `acquire` with `add(fn)` | |

A turn is one model step plus the inputs it asked for, until it asks for none. The model's one
tool is the kernel's `python(code)`, offered through the provider's standard tool calling;
every call runs as `kernel.run(code)`, each only on `approval`'s yes
(`approval.approve({"name": "python", "input": {"code"}})`: at once when the jail confines the
kernel; with `--no-jail`, the person's answer in the approval modal). A no is its answer
(`DECLINED`), so approval is one place for any model provider, and the loop keeps no copy of
the rule. A call to any other name, or one with no `code` string, is answered with
text saying so (`refusal`, pure) and runs nothing. A turn stopped part-way still answers every
call: the one in the kernel when the stop came with `interrupted: ... it may have partly run`,
one that had its result (the stop came while its notes were made or the prompt read) with that
result, the rest (the one at the approval question included) with `not run: ...`. The transcript and
the kernel are rows of their own, so the history and the namespace outlive the loop: replace
`model` (or the ui) and the loop reloads while the conversation carries on.

After each input that ran, the loop calls every function in `memory` with
`{"code", "result", "touched"}` (`touched`: `kernel.touched()`, the project files the input
opened) and puts what they return after the result (`remembered`, sorted, so the order rows
added them in means nothing; one that fails says so in one line). The person sees the input's
own output as the result, and a `note` for each memory note, by its first line. `memory` is a
row of its own, depending on nothing, so neither the loop nor a row adding to it reloads the
other; the rows that add to it (`kernel:shell_hints`, `context:on_touch`) depend on
`transcript`, so `/clear` starts them afresh and they tell a new conversation again.

Each turn is classified by `stops.classify` (pure; the table is in its docstring, after
../harness/ARCHITECTURE.MD): only `act` runs calls, only `answered` ends the reply, and a
truncated, silent or undecodable turn is fed back with harness's own wording up to
`max_nudges` times per reply. A turn that did not act keeps no calls on its transcript
entry, so nothing is left for a result to answer. A provider's assistant message rides on its
entry as `provider`, for the model to replay unchanged.

Every request begins with the system prompt the conversation began with (`system.text()`, then
`kernel.instructions()`), kept in the transcript as its first `{"role": "system"}` entry. A
model server reuses its work on a conversation only up to the first token that differs from
the last request, so a prompt sent fresh each time would make the whole conversation new to it
whenever the prompt changed: minutes of prompt processing with a local model before the first
new token, a restart of Claude Code and the loss of its cache with Claude. The loop still reads
the prompt before each message the model reads (the person's message, an input's result, a
nudge); when it reads differently from the last one kept, the new reading is kept as another
`system` entry and what changed (`prompt.changes`, pure: each part, a paragraph, that is new or
reads differently, whole, and the first line of each that is gone) goes with that message, while
the person sees a `note`. A loop that reloads (a new model, a new ui) carries on from what the
transcript says the model was told; `/clear` empties it, so the next conversation begins with
the prompt as it reads then.

The date is not in the prompt, which would then read differently every midnight: the model would
be told its instructions changed, and the transcript would keep another whole prompt, each day.
The loop tells it with the person's message instead (`reply`), when the transcript has told no
date yet or the last one it told is another day's: the entry's content starts
`(Today's date: 2026-10-07.)` and the entry carries the date as `"today"`, which is how the loop
finds the last one told. So a resumed session (the transcript is a file) does not tell it again
the same day, and `/clear` (an empty transcript) does. A message that also tells a change in the
instructions has the date first, then the change, then the person's words. The clock is
`LoopModel`'s `today` (the real date in the `agent:loop` row; a test gives its own). And a new
session begins with the same prompt as one the day before in the same project (unless the
branch, a context file or an extension changed it), so a local model server that keeps its
prompt cache across conversations can reuse it. The providers send
`content` alone, so `today` never reaches a model.

Reading the prompt (`system.text()`, whose context-file sections may read many files and search
the project, and `kernel.instructions()`) and asking `memory` (the on-touch functions read rule
files) run in a worker thread (`asyncio.to_thread`), not on the event loop, which cordis and the
TUI share, so a slow section function never freezes the app. The loop awaits each, so one runs
at a time; the transcript is changed only once each is done, so a reply stopped meanwhile
leaves it whole (stopped while the person's message was being dated and the prompt read, the
message is kept and answered as stopped, as one stopped in its first model step is). What runs
there must not need the event loop: a section function, `kernel.instructions()` and a `memory`
function each read and return text.
