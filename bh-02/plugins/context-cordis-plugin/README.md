# context-cordis-plugin

What the model is told about where it is working.

| Row | Binds | Consumes |
|---|---|---|
| `context:project` | `system` (`text() -> str`); config: `root` (default `.`), `instructions` (default `["CLAUDE.md", "AGENTS.md"]`), `max_chars` | |

`text()` is read fresh for every request: who the model is (the model in bh-02, not Claude
Code: a CLAUDE.md is often written for Claude Code, and the claude-code provider's prompt opens
with Claude Code's own line), what bh-02 is made of (cordis rows the person reshapes while it
runs), the working directory, the git branch (from `.git/HEAD`, no subprocess), today's date,
and the first of the project's instructions files that exists, capped, introduced as meant for
whichever agent works there. Edit CLAUDE.md and the next request carries the edit; nothing
reloads. `describe` is the prompt as a pure function of what was found.
