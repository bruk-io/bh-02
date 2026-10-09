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

## Layers from an earlier bh-02

Some rows have been renamed or merged since earlier versions (`llm` is now `loop`, `kernel` is
`python`, `jail` is `runner` and `layers` is `host`, for four), and so have some components
(`chat:session` is now `chat:converse`, `tui:app` is `tui:ui`). A session's own layer is brought up to date when
you resume it. A `--patch` file is yours, so bh-02 stops before the app starts and says what to
change:

```text
error: a --patch file names rows this bh-02 renamed or no longer has:
  mine.toml: row 'llm' is now 'loop'; rename its id
run `bh-02 update-layer mine.toml` to rewrite it (the original is kept beside it as .bak), then run again
```

`bh-02 update-layer` rewrites the file in today's names and keeps the original, comments and
all, as `FILE.bak`:

```text
$ bh-02 update-layer mine.toml
mine.toml: row 'llm' is now 'loop'; rename its id
rewritten; the original, with its comments, is mine.toml.bak
$ bh-02 update-layer mine.toml
mine.toml is up to date: nothing to change
```

A file with both an old row and its new name (`llm` and `loop`) is refused unchanged: which one's
settings win is yours to decide.
