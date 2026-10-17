# Command line

`bh-02` starts a session in the current directory. Its subcommands list sessions, follow a
sub-agent's event log and check a startup file's docstrings. Each block below is the command's own
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
  watch           Follow one sub-agent's event log, read-only: SESSION is...
```

- `--model` with a `--patch` that sets the model row's config is refused: the patch chooses the
  model ([Models](../using/models.md#a-patch-that-sets-the-model)).
- `--resume` with `--no-jail` is refused: a resumed session keeps the jail it started with.
- `--resume` with `--model` carries the session on with that model.
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
| `1` | a layer file can't be read, names old rows or has a row with no `use`, the composition could not start, or the session ended with an error. bh-02 says why in one line, starting `error:`. |
| `2` | a usage error: an unknown option, a `--patch` file that doesn't exist, a `--resume` that matches no session or more than one. For `check-examples`, also a file it can't check (not readable, not Python): it exits `1` only for a finding. |

## Environment

| Variable | What it changes |
|---|---|
| `XDG_STATE_HOME` | where sessions live: `$XDG_STATE_HOME/bh-02/sessions/` (default `~/.local/state/bh-02/sessions/`), and the projects' auto memory |
| `XDG_CONFIG_HOME` | where your models file and startup file are: `$XDG_CONFIG_HOME/bh-02/` (default `~/.config/bh-02/`) |
| `SHELL` | the shell a `!COMMAND` line runs in (`/bin/sh` when unset) |

The Claude credential is not an environment variable of bh-02's: it is read from `local.env`
([Get started](../get-started.md#the-credential)).
