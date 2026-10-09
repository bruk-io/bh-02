# chat-cordis-plugin

The chat row: what runs once a `loop`, an `input`, an `output`, `commands` and `jobs` are bound.

| Row | Consumes | What it does |
|---|---|---|
| `chat:converse` | `loop`, `input`, `output`, `commands` (`claims`, `run`, `take_for_model`), `jobs` (`settled`) | wait until no restart a command queued is pending, read, show the streamed reply, repeat until the input ends; a line `commands` claims (a `/command`, or `!` and a shell command) goes to it and its answer is shown (the command is cancelled if the input closes first); what commands left for the model (`for_model`, which `commands` holds) is taken and put in front of the person's next message; a recoverable failure is shown and the chat carries on. Binds `done` |

It is one `background` effect, so it stops when a value it uses leaves and starts again
against the replacement. It binds that task as `done`, which resolves when the chat ends (the
shell waits on it). `done` is how "the chat is finished" reaches the bootstrap without
`Runtime.idle()`, which is process-wide and would also wait on a provider's own background work
(a heartbeat, a reconnect loop) that has nothing to do with the chat. The shell doesn't reach
into the store for it: its own `shell` row depends on `done` as any component depends on
anything, so a composition whose chat row doesn't bind it is a bootstrap error, not a silent
hang. `chat.py` is the logic the row runs (`converse`), the shapes it needs
(`Loop`, `Input`, `Output`, `Commands`, `Jobs`) and `Recoverable`; `testing.py` ships fakes for
the shapes.

Which lines are commands is the `commands` value's to say (`claims(line)`), never the chat's:
a slash command, or a line starting with a prefix a layer's row claimed (`!`). A command runs
until it answers or the input closes (`input.closed()`: the person left), which cancels it, so
bh-02 doesn't live on, blank, until a `!` command ends; Ctrl-C (`interrupted()`) is a turn's
and doesn't stop a command. A command's answer may carry `for_model` events (CONTRACTS.md:
event; `!COMMAND`'s output): the `commands` value holds them, not this row, and the chat takes
them (`take_for_model()`) for the person's next message, in the order the commands ran, each a
paragraph of its own in front of it, so `loop.reply` is still given one message and the model
reads the output with it, never during a turn. Lines are read one at a time, so a `!` line
typed during a turn runs after it. `commands` depends on nothing, so a restart of this row (a
`/model` switch reloads the loop, and this row with it) keeps what is held; a `cleared` event
(`/clear`) drops it, and a `compacted` one (`/compact`, whose summary never held it) keeps it.

Before each read the chat waits until no restart a command queued in `jobs` is pending
(`jobs.settled()`): `/clear`, `/compact`, `/model NAME` and `/restart loop` restart the loop,
which reloads this row, and the row is then waiting, not holding a line. So a line typed right
after such a command stays with the input, and the new row reads it for the new loop: the old
loop never answers it, a restart never stops a turn it started, and none is dropped.
