# Commands

Most of what you type is a message to the model. Two kinds of line are bh-02's instead and never
reach the model: slash commands, and `!` followed by a shell command.

## Keys

| Key | What it does |
|---|---|
| `Enter` | sends the message or command in the composer |
| `Ctrl+C` | stops the running reply. It never quits, and it doesn't stop a command. |
| `Ctrl+P` | opens the command palette |
| `Ctrl+Q` | leaves bh-02 (so do `/exit` and `/quit`) |

A line you send while a reply runs waits for the reply to end. One you send while a command's
restart runs (`/clear`, `/compact`, `/model NAME`, `/restart`) waits for the restart, and reaches
the new loop.

## Slash commands

A line is a command when it starts with `/name` followed by a space or nothing. A line such as
`/tmp/app.py is broken` is a message. An unknown command says so and goes nowhere.

`/help` lists the commands. In a shipped session it shows these:

| Command | What it does |
|---|---|
| `/help` | lists the commands |
| `/clear` | starts a new conversation and an empty Python process, the old conversation kept as `transcript.jsonl.bak`. The screen clears to one note; the session's usage totals stay. Running sub-agents end, each with a note. |
| `/compact [WHAT TO KEEP]` | asks the model to summarise the conversation, then carries on in a new one that starts from the summary. The Python process keeps its namespace, and running sub-agents carry on. |
| `/model [NAME]` | lists the models, or switches to `NAME` for this session ([Models](models.md)); running sub-agents end, each with a note |
| `/memory` | lists the memory files the model is told and how each loads ([Memory](memory.md)) |
| `/agents [stop [NAME] \| watch NAME]` | lists the sub-agents running (name, type, what each is doing, its transcript's path), ends one or all of them, or says the command that follows one's events ([Sub-agents](#sub-agents)) |
| `/release` | stops what runs in the jail (the Python process, the extensions' process, each running sub-agent's Python process) until the next input ([The jail](jail.md)); sub-agents' conversations go on |
| `/rows` | shows the running composition: each row, the component that fills it, and its state |
| `/explain ROW` | says what cordis knows about a row |
| `/restart ROW` | starts a row afresh; the rows that depend on it reload |
| `/exit` | leaves bh-02 (so does `/quit`) |

The model's own extensions can add commands to this list while bh-02 runs
([The model's extensions](../extending/extensions.md)).

### `/compact`

Use `/compact` when a conversation has grown long, and add what you want kept after the command:
`/compact the failing test and its fix`. The screen keeps only the note carrying the summary. How
long the model has to write it, what stops it, and where the old conversation is kept (for `/clear`
too): [the conversation row](../reference/plugins/agent.md).

### `/restart` and `/rows`

`/rows` shows every row of the running program. `/restart ROW` gives one row a fresh start: for
example `/restart python` starts a new Python process, which runs your startup files again when it is jailed. `/clear`
is a restart too, of the conversation's rows. [Rows and layers](../how-it-works/rows-and-layers.md)
explains what a row is.

### Sub-agents

The model can start sub-agents (`agent`), tell a running one something (`agent_send`, which the
child reads framed as from its parent agent) and end one (`agent_stop`). `/agents` lists those
running: name, type, foreground or background, what each is doing, and the path of its
transcript. `/agents watch NAME` says the command to run in another terminal, `bh-02 watch SESSION NAME`,
which follows that sub-agent's event log read-only ([`bh-02 watch`](../reference/command-line.md#bh-02-watch)); it
works for a sub-agent that has ended too. While any run, the status bar shows `agents: N running`
(absent at none). `/agents stop NAME` ends one, `/agents stop` all of them; each conversation ends with
its Python process. Ctrl-C stops the reply and the sub-agent it waits on, but not the background
ones: its notice says how many still run and that `/agents stop` ends them. `/clear`, `/model`
and `/restart agents` end the running ones too, each with a note; `/compact` keeps them, and
`/release` stops only their Python processes. Details:
[subagents-cordis-plugin](../../../bh-02/plugins/subagents-cordis-plugin/README.md).

## Shell commands: `!COMMAND`

A line that starts with `!` runs the rest of the line in your shell:

```text
!git log --oneline -5
```

It runs as you, in the project's directory, through `$SHELL -c` (or `/bin/sh`). It is not in the
jail and bh-02 doesn't ask first, since you typed it. Its environment is bh-02's, less
`ANTHROPIC_*` and `CLAUDE*`.

What it prints is shown as plain text, followed by how it ended (`exit status 0`). The model
reads that output with your next message, never in the middle of a reply. A `/model` switch or a
`/compact` in between keeps it for the model; `/clear` drops it.

bh-02's app owns the terminal, so the command gets none: it has no input, and a program that
needs the terminal (a password prompt, an editor) fails. `Ctrl+C` doesn't stop it, and says so if
you press it while one runs. It is stopped after 120 seconds (the `shell-command` row's
`timeout`), or when you leave bh-02.

## The command palette

`Ctrl+P` opens a palette of the commands. Choosing one runs it, or puts it in the composer when it
takes arguments, for you to finish. `/model` has an entry for each model you can switch to, such
as `/model haiku`. Shell commands aren't in the palette: you type those.

## Completing a command as you type

Type `/` in the composer and the commands that match appear in a list above it, the same ones
the palette shows (including arguments such as `/model haiku`). Prefix matches come first, then
commands that contain what you typed; at most eight rows show, and the list scrolls.

| Key | While the list is open |
|---|---|
| `Up` / `Down` | move the highlight |
| `Tab` | complete the line to the highlighted command, without running it |
| `Enter` | take the highlighted command if you moved the highlight, or if what you typed so far is the start of its name (`/he` runs `/help`; `/mo` gives `/model `); otherwise send what you typed (`/model` and `/model h` are sent as they are) |
| `Esc` | close the list for this line; the text stays |
| `Ctrl+J`, `Shift+Enter` | start a new line and close the list (a command is one line) |

A click on a row runs it. The list closes when you send, when a question comes up or when the
composer loses focus. Every other key works as without it.
