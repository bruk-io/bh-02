# context-cordis-plugin

What the model is told about where it is working.

| Row | Binds | Consumes |
|---|---|---|
| `context:project` | `system` (`text() -> str`, `add(section) -> remover`); config: `root` (default `.`), `instructions` (default `["CLAUDE.md", "AGENTS.md"]`), `max_chars` | |

`text()` is read fresh for every request: who the model is (the model in bh-02, not Claude
Code: a CLAUDE.md is often written for Claude Code, and the claude-code provider's prompt opens
with Claude Code's own line), what bh-02 is made of (cordis rows the person reshapes while it
runs), the working directory, the git branch (from `.git/HEAD`, no subprocess), today's date,
and the first of the project's instructions files that exists, capped, introduced as meant for
whichever agent works there. Edit CLAUDE.md and the model's next message carries the edit (the
loop tells it as a change, so the prompt the conversation began with stays as it was); nothing
reloads. `describe` is the prompt as a pure function of what was found.

`system` is also a broker: a row with something to tell the model `acquire`s a section,
`yield acquire(system.add, section)` (`section: () -> str`, read with the rest each time), and
the remover takes it out when the row leaves. `extensions:extensions` adds how to extend
bh-02, and each prompt section an extension adds.
