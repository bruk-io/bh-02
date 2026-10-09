# Get started

bh-02 is a coding agent in a terminal app. The model works by writing Python, at a Python REPL of
its own that lasts the run, and its code runs inside a jail. This page takes you from a clone to
a first session.

## What you need

- [uv](https://docs.astral.sh/uv/). It fetches Python 3.15 for you.
- A Claude subscription, and Claude Code's `claude` command to make a token for it. You can also
  use a model of your own instead: see [Models](using/models.md).
- For the jail: macOS, or Linux with bubblewrap installed (the `bubblewrap` package). Anywhere
  else, run bh-02 with `--no-jail`.

## Install

Clone the repository and install every package in it:

```sh
git clone https://github.com/bruk-io/bh-02 && cd bh-02
uv sync --all-packages
```

This puts bh-02, its plugins and the libraries in the checkout's `.venv/`. From the checkout,
`uv run bh-02` starts it.

To have `bh-02` as a command on your `PATH`, install it from the checkout as a uv tool:

```sh
uv tool install --editable ./bh-02/app
```

The plugins and libraries are installed from the checkout, so a `git pull` updates the command
too. After a pull that adds a plugin or changes a dependency, run the same command again with
`--reinstall`.

## The credential

bh-02 reaches Claude through Claude Code, on your subscription. It needs a Claude Code OAuth
token in a file of its own:

1. Run `claude setup-token`. It makes a long-lived token for your subscription.
2. At the root of the checkout, create a file named `local.env` with one line:
   `CLAUDE_CODE_OAUTH_TOKEN=` followed by the token.
3. Make the file readable only by you: `chmod 600 local.env`.

`local.env` is git-ignored. bh-02 looks for it above its own install, so it finds the checkout's
file from any directory you work in. The model row reads it itself and hands the token only to
the Claude Code process it starts. The model's code never gets it: the jail hides the file and
scrubs the environment.

!!! warning
    Keep the token in `local.env` and nowhere else. Don't commit it, put it on a command line or
    in another file, and don't set `ANTHROPIC_API_KEY` in its place.

Without a token bh-02 still starts, and each message answers with an error that says where to
put one.

## A first session

Run bh-02 in the project you want to work on. With the tool installed:

```sh
cd ~/some/project
bh-02
```

Without it, run the checkout's own copy: `~/path/to/bh-02/.venv/bin/bh-02`.

The screen is the conversation, with the box you type in (the composer) under it and the status
bar along the bottom. The status bar shows the session's id, the model and its provider, and how
well the jail holds, for example:

```text
session: 20261008-225453-f7e7 │ model: sonnet (claude-code) │ jail: jailed fs_write ✓ network ✓ fs_read ~ env ✓
```

Type a message and press Enter. The model answers, and runs Python as it works: each call is an
input, shown with what it printed. While a reply runs, `Ctrl+C` stops it. `Ctrl+P` lists the
commands, and `Ctrl+Q`, `/exit` or `/quit` leaves.

When you leave, bh-02 prints the session's id and how to continue it:

```text
session 20261008-225423-07f8  (uv run bh-02 --resume to continue it)
```

## Continue a session

```sh
bh-02 --resume          # this directory's newest session
bh-02 --resume 07f8     # one session: its id, the start of it, or its last part
bh-02 sessions          # this directory's sessions, newest first
```

The conversation comes back, with the model the session last used. The Python namespace does
not: it lasts one run, and the model is told so. [Sessions](using/sessions.md) has the details.

## Run without the jail

```sh
bh-02 --no-jail
```

The model's code then runs with your own permissions, so bh-02 shows you each input, code and
all, and runs it only when you answer `y`. Use it where the jail can't run. A resumed session
keeps the jail it started with, so `--resume` refuses `--no-jail`. [The jail](using/jail.md) says
what the jail holds and what you give up without it.

## Next

- [Commands](using/commands.md): what you can type besides a message.
- [Models](using/models.md): Claude's other models, and models of your own.
- [Rows and layers](how-it-works/rows-and-layers.md): what bh-02 is made of.
