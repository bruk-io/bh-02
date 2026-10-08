# context-cordis-plugin

What the model is told about who and where it is, and what the guidance and rules for a file
say when the model first works on it.

| Row | Binds | Consumes |
|---|---|---|
| `context:project` | `system` (`text() -> str`, `add(section) -> remover`, `touched(paths) -> [(file, text)]`); config: `root` (default `.`), `files` (the context files after bh-02's own; default `["$XDG_CONFIG_HOME/bh-02/context.toml", ".bh-02/context.toml"]`), `max_chars` (what the context files' sections may say in the prompt, all together; default 20,000), `home` | |
| `context:on_touch` | adds `OnTouch` to `memory`; no config: the context files are `system`'s | `system` (`touched`), `memory` (`add`), `transcript` (`messages`) |

`text()` is organised as Claude Code's is, and read fresh each time it is asked:

1. **who the model is**, bh-02's own: the model in bh-02, not Claude Code (a CLAUDE.md is often
   written for Claude Code, and the claude-code provider's prompt opens with Claude Code's own
   line), and what bh-02 is made of (cordis rows the person reshapes while it runs);
2. **the project context**: the working directory and the git branch (from `.git/HEAD`, no
   subprocess, read as a section's file is: through no link); then what the context files'
   sections say; then the sections other rows add (`add`).

`agent:loop` sends a conversation the prompt it began with and tells a later change as a note.
The date is not in the prompt, which would then change every midnight: the loop tells it with
the person's message. Nor is what the kernel's jail can read: when it reads by allowlist
(Linux: `kernel.reads()` names the trees), the kernel's own instructions, which the loop sends
after `text()`, say which trees and that nothing else is there, the person's home directory
included, so this row depends on no kernel. `describe` is the prompt as a pure function of
what was found.

`touched(paths)` is what the context files' `on_touch` sections say about some files an input
opened (absolute), each `(file, text)`, read fresh from the same context files as `text()`, with
the same `root` and `home`. `context:on_touch` asks it rather than reading the context files
itself, so what a layer sets on the `system` row (`files`, `root`, `home`) reaches both, and
each file is read and searched once. It depends on `system`, `memory` and `transcript`;
`context:project` depends on nothing, so the on-touch row reloads with it only when the `system`
row changes, and with `transcript` at each new conversation (`/clear`), which `system` and its
caches outlive. What the conversation was told before the row began (a resumed session's, or
before it reloaded) it reads from the transcript once, at the first input that opens a file:
the notes the loop told with each result, which it keeps on the `tool` entry (`notes`). A text
one of them holds whole is told already, so a resume does not tell it again: the note itself,
or one of the texts the row's note joins with a blank line, ending where the note ends, where it
was cut short, or where the next text begins (bh-02's own on-touch functions begin one `From
FILE, guidance for work under` or `From FILE, a rule for`, and a section that failed `(bh-02
could not make the section`). One cut short, one changed since and one cut back since (the
paragraphs now gone follow it, however they begin) are told, and so is one that another
function's text follows in the note: told twice rather than never. A note the result printed is not one
told. An entry from before the loop kept `notes` is searched instead: a text it holds whole
after a blank line, where a note ends (the entry's end, the mark of a note cut short, or
another note: bh-02's begin with `(`, the context files' with `From `), but not one the entry
starts with; where a result ends is not marked there, so a text an input printed that way counts
too.

`agent:loop` calls `text()` on its `executor` (`agent:executor`), in a thread off the event loop
the TUI runs on, one call at a time, so a section function that reads many files or searches a
large project freezes nothing; it runs in that thread too, and must not need the event loop. So
do the `on_touch` functions (`context:on_touch` is a `memory` function, which the loop calls the
same way, and it calls `touched()` there). `executor` waits for each call to end before the next
begins, a reading a stopped reply left running included, and it is a row of its own that
`/clear` and `/model` don't reload, as `system` is, so the one set of caches of what was read
and searched, which `text()` and `touched()` share, is used by one thread at a time and takes no
lock. Only a new `executor` (its row restarted, or replaced by a layer) can start a call beside
one the last left running; the caches' changes are single dict operations, so the worst that
costs is a file read or a search done twice.

## Context files

A context file is TOML, a list of sections, each some files and the function that says what
they mean to the model:

```toml
[[section]]
files    = ["AGENTS.md", "CLAUDE.md", "**/AGENTS.md", "**/CLAUDE.md"]
function = "context_cordis_plugin.sections:place"
on_touch = "context_cordis_plugin.sections:place_touched"
```

- `files`: patterns from the project's root (`*`, `**/` for any depth; `**/AGENTS.md` matches the
  root's too); `~/...` and `/...` are paths of their own, with no wildcard. Each time the prompt
  is read, a pattern with no wildcard is looked for, and one with a wildcard is searched for again
  only if a directory the last search looked in has changed since (a file in it added, moved or
  removed): one `stat` per directory, not a walk, so a new guide or rule reaches the model's next
  message. A search walks into what the pattern names (`.claude/rules/`, watching the nearest
  directory above it until it is there), and below that skips hidden directories and those tools
  fill (`node_modules`, `build`, `dist`, `target`, `vendor`, virtualenvs).
- `function`: a full module path, `package.module:function`, called as
  `function(files, root=root, home=home) -> str` with the files that matched, in the order of
  the patterns, each once; it returns what the model is told ('' for nothing). It runs each
  time the prompt is read, in the loop's worker thread. One that can't be imported, or raises,
  says so in one line, and the other sections still say theirs. bh-02's own read each file with
  `read(path, files, root)` (below), and a function of yours may: a file it reads itself may
  have been made a link since it was found.
- `on_touch` (optional): another, called as `on_touch(files, touched, root=root, home=home)`
  after each input that opened files in the project (`touched`, absolute: `kernel.touched()`),
  returning a mapping of each of its files that bears on them to the text to tell with that
  input's result. `context:on_touch` tells each once a conversation (again if what it says
  changed), at most 20,000 characters with one result, so a path-scoped rule or a
  subdirectory's AGENTS.md arrives the first time the model works on a file it covers, as
  Claude Code's do when its Read, Write or Edit touches one. A text that note cut short, or
  left out, is not told yet: the next input that opens a file it covers tells it whole (one
  longer than 20,000 characters by itself is told once, cut). A section may have only `on_touch`.

The sections are read in order from bh-02's own file (`context.toml`, in the package), then each
of `files`: yours, `$XDG_CONFIG_HOME/bh-02/context.toml` (else `~/.config/bh-02/context.toml`),
then the project's, `.bh-02/context.toml`. A name in `files` starting `$XDG_CONFIG_HOME/` is in
that directory, or in `home`'s `.config` when the variable is unset or empty
(`cordis_helpers.config_home`, as for the models file and the kernel's startup files); one
starting `~` is in `home`; any other is from the project's root. Each appends its sections;
`replace = true` at a file's top starts the list afresh. Each of `files` is read again whenever
it changes, so a section added reaches the model's next message.

**bh-02's own file is read once**, as the `system` row starts. It is trusted whole (a function
it names is imported and run in bh-02's process), so it is bh-02's code, as its modules are,
and like them it is read before any of the model's code runs (the row starts before the kernel
and the extensions' worker) and not again. That matters when bh-02 works on its own checkout
(an editable install): the file is then in the project. The jail denies an input writing it
(`layers.code`, the brig plugin's README), and where it can't (bh-02 run in the package's own
directory, or with `--no-jail`), what an input wrote there waits for bh-02, or the row
(`/restart system`), to start again, as an edit to any of bh-02's modules does: never the next
message (`test_bh_02_s_own_context_file_is_read_once_as_the_row_starts`). Holding the file to
the project's terms instead would have cost every session in the checkout your own guidance
(`~/AGENTS.md`, `~/CLAUDE.md`) and the rule files, which those terms refuse. If you edit it
while working on bh-02, start bh-02 again to see the change.

**The project's file is held to what the model may do itself**, because the model can write it
and bh-02 acts on it in its own process, outside the jail. So it may name only bh-02's own
functions (`context_cordis_plugin.sections:*`, as `function` and as `on_touch`), and only files
in the project that are not hidden (no `~`, `/`, `..` or part starting with `.`), and it may not
`replace` the sections before it. A function or a file outside the project of your own goes in
your file. A context file is the project's when the model could have written it or chosen what
it is: as named, as it resolves, or through any directory or link on its way
(`cordis_helpers.walked`, the walk the models file and the kernel's startup files are held to),
it is in the project. So a file of yours inside it (bh-02 run in your home, a
`$XDG_CONFIG_HOME` in the project) is the project's; so is `.bh-02/context.toml` (or `.bh-02`)
made a link to a file outside it, such as one the model wrote in the jail's scratch directory;
and so is your file when it is a link into the project (`~/.config/bh-02/context.toml` kept in
`~/dotfiles`, and bh-02 run there), since the model could repoint the file the link leads to.

And whichever file a section came from, nothing is read through it that the jail keeps from
the model: a file reached from the project must be in it, a link in the project counts only
when it leads to another file the section found (a CLAUDE.md linking to the AGENTS.md beside
it), a file in the project reached through a linked directory, or with a second name (a hard
link), is not read, and a file named like a secret (`local.env`, `.env`, `*.env`) is never read.
A link of your own, outside the project (`~/AGENTS.md` into your dotfiles), is yours to follow,
unless it leads through the project (bh-02 run in those dotfiles): the model could repoint its
end, so it is not read (the project's own `AGENTS.md`, that same file, is, on the project's
terms). That is decided when the files are found, and the model can make a link at any moment
after, so the read is safe by itself too: `read(path, files, root)`, which bh-02's own functions
read every file with, walks to a file in the project from its root through no link (`O_NOFOLLOW`
on every part) and reads it from what that opened, only when it is a regular file with one name
(a pipe is refused, not waited on); a link there is read as its target, the same way, only when
that is another of `files`; a file outside the project is read as it is named. A file it does
not read raises an error saying why, so the section says it could not be made.

bh-02's own functions (`sections.py`):

| Function | What it says |
|---|---|
| `place` | Guidance files, each of which applies to everything under the directory it sits in: at the project's root or outside the project (yours, in your home) whole, broadest first, each once (a CLAUDE.md linking to the AGENTS.md beside it is read once); further down, named for the model to read before it works there. |
| `rules` | Rule files, as each one's frontmatter says (`rule`): `alwaysApply: true`, or no frontmatter, whole; `paths` or `globs` (a list, or one comma-separated string, split only at the commas outside braces) named with them as written, for files they cover; a `description` named with it, for when it bears on the work; `alwaysApply: false` and nothing else not at all (yours to bring in). |
| `whole` | Each file, whole. |
| `named` | Each file by name, to read when it bears on the work. |
| `place_touched` (an `on_touch`) | The guidance further down that covers a file an input opened (the file is under its directory), whole, broadest first, one of two with the same text. |
| `rules_touched` (an `on_touch`) | The rules whose `paths` or `globs` match a file an input opened (from the project's root; a pattern with no `/`, `*.tsx`, at any depth; each `{a,b}` group one of its alternatives, as Claude Code's `paths` write it: `src/**/*.{ts,tsx}`), each whole. |

bh-02's own file reads `~/AGENTS.md`, `~/CLAUDE.md`, the project's `AGENTS.md`, `CLAUDE.md` and
their `.local.md`, and those further down, with `place` (and `place_touched`); and
`.claude/rules/**/*.md` and `.cursor/rules/**/*.mdc` with `rules` (and `rules_touched`). So the
prompt names the guidance further down and the rules for some files, and each arrives whole
with the result of the first input that opens a file it covers.

## The broker

`system` is also a broker: a row with something to tell the model `acquire`s a section,
`yield acquire(system.add, section)` (`section: () -> str`, read with the rest each time), and
the remover takes it out when the row leaves. `extensions:extensions` adds how to extend bh-02,
and each prompt section an extension adds.
