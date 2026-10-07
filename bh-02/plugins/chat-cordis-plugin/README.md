# chat-cordis-plugin

The chat row: what runs once a `loop`, an `input`, an `output` and `commands` are bound.

| Row | Consumes | What it does |
|---|---|---|
| `chat:session` | `loop`, `input`, `output`, `commands` (`claims`, `run`) | read, show the streamed reply, repeat until the input ends; a line `commands` claims (a `/command`, or `!` and a shell command) goes to it and its answer is shown, but for what it gives the model (`for_model`), which is held and put in front of the person's next message; a recoverable failure is shown and the chat carries on. Binds `done` |

It is one `background` effect, so it stops when a value it uses leaves and starts again
against the replacement. It binds that task as `done`, which resolves when the chat ends (the
shell waits on it). `chat.py` declares the four shapes it needs (`Loop`, `Input`, `Output`,
`Commands`) and `Recoverable`; `testing.py` ships fakes for them.

Which lines are commands is the `commands` value's to say (`claims(line)`), never the chat's:
a slash command, or a line starting with a prefix a layer's row claimed (`!`). A command's
answer may carry `for_model` events (CONTRACTS.md: event; `!COMMAND`'s output): they are not
shown, but held, in the order the commands ran, and put in front of the person's next message,
each a paragraph of its own, so `loop.reply` is still given one message and the model reads
the output with it, never during a turn. Lines are read one at a time, so a `!` line typed
during a turn runs after it. A `cleared` event (`/clear`) drops what is held, and a restart
of this row (a `/model` switch reloads the loop, and this row with it) starts without it.
