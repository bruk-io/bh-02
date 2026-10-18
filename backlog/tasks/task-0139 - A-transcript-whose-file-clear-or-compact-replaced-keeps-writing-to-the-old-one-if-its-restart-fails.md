---
id: TASK-0139
title: >-
  A transcript whose file /clear or /compact replaced keeps writing to the old
  one if its restart fails
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 05:20'
updated_date: '2026-10-18 13:17'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Decision (the owner's, in the delegation): a transcript whose file was replaced under it REFUSES the next append with an error naming /restart transcript, never writing the old conversation into the new file.
1. host_paths.Appender (owns the descriptor): on the writing thread, before each write, compare the file it means (the stat of the descriptor it holds, or of the file at its path when it was made, for a first write still to come) with the file at the path now (lstat, samestat); a different file, a link, or none raises the new host_paths.Replaced (an OSError) as the kept failure: nothing queued after it is written, append/flush/close raise it. Tests in libs/host-paths/tests/test_host_paths_appender.py (rename over, removal, link, never-opened, and the stray file not created).
2. agent plugin FileTranscript: translates Replaced into TranscriptReplaced (OSError with kind and message: a recoverable failure naming '/restart transcript'), from append, flush and the row's exit, so chat shows it and carries on and the person can type the command. The refused entry stays out of memory too.
3. Loop-level tests (test_agent_conversation.py): /clear and /compact rewrite the file, the restart is made to fail (Loader.fails + _drain), the next reply is refused with the message, the new file stays as the rewrite left it, and /restart transcript (a fresh FileTranscript, and a real runtime row retire) carries on; both with the descriptor held and a transcript that never wrote.
4. Docs: appender docstring, host-paths CLAUDE.md/README, agent README, CONTRACTS.md transcript row, docs/bh-02 loop page, transcript.py docstring.
Proof: plant the violation (disable the check) and see the new tests fail; scripts/check host-paths and agent plugin; arch-check --no-fix (host-paths gate).
<!-- SECTION:PLAN:END -->
