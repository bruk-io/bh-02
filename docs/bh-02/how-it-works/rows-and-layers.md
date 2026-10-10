# Rows and layers

bh-02 is a cordis program. Every part of it is a row: the model, the agent loop, the Python
process, the runner that jails it, the app on screen, the slash commands. No part imports
another. They agree on keys, and any of them can be replaced while bh-02 runs.

## A row, a component, a key

A **row** is one part of the running program: an `id` (its role), the **component** that fills it
(`use`), and its `config`. A component is an async generator that yields effects: it binds
values under **keys**, registers entries in other rows' registries, starts background work. Its
keyword-only parameters are the keys it needs.

For example, the `loop` row is filled by `agent:loop`. It needs `model`, `tools`, `transcript`,
`system`, `approval`, `output`, `asides` and `executor`, and binds `loop`. The `chat` row
(`chat:converse`) needs `loop`, and reads your messages and shows the replies.

A consumer states what it needs of a key as a Protocol of its own, and cordis checks the bound
value against it before the consumer starts. A provider imports nothing to satisfy it; it just
has the methods. The keys and their shapes are written down in one place:
[Contracts](../reference/contracts.md).

## What reloads when

A component runs only while every key it needs is bound. Replace a binding and exactly the rows
that depend on it reload; nothing else does. That is why bh-02 splits some parts into rows of
their own:

- **The conversation survives a model switch.** The transcript is its own row, so `/model`
  reloads the model row and the loop over it, and the conversation carries on.
- **The namespace survives a new model or app.** The `python` row depends on the runner, the
  `approval` rule and brokers that never reload, so a new model or ui keeps the Python process
  and what it holds. A new runner starts a new one.
- **The screen never reloads.** The `ui` row (`tui:ui`) depends on nothing but its config. Small
  rows such as `status` and `grades` depend on what they show and push into the app's frame, so a
  change to what they show reloads them instead of the app. What they show is never replaced by
  `/clear` or `/model`, so neither reloads the status bar.

`/rows` shows each row and its state. [The app](../reference/app.md#the-compositions) has the
shipped rows and what each depends on.

## Why the shipped rows are cut where they are

Several parts of `bh-02.toml` are rows of their own only so that a reload elsewhere leaves them
alone:

- **`tools`**, the broker of the model's tools (each a standard spec and the function that runs a
  call, offered in name order), depends on nothing. A tool's row restarting (the python row's, on
  `/clear`) reloads neither the loop nor any other row.
- **`models`** (`models:catalog`) is the models there are and which one the model row names, read
  fresh each time and depending on the loader and `host` alone. `/model` (the `switch` row) and
  the status bar read it, not `model`, so a switch reloads neither.
- **`executor`** depends on nothing, so `/clear` and `/model`, which reload the loop, keep it.
  Nothing stops a reading of the prompt part-way, so however often the loop reloads, Ctrl-C
  after Ctrl-C leaves at most one reading running, and the next waits for it.
- **`asides`**, **`access`** and **`system`** are brokers that depend on nothing (`system` on its
  config alone). The row that adds to `asides` and `access`, memory's on-touch row, depends on
  `transcript`, so a new conversation (`/clear`) is told afresh and a resumed one is not told
  again what its transcript holds. It has no config of its own: it asks the `memory` row, whose
  `root`, `home`, `instruction_files` and `excludes` hold for both.
- **`memory-auto`** is a row of its own over `transcript`, so a new conversation reads the
  MEMORY.md index afresh, and `disabled = true` on it turns auto memory off.
- **`status`** depends on the loader, `models`, `session` and `frame`; **`grades`** on the runner,
  the `approval` rule (which tell it each start), `frame` and `output`. None of these does
  `/clear` or `/model` replace.
- **`jobs`** runs the restarts commands ask for (`/clear`, `/compact`, `/model NAME`,
  `/restart ROW`) one at a time, after the command has answered, a failure told to you. It
  depends on `output` alone, and the chat reads your next line only once none is pending, so a
  line typed during a restart reaches the new loop.
- **`conversation`** (`/clear` and `/compact`) depends on `model`, `tools` (the specs, offered as
  the loop offers them), the loader, `commands`, `output` and `jobs`, never on the loop or the
  transcript it restarts: their restart would reload it mid-command. It finds the transcript's
  file from the row as the loader mounted it.
- **`shell-command`** claims the `!` prefix in `commands`, which only a row in a layer can do; an
  extension can't.

Each row's own README has its config: [The app](../reference/app.md#the-plugins) links them.

## Brokers

Some keys hold a collection that many rows add to: the slash commands (`commands`), the app's
status bar and palette (`frame`), the sections of the system prompt (`system`), the model's tools
(`tools`), what the model is told beside each call's result (`asides`) and what is asked before a file is
opened (`access`). One row binds the collection. Each contributor registers an entry with
`acquire`, which keeps the remover the registration returns and calls it when the contributor's
row goes. So adding or retiring a command reloads nothing else. This is the paper's service
broker (section 6.2).

## Layers

The rows come from layer files, applied in order: the shipped `bh-02.toml`, the session's own
layer, then any `--patch` files. A new `id` adds a row and a known one replaces its fields. The
loader watches every layer file, so editing one reshapes the running program: `/model NAME` is an
edit to the session's layer, and the loader swaps the one row that changed.

The shell adds three rows of its own after every layer, pinned so no layer removes them:
`host` (the layer files, and the paths the jail must protect), `session` (the running session)
and `shell` (which waits for the chat to end, and follows it across a restart of the chat
row).

[Layers](../using/layers.md) shows how to write a layer of your own. cordis's design doc has the
model in full: [cordis](../../cordis/index.md).
