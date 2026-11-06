---
id: TASK-0196
title: 'bruk-io/brig: a Seatbelt jail for darwin'
status: To Do
assignee: []
created_date: '2026-11-06T15:47:00Z'
labels:
  - brig
  - size-8
dependencies: []
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Built in bruk-io/brig, on its own board. This task tracks what bh-02 needs, and closes when a commit on that repository's main delivers it. Moved out of the intent TASK-0176 (Move bh-02 off its in-repo brig onto bruk-io/brig), where it was TASK-0176.05, so the Linux migration can close: the owner has put the Mac on hold. TASK-0176.01 has the measurement.

Until it lands, runner:confined refuses to start on darwin and names runner:unconfined (--no-jail), as TASK-0176's criterion #6 requires. The new brig has only bwrap; Seatbelt is bruk-io/brig TASK-0001's criterion #4. Size-8: it needs a Mac to prove, and the read model differs from bwrap's (a denylist against an allowlist), which the runner's policy function (spec_for, to_brig) then has to express.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 bruk-io/brig jails a command on darwin under the same public API as bwrap (an FsPolicy, an EnvPolicy, channels, teardown), with no network
- [ ] #2 Its e2e tests pass on a Mac, and the four axes bh-02 shows are graded for it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
On hold: the owner, during the migration, said the Mac has to hold off for a while and took it out of the goal. Earlier, the owner, 2026-10-31: wait on Seatbelt, i.e. build it when a Mac run can prove it, not before (recorded on bruk-io/brig TASK-0001 too). Carried over from TASK-0176.05, now archived.
<!-- SECTION:NOTES:END -->
