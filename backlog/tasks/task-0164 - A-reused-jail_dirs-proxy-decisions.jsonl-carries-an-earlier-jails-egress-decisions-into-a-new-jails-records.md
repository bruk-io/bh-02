---
id: TASK-0164
title: >-
  A reused jail_dir's proxy-decisions.jsonl carries an earlier jail's egress
  decisions into a new jail's records
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 22:30'
updated_date: '2026-10-19 00:26'
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
- [x] #1 A SPEC.md decision paragraph rules how a new jail never reads an earlier jail's egress decisions, naming this task and ending (Ruled YYYY-MM-DD, decision-N.)
- [x] #2 A test plants a proxy-decisions.jsonl holding an earlier jail's line in the jail_dir before Jail.create and shows the new jail's egress_decisions return none of it; it is seen failing before the change and passing after
- [x] #3 scripts/check libs/brig passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Write the failing test first: in libs/brig/tests/integration/test_egress_decisions.py plant a proxy-decisions.jsonl holding an earlier jail's allow line in the jail_dir before Jail.create (launch), run a real denied request, and assert read_egress_decisions returns only this jail's deny, none of the planted line (controls: file planted and present at create; this jail's own deny is returned). Run on unchanged code: must fail. Unit tests: Helper.log_path default None/absolute-only; connect_proxy declares its decisions file as log_path equal to --log.
2. SPEC.md first: decision-205 paragraph next to decision-204 ruling option 1 (Helper.log_path, create removes it before the helper starts) and why not the reader's cursor at create (state a rehydrated jail would need persisted, race with an earlier proxy, file only grows) or the jail id in the name (compile has no jail id; ids can be reused; files accumulate); amend decision-204 'not covered' and the Helper lifetimes sentence to point at it.
3. Code: mech/contract.py Helper.log_path (+absolute guard); mech/connect_proxy.py declares log_path=log_path; run/host.py generalises _remove_ready_files to remove ready_path and log_path of every helper before any starts.
4. Proof: new test fails before (planted line read), passes after; mutation: drop the removal call -> test fails. scripts/check libs/brig once at the end.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ruling: libs/brig/SPEC.md section 6, decision-205 (2026-10-19), option 1 (same shape as decision-204): Helper gains log_path beside ready_path; HostRuntime.create removes every helper's declared ready_path and log_path (renamed _remove_declared_files in run/host.py) before any helper starts, LAUNCH_SCOPED included; a link is removed not followed; an unremovable path is an OSError from create with a note, nothing started. connect_proxy declares its decisions file (the --log argument) as log_path. Why not the reader's cursor at the end (the cursor is the embedder's and stateless, so the jail would carry an offset a rehydrated jail must read, or each embedder measures; old lines stay for cursor 0; file grows) nor the jail id in the name (compile() is pure and has no id, only jail_dir and platform; ids can repeat in a reused dir; a file per jail; decisions_path changes for callers). decision-204's 'not covered' sentence and the Helper lifetimes sentence now point at decision-205. Code: mech/contract.py, mech/connect_proxy.py, run/host.py. Tests: integration/test_egress_decisions.py::test_a_new_jail_never_reads_an_earlier_jails_egress_decisions (plants an earlier jail's allow line for earlier-jail.test in proxy-decisions.jsonl before Jail.create; controls: the plant is read as a decision before create, and this jail's own deny for 127.0.0.1 comes back; asserts hosts == ['127.0.0.1']); integration/test_helpers.py (stale log gone at the helper's own start for JAIL_LIFETIME and LAUNCH_SCOPED and the file then holds only this launch's line, neighbour kept; an unremovable log refuses create with no helper started, same-test control); unit tests for Helper.log_path (default None, absolute only, error names the field) and for connect_proxy declaring --log's path as log_path. Evidence, AC2 seen failing: on the unchanged code (SPEC and test only) the new egress test failed with 'this jail's records hold a decision an earlier jail's proxy made: [earlier-jail.test, 127.0.0.1]'; after the change the file's 7 tests pass. Mutation checks (scratch copy plus sha256, restored, hashes match d4563aaa... and 80ec427b...): removing log_path=log_path from connect_proxy fails the egress test and the unit test; removing the log_path entry from the removal pass fails the egress test and the three new test_helpers cases. The tests use HostRuntime and no bwrap, so they run here (not skipped). AC3: scripts/check libs/brig exit 0 (format, lint, mypy strict, 1386 passed 111 skipped, gates all ok, docs ok; tokens skipped, no bh-01). The full scripts/check was not run.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
......................................................s..ss...ssss.s.s.s [ 48%]
......ss..ss..sss.ss.s.s..ss..sss...s......s............................ [ 50%]
........................................................................ [ 51%]
........................................................................ [ 53%]
..............................ssssssssssssssssssssssssssssssssssssssssss [ 55%]
sssssssssssssssssssssssss............................sssssssss..s......s [ 57%]
.......s......................................................s......... [ 59%]
........................................................................ [ 60%]
........................................................................ [ 62%]
...sss.................................................................. [ 64%]
........................................................................ [ 66%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
................................................................         [100%]
3908 passed, 118 skipped in 192.73s (0:03:12)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 3.95 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (independent): not closed. Full scripts/check exit 0 (3908 passed, 118 skipped, gates and docs ok), recorded on the task, no files changed. AC1-3 met on the evidence. close-task refused: a bug closes with its repro recorded (record-check TASK-0164 --repro -- uv run pytest libs/brig/tests/integration/test_egress_decisions.py::test_a_new_jail_never_reads_an_earlier_jails_egress_decisions, run on the pre-fix code), or a 'No repro:' note. The worker saw it fail before the change but did not record it; the reviewer cannot rerun it failing without changing code. Once recorded, this closes with no other findings.
<!-- SECTION:NOTES:END -->
