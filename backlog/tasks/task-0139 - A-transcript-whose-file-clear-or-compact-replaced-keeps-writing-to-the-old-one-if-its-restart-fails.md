---
id: TASK-0139
title: >-
  A transcript whose file /clear or /compact replaced keeps writing to the old
  one if its restart fails
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 05:20'
updated_date: '2026-10-18 13:14'
labels:
  - agent
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0136.06 made FileTranscript hold its file open (host_paths.Appender). /clear and /compact replace the transcript's file by rename (transcript.rewrite) and queue the restart of the loop and transcript rows in jobs. If that restart fails, the person is told ('/restart transcript begins the new one'), but the old FileTranscript is still mounted: its held descriptor is on the replaced file's old inode, so entries appended meanwhile are lost, not written to the new file (before 0136.06 they were appended to the new file by path, after the seed, which was also wrong). Decide what a transcript should do once its file was replaced: reopen by path, refuse with an error that says /restart transcript, or detect it (fstat vs stat) at the next write.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The behaviour of a transcript whose file was replaced under it is decided and tested: an entry appended after a /clear or /compact whose restart failed is either written to the new file or refused with an error naming /restart transcript, never lost silently
<!-- AC:END -->
