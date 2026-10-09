---
id: TASK-0057
title: >-
  Keep a conversation's tool list fixed, and tell changes without losing the
  cache
status: Done
assignee: []
created_date: '2026-10-09 00:36'
updated_date: '2026-10-09 20:02'
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
- [x] #1 The transcript records the tool list a conversation began with and each later change (added, removed, redefined), so a resumed session rebuilds the same requests
- [x] #2 The model is told of a change with the next result or message, as a prompt change is told
- [x] #3 Each provider decides how a change reaches the model; the openai provider's choice and what it costs the cache are written in the models README
- [x] #4 What Claude Code does with an MCP tool-list change (whether it offers the new tool, whether it keeps its cache or restarts) is measured and written in the models README, and the claude-code provider uses the cheapest route that works
- [x] #5 `/clear` and `/compact` begin the new conversation with the current tool list
- [x] #6 Tests cover a tool added, removed and redefined mid-conversation, and a resume after each
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The transcript keeps the tools as `{"role": "tools"}` entries: the first `{"tools": [specs]}` at a conversation's first request (once `requires` are ready), each later one a change, `added`/`removed`/`redefined` (agent_cordis_plugin.toolset, pure). Before each message the model reads (a person's message, a result, a nudge) the loop reads the list again and keeps and tells a change, as a prompt change is (`toolset.told`; the person sees "told the model its tools changed since the conversation began"). A tool the conversation has that is missing for less than `wait` seconds is restarting, not removed (`clock` is injectable). request_for drops `tools` entries; /compact's "nothing said" check skips them.

Which list a request offers is the model's `tool_changes`: `fixed` (default when absent) offers the list the conversation began with, `listed` the one the transcript last recorded. Both shipped providers say `fixed`, each with why: openai (a chat template renders tools at the prompt's start; OpenAI's cache is a prefix) and claude-code (tools come first in Claude Code's requests, and a changed list means restarting it on its session). A call naming a tool added since says it comes with the next conversation; one naming a removed tool says so and doesn't run. A resumed loop reads both lists from the transcript, so it sends the same requests; a transcript from before keeps its list from its next request, telling nothing.

AC #4 is read from the code, not measured (no subscription token here): the pinned CLI (2.1.280) refreshes an MCP server's tools on tools/list_changed and sends late additions/removals as tool_addition/tool_removal blocks under mid-conversation-tool-changes-2026-07-01 (inline definitions under inline-tools-2026-09-15), keeping the cache, falling back to tools[] when rejected. The Agent SDK 0.2.158 drops what an in-process MCP server sends on its own, so bh-02 can't send list_changed; reconnect_mcp_server would relist but whether it counts as a late addition is unmeasured. So `fixed` is the cheapest route that works today; the models README says all of this and what would change it. TASK-0060 makes an added tool callable from python meanwhile.
<!-- SECTION:NOTES:END -->
