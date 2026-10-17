---
id: TASK-0133
title: 'brig: call a jail''s process starter its supervisor everywhere, never its agent'
status: To Do
assignee: []
created_date: '2026-10-17 14:34'
updated_date: '2026-10-17 19:04'
labels:
  - brig
  - size-2
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner, 2026-10-17. decision-0001 named the thing inside a jail that starts, signals, waits for and stops its processes "an agent" ("The Runtime protocol: an instance and an agent"), and brig's SPEC (about 46 uses) and code (about 69, including runtime/_oci_agent.py and AgentStartFailed) say it, while the code's own protocol for the same role is Supervisor (run/runtime.py, LinkedSupervisor, HostSupervisor). Two names for one thing, and in this repository "agent" already means bh-02's conversation loop (the agent plugin) and a sub-agent (GLOSSARY.md; the subagents plugin): bh-02's naming rule is one word, one thing. HostSupervisor is not even inside the jail, so "an agent inside" is false for it. The role is a jail's supervisor, in three forms: the supervisor program as PID 1 (LinkedSupervisor), the host-side HostSupervisor, and the docker exec one; "the supervisor program" names brig's PID 1 where the difference matters.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No brig source, test or SPEC.md text calls the supervisor role an agent: runtime/_oci_agent.py and AgentStartFailed renamed with pypeeker rename, every other use reworded; a grep for agent in libs/brig finds only uses that mean something else, each listed in the notes
- [ ] #2 decision-0001 gets a dated amendment line naming the change, its body left as the record
- [ ] #3 scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Archived 2026-10-17: brig moved to a repository of its own (TASK-0135, archived), and the old libs/brig is frozen until the new one replaces it. The new brig's decision-0001 (rule 12) names the role supervisor everywhere, enforced by a pypeeker rule.
<!-- SECTION:NOTES:END -->
