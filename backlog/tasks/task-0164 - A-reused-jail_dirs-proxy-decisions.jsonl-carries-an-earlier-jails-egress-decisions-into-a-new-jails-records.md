---
id: TASK-0164
title: >-
  A reused jail_dir's proxy-decisions.jsonl carries an earlier jail's egress
  decisions into a new jail's records
status: To Do
assignee: []
created_date: '2026-10-18 22:30'
labels:
  - brig
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing TASK-0150 (decision-204 removes a helper's declared ready file before it starts the helper, so proxy.port can no longer be an earlier jail's). The same reuse leaves the proxy's decisions file behind: brig/proxy/server.py's _Decisions opens <jail_dir>/proxy-decisions.jsonl in append mode, and brig/run/egress.py folds the file's lines into the embedder's records from a byte cursor starting at 0, so a new jail in a reused jail_dir (decision-181) reads an earlier jail's allow/deny lines as its own decisions. It is evidence, not the boundary (SPEC.md law 8, section 11), so the harm is a wrong audit trail, but a record that attributes another jail's denial to this jail's action is wrong. decision-204 names it as not covered. Options to rule on: the runtime clears a helper's declared log before it starts it (a second Helper field next to ready_path), or the reader starts its cursor at the file's end at create, or the file name carries the jail id.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A SPEC.md decision paragraph rules how a new jail never reads an earlier jail's egress decisions, naming this task and ending (Ruled YYYY-MM-DD, decision-N.)
- [ ] #2 A test plants a proxy-decisions.jsonl holding an earlier jail's line in the jail_dir before Jail.create and shows the new jail's egress_decisions return none of it; it is seen failing before the change and passing after
- [ ] #3 scripts/check libs/brig passes
<!-- AC:END -->
