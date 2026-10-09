# memory-cordis-plugin

Claude Code's memory in bh-02, as [Claude Code's docs](https://code.claude.com/docs/en/memory)
describe it: the CLAUDE.md and AGENTS.md files, the files they import and the rules, found where
Claude Code finds them and told as a section of the system prompt; the ones for a subdirectory
or some files told with the result of the first input that opens a file they cover; auto
memory, the notes the model keeps for itself; and `/memory`, which lists them. The system prompt itself is agent's (`agent:system`); this adds a
section to it.

| Row | Binds | Consumes |
|---|---|---|
| `memory:files` | `memory` (`text() -> str`, `touched(paths) -> [(file, text)]`, `listed() -> [Entry]`, `places()`); registers `/memory`; config: `root` (default `.`), `home`, `instruction_files` (default `claude-md-or-agents-md`), `excludes`, `managed` | `system` (`add`), `commands` (`register`), `layers` (`memory`: for `/memory`) |
| `memory:auto` | adds auto memory to `system`: how to keep it, and its MEMORY.md index | `system` (`add`), `layers` (`memory`), `transcript` (its lifetime) |
| `memory:on_touch` | adds `OnTouch` to `notes`, and its `before_write` to `access`; no config: the memory files are `memory`'s | `memory` (`touched`), `notes` (`add`), `transcript` (`messages`), `access` (`before_write`) |

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
they are written for the model whatever agent they name, and that the later file wins where two
disagree. `""` when nothing loads.

## What loads on demand

`touched(paths)` (the files a call opened, as its tool answered: the python tool's inputs',
its Python process's `touched()`, standing in for Claude Code's Read, Write and Edit), broadest first: for each directory between such a file and the project's
root, its `CLAUDE.md` and `CLAUDE.local.md` (and its `AGENTS.md` as `instruction_files` says:
by default where it has none of the three CLAUDE files and no CLAUDE.md is above the project),
and the rules in its own `.claude/rules/` (one without `paths` for everything under it; one with
them, matched from that directory); then each of your rules and the project's whose `paths`
match. A pattern is from the project's root (`src/api/**/*.ts`), with no `/` at any depth
(`*.tsx`), each `{a,b}` group one of its alternatives.

**Before a write, too.** The row also answers `access` (`agent:access`) before a file is written
(`OnTouch.before_write`): the first write to a file whose on-demand instructions this
conversation has not been told is refused, naming them, and they follow as that call's note (the
refused file is among what it touched), so the next write goes ahead. That is Claude Code's
read-before-edit, in bh-02's terms: the instructions arrive before the file changes. It sees only
what the tool asks about (the python tool: Python's own `open()` of a project file, not a program
an input runs, nor `os.open`, a rename or a delete), and a refusal stops one open mid-input: the
input runs on, or ends at the PermissionError, so it may be half done, and the model hears of the
refusal with the result even when the code caught it. A memory file itself is never refused (its
own text is what the model is changing), and no read is.

`memory:on_touch` tells each with that input's result as `From <file>, ...:` and the text, once a
conversation (again when its text changes), at most 20,000 characters with one result (a file
the cap cut is told whole with a later input that opens a file it covers). A memory file the
model opened itself is in the conversation already and is not told after that, as Claude Code
does not load one its own tools read. It depends on `transcript`, so a new conversation
(`/clear`, `/compact`) is told afresh, and a resumed one is not told again what its transcript's
`tool` entries hold: the notes the loop keeps on each (`notes`), where a text of this row's ends
where the note does, where it was cut short, or where the next text begins (`From FILE,
instructions ...` or `From FILE, a rule for ...`). An entry from before the loop kept them is
searched instead.

## What bh-02 does differently, and why

- **An import out of the project, from a file in it, is not followed.** Claude Code asks the
  first time. bh-02 reads memory in a worker thread with nobody to ask, and the model can write
  the project's CLAUDE.md (an `@~/.ssh/id_ed25519` there would hand it a key the jail hides), so
  it says in the prompt that it did not import that file, and why. Your own files
  (`~/.claude/CLAUDE.md`, a directory above the project) may import from anywhere.
- **No link the model could have made is followed.** A file in the project is walked to from
  its root through no link (`O_NOFOLLOW` on every part, `host_paths.read_beneath`) and read
  only when it is a regular file with one name; a link there is read only when it leads to another memory file (a CLAUDE.md
  linking to the AGENTS.md beside it, read once). A file of yours whose way passes through the
  project (`~/.claude/CLAUDE.md` a link into a dotfiles repository bh-02 runs in;
  `host_paths.passes`, as the models file is walked) is not read,
  and nothing named like a secret (`local.env`, `.env`) ever is.
- **`/memory` lists, it doesn't open.** bh-02's app owns the terminal, so `/memory` names each
  file, marked by how it loads (✓ at launch, … on demand, · not there, ✗ excluded or not read),
  and you open one in your own editor.
- **Auto memory adds no tool.** The model writes its notes with whatever tools the
  composition gives it, as it writes any file, and this plugin names none: bh-02 is not CodeAct
  only. A tool that can write the directory says so itself (the python tool names the
  directories its jail lets it write).

## Auto memory

`memory:auto` is Claude Code's auto memory: notes the model keeps for itself across
conversations. Each project has a directory of its own outside the repository,
`$XDG_STATE_HOME/bh-02/projects/<project>/memory` (else under `~/.local/state`), where
`<project>` is the git repository's root (a worktree's main repository, so its worktrees share
one), named as Claude Code names it (every character but a letter or a digit a `-`). The
command line works it out (`bh_02.bootstrap.memory_directory`), makes it, and hands it to the
`layers` value, whose `memory` the jail lets an input write. On Linux it is the one directory
outside the project the jail lets an input read, so another project's memory is not there.

The model is told how to keep it (`auto_section`): what is worth a memory and what is not, its
four kinds (`user`, `feedback`, `project`, `reference`), one topic file per memory with
frontmatter, and one line for each in `MEMORY.md`, the index. The index's first 200 lines or
25KB (`indexed`) follow, read from the directory through no link (the model writes it). It is
read once a conversation, at its first reading of the prompt, and kept for the rest of it
(`AutoMemory`; the row depends on `transcript`, so `/clear` and `/compact` read it afresh), as
Claude Code reads it at the start of one: a write to it later in the conversation is the
model's own, and telling it back as a change in its instructions would only repeat it.
`disabled = true` on the `memory-auto` row turns auto memory off.

## Reading safely

`reading.py`'s `read(path, files, root)` is the one way a memory file is read, for the prompt
and for an input's result alike. `markdown.py` (`imports`, `uncommented`) and `rules.py`
(`rule`, `matches`) are pure.
