---
id: decision-0003
title: >-
  Complete slash commands in the composer from the commands the palette already
  reads
date: '2026-10-13 23:45'
status: accepted
---
## Context

The owner (2026-10-13): typing `/` in the composer shows nothing, so the person has to know a
command's name or open the palette (Ctrl-P). Claude Code shows the matching commands as you type.

How commands reach the screen today:

- `commands:registry` binds `commands`, a broker that depends on nothing (CONTRACTS.md:
  commands). Rows add to it with `register(spec, run)`: the operator's commands
  (`commands:operator`), `/clear` and `/compact` (agent), `/model` (models), `/agents` (agents),
  `/release` (runner), memory's and the extensions' own. A spec is `name`, `help`, `usage` and,
  optionally, `choices()`: arguments offered as entries of their own (`/model haiku`), read
  when asked. Only `/model` has `choices` today; an extension's spec arrives as data over IPC,
  so a `choices` in it is not callable and offers nothing. The chat row (`chat:converse`) asks
  `commands.claims(line)` (the line stripped first) and runs a command's line; the ui never
  runs one itself, it only `send`s a line to the input.
- `tui:palette` (depends on `commands` and `frame`) pushes `commands.specs` into the app's own
  broker, `frame.commands(specs)` (CONTRACTS.md: frame). It is the one bridge from the commands
  broker to the screen.
- `tui:ui` depends on nothing but its config, so no reload elsewhere restarts the app and loses
  the transcript (`tui_cordis_plugin/wiring.py`, `ui`).
- The app lists what the palette shows with `palette_entries()`:
  `frame.palette_entries(frame.offered_commands())`, a pure function of the pushed specs that
  adds each spec's `choices` as entries and the ui's own `/help` and `/exit`, a call offered
  twice shown once, and a `choices()` that raises offering none. `choose(entry)` runs an entry
  through `send`, or, when it takes arguments (`usage`), puts `/name ` in the composer.
- The palette opens only while no question is up (`action_command_palette`, `_asking`). Its
  provider calls `palette_entries()` when it opens and again on every keystroke
  (`widgets/palette.py`, `discover` and `search`), so every `choices()` runs once per key, on
  the app's event loop. Its rows are built as `Content` with the help escaped, not markup.
- `choices()` can do I/O: `/model`'s calls `models.listed()`, which reads the models file
  each time it is asked (`models_cordis_plugin/switch.py`, `_choices`; `catalog.py`).
- The composer is a `TextArea` (`widgets/composer.py`): an `on_key` that runs before
  TextArea's own handling sends on Enter and starts a new line on Ctrl-J or Shift+Enter. Up
  and Down only move the cursor (there is no input history); Tab moves focus (TextArea's
  default `tab_behavior`); Esc means nothing to the app.

The rules this must keep (bh-02/CLAUDE.md, CONTRACTS.md): nothing blocks the event loop the TUI
shares; `tui:ui` depends on nothing; no plugin imports another, and they agree by key and
shape; brokers stay commutative; the ui runs no command itself.

**Who owns commands.** The owner asked whether commands should be the TUI's. They stay a
neutral broker: a command is something bh-02 does, and the TUI is one way to show and invoke
it. The chat row runs commands, claimed prefixes (`!`) route lines that are not slash commands,
the broker holds `for_model` output across a chat restart, and a composition with another ui,
or a test composition with a fake one, uses the same commands. Owned by the TUI, every
contributor would depend on a TUI key and reload with it, and a composition without the TUI
would have no commands. The TUI owns how commands look and the keys that reach them, through
its `frame`; a command that only makes sense in the TUI (a `/theme`, say) is a TUI row
registering into `commands` like any other row, or handled by the app as `/exit` is.

## Options

| | Approach | For | Against |
|---|---|---|---|
| A | `/` typed into an empty composer opens the Ctrl-P palette | Small; fuzzy search, choices and "finish the arguments in the composer" already work | A modal takes the person out of the composer; typing a command no longer feels like typing |
| B | An inline list above the composer, filtered as the person types | Typing stays in the composer; each command's help is shown | A widget and key routing to write |
| C | Ghost text: the one best completion, greyed, Tab to accept | Least on screen | One suggestion only, so it does not help finding commands; Textual's `Suggester` serves `Input`, not `TextArea`, so it would be custom rendering |
| D | The `textual-autocomplete` package | Prebuilt | A dependency pinned against Textual 8.2, still adapted to a multi-line composer |

## Decision

**B, an inline list, in the tui plugin alone, fed by what the palette already reads.**

### No new key, no row, no change outside the tui plugin

The list reads `palette_entries()`, the palette's own list, so the two views of the commands
always agree and nothing changes in `commands`, `tui:palette` or the `frame` key's shape. Every
plugin that registers a command, now or later, is offered with no work of its own. `tui:ui`
keeps depending on nothing. The dependency is not hidden: it runs `tui:palette` -> `commands`,
declared, and `frame` is read the way it is meant to be. Without `tui:palette` in the layers
(or while it reloads) the list offers only `/help` and `/exit`, as the palette does.

The list is part of the app, not a row of its own. `tui:status` and `tui:grades` are rows
because each brings another key's data into `frame`; the list brings nothing in, it is a view
over what `frame` already holds, as the Ctrl-P provider is. A row would need a new `frame`
shape and gain nothing.

### Read once each time the list opens, filter as the person types

The list opens when the composer's text, stripped as the broker strips it, becomes a single
line starting with `/` (from not being one), and takes its entries then: one `choices()` call
per command per opening, never one per keystroke. That costs less than the palette, which reads
them on every key. Each keystroke filters the snapshot. The list ignores the `frame`'s commands
changing while it is open (the app's `on_frame_changed` already does nothing for them); a
command registered or removed meanwhile shows at the next opening, and choosing one whose row
has gone is answered by the chat row as an unknown command, never reaching the model. It closes
when the text stops being a one-line `/` line, when it is sent, on Esc, when the composer
loses focus, and when a question is put up; it does not open while a question is up. Ctrl-P's
`choose` writing `/name ` into the composer opens it, showing that command's choices.

### A pure matcher, and one place that cleans what is shown

`frame.completions(entries, text) -> tuple[PaletteEntry, ...]`, pure, public in `frame.py`'s
`__all__`: nothing for text that is not one line starting with `/` once stripped; otherwise
the entries whose `call` starts with the text, in the palette's order, then those that contain
it, case-insensitive. Arguments need no rule of their own: `palette_entries` already holds
`/model haiku`, so `/model h` matches it.

`palette_entries`, which both views share, strips control characters (C0, DEL, C1) from each
entry's call, help and usage: an extension the model wrote registers commands, and model names
come from the models file (and, after TASK-0088, a server). The rows are built as `Content`,
the help escaped, never markup strings, as the palette's are: a `usage` like `[NAME]` is text.

### The widget

`widgets/completions.py`: an `OptionList` subclass with `can_focus = False`, in the layout's
flow between the transcript and the composer, `display: none` until it has entries, at most 8
rows tall and scrolling past that. Each row is one line: the call, then its help dimmed and cut
with an ellipsis to the width, and `usage` for an entry that takes arguments. The transcript
(`1fr`, anchored to its end) gives up at most those 8 rows and keeps its newest line in view.
The highlight moves by setting `highlighted`, so the composer keeps focus; a click on a row
(`OptionSelected`) goes through `choose`. It takes `PaletteEntry` values (call, help, usage),
a plain frozen dataclass with nothing of the commands broker in it, so another source of
completions could feed it later.

### Keys, only while the list is open

The composer's `on_key` stops these and prevents their default, so neither TextArea's cursor
bindings nor the screen's Tab-to-focus see them:

- Up and Down move the highlight. (Free today; an input history added later would have to
  share them.)
- Tab completes the composer to the highlighted call (with a trailing space when it takes
  arguments) and runs nothing. With the list closed, Tab moves focus as now.
- Enter takes the highlighted entry through `choose` (it runs, or, when it takes arguments, the
  composer gets `/name ` and the list shows that command's choices) only when the person has
  moved the highlight, or has typed no space yet and the text is a strict prefix of the
  highlighted call (`/he` runs `/help`, `/mo` gives `/model `). Otherwise Enter sends the text
  as typed: an exact call (`/model` lists the models), a call with a trailing space and no
  argument (`/model ` too), an argument the list does not know (`/agents stop general-2`), or
  one that prefixes a choice (`/model h` sends `/model h`; Tab or a moved highlight takes
  `/model haiku`). Typed text is never replaced by an entry the person did not pick.
- Esc closes the list and leaves the text. A flag, cleared when the text stops being a
  one-line `/` line and when a line is sent, keeps it shut until then. TextArea never sees the
  Esc.
- Ctrl-J or Shift+Enter (a new line) closes it: a command is one line.

### Not now

Completions for other triggers (`@` for files, `!` for shell history) are not part of this.
When a second one is wanted, its source is the decision to make then (a TUI-local push into
`frame`, or a broker of its own); the widget already takes plain entries. Letting the palette
snapshot in `discover` too, so both views read once per opening, is a follow-up.

### Where the work is

`tui_cordis_plugin/frame.py` (`completions`; control characters stripped in
`palette_entries`), `widgets/completions.py` (new, re-exported by `widgets/__init__.py`
alone), `widgets/composer.py` (key routing while open), `app.py` (layout, the snapshot, open
and close, the question rule; `on_frame_changed`'s docstring). CONTRACTS.md's `frame` row: the
specs are read when the palette is searched and when the composer's list opens. The tui
plugin's README (its palette paragraph) and `docs/bh-02/using/commands.md` describe it. One
task, size 2.

### Tests

Unit: `completions` (prefix before substring, palette order, case, arguments, not a `/` line,
a leading space, more than one line, an empty `/`); `palette_entries` stripping control
characters. Pilot:
- `/mo` shows `/model`; Tab completes it and focus stays in the composer.
- Enter on `/mo` gives `/model ` and the models; Enter on `/model ` sends `/model`; Enter on
  `/model h` sends `/model h`; Down then Enter on `/model h` runs `/model haiku`.
- Enter on `/he` runs `/help`; Enter on a typed `/agents stop x` that matches nothing sends it.
- Esc keeps the text and the list stays shut until the line changes.
- Ctrl-J and Shift+Enter close it.
- A click on a row runs it.
- No list while a question is up; a question arriving while it is open closes it.
- Ctrl-P while it is open; Ctrl-P's `choose` opens it on that command's choices.
- While a reply streams, Enter on an entry goes through `send` and is drawn after the reply.
- Eight entries on a 15-row terminal leave at least one transcript line; at 40 columns each
  entry is one row.
- A spec whose `choices` counts its calls is called once per opening, not per key.

## Consequences

- No row gains a dependency and nothing reloads that did not before.
- The palette and the list cannot disagree: both are `palette_entries()`.
- A command's `choices()` is called once per opening of the list, and once per key while the
  palette is open, on the event loop: it must stay cheap. TASK-0088 carries this as a
  criterion of its own: `/model`'s `choices` reads a cached list of discovered models, filled
  off the loop, and never discovers itself.
- Any message the person starts with `/` (a path, `/usr/...`) opens the list once and calls
  every `choices()` once.
- TASK-0087 marking the default in `/model`'s list would show in this list too, through
  `/model`'s `choices` help.
- Claimed prefixes (`!`) are not offered, as the palette does not offer them.

## Reviews

Three reviews, 2026-10-13, none by the author, each ACCEPT WITH CHANGES; all taken:

- **Composition.** The design holds in cordis terms. Corrected: the palette reads entries on
  every keystroke, not once per opening. Said now: what a stale snapshot does (safe: an
  unknown command), the list without `tui:palette`, `on_frame_changed` ignoring commands while
  open, why the list is not a row, closing when a question is put up, Esc kept from TextArea.
- **Boundaries.** No gate tripped. Corrected: the real-launch tests run the TUI, so the
  ownership reason names another ui or a fake. The TASK-0088 constraint is now that task's own
  criterion. Said now: rows as `Content` with help escaped, control characters stripped in
  `palette_entries`, `completions` in `__all__`, the exact-call Enter rule, the input-history
  note, TASK-0087's mark.
- **Textual.** Buildable on Textual 8.2.8 (`on_key` pre-empts the bindings; Esc is free).
  Corrected: the list sits in the layout's flow, not docked (docked, it covered the status
  bar), and cannot take focus (a click would have blurred the composer and closed it). The
  Enter rule now never replaces typed text the person did not pick; Shift+Enter closes the
  list; rows are one line; Tab with the list closed is unchanged; more Pilot tests.

Accepted by the owner, 2026-10-14, with the defaults above as written (the Enter rule, the
8-row cap, the list opening on Ctrl-P's `choose`). Built by TASK-0090, under the intent
TASK-0089.
