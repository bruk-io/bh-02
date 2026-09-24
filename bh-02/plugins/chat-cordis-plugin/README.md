# chat-cordis-plugin

The chat row: what runs once a `loop`, an `input`, an `output` and `commands` are bound.

| Row | Consumes | What it does |
|---|---|---|
| `chat:session` | `loop`, `input`, `output`, `commands` (`run`) | read, show the streamed reply, repeat until the input ends; a `/command` line goes to `commands` and its answer is shown; a recoverable failure is shown and the chat carries on. Binds `done` |

It is one `background` effect, so it stops when a value it uses leaves and starts again
against the replacement. It binds that task as `done`, which resolves when the chat ends (the
shell waits on it). `chat.py` declares the four shapes it needs (`Loop`, `Input`, `Output`,
`Commands`) and `Recoverable`; `testing.py` ships fakes for them.
