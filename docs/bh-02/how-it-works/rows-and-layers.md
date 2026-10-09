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
`system`, `approval`, `output`, `notes` and `executor`, and binds `loop`. The `chat` row
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
  `/clear`, so it reloads none of the status bar.

`/rows` shows each row and its state. [The app](../reference/app.md#the-compositions) has the
shipped rows and what each depends on.

## Brokers

Some keys hold a collection that many rows add to: the slash commands (`commands`), the app's
status bar and palette (`frame`), the sections of the system prompt (`system`), and what the
model is told after each input (`notes`). One row binds the collection. Each contributor
registers an entry with `acquire`, which keeps the remover the registration returns and calls it
when the contributor's row goes. So adding or retiring a command reloads nothing else.

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
