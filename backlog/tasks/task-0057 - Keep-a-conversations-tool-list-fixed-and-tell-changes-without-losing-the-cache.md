---
id: TASK-0057
title: >-
  Keep a conversation's tool list fixed, and tell changes without losing the
  cache
status: To Do
assignee: []
created_date: '2026-10-09 00:36'
labels:
  - agent
  - tools
  - models
dependencies:
  - TASK-0056
references:
  - >-
    https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages
  - >-
    https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
  - >-
    https://github.com/deepseek-ai/deepseek-harness/blob/main/.agents/notes/implemented/architecture/2026-09-20-dynamic-tool-updates.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
With a tools broker (TASK-0056) the tool list can change mid-conversation: an extension registers a tool, a layer edit adds a row. Tool definitions are the very start of the prompt, so a changed list invalidates a model server's whole cache: a local model reprocesses the conversation for minutes (it looks frozen) and Claude Code restarts. bh-02 already solved this for the system prompt (`agent_cordis_plugin.prompt`: send the prompt the conversation began with, tell a change as a note). Anthropic's API adds and removes tools mid-conversation as `tool_addition`/`tool_removal` blocks in `role: "system"` messages (beta `mid-conversation-tool-changes-2026-07-01` by reference, `inline-tools-2026-09-15` with full definitions), keeping the cached prefix. DeepSeek Harness records each request's tool list and each change as session events and lets each model declare the wire form (`toolUpdate: addition-only | in-history`), falling back to the current list (cache lost) where a provider supports neither. bh-02's Claude route declares tools to Claude Code over an in-process MCP server, so what Claude Code does with an MCP `tools/list_changed` notification decides that route.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The transcript records the tool list a conversation began with and each later change (added, removed, redefined), so a resumed session rebuilds the same requests
- [ ] #2 The model is told of a change with the next result or message, as a prompt change is told
- [ ] #3 Each provider decides how a change reaches the model; the openai provider's choice and what it costs the cache are written in the models README
- [ ] #4 What Claude Code does with an MCP tool-list change (whether it offers the new tool, whether it keeps its cache or restarts) is measured and written in the models README, and the claude-code provider uses the cheapest route that works
- [ ] #5 `/clear` and `/compact` begin the new conversation with the current tool list
- [ ] #6 Tests cover a tool added, removed and redefined mid-conversation, and a resume after each
<!-- AC:END -->
