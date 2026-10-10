# commands-cordis-plugin

Slash commands and line prefixes, as a broker (paper 6.2), on `cordis-helpers`' `Registry`, and
`!COMMAND`, a shell command the person runs from the composer.

| Row | Binds / registers | Consumes |
|---|---|---|
| `commands:registry` | `commands`: `register(spec, run) -> remover`, `claim(prefix, spec, run) -> remover`, `specs()`, `claims(line)`, `run(line)`, `take_for_model()`; `/help` is its own | |
| `commands:jobs` | `jobs`: the restarts commands ask for, run one at a time in its own work (`put(job, failed)`), a failure told to the person; `pending()`, `settled()`, which the chat row waits on before it reads a line | `output` (`notice`) |
| `commands:operator` | registers `/rows`, `/explain ROW`, `/restart ROW` (the restart queued in `jobs`) | `commands`, `loader`, `jobs` (`put`) |
| `commands:shell_command` | claims `!`: `!COMMAND` runs in the person's shell; config: `prefix` (`!`), `cwd` (`.`, the project), `timeout` (120 s), `shell` (empty: `$SHELL`, else `/bin/sh`) | `commands` (`claim`) |

A row offers commands by `acquire(commands.register, spec, run)`, so a row that leaves takes
its commands with it. A line is a command only when it is `/name` then whitespace or the end;
an unknown one says so and never reaches the model.

A row in a layer can also take every line that starts with a character of its choosing:
`acquire(commands.claim, "!", spec, run)`. `run` gets the rest of the line, `/help` lists the
prefix with `spec`'s usage (`!COMMAND`), and the palette doesn't (a prefix is typed, not
chosen). The prefixes are a second `Registry` inside the value, so a character is one row's: a
second claim is refused, as a second command of one name is. A prefix is one character, and
not one that ordinary words start with (a letter, a digit), a space or `/`; any other symbol is
accepted, so which one messages don't start with is the layer's author's to choose: `$` starts
a price, `#`, `-` and `>` Markdown, `{` pasted JSON, and a claimed one takes those messages from
the model (`!` is the shipped one). `claims(line)` is how
`chat:converse` asks whether a line is the harness's (a slash command, known or not, or a
claimed prefix's) rather than the model's, so what counts as a command is decided here alone.
Only a row in a layer may claim: an extension's `commands` (extensions-cordis-plugin) refuses
`claim`, and its host passes on nothing but a command, a field, a section and a tool, since a prefix
takes every line the person starts with it and `!` runs them in the person's shell.

`!COMMAND` (`shell_command.py`) runs as the person, since the person typed it: not in the jail
and without asking, in the project (`cwd`), through `$SHELL -c`, in bh-02's environment less
`ANTHROPIC_*` and `CLAUDE*` (as `runner:unconfined` drops them: what it prints goes to the
model). The app owns the terminal, so the command gets none of it: stdin is empty, stdout and
stderr are captured as one stream (its start and end kept past 20,000 bytes, as an input's
output is, each cut where a character begins), and it runs in a session of its own, so a
program that opens `/dev/tty` (a password prompt) fails rather than drawing over the app. What
it printed is shown as plain text: no escape (colour, `tput sgr0`'s `ESC ( B`, line drawing,
a reset) and no control character but tab and newline is left in it, and a line it wrote over
(`\r`, a progress bar) reads as it ended up. Ctrl-C doesn't stop a command (CONTRACTS.md:
`input`; the ui says so when it is pressed while one runs), so it is stopped at its `timeout`:
its process group gets SIGTERM, then SIGKILL. The person leaving (`input.closed()`) stops it
the same way: `chat:converse` cancels it. A program it left running in the background that
still holds its output is ended once the shell has exited; one whose output goes elsewhere
(`cmd > log &`) is the person's to keep. A command that can't start (no such `shell` or `cwd`)
says why and which of the row's config to set. Its answer is a `note` for the person (what it
printed, how it ended) and a `for_model` event (CONTRACTS.md: event), which the `commands`
value holds rather than answering; `chat:converse` takes it (`take_for_model()`) and puts it in
front of the person's next message, so the model reads the output with it, never during a turn
(a line typed during a turn runs once the turn has ended). The registry depends on nothing, so
a restart of the chat row (`/model` switching reloads it) keeps what is held; a new
conversation (`/clear`'s `cleared`) drops it, with a note saying so, and one carried on from a
summary (`/compact`'s `cleared`, `compacted`) keeps it: the summary was written from what the
model read, which never held it. It is held in memory, so a session left and resumed before the
next message starts without it.

The operator acts through cordis's loader handle (`status`, `entries`, `restart`, `explain`),
never the runtime. A restart replaces rows the chat session depends on, which restarts the
session itself, so a command never restarts rows in the session's task: it queues the restart
in `jobs` (`commands:jobs`, `jobs.py`) and answers, ending with a `restarting` event naming the
rows. The jobs row runs what is queued one at a time, in its own work (cordis-helpers'
`perform`), and tells the person through `output.notice` when one fails, worded as the command
that queued it says (`failed`). The chat row reads its next line only once nothing is pending
(`settled`), so the restart reloads it while it waits, holding no line, and a line typed
meanwhile reaches the new loop. Every command that restarts rows queues there: `/restart`,
`/clear` and `/compact` (the conversation row), `/model NAME` (the switch row). The jobs row
depends on `output` alone, which never reloads, so no restart it runs reloads it.

`/model` is the models plugin's (`models:switch`), beside the catalog it reads; `/clear` and
`/compact` are the agent plugin's conversation row's (`agent:conversation`), beside the
transcript they rewrite. So the operator depends on neither `model` nor `models`, and a
composition without them keeps `/rows`, `/explain` and `/restart`.
