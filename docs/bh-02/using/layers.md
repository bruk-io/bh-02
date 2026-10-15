# Layers

Everything bh-02 is, is a list of rows, and the rows come from layer files. A layer of your own
changes any part of bh-02: another jail setting, a row turned off, a plugin added.

## Rows and layer files

A layer is a TOML file of `[[plugin]]` tables, one per row:

```toml
[[plugin]]
id = "runner"               # the row's role
use = "runner:confined"     # the component that fills it: plugin:component, or module:attribute
config = { write = ["."] }  # its configuration
```

bh-02 applies three kinds of layer, in this order:

1. `bh-02.toml`, the shipped composition: the whole harness.
2. The session's own `session.toml`, which bh-02 writes ([Sessions](sessions.md)).
3. Your `--patch` files, in the order you give them.

A row with a new `id` is added. A row with a known `id` replaces that row's fields: give only the
fields you change. A `config` replaces the row's whole config; it doesn't merge with it.
`disabled = true` turns a row off. Order within a file means nothing: what a row depends on
decides when it starts.

[The app](../reference/app.md#the-compositions) lists the shipped rows, and
[Rows and layers](../how-it-works/rows-and-layers.md) explains how they fit.

## Patching: `--patch`

Start bh-02 with a layer of your own over the shipped one:

```sh
bh-02 --patch mine.toml
```

`--patch` can be given more than once. For example, this layer turns off auto memory:

```toml
[[plugin]]
id = "memory-auto"
disabled = true
```

`/rows` then shows the row as `disabled`. Three rows bh-02 adds itself (`host`, `session` and
`shell`) are pinned on, so no layer removes them.

A session remembers the names of the patches it started with, and `bh-02 sessions` lists them,
but a resume applies only the patches you give it then.

## Layers are live

bh-02 watches every layer file while it runs. Edit one, by hand or with `/model`, and the rows
that changed are swapped, the rows that depend on them reload, and everything else carries on. An
edit that can't be applied changes nothing, and is reported when you leave (the app owns the
terminal while it runs).

The model's code can't write a layer file: the jail protects them.

## Seeing the composition

- `/rows` shows each row, the component that fills it and its state.
- `/explain ROW` says what cordis knows about one row.
- `--trace FILE` appends every row's lifecycle events to `FILE` (the app owns the terminal, so
  they go to a file).

## A layer that names what bh-02 doesn't have

bh-02 renames its own rows and plugins now and then, and it doesn't translate the old names. A
layer that names a plugin, a component or a row bh-02 no longer has fails at boot, whichever layer
it is: the shipped one, a session's own `session.toml`, or a `--patch` file. bh-02 exits with code
1, once the terminal is yours again, and says which row could not start, the `use` it names and
which plugins are installed:

```text
error: could not start:
loop: unresolved: ModuleNotFoundError: No module named 'nonesuch' (use 'nonesuch:loop'; no 'nonesuch' plugin either; installed plugins: agent, chat, commands, extensions, memory, models, python, runner, subagents, tui)
chat#16: inactive
  waiting on: loop
shell#32: inactive
  waiting on: done
error: chat needs loop; no row provides it
```

To fix it, edit the layer so the row names what exists: the plugin from the list in the message,
and a component that plugin has (for a plugin that is there but has no such component, the message
lists the components it has). A row of your own with no `use`, whose `id` bh-02 doesn't have, is
refused the same way, naming the row. After a `git pull` that renames a plugin, install again with
`--reinstall` first ([Get started](../get-started.md)): the names come from what is installed.

A run that fails this way makes no session. A resumed session whose layer names something bh-02
dropped is kept: edit its `session.toml`, in its directory under `bh-02/sessions/` in the state
directory (`$XDG_STATE_HOME`, else `~/.local/state`), or start a new session.
