# context-cordis-plugin

What the model is told about who and where it is.

| Row | Binds | Consumes |
|---|---|---|
| `context:project` | `system` (`text() -> str`, `add(section) -> remover`); config: `root` (default `.`), `files` (the context files after bh-02's own; default `["~/.config/bh-02/context.toml", ".bh-02/context.toml"]`), `max_chars` (what the context files' sections may say, all together; default 20,000), `home` | |

`text()` is organised as Claude Code's is, and read fresh each time it is asked:

1. **who the model is**, bh-02's own: the model in bh-02, not Claude Code (a CLAUDE.md is often
   written for Claude Code, and the claude-code provider's prompt opens with Claude Code's own
   line), and what bh-02 is made of (cordis rows the person reshapes while it runs);
2. **the project context**: the working directory, the git branch (from `.git/HEAD`, no
   subprocess) and today's date; then what the context files' sections say; then the sections
   other rows add (`add`).

`agent:loop` sends a conversation the prompt it began with and tells a later change as a note.
`describe` is the prompt as a pure function of what was found.

## Context files

A context file is TOML, a list of sections, each some files and the function that says what
they mean to the model:

```toml
[[section]]
files    = ["AGENTS.md", "CLAUDE.md", "**/AGENTS.md", "**/CLAUDE.md"]
function = "context_cordis_plugin.sections:place"
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
  time the prompt is read. One that can't be imported, or raises, says so in one line, and the
  other sections still say theirs.

The sections are read in order from bh-02's own file (`context.toml`, in the package), then each
of `files`: yours, then the project's. Each appends its sections; `replace = true` at a file's
top starts the list afresh. A file is read again whenever it changes, so a section added
reaches the model's next message. **The project's file may name only bh-02's own functions**
(`context_cordis_plugin.sections:*`): the model can write it, and a function it named would run
in bh-02's process, outside the jail. A function of your own goes in your file.

bh-02's own functions (`sections.py`):

| Function | What it says |
|---|---|
| `place` | Guidance files, each of which applies to everything under the directory it sits in: at the project's root or outside the project (yours, in your home) whole, broadest first, each once (a CLAUDE.md linking to the AGENTS.md beside it is read once); further down, named for the model to read before it works there. |
| `rules` | Rule files, as each one's frontmatter says (`rule`): `alwaysApply: true`, or no frontmatter, whole; `paths` or `globs` named with them, for files they cover; a `description` named with it, for when it bears on the work; `alwaysApply: false` and nothing else not at all (yours to bring in). |
| `whole` | Each file, whole. |
| `named` | Each file by name, to read when it bears on the work. |

bh-02's own file reads `~/AGENTS.md`, `~/CLAUDE.md`, the project's `AGENTS.md`, `CLAUDE.md` and
their `.local.md`, and those further down, with `place`; and `.claude/rules/**/*.md` and
`.cursor/rules/**/*.mdc` with `rules`.

## The broker

`system` is also a broker: a row with something to tell the model `acquire`s a section,
`yield acquire(system.add, section)` (`section: () -> str`, read with the rest each time), and
the remover takes it out when the row leaves. `extensions:extensions` adds how to extend bh-02,
and each prompt section an extension adds.
