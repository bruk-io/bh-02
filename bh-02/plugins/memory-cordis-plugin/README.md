# memory-cordis-plugin

Claude Code's memory in bh-02, as [Claude Code's docs](https://code.claude.com/docs/en/memory)
describe it: the CLAUDE.md and AGENTS.md files, the files they import and the rules, found where
Claude Code finds them and told as a section of the system prompt; the ones for a subdirectory
or some files told with the result of the first input that opens a file they cover; and
`/memory`, which lists them. The system prompt itself is agent's (`agent:system`); this adds a
section to it.

| Row | Binds | Consumes |
|---|---|---|
| `memory:memory` | `memory` (`text() -> str`, `touched(paths) -> [(file, text)]`, `listed() -> [Entry]`, `places()`); registers `/memory`; config: `root` (default `.`), `home`, `instruction_files` (default `claude-md-or-agents-md`), `excludes`, `managed` | `system` (`add`), `commands` (`register`) |
| `memory:on_touch` | adds `OnTouch` to `notes`; no config: the memory files are `memory`'s | `memory` (`touched`), `notes` (`add`), `transcript` (`messages`) |

## What loads at launch

`text()`, read fresh before each message the model reads, so an edit reaches the next one:

1. **The managed policy**: `/etc/claude-code/CLAUDE.md` on Linux, `/Library/Application
   Support/ClaudeCode/CLAUDE.md` on macOS (the row's `managed` to name another). No exclude
   removes it.
2. **Yours**: `~/.claude/CLAUDE.md`, then each rule in `~/.claude/rules/` without `paths`.
3. **Each directory from the filesystem's root down to the project's**: its `CLAUDE.md`, its
   `.claude/CLAUDE.md`, at the project's own the rules in `.claude/rules/` without `paths`, then
   its `CLAUDE.local.md`. So a project's instructions come after yours, and the ones nearest
   where bh-02 runs are read last.
4. **AGENTS.md** and `.claude/AGENTS.md`, as `instruction_files` says (Claude Code's **Project
   instructions** setting): `claude-md-or-agents-md` (the default) reads them only when no
   directory above has a `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` (your
   `~/.claude/CLAUDE.md` does not count); `claude-md-and-agents-md` reads both, CLAUDE.md
   first; `claude-md` never; `managed-only` reads only the managed policy at launch (a
   subdirectory's CLAUDE.md and rules still load on demand).

Each file's block-level HTML comments (`<!-- notes for maintainers -->`, on their own lines) are
taken out, and the files it imports follow it: `@path`, relative to the file, absolute, or
`@~/...`, at a line's start or after whitespace, up to four hops, never in a code block or a code
span, a space written `\ `. A file larger than 4 MiB is skipped. `excludes` (globs over absolute
paths, as Claude Code's `claudeMdExcludes`) leaves out a file whose path, or where its links
lead, matches.

Each is told as `Contents of <file> (<what it is>):` and the text, after a paragraph saying that
where these files name Claude Code they mean the model in bh-02, and that the later file wins
where two disagree. `""` when nothing loads.

## What loads on demand

`touched(paths)` (the files an input opened, `kernel.touched()`, standing in for Claude Code's
Read, Write and Edit), broadest first: for each directory between such a file and the project's
root, its `CLAUDE.md` and `CLAUDE.local.md` (and its `AGENTS.md` as `instruction_files` says:
by default where it has none of the three CLAUDE files and no CLAUDE.md is above the project),
and the rules in its own `.claude/rules/` (one without `paths` for everything under it; one with
them, matched from that directory); then each of your rules and the project's whose `paths`
match. A pattern is from the project's root (`src/api/**/*.ts`), with no `/` at any depth
(`*.tsx`), each `{a,b}` group one of its alternatives.

`memory:on_touch` tells each with that input's result as `From <file>, ...:` and the text, once a
conversation (again when its text changes), at most 20,000 characters with one result (a file
the cap cut is told whole with a later input that opens a file it covers). A memory file the
model opened itself is in the conversation already and is not told after that, as Claude Code
does not load one its own tools read. It depends on `transcript`, so a new conversation
(`/clear`, `/compact`) is told afresh, and a resumed one is not told again what its transcript's
`tool` entries hold.

## What bh-02 does differently, and why

- **An import out of the project, from a file in it, is not followed.** Claude Code asks the
  first time. bh-02 reads memory in a worker thread with nobody to ask, and the model can write
  the project's CLAUDE.md (an `@~/.ssh/id_ed25519` there would hand it a key the jail hides), so
  it says in the prompt that it did not import that file, and why. Your own files
  (`~/.claude/CLAUDE.md`, a directory above the project) may import from anywhere.
- **No link the model could have made is followed.** A file in the project is walked to from
  its root through no link (`O_NOFOLLOW` on every part) and read only when it is a regular file
  with one name; a link there is read only when it leads to another memory file (a CLAUDE.md
  linking to the AGENTS.md beside it, read once). A file of yours whose way passes through the
  project (`~/.claude/CLAUDE.md` a link into a dotfiles repository bh-02 runs in) is not read,
  and nothing named like a secret (`local.env`, `.env`) ever is.
- **`/memory` lists, it doesn't open.** bh-02's app owns the terminal, so `/memory` names each
  file, marked by how it loads (✓ at launch, … on demand, · not there, ✗ excluded or not read),
  and you open one in your own editor.
- **Auto memory** (the notes Claude Code writes itself) is not here yet.

## Reading safely

`reading.py`'s `read(path, files, root)` is the one way a memory file is read, for the prompt
and for an input's result alike. `markdown.py` (`imports`, `uncommented`) and `rules.py`
(`rule`, `matches`) are pure.
