# commands-cordis-plugin

Slash commands, as a broker (paper 6.2), on `cordis-helpers`' `Registry`.

| Row | Binds / registers | Consumes |
|---|---|---|
| `commands:registry` | `commands`: `register(spec, run) -> remover`, `specs()`, `run(line)`; `/help` is its own | |
| `commands:operator` | registers `/rows`, `/explain ROW`, `/restart ROW`, `/clear`, `/model [NAME]`; config: `layer`, `model_row` (`model`), `clear`, `forget` | `commands`, `loader`, `models` |

A row offers commands by `acquire(commands.register, spec, run)`, so a row that leaves takes
its commands with it. A line is a command only when it is `/name` then whitespace or the end;
an unknown one says so and never reaches the model.

The operator acts through cordis's loader handle (`status`, `entries`, `restart`,
`reload`, `explain`), never the runtime. A restart replaces rows the chat session depends on, which
restarts the session itself, so restarts are queued to the operator row's own background work
(cordis-helpers' `perform`) rather than run in the session's task. `/clear` empties the
`forget` files first (Claude Code's session id, the loop's transcript), since a restarted model
row would otherwise read the old conversation back, and answers with events rather than text:
`cleared` (CONTRACTS.md: event), so the ui drops the old conversation from its screen, then a
note saying so. (`/compact`, which asks the model for a summary, is the agent plugin's
`agent:compact` row, so the operator never depends on the model.)

`/model` lists the models (the `models` value: the built-ins, the models file's, the model
row's own), the one the model row names marked `●`, each with its provider and id, and says
where the models file is, or, when it is in the project and so not read (`models.problem`),
why and where it must be instead. `/model NAME` switches by name, across providers: it asks
`models.check(NAME)` first, so a name that is no model, or a model whose table has a problem,
is said and changes nothing; then it names NAME as the model row's `default` in the session's
layer (`layer`, on the row `model_row`) with cordis's `read_layer`/`format_layer` and queues a
`reload` of the layers (the watcher would notice too, half a second later), so the choice is
composition and a resumed session keeps it; a NAME the row already names changes nothing. Its
spec carries `choices`, one per usable model, which the palette offers as entries of their
own (`/model haiku`). The operator depends on `models`, not on `model`, so a switch reloads
the model row and what uses it, never the operator running the switch. Both answers end with
`restarting` (CONTRACTS.md: event), naming the rows about to restart, so the ui holds a line
typed meanwhile for them rather than handing it to the old model.
