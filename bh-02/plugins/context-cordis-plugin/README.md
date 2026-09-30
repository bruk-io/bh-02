# context-cordis-plugin

What the model is told about where it is working.

| Row | Binds | Consumes |
|---|---|---|
| `context:project` | `system` (`text() -> str`); config: `root` (default `.`), `instructions` (default `["CLAUDE.md", "AGENTS.md"]`), `max_chars` | `kernel` (`reads()`: what its jail can read) |

`text()` is read fresh for every request: the working directory, the git branch (from
`.git/HEAD`, no subprocess), today's date, and the first of the project's instructions files
that exists, capped. Edit CLAUDE.md and the next request carries the edit; nothing reloads.
When the kernel's jail reads by allowlist (Linux: `kernel.reads()` names the trees), the
prompt says which trees it reads and that nothing else is there, the person's home directory
included (no `~/.gitconfig`, `~/.ssh`, dotfiles), so the model spends no steps on reads that
can't succeed. darwin's jail reads everything but the secrets, and nothing is said.
`describe` is the prompt as a pure function of what was found.
