# commands-cordis-plugin

Slash commands and line prefixes, as a broker (paper 6.2), on `cordis-helpers`' `Registry`, and
`!COMMAND`, a shell command the person runs from the composer.

| Row | Binds / registers | Consumes |
|---|---|---|
| `commands:registry` | `commands`: `register(spec, run) -> remover`, `claim(prefix, spec, run) -> remover`, `specs()`, `claims(line)`, `run(line)`; `/help` is its own | |
| `commands:operator` | registers `/rows`, `/explain ROW`, `/restart ROW`, `/clear`, `/model [NAME]`; config: `layer`, `model_row` (`model`), `clear`, `forget` | `commands`, `loader`, `models` |
| `commands:shell_command` | claims `!`: `!COMMAND` runs in the person's shell; config: `prefix` (`!`), `cwd` (`.`, the project), `timeout` (120 s), `shell` (empty: `$SHELL`, else `/bin/sh`) | `commands` (`claim`) |

A row offers commands by `acquire(commands.register, spec, run)`, so a row that leaves takes
its commands with it. A line is a command only when it is `/name` then whitespace or the end;
an unknown one says so and never reaches the model.

A row in a layer can also take every line that starts with a character of its choosing:
`acquire(commands.claim, "!", spec, run)`. `run` gets the rest of the line, `/help` lists the
prefix with `spec`'s usage (`!COMMAND`), and the palette doesn't (a prefix is typed, not
chosen). The prefixes are a second `Registry` inside the value, so a character is one row's: a
second claim is refused, as a second command of one name is. A prefix is one character that no
message starts with by chance: not a letter, digit or space, and not `/`. `claims(line)` is how
`chat:session` asks whether a line is the harness's (a slash command, known or not, or a
claimed prefix's) rather than the model's, so what counts as a command is decided here alone.
Only a row in a layer may claim: an extension's `commands` (extensions-cordis-plugin) refuses
`claim`, and its host passes on nothing but a command, a field and a section, since a prefix
takes every line the person starts with it and `!` runs them in the person's shell.

`!COMMAND` (`shell_command.py`) runs as the person, since the person typed it: not in the jail
and without asking, in the project (`cwd`), through `$SHELL -c`, in bh-02's environment less
`ANTHROPIC_*` and `CLAUDE*` (as `kernel:unjailed` drops them: what it prints goes to the
model). The app owns the terminal, so the command gets none of it: stdin is empty, stdout and
stderr are captured as one stream (escapes taken out, its start and end kept past 20,000 bytes,
as an input's output is), and it runs in a session of its own, so a program that opens
`/dev/tty` (a password prompt) fails rather than drawing over the app. Ctrl-C doesn't stop a
command (CONTRACTS.md: `input`), so it is stopped at its `timeout`: its process group gets
SIGTERM, then SIGKILL. A program it left running in the background that still holds its output
is ended once the shell has exited; one whose output goes elsewhere (`cmd > log &`) is the
person's to keep. Its answer is a `note` for the person (what it printed, how it ended) and a
`for_model` event (CONTRACTS.md: event): `chat:session` holds that and puts it in front of the
person's next message, so the model reads the output with it, never during a turn (a line
typed during a turn runs once the turn has ended). A new conversation (`/clear`) drops what is
held, and so does a restart of the chat row (`/model` switching reloads it) before the next
message.

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
