# agent-cordis-plugin

A harness-owned agent loop, and the transcript it reads.

| Row | Binds | Consumes |
|---|---|---|
| `agent:loop` | `loop`; config: `max_nudges` (default 2) | `model` (`complete`), `kernel` (`spec`, `confined`, `instructions`, `run`), `transcript` (`messages`, `append`), `system` (`text`), `output` (`confirm`) |
| `agent:transcript` | `transcript`; config: `path` (a JSON-lines file), in memory when unset | |

A turn is one model step plus the inputs it asked for, until it asks for none. The model's one
tool is the kernel's `python(code)`, offered through the provider's standard tool calling;
every call runs as `kernel.run(code)`. When the kernel is not `confined` (`--no-jail`), each
input is put to the person first (`output.confirm`, `{"name": "python", "input": {"code"}}`, the
approval modal) and a no is its answer (`DECLINED`), so approval is one place for any
model provider. A call to any other name, or one with no `code` string, is answered with
text saying so (`refusal`, pure) and runs nothing. A turn stopped part-way still answers every
call: the one in the kernel when the stop came with `interrupted: ... it may have partly run`,
the rest (the one at the approval question included) with `not run: ...`. The transcript and
the kernel are rows of their own, so the history and the namespace outlive the loop: replace
`model` (or the ui) and the loop reloads while the conversation carries on.

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
