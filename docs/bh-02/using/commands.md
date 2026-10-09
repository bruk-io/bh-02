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

A line you send while a reply runs waits for the reply to end.

## Slash commands

A line is a command when it starts with `/name` followed by a space or nothing. A line such as
`/tmp/app.py is broken` is a message. An unknown command says so and goes nowhere.

`/help` lists the commands. In a shipped session it shows these:

| Command | What it does |
|---|---|
| `/help` | lists the commands |
| `/clear` | starts a new conversation and an empty Python process, the old conversation kept as `transcript.jsonl.bak`. The screen clears to one note; the session's usage totals stay. |
| `/compact [WHAT TO KEEP]` | asks the model to summarise the conversation, then carries on in a new one that starts from the summary. The Python process keeps its namespace. |
| `/model [NAME]` | lists the models, or switches to `NAME` for this session ([Models](models.md)) |
| `/memory` | lists the memory files the model is told and how each loads ([Memory](memory.md)) |
| `/release` | stops the Python process until the next input ([The jail](jail.md)) |
| `/rows` | shows the running composition: each row, the component that fills it, and its state |
| `/explain ROW` | says what cordis knows about a row |
| `/restart ROW` | starts a row afresh; the rows that depend on it reload |
| `/exit` | leaves bh-02 (so does `/quit`) |

The model's own extensions can add commands to this list while bh-02 runs
([The model's extensions](../extending/extensions.md)).

### `/compact`

Use `/compact` when a conversation has grown long. The model has 300 seconds to write the summary
(the `conversation` row's `timeout`), and a note says so as it starts. `Ctrl+C` doesn't stop it, since
it is a command, not a reply; leaving bh-02 does, and then nothing changes. Add what you want kept
after the command: `/compact the failing test and its fix`.

The old conversation is kept beside the new one as `transcript.jsonl.bak` in the session's
directory, and a later one's as `.bak.2`, and so on. `/clear` keeps it the same way.

### `/restart` and `/rows`

`/rows` shows every row of the running program. `/restart ROW` gives one row a fresh start: for
example `/restart kernel` starts a new Python process, which runs your startup files again when it is jailed. `/clear`
is a restart too, of the conversation's rows. [Rows and layers](../how-it-works/rows-and-layers.md)
explains what a row is.

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
needs the terminal (a password prompt, an editor) fails. `Ctrl+C` doesn't stop it. It is stopped
after 120 seconds (the `shell-command` row's `timeout`), or when you leave bh-02.

## The command palette

`Ctrl+P` opens a palette of the commands. Choosing one runs it, or puts it in the composer when it
takes arguments, for you to finish. `/model` has an entry for each model you can switch to, such
as `/model haiku`. Shell commands aren't in the palette: you type those.
