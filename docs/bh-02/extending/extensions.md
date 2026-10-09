# The model's extensions

The model can extend bh-02 itself, while it runs. It writes a module of cordis components to the
project, and bh-02 loads it within half a second: a new slash command for you, a field in the
status bar, or text in its own prompt. No layer changes and nothing restarts.

## How an extension is loaded

- An extension is a file, `.bh-02/plugins/NAME.py` in the project (`NAME` in lowercase letters,
  digits and `_`). The model writes it from an input, like any other file. So can you.
- bh-02 looks at the directory every half second. A new file is loaded, a changed one is loaded
  afresh, and a deleted one is unloaded, taking back everything it added.
- The directory is the project's, so its extensions load again in every later session there. A
  repository you clone that ships a `.bh-02/plugins/` loads its extensions too, under the same
  rules as the model's.

The model's prompt tells it how to write one: enough cordis to get it right, the three keys it
can reach, and how to try a component in an input before writing its file.

## What an extension can do

An extension reaches bh-02 through three keys, each of which only adds, and each addition is
taken back when the extension goes:

| Key | What it adds |
|---|---|
| `commands.register(spec, run)` | a slash command for you. A name bh-02 already has is refused. |
| `frame.status(field, text, *shorter)` | a status bar field, shown as `NAME:field` so it can't cover another |
| `system.add(text)` | text in the model's own prompt, told with the next message it reads |

It can't claim a line prefix such as `!` (that takes every line you start with it, so only a row
in a layer may), replace a row, rebind one of bh-02's keys, or reach the loader. Those don't exist
where it runs. Its components may bind keys of their own for its other components to use.

A small one, which adds a command that keeps a list:

```python
from cordis import Effects, acquire, component


@component
async def notes(*, commands) -> Effects:
    kept: list[str] = []

    async def run(args: str) -> str:
        if args:
            kept.append(args)
        return "\n".join(kept) or "nothing kept yet"

    spec = {"name": "keep", "help": "Keep a line for later", "usage": "/keep [LINE]"}
    yield acquire(commands.register, spec, run)
```

## Where it runs

Not in bh-02's process. The runner starts a second process for extensions, jailed as the
model's inputs are. Each load is put to the `approval` rule, as an input is: jailed, it loads
without asking; with `--no-jail`, you are asked first, with the extension's source shown, and a
no leaves it unloaded until the file changes. What crosses back to bh-02 is data only: a
command's spec, its arguments and its answer, a field's text, a section's text.

`/release` stops the extensions' process along with the Python process: each row stops its own.
Every extension loads again once the next input has started the Python process, or at once when
one of them changes.

## How it went

- The status bar's `ext:` field lists the extensions and how each is, such as `ext: notes ✓` for the example above.
- `.bh-02/plugins/status.json` is what the model reads: each extension's state (`active`,
  `partly up`, `failed`, `loading`), each component's, any error, its commands, and anything bh-02
  refused.

bh-02 reads that directory with your permissions, so it follows no link there. A link, a file with
a second name (a hard link), or a link on the way (`.bh-02` or the directory itself) is not
loaded, since it could lead to a file the jail hides. status.json, or the model's prompt, says
what to write instead.

The extensions plugin's README has the full account, with the tests that hold it:
[extensions-cordis-plugin](../reference/plugins/extensions.md).
