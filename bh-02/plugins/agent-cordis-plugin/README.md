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
