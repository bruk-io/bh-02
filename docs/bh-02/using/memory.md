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
`MEMORY.md` index and a file per memory. The model writes them with the tools it has, as it
writes any file.

They live outside the repository, in a directory of the project's own:
`$XDG_STATE_HOME/bh-02/projects/<project>/memory`, under `~/.local/state` when the variable is not
set. `<project>` is the git repository's root, so the worktrees of one repository share it. The
jail lets the model's code write there.

At the start of each conversation the model is told how to keep these memories, then the index's
first 200 lines (or 25KB). It is read once a conversation, so memories the model writes during
one are not told back to it.

To turn auto memory off, disable its row in a layer of your own:

```toml
[[plugin]]
id = "memory-auto"
disabled = true
```

The memory plugin's README has the full rules: [memory-cordis-plugin](../reference/plugins/memory.md).
