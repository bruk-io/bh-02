---
id: decision-0003
title: >-
  Complete slash commands in the composer from the commands the palette already
  reads
date: '2026-10-13 23:45'
status: proposed
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
  when asked. The chat row (`chat:converse`) asks `commands.claims(line)` and runs a command's
  line; the ui never runs one itself.
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
- The palette opens only while no question is up (`action_command_palette`, `_asking`).
- `choices()` can do I/O: `/model`'s calls `models.listed()`, which reads the models file each
  time it is asked (`models_cordis_plugin/switch.py`, `_choices`; `catalog.py`). The palette
  calls it once each time it opens, on the app's event loop.
- The composer is a `TextArea` (`widgets/composer.py`): Enter sends, Ctrl-J or Shift+Enter
  starts a new line; Up and Down only move the cursor (there is no input history).

The rules this must keep (bh-02/CLAUDE.md, CONTRACTS.md): nothing blocks the event loop the TUI
shares; `tui:ui` depends on nothing; no plugin imports another, and they agree by key and
shape; brokers stay commutative; the ui runs no command itself.

**Who owns commands.** The owner asked whether commands should be the TUI's. They stay a
neutral broker: a command is something bh-02 does, and the TUI is one way to show and invoke
it. The chat row runs commands, claimed prefixes (`!`) route lines that are not slash commands,
the broker holds `for_model` output across a chat restart, and compositions without the TUI
(the real-launch tests, another ui) use the same commands. Owned by the TUI, every contributor
would depend on a TUI key and reload with it, and a composition without the TUI would have no
commands. The TUI owns how commands look and the keys that reach them, through its `frame`;
a command that only makes sense in the TUI (a `/theme`, say) is a TUI row registering into
`commands` like any other row, or handled by the app as `/exit` is.

## Options

| | Approach | For | Against |
|---|---|---|---|
| A | `/` typed into an empty composer opens the Ctrl-P palette | Small; fuzzy search, choices and "finish the arguments in the composer" already work | A modal takes the person out of the composer; typing a command no longer feels like typing |
| B | An inline list above the composer, filtered as the person types | Typing stays in the composer; each command's help is shown | A widget and key routing to write |
| C | Ghost text: the one best completion, greyed, Tab to accept | Least on screen | One suggestion only, so it does not help finding commands; Textual's `Suggester` serves `Input`, not `TextArea`, so it would be custom rendering |
| D | The `textual-autocomplete` package | Prebuilt | A dependency pinned against Textual 8.2, still adapted to a multi-line composer |

## Decision

**B, an inline list, in the tui plugin alone, fed by what the palette already reads.**

### No new key, no change outside the tui plugin

The list reads `palette_entries()`, the palette's own list, so the two views of the commands
always agree and nothing changes in `commands`, `tui:palette` or the `frame` key's shape. Every
plugin that registers a command, now or later, is offered with no work of its own. `tui:ui`
keeps depending on nothing.

### Read once each time the list opens, filter as the person types

The list opens when the composer's text becomes a single line starting with `/` (from not
being one), and takes its entries then, as the palette does when it opens: one `choices()` call
per command per opening, never one per keystroke, so `/model`'s read of the models file costs
what Ctrl-P costs. Each keystroke filters that snapshot. It closes when the text stops being a
one-line `/` line, when it is sent, on Esc, and when the composer loses focus; it does not open
while a question is up.

### A pure matcher

`frame.completions(entries, text) -> tuple[PaletteEntry, ...]`, pure: nothing for text that is
not one line starting with `/`; otherwise the entries whose `call` starts with the text, in the
palette's order, then those that contain it, case-insensitive. Arguments need no rule of their
own: `palette_entries` already holds `/model haiku`, so `/model h` matches it.

### The widget

`widgets/completions.py`: an `OptionList` docked above the composer, hidden until it has
entries, at most 8 rows tall (scrolling past that), each row the call and its help, dimmed,
and `usage` for an entry that takes arguments. It takes `PaletteEntry` values (call, help,
usage), a plain frozen dataclass with nothing of the commands broker in it, so another source
of completions could feed it later.

### Keys, only while the list is open

- Up and Down move the highlight (the composer has no other use for them on a one-line `/`
  line).
- Tab completes the composer to the highlighted call (with a trailing space when it takes
  arguments) and runs nothing.
- Enter takes the highlighted entry through `choose`: it runs, or, when it takes arguments, the
  composer gets `/name ` and the list shows that command's choices. When the typed text is
  itself an entry's call, or nothing matches, Enter sends the text as typed, so an argument
  the list does not know (`/agents stop general-2`) is never replaced by one it does.
- Esc closes the list for this line and leaves the text; it opens again only once the text has
  stopped being a `/` line.
- Ctrl-J (a new line) closes it: a command is one line.

### Not now

Completions for other triggers (`@` for files, `!` for shell history) are not part of this.
When a second one is wanted, its source is the decision to make then (a TUI-local push into
`frame`, or a broker of its own); the widget already takes plain entries.

### Where the work is

`tui_cordis_plugin/frame.py` (`completions`), `widgets/completions.py` (new),
`widgets/composer.py` (key routing while open), `app.py` (mounting, the snapshot, open and
close, the question rule). CONTRACTS.md's `frame` row: the specs are read each time the
palette or the composer's list opens. The tui plugin's README and
`docs/bh-02/using/commands.md` describe it. One task, size 2.

### Tests

Unit: `completions` (prefix before substring, palette order, case, arguments, not a `/` line,
more than one line, an empty `/`). Pilot: `/mo` shows `/model`; Tab completes it; Enter on
`/mo` puts `/model ` and shows the models; Enter on `/he` runs `/help`; Enter on a typed
`/agents stop x` that matches nothing sends it as typed; Esc keeps the text and the list stays
shut until the line changes; no list while a question is up; a spec whose `choices` counts its
calls is called once per opening, not per key.

## Consequences

- No row gains a dependency and nothing reloads that did not before.
- The palette and the list cannot disagree: both are `palette_entries()`.
- A command's `choices()` is called once per opening of the list, as by the palette. A
  `choices()` that does slow work (TASK-0088's discovered models, if it lists them there)
  would stall the event loop once per `/` typed: it must stay cheap (a cached list), or the
  spec grows an asynchronous form, decided in that task.
- Claimed prefixes (`!`) are not offered, as the palette does not offer them.

## Reviews

(Pending.)
