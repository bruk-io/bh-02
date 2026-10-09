# Memory

bh-02 tells the model what your instruction files say, the way Claude Code does: the same
`CLAUDE.md`, `AGENTS.md` and rules files, found in the same places. It also gives the model a
place of its own to keep notes across conversations: auto memory.

## Instruction files

These files become a section of the model's system prompt. They are read again before each
message the model reads, so an edit reaches its next one. In order:

1. **The managed policy**: `/etc/claude-code/CLAUDE.md` on Linux,
   `/Library/Application Support/ClaudeCode/CLAUDE.md` on macOS.
2. **Yours**: `~/.claude/CLAUDE.md`, then each rule in `~/.claude/rules/` that has no `paths`.
3. **Each directory from `/` down to the project**: its `CLAUDE.md`, its `.claude/CLAUDE.md`, and
   its `CLAUDE.local.md`. At the project itself, the rules in `.claude/rules/` with no `paths`
   come before `CLAUDE.local.md`.
4. **`AGENTS.md`** and `.claude/AGENTS.md`, by default only where no directory above has a
   `CLAUDE.md` of any kind.

Where two files disagree, the later one wins, so the files nearest the project count most. A file
can pull in another with `@path` (relative, absolute, or `@~/...`), up to four imports deep.
HTML comments on lines of their own are taken out.

Some files load only when the model needs them: a subdirectory's `CLAUDE.md`, and a rule whose
`paths` match a file. The first time an input in a conversation opens a file they cover, they
arrive whole with that input's result. Claude Code does the same when its own tools touch a file.

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

Auto memory is the model's own notes, kept across conversations as Claude Code keeps them: a
`MEMORY.md` index and a file per memory. The model writes them with the tools it has, as it
writes any file.

They live outside the repository, in a directory of the project's own:
`$XDG_STATE_HOME/bh-02/projects/<project>/memory`, under `~/.local/state` when the variable is not
set. `<project>` is the git repository's root, so the worktrees of one repository share it. The
jail lets the model's code write there.

At the start of each conversation the model is told how to keep these notes, then the index's
first 200 lines (or 25KB). It is read once a conversation, so notes the model writes during one
are not told back to it.

To turn auto memory off, disable its row in a layer of your own:

```toml
[[plugin]]
id = "memory-auto"
disabled = true
```

The memory plugin's README has the full rules: [memory-cordis-plugin](../reference/plugins/memory.md).
