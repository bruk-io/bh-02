# Command line

`bh-02` starts a session in the current directory. Its subcommands list sessions, print one laid out in
time, follow a sub-agent's event log and check a startup file's docstrings. Each block below is the command's own
`--help`.

## `bh-02`

```text
Usage: bh-02 [OPTIONS] [COMMAND] [ARGS]...

  A coding agent in a terminal app. The model acts in Python, through the
  python tool, in a persistent Python process inside a jail. Its models are
  the endpoints in the models file: Claude through Claude Code (on the Claude
  subscription, with the CLAUDE_CODE_OAUTH_TOKEN in local.env that `claude
  setup-token` makes, or through a gateway), and any OpenAI-compatible model.
  Every run is a session that `--resume` continues.

Options:
  --model TEXT   The model to start on, by name, ENDPOINT/MODEL: one of your
                 endpoints' in ~/.config/bh-02/models.toml
                 ($XDG_CONFIG_HOME/bh-02/models.toml), whose `default` is used
                 otherwise; /model lists them.
  --patch FILE   A layer file applied over the shipped composition.
                 Repeatable.
  --trace FILE   Append every row's lifecycle event to FILE (the app owns the
                 terminal).
  --no-jail      Run the model's code unjailed, with your own permissions;
                 every input asks.
  --resume [ID]  Continue this directory's newest session, or the one named:
                 its id, the start of it, or its last part (the status bar's
                 short id; `bh-02 sessions` lists them).
  --help         Show this message and exit.

Commands:
  check-examples  Check the docstrings of the functions and classes...
  sessions        List this directory's sessions, newest first: each...
  trajectory      Print a session laid out in time, read-only: each...
  watch           Follow one sub-agent's event log, read-only: SESSION is...
```

- `--model` with a `--patch` that sets the model row's config is refused: the patch chooses the
  model ([Models](../using/models.md#a-patch-that-sets-the-model)).
- `--resume` with `--no-jail` is refused: a resumed session keeps the jail it started with.
- `--resume` with `--model` carries the session on with that model.
- `--resume` of a session another bh-02 is running is refused, exit code 1, naming the process that
  holds it, before any row starts and before the session is touched; leave that bh-02 first
  ([One bh-02 at a time](../using/sessions.md#one-bh-02-at-a-time)). `sessions`, `trajectory` and
  `watch` read a held session as they do any other.
- A layer (the shipped one, the session's or a `--patch` file) that names a plugin or component
  bh-02 doesn't have fails at boot, exit code 1, with the loader's error naming the row, its `use`
  and the installed plugins; nothing translates an old name
  ([Layers](../using/layers.md#a-layer-that-names-what-bh-02-doesnt-have)).

When you leave, bh-02 prints the session's id and the command that continues it, on stderr.

The app owns the terminal while it runs, so nothing else writes there: `--trace` appends to a
file, a layer file that could not be reloaded is reported after the app exits, and the Python
process's and brig's children write their stderr to files.

## `bh-02 sessions`

```text
Usage: bh-02 sessions [OPTIONS]

  List this directory's sessions, newest first: each one's id, when it
  started, the model it started on and any `--patch` files it started with,
  which may have replaced the model. A record that can't be read is skipped,
  and named on stderr.

Options:
  --help  Show this message and exit.
```

## `bh-02 watch`

```text
Usage: bh-02 watch [OPTIONS] SESSION AGENT

  Follow one sub-agent's event log, read-only: SESSION is a session's id
  (`bh-02 sessions`) and AGENT the agent's name (`/agents` in the session says
  the command, such as `bh-02 watch 20261012-091500-ab12 general-1`). Stops
  when the agent ends; Ctrl-C leaves it sooner. Nothing is written, and only
  names bh-02 made are accepted.

Options:
  --once  Print what the log holds now and stop, instead of following it.
  --help  Show this message and exit.
```

Run it in a second terminal while the sub-agent works: `/agents watch NAME` in the session says
the exact command. It reads the child's `events.jsonl` (the asked prompt, what it said, each
tool call and result, its usage, and the report it ended with), one line an event, with streamed
text run together. It opens the file read-only, follows no link, and refuses a SESSION or AGENT
that is not a name bh-02 made (a session id such as `20261012-091500-ab12`, an agent such as
`general-1`), so neither can name a path. Anything the model wrote is shown as plain text, with
no escape sequence. It works the same inside tmux or outside it.

## `bh-02 trajectory`

```text
Usage: bh-02 trajectory [OPTIONS] [ID]

  Print a session laid out in time, read-only: each reply, its steps (model,
  time to first chunk, generation time, speed, usage, cost), their calls
  (answer, wait, run time), the sub-agents they started and the rows that
  reloaded, with times in your local time. ID is the session as `--resume`
  takes it (its id, the start of it or its last part; `bh-02 sessions` lists
  them), the newest in this directory when left out. Nothing is written, and
  the files are read through no link.

Options:
  -f, --follow  Keep reading the files and print what is new, until Ctrl-C.
  --help        Show this message and exit.
```

It prints what the session's files hold, as lines indented by what is inside what. Times are in
your local time (the files keep UTC), shown as a time of day, with the date where it differs from
the reply's. The date the model is told is also your local day, so near midnight UTC it can
differ from the date in the files.

```text
row first load  20:40:00.000  34 rows in 0.12s
conversation 1  transcript.jsonl  2026-10-17 20:47:12.345
  reply 1  2026-10-17 20:47:12.345  fix the bug in foo
    step 1  20:47:12.400  claude-opus-5-5  first chunk 1.20s  generated in 3.40s  62.4 tokens/s  in 1,200 tokens  out 212 tokens  cache read 1,000  cost $0.0312
      settings: work/opus via claude-code, max_tokens 4096, temperature 0.2
      row reload transcript  20:47:14.000
      call python  20:47:17.000  answer yes (waited 4.20s)  ran 0.80s
        nested call read_file  20:47:17.100  answer unasked  ran 0.01s
      call agent  20:47:18.000  answer unasked  ran 12.00s  started sub-agent general-1
        sub-agent general-1
          row first load  20:47:18.900  15 rows in 0.06s
          conversation 1  transcript.jsonl  2026-10-17 20:47:19.000
            reply 1  2026-10-17 20:47:19.000  count the files
              step 1  20:47:20.000  claude-haiku-5  first chunk 0.30s  generated in 0.70s
    row failed model  20:47:21.500  RuntimeError('boom')
    step 2  20:47:31.000  first chunk 0.50s  generated in 1.00s  30.0 tokens/s  in 1,500 tokens  out 30 tokens
```

- **A reply** is a message of yours and the steps taken to answer it (with the loop's nudges, when a
  step did not count). **A step** shows the model that answered, the seconds to its first chunk,
  the generation time after it, output tokens per second over that time, the tokens used and the
  cost, and its settings (`settings:`) only when they are new to the conversation or changed. **A
  call** shows its tool, what approval made of it (`answer unasked`, `yes` or `no`) and how long you
  took to answer, how long the tool ran, and the calls its input made through `tools` under it. A
  call whose result is not in the transcript says `no result recorded`.
- **A row line** is a row of the composition loading or failing, from the session's `rows.jsonl`. It is
  printed in time order, before the first reply, step or call that came after it, at that line's
  indentation; one with nothing after it comes last. A sub-agent's rows (`agents/NAME/...`) are placed
  among that sub-agent's lines. There are three kinds:
  - **`row first load`** is a row loading for the first time in the session: its row id is not in the
    file before. The first loads that follow one another, with no reload or failure of that
    writer's rows and none of its lines between, are one line with how many rows came up and the time
    from the first to the last (`row first load  20:40:00.000  34 rows in 0.12s`): that is the session
    starting, before your first reply, and under a `sub-agent` line the rows that sub-agent came up with.
    A single row is named (`row first load NAME`). Rows that come up after your first reply, such as
    ones a layer edit adds, are a line of their own, counted the same way. `rows.jsonl` has the names.
  - **`row reload NAME`** is a row that loaded again: it was restarted, as `/clear` does, or a
    dependency it uses was replaced (a `/model` switch, an edit to a layer). Each is a line.
  - **`row failed NAME`** is a row whose setup failed, with the error. Each is a line.

  A session you `--resume` goes on in the same `rows.jsonl`, so the rows of the resumed run, which
  were all seen before, are `row reload` lines.
- **Conversations** are the session's transcript files: the backups `/clear` and `/compact` kept
  come first, in the order of their first `at` (else of the time they were copied), and the live
  `transcript.jsonl` is last. A conversation `/compact` began says so, with what you asked it to
  keep, and the summary step's time and cost; one that follows another without that was cleared.
- **A sub-agent** is shown under the call that started it, with its own times (a background agent
  keeps running after the call returns). One no call names, such as a call you interrupted, comes
  after the conversations, in the order of its own times.
- **A field the file does not have** is left out of its line: the answer to a message the model was
  never asked is a step with no time, and a call refused before approval has no answer.
- **`--follow`** reads every file again each second and prints the lines it has not printed, so a
  `/clear` or `/compact` that replaces the live file carries on with the new one. A call whose result
  is not written yet is printed once it is. Ctrl-C leaves it.
- It only reads: the files are opened read-only through `host_paths`, beneath the sessions' state,
  following no link; a sub-agent is a name in the session's `agents/` directory that `bh-02 watch`
  would accept; a line being written when it reads is skipped; and nothing in a transcript reaches the
  terminal as an escape sequence or any other control character.

The raw request of a step is not shown yet.

## `bh-02 check-examples`

```text
Usage: bh-02 check-examples [OPTIONS] FILES...

  Check the docstrings of the functions and classes startup files tell for an
  example in each (a doctest block, or a `::` literal block) and for doctest
  blocks that parse, each with a blank line before it. It reads each FILE and
  runs none of its code, needs no session and no model, and exits 1 on a
  finding, 0 on none and 2 when it can't check a file. ruff checks the rest of
  the convention (`ruff check --isolated --no-fix --select
  D101,D103,D205,D415,D419 FILE`), and mypy the types, with `mypy --strict
  --config-file= FILE`.

Options:
  --help  Show this message and exit.
```

It is the example rule of the docstring check a session runs at start, as a command for you, a
pre-commit hook or CI ([Checking the docstrings and types](../how-it-works/python-tool.md#checking-the-docstrings-and-types)
has the ruff and mypy lines beside it and how to wire them). It prints one line a finding,
`FILE:LINE: CODE NAME: what to do`, with the codes `example` (no example) and `doctest` (a doctest
block that does not parse, or has no blank line before it).

## Exit codes

| Code | When |
|---|---|
| `0` | the session ended normally, or a subcommand did its job (`check-examples`: no finding) |
| `1` | a layer file can't be read, names old rows or has a row with no `use`, the session `--resume` names is held by another bh-02, the composition could not start, or the session ended with an error. bh-02 says why in one line, starting `error:`. |
| `2` | a usage error: an unknown option, a `--patch` file that doesn't exist, a `--resume` that matches no session or more than one. For `check-examples`, also a file it can't check (not readable, not Python): it exits `1` only for a finding. |

## Environment

| Variable | What it changes |
|---|---|
| `XDG_STATE_HOME` | where sessions live: `$XDG_STATE_HOME/bh-02/sessions/` (default `~/.local/state/bh-02/sessions/`), and the projects' auto memory |
| `XDG_CONFIG_HOME` | where your models file and startup file are: `$XDG_CONFIG_HOME/bh-02/` (default `~/.config/bh-02/`) |
| `SHELL` | the shell a `!COMMAND` line runs in (`/bin/sh` when unset) |

The Claude credential is not an environment variable of bh-02's: it is read from `local.env`
([Get started](../get-started.md#the-credential)).
