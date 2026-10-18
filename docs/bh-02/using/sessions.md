# Sessions

Every run of bh-02 is a session. A session keeps what you need to carry on later: the
conversation, the screen's history and the choices the run started with.

## Where a session lives

A session is a directory, `$XDG_STATE_HOME/bh-02/sessions/<id>/`, or
`~/.local/state/bh-02/sessions/<id>/` when `XDG_STATE_HOME` is not set. Its id is the time it
started and a short suffix, such as `20261008-225423-07f8`. It holds:

| File | What it is |
|---|---|
| `session.toml` | the session's own layer: the model, and where the rows below keep their files. `/model` edits it. |
| `transcript.jsonl` | the conversation, which the model is sent again at each step |
| `events.jsonl` | what the screen showed, drawn again when you resume |
| `rows.jsonl` | each row that reloaded or failed, with the time (one JSON object a line, readable by you alone); `bh-02 trajectory` prints it |
| `meta.json` | the session's id, the directory it ran in, when it started, the model it started on, and any `--patch` files it started with |
| `running.lock` | the lock the running bh-02 holds on the session, with its process id in it (see [One bh-02 at a time](#one-bh-02-at-a-time)) |
| `claude/` | Claude Code's own state for the session, when the model is Claude |

## One bh-02 at a time

A running bh-02 holds its session: it takes a lock on `running.lock` in the session's directory when
it starts and keeps it until it ends. A second `bh-02 --resume` of that session, from another
terminal, is refused before it starts a thing, because two bh-02s writing one session would
interleave their conversations in its transcript, its screen history and its row log:

```text
error: session 20261008-225423-07f8 is held by bh-02 process 4242, which is running it; two bh-02s writing one session would interleave its conversation. Leave that bh-02 first (Ctrl-Q in its window), then resume the session again
```

Leave the one that holds it (Ctrl-Q, or end the process the message names) and resume again. The
lock is the operating system's, so it goes when the process does, however it ends: a bh-02 that
crashed or was killed leaves no stale lock, and `running.lock` staying in the directory means
nothing. `bh-02 sessions`, `bh-02 trajectory` and `bh-02 watch` only read, take no lock and work on
a session that is held; so does a second bh-02 that starts a new session, which is a session of its
own.

## When bh-02 was killed mid-write

If bh-02 is killed while it writes the conversation, `transcript.jsonl` can end in half a line.
`--resume` carries on without that unfinished entry: the half line is kept beside the file as
`transcript.jsonl.torn` (readable by you alone; a second time makes `transcript.jsonl.torn.2`),
and the conversation continues from the last whole entry. Any other line that is not JSON is not
a write cut short, so a resume stops and names the file and the line number: repair or remove the
line in an editor, or start a new session instead.

## When bh-02 was killed during a call

A call the model asked for is run after the step that asked for it is written to the conversation.
If bh-02 is killed while one runs, `--resume` finds a call with no result. The next message you send
answers it first, telling the model that bh-02 stopped before the call finished and that it may
have partly run, so the model can check what it did instead of assuming it ran or did not. The
answer is written to `transcript.jsonl` like any other; nothing is shown on screen.

## Listing sessions

```sh
bh-02 sessions
```

This lists the sessions started in the current directory, newest first, one line each: the id, when
it started, and the model it started on (its stack; an earlier bh-02's session says `claude` or
`ollama`, and one that started with no model named (no `--model`, no `default` in the models file) or whose
`default` couldn't be used says `default`: it follows that default, and the first message says what
to write or what is wrong with it), then `patched:` and the names of any
`--patch` files it started with (`patched: echo.toml`). That label is what the session started on,
not always the model that answered: `/model` switches, a patch can replace the `loop` row, and a
resume with other patches keeps the label it started with.

A session whose `meta.json` can't be read (not JSON, a key missing, a value of the wrong type) is
skipped, never fatal: `bh-02 sessions` names it on stderr, and `--resume` passes over it (and
says what is wrong if you name it).

The status bar shows the running session's id. When the bar is narrow it shows the id's last
part, such as `07f8`, and `--resume` takes that too.

A session's sub-agents keep their conversation and an event log beside it
(`<id>/agents/NAME/transcript.jsonl` and `events.jsonl`, the log readable by you alone and, like the
rest of the session's state, not by the model's code). `bh-02 watch ID NAME` follows one, and
`bh-02 trajectory` shows each under the call that started it; the
[command line](../reference/command-line.md#bh-02-watch) says how.

## Seeing what happened

```sh
bh-02 trajectory              # the newest session in this directory, laid out in time
bh-02 trajectory 07f8         # a session by its id, the start of it, or its last part
bh-02 trajectory --follow     # keep reading, and print what is new, while a reply runs
```

`bh-02 trajectory` prints a session read-only, from its files: each reply with your message and the
time, each model step with the model, the time to its first chunk, how long it generated, the speed
in tokens per second, the tokens used, what it cost and its settings, each call with what approval
made of it, how long you took to answer, how long it ran and the calls its input made, each sub-agent
under the call that started it, each `/compact` with the summary step's time and cost, and each row
that reloaded or failed (from `rows.jsonl`) among the lines it fell between. Times are your local
time. Conversations come in order, the ones `/clear` and `/compact` kept first, and `--follow`
carries on across either. A session from before bh-02 recorded times prints without them.
The [command line](../reference/command-line.md#bh-02-trajectory) shows the output and says what it
holds back.

## Resuming

```sh
bh-02 --resume              # the newest session in this directory
bh-02 --resume 07f8         # a session by its id, the start of it, or its last part
bh-02 --resume --model claude/opus # carry on with another model
```

An id that matches more than one session is refused, with the matches listed: give more of it.

When you leave, bh-02 prints the command that continues the session you left: `--resume` alone
when it is the newest here, otherwise with its id.

What a resume brings back, and what it doesn't:

- **Back**: the conversation, the last 400 entries of the screen, the model the session last
  used, and the jail it started with. The status bar marks the session `(resumed)`.
- **Not back**: the Python namespace. It lasts one run, so the model starts with an empty REPL
  and is told so. Functions you want every time belong in a startup file
  ([The python tool](../how-it-works/python-tool.md)).
- **Refused**: `--no-jail`. A resumed session keeps the jail it started with.

A resume boots the session's own layer as it is: nothing translates old names. A session whose
layer names a plugin or component bh-02 no longer has fails at boot like any layer
([Layers](layers.md#a-layer-that-names-what-bh-02-doesnt-have)); the session is kept, so you can edit
its `session.toml` and resume it again.

## A new conversation in the same session

Two commands start the conversation over without leaving the session:

- `/clear` starts a new conversation and an empty Python process. The screen clears to one note.
  The usage totals in the status bar are the session's, so they stay.
- `/compact [WHAT TO KEEP]` asks the model to summarise the conversation and carries on in a new
  one that starts from the summary. The Python process keeps its namespace.

Either way the old transcript is kept beside the new one, so a cleared conversation isn't lost
([Commands](commands.md#compact)).

## Runs that don't start

A run that stops before the app comes up (a layer file that can't be read, say) leaves no
session behind, and so does a new run whose composition never starts (`could not start`). A
resumed session that can't start is kept, so you can fix the cause and resume it again. It isn't
offered to resume until then: bh-02 says it did not start, and which layer to change.
