# Memory

bh-02 tells the model what your instruction files say, the way Claude Code does: the same
`CLAUDE.md`, `AGENTS.md` and rules files, found in the same places. It also gives the model a
place of its own to keep memories across conversations: auto memory.

## Instruction files

These files become a section of the model's system prompt. They are read again before each
message the model reads, so an edit reaches its next one. Which files load, in what order (the
nearest the project count most), how `@path` imports work, and which load only when an input
opens a file they cover: [what loads at launch](../reference/plugins/memory.md#what-loads-at-launch)
and [on demand](../reference/plugins/memory.md#what-loads-on-demand).

`/memory` lists every file, marked by how it loads: `✓` at launch, `…` on demand, `·` not there,
`✗` excluded or not read. Open them in your own editor: bh-02's app owns the terminal.

A sub-agent is told them too: its prompt has the same instruction files, and its inputs are told
what loads on demand, in its own conversation. It has no auto memory and no `memory` tool: several
sub-agents writing one directory would race the main conversation.

## What bh-02 does differently

The model can write files in the project, so bh-02 reads memory with that in mind:

- A file in the project doesn't import anything from outside it. The prompt says which import was
  passed over and why. Your own files, outside the project, may import from anywhere.
- No link the model could have made is followed, and nothing named like a secret
  (`local.env`, `.env`) is read.

## Settings

The `memory` row's config, set in a layer ([Layers](layers.md)):

| Setting | What it does |
|---|---|
| `instruction_files` | when `AGENTS.md` is read: `claude-md-or-agents-md` (the default, as above), `claude-md-and-agents-md` (both, `CLAUDE.md` first), `claude-md` (never), `managed-only` (only the managed policy at launch) |
| `excludes` | globs over absolute paths; a file that matches is left out (Claude Code's `claudeMdExcludes`) |
| `managed` | the managed policy file, when not the platform's |
| `root` | the project: `.`, the working directory, by default |
| `home` | the home directory whose `~/.claude/` is read: yours by default |

The on-demand files follow the same settings.

## Auto memory

Auto memory is the model's own memories, kept across conversations as Claude Code keeps them: a
`MEMORY.md` index and a file per memory. The model saves, reads and deletes them with its
`memory` tool, so auto memory works whatever other tools the model has.

The `memory` tool writes outside the jail, from bh-02's own process, and does not ask you. That
is on purpose. The code that writes is bh-02's, not the model's, and it writes only in the
project's memory directory (below), through no link: a link, or a second name for another file,
that the model left there is refused, never followed, and nothing outside the directory is read,
written or removed. The jailed model can already write that directory without asking, so asking
would protect nothing, and a jail per save would be a whole process for a small file write.
No other tool gets this: [the jail and approval](../how-it-works/jail-and-approval.md#the-memory-tool-runs-outside-the-jail)
says which are asked about, and why this one is not.

The memories live outside the repository, in a directory of the project's own:
`$XDG_STATE_HOME/bh-02/projects/<project>/memory`, under `~/.local/state` when the variable is not
set. `<project>` is the git repository's root, so the worktrees of one repository share it.

- A memory has a name (a slug such as `prefers-tabs`), a type (`user`, `feedback`, `project` or
  `reference`), a one-line description and a text. Saving under a name that exists updates that
  memory, never a second file. A save whose name, type or description does not fit is refused,
  saying what to fix.
- `MEMORY.md` has one line for each memory the tool saved, kept as memories are saved and deleted.
  Lines you wrote yourself, such as headings, notes and links to anything else, are left as they
  are.
- A file the model writes in that directory by other means (with Python, say) is its own and is
  not checked.

At the start of each conversation the model is told how to keep these memories, then the index's
first 200 lines (or 25 KB). It is read once a conversation, so memories the model saves during
one are not told back to it; the next conversation lists them.

Among its rules for keeping memories, the model is told:

- to check the index for a memory that already covers a new one, and save under its name rather
  than add a duplicate;
- for `feedback` and `project`, to follow the rule or fact with a **Why:** line and a **How to
  apply:** line;
- to write dates as absolute ones, not relative ones;
- to make `description` one specific line, since it decides whether the memory is relevant;
- not to save what only matters to this conversation, or what the code, its history or CLAUDE.md
  already records; asked to save one of those, to ask what was non-obvious about it and save that;
- to check a memory that names a file, function or flag against the code or git log before
  recommending it;
- to keep each memory under 200 lines and 4 KB, organised by topic: to split or summarise one
  that outgrows that.

To turn auto memory off, and the `memory` tool with it, disable its row in a layer of your own:

```toml
[[plugin]]
id = "memory-auto"
disabled = true
```

The memory plugin's README has the full rules: [memory-cordis-plugin](../reference/plugins/memory.md).
