---
id: TASK-0188
title: >-
  Find out how Claude Code's extract-memories pass saves memories without the
  main agent
status: In Progress
assignee:
  - '@claude'
created_date: 2026-10-10 12:15
updated_date: '2026-11-04T13:51:00Z'
labels:
  - memory
  - size-1
  - finish-moved
dependencies: []
priority: low
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The CLI bundled with claude-agent-sdk 0.2.159 (2.1.281) has a background pass that saves memories from a conversation (`querySource` `extract_memories`, event `tengu_extract_memories_extraction`), besides the main agent saving its own. Found while comparing bh-02's auto memory with Claude Code's (2026-10-10), not yet read. bh-02's model saves a memory only when it decides to; if a main agent under-saves, a pass like this is Claude Code's answer. A draft until it is accepted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The task's notes say when the pass runs, which model, what it reads, what its prompt asks for, what it may write and its limits, each with where in the CLI's code it was read
- [ ] #2 The notes say whether bh-02 should do the same, and a follow-up task is logged if so
- [ ] #3 The notes say how Claude Code's extract-memories pass saves memories without the main agent, naming the bundled CLI version read (SDK 0.2.158)
- [ ] #4 The notes say what of it DRAFT-0002 would reuse
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).

SPIKE FINDINGS (worker, 2026-11-04). What was read: the bundled CLI at .venv/lib/python3*/site-packages/claude_agent_sdk/_bundled/claude from claude-agent-sdk 0.2.158 (the binary reports 2.1.280; the draft named 0.2.159 / 2.1.281, which is not installed here). It is a bun single-file binary; its JS chunks are embedded as readable text (extracted with `strings`), identifiers minified, so locations below are the chunk (chunk-6t6ecsgq.js, which exports initExtractMemories, executeExtractMemories, drainPendingExtraction, createAutoMemCanUseTool, isAllowedAutoMemWritePath) and function names as minified. No credential was read or copied.

WHEN IT RUNS. initExtractMemories (VVn) installs a per-session extractor. The turn-end path (the stop-hook code that also arms prompt suggestions) calls executeExtractMemories(messages, appendSystemMessage) for the main agent only (`!agentId`, so never for a sub-agent), if f0e() holds: server flag tengu_passport_quail (default false) or the CCR config. Not awaited (fire and forget) unless the sync env is set. Guards in ce()/F(): auto memory enabled (Ma(): CLAUDE_CODE_DISABLE_AUTO_MEMORY, autoMemoryEnabled setting, not remote/simple mode), not w1(), not when ir() is non-null (unidentified); skipped when the main agent itself already wrote a memory file in the range since the last extraction (Y(): a Write/Edit to a path under the memory dir, 'skipped_direct_write'); skipped when there is no user prose since the last pass (a user message of >= 3 words, 'skipped_no_prose'); cadence every N turns (flag tengu_bramble_lintel, default 1). One at a time: a turn ending during a run stashes its context and one trailing run follows (event tengu_extract_memories_coalesced). At exit, drainPendingExtraction waits up to 60 s. Cursor: lastMemoryMessageUuid, so each pass sees only messages after the last one.
A second mode (CLAUDE_CODE_POST_TURN_MEMORY + _CONFIG with instruction / every_n_turns / max_turns / idle_flush_s) is for Anthropic's remote (CCR) sessions: the pass calls memory MCP tools; not relevant to bh-02.

WHICH MODEL / WHAT IT READS. runForkedAgent (Gw) with cacheSafeParams = CW(context): the parent's own systemPrompt, userContext, systemContext, toolUseContext, and the whole conversation as forkContextMessages. No model override is passed, so the pass runs on the session's own model through the parent's options (inferred from the absent override; I did not find a separate model name for it). It shares the parent's prompt cache (events log cache read/create). So it 'reads' the entire conversation as its prefix, then is told to use only the last ~N new messages. querySource and forkLabel are 'extract_memories'; skipTranscript (nothing written to the session log).

PROMPT (function te(), same chunk). One user message appended after the conversation: 'You are now acting as the memory extraction subagent. Analyze the most recent ~N messages above and use them to update your persistent memory systems.' + the available tools + a turn-budget hint (turn 1: read in parallel every file you might update; turn 2: write in parallel) + 'You MUST only use content from the last ~N messages ... no grepping source files, no reading code, no git' + a manifest '## Existing memory files: Check this list before writing - update an existing file rather than creating a duplicate' (the listing is built from the memory dir, xxe) + 'If nothing is worth saving, output only 'Nothing to save.'' + 'If the user explicitly asks you to remember something, save it immediately ... forget: find and remove the entry' + 'Apply the memory types, what-not-to-save criteria, and frontmatter format from the Memory section of your system prompt - it is already in your context above.' So the memory taxonomy is NOT repeated: it relies on the main system prompt's Memory section being in the shared prefix.

WHAT IT MAY WRITE, AND LIMITS. canUseTool = nun(memoryDir): allowed Read/Grep/Glob (with the session's read rules), read-only shell, Write/Edit only on .md files inside the memory directory (x5e: path ends .md and Qq(): under the dir, not a protected subdir such as .git or agents), and shell `rm` / PowerShell Remove-Item of absolute .md paths in the memory dir, no flags except -f, no globs, no redirects. Everything else (MCP, Agent, other writes) is denied with a message and logged (tengu_auto_mem_tool_denied). maxTurns 5. Result: files written are collected from the pass's Write/Edit tool calls (Te); files other than MEMORY.md go to appendSystemMessage so the main UI shows 'memories saved'. Errors are swallowed and logged (tengu_extract_memories_error); never raised into the main turn.

HOW IT SAVES WITHOUT THE MAIN AGENT, in one line: after a turn ends, a forked copy of the same agent (same prompt prefix, cache and model), restricted to the memory dir, is asked once what in the new messages is worth saving and writes the files itself; the main agent is not asked and its turn is not held up.

SHOULD bh-02 DO THE SAME? Not yet, and no follow-up is logged: nothing shows bh-02's model under-saves (the draft's premise is 'if a main agent under-saves'; scripts/model-friction could show it). If it does, the shape to copy is cheap: a post-turn background conversation with the same prefix, the tools limited to TASK-0068's memory tool, a skip when the main agent saved in the range, a 'new user prose since last pass' guard, one run at a time with a trailing run, a small turn cap. Open for the owner: bh-02 must pay for the extra model call per turn (Claude Code gates it by a server flag and every_n_turns) and whether the person sees what was saved.

WHAT DRAFT-0002 WOULD REUSE. DRAFT-0002 is the auto-dream tidy pass, a different pass (consolidation on a 24 h / 5 sessions trigger), so only the mechanics carry over: (1) a forked agent whose permissions are a canUseTool allow-list by path (here: memory dir, .md only, deletes only via rm of .md, denials reported to the model); in bh-02 TASK-0068's memory tool already gives that by construction; (2) the 'Existing memory files' manifest in the prompt; (3) one-at-a-time with a coalesced trailing run, and drain-with-timeout at exit; (4) a turn cap (5) and errors that never reach the main turn; (5) appendSystemMessage-style summary to the person of what changed. It does not reuse the trigger, the cursor on messages, or the 'skip if main agent wrote' rule.
<!-- SECTION:NOTES:END -->
