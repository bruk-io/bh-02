# Command line

`bh-02` starts a session in the current directory. Its two subcommands list sessions and bring old
layer files up to date. Each block below is the command's own `--help`.

## `bh-02`

```text
Usage: bh-02 [OPTIONS] [COMMAND] [ARGS]...

  A coding agent in a terminal app. The model acts in Python, through the
  python tool, in a persistent kernel inside a jail. Claude is reached through
  Claude Code on the Claude subscription, with the CLAUDE_CODE_OAUTH_TOKEN in
  local.env (`claude setup-token` makes one); any OpenAI-compatible model can
  be added to the models file. Every run is a session that `--resume`
  continues.

Options:
  --model TEXT   The model to start on, by name: sonnet (the default), opus,
                 haiku, or one of yours in ~/.config/bh-02/models.toml
                 ($XDG_CONFIG_HOME/bh-02/models.toml); /model lists them.
  --patch FILE   A layer file applied over the shipped composition.
                 Repeatable.
  --trace FILE   Append every row's lifecycle event to FILE (the app owns the
                 terminal).
  --no-jail      Run the kernel unjailed, with your own permissions; every
                 input asks.
  --resume [ID]  Continue this directory's newest session, or the one named:
                 its id, the start of it, or its last part (the status bar's
                 short id; `bh-02 sessions` lists them).
  --help         Show this message and exit.

Commands:
  sessions      List this directory's sessions, newest first: each one's...
  update-layer  Rewrite a layer file (a --patch file) that names rows...
```

- `--model` with a `--patch` that sets the model row's config is refused: the patch chooses the
  model ([Models](../using/models.md#a-patch-that-sets-the-model)).
- `--resume` with `--no-jail` is refused: a resumed session keeps the jail it started with.
- `--resume` with `--model` carries the session on with that model.

When you leave, bh-02 prints the session's id and the command that continues it, on stderr.

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

## `bh-02 update-layer`

```text
Usage: bh-02 update-layer [OPTIONS] FILE

  Rewrite a layer file (a --patch file) that names rows this bh-02 renamed or
  no longer has, in today's names, and say what changed. The original is kept
  as FILE.bak (with its comments, which the rewrite does not carry over; an
  earlier FILE.bak is replaced, and the output says so). A file already up to
  date is left as it is, so running it again changes nothing. A file with a
  renamed row whose new id it already has (both `llm` and `loop`) is refused,
  unchanged: which one wins is the person's call.

Options:
  --help  Show this message and exit.
```

[Layers](../using/layers.md#layers-from-an-earlier-bh-02) shows it at work.

## Exit codes

| Code | When |
|---|---|
| `0` | the session ended normally, or a subcommand did its job |
| `1` | a layer file can't be read or names old rows, the composition could not start, or the session ended with an error. bh-02 says why in one line, starting `error:`. |
| `2` | a usage error: an unknown option, a `--patch` file that doesn't exist, a `--resume` that matches no session or more than one |

## Environment

| Variable | What it changes |
|---|---|
| `XDG_STATE_HOME` | where sessions live: `$XDG_STATE_HOME/bh-02/sessions/` (default `~/.local/state/bh-02/sessions/`), and the projects' auto memory |
| `XDG_CONFIG_HOME` | where your models file and startup file are: `$XDG_CONFIG_HOME/bh-02/` (default `~/.config/bh-02/`) |
| `SHELL` | the shell a `!COMMAND` line runs in (`/bin/sh` when unset) |

The Claude credential is not an environment variable of bh-02's: it is read from `local.env`
([Get started](../get-started.md#the-credential)).
