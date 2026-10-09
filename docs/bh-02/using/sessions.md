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
| `meta.json` | the session's id, the directory it ran in, when it started, the model it started on, and any `--patch` files it started with |
| `claude/` | Claude Code's own state for the session, when the model is Claude |

## Listing sessions

```sh
bh-02 sessions
```

This lists the sessions started in the current directory, newest first, one line each: the id,
when it started, and the model it started on (its stack; an earlier bh-02's session says `claude`
or `ollama`), then `patched:` and the names of any `--patch` files it started with
(`patched: echo.toml`). That label is what the session started on, not always the model that
answered: `/model` switches, a patch can replace the `loop` row, and a resume with other patches
keeps the label it started with.

A session whose `meta.json` can't be read (not JSON, a key missing, a value of the wrong type) is
skipped, never fatal: `bh-02 sessions` names it on stderr, and `--resume` passes over it (and
says what is wrong if you name it).

The status bar shows the running session's id. When the bar is narrow it shows the id's last
part, such as `07f8`, and `--resume` takes that too.

## Resuming

```sh
bh-02 --resume              # the newest session in this directory
bh-02 --resume 07f8         # a session by its id, the start of it, or its last part
bh-02 --resume --model opus # carry on with another model
```

An id that matches more than one session is refused, with the matches listed: give more of it.

When you leave, bh-02 prints the command that continues the session you left: `--resume` alone
when it is the newest here, otherwise with its id.

What a resume brings back, and what it doesn't:

- **Back**: the conversation, the last 400 entries of the screen, the model the session last
  used, and the jail it started with. The status bar marks the session `(resumed)`.
- **Not back**: the Python namespace. It lasts one run, so the model starts with an empty REPL
  and is told so. Helpers you want every time belong in a startup file
  ([The python tool](../how-it-works/python-tool.md)).
- **Refused**: `--no-jail`. A resumed session keeps the jail it started with.

A session's layer from an earlier bh-02, with rows that have since been renamed, is brought up to
date when you resume it ([Layers](layers.md#layers-from-an-earlier-bh-02)). A session started on
Anthropic's Messages API (`anthropic:completion`) resumes on Claude Code, from its transcript. A
session started on the first Claude Agent SDK stack, where Claude Code ran its own loop, can't be
resumed: `--resume` says so in one line; start a new one.

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
resumed session that can't start is kept, so you can fix the cause and resume it again.
