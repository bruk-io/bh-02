---
id: TASK-0139
title: >-
  A transcript whose file /clear or /compact replaced keeps writing to the old
  one if its restart fails
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 05:20'
updated_date: '2026-10-18 13:29'
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
- [x] #1 The behaviour of a transcript whose file was replaced under it is decided and tested: an entry appended after a /clear or /compact whose restart failed is either written to the new file or refused with an error naming /restart transcript, never lost silently
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision (the owner's): a transcript whose file was replaced under it REFUSES, naming /restart transcript; it never writes the old conversation into the new file, nor into the old inode.
What changed: host_paths.Appender (libs/host-paths/src/host_paths/appender.py) now means one file: the one it holds open, or, before its first write, the one standing at the path when it was made. On its writing thread, before each write, it compares that file with a no-follow stat of the path (os.path.samestat); another file, a link, or none raises the new host_paths.Replaced (an OSError), kept like any failed write (nothing queued after it is written; append, flush and close raise it; the descriptor still closes). The first open compares the opened file with the one meant too, so a transcript that had written nothing yet (a resumed session, /clear as the first command) cannot open the new file after the old conversation either, and a removed file is not re-created by the write. agent plugin FileTranscript (transcript.py) says it as TranscriptReplaced(OSError) with kind transcript_replaced and a message naming the file and /restart transcript, from append, flush and the row's leaving: a recoverable failure, so chat:converse shows it and carries on and the person can type the command (a plain OSError would end bh-02). Docs: appender docstring, host-paths README and CLAUDE.md, agent README, conversation.py and transcript.py docstrings, CONTRACTS.md transcript row, docs/bh-02/how-it-works/loop.md.
Tests: libs/host-paths/tests/test_host_paths_appender.py (renamed over, removed, turned into a link, each held open and not yet opened; neither file written, no file created; earlier lines stay; descriptor closed; a file truncated or appended to in place is still the file; a file that appears before the first write when there was none is appended to). test_agent_transcript.py (FileTranscript directly). test_agent_conversation.py, from the loop: /clear and /compact (x file held open / nothing written yet) rewrite the file, the restart is made to fail (Loader.fails, _drain, jobs.told is unrestarted(...)), the next reply raises TranscriptReplaced (kind, message with /restart transcript, an OSError with the Recoverable shape), the next append and flush too, the new file and the .bak are byte-identical afterwards and hold no refused text, then a fresh FileTranscript over the file (what /restart transcript mounts) answers and writes only the new conversation; and a real cordis Runtime row: the row's retire after a refusal completes (cordis swallows the undo's error as a teardown-error event) and the next row writes to the new file.
Planted violation seen failing: with the check removed from Appender (_unreplaced a no-op and the guard in _hold off) 8 appender tests and all 5 new agent tests fail (DID NOT RAISE Replaced / TranscriptReplaced); with only _unreplaced off, 7 appender tests fail; restored, all pass.
Commands: uv run pytest libs/host-paths + agent plugin (242 passed, 1 skipped); scripts/check libs/host-paths (format, lint, types, tests 68 passed, gates all ok, docs ok; exit 0); scripts/check bh-02/plugins/agent-cordis-plugin --no-gates --no-docs (174 passed, 1 skipped; exit 0); scripts/arch-check --no-fix (exit 0); the other Appender users (app row log, command line, watching, sub-agent event log): 56 passed.
Known limit, filed as TASK-0152: the check is on the writing thread, so the first message after a failed restart is queued, the model is asked once, and the refusal surfaces at the step's entry append (every later append is refused at once). Also filed TASK-0153: a plain transcript write failure (a full disk) is not Recoverable, so by the code it ends bh-02 (read, not run).

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
...............................................sss...ssss.s.s.s...s...s. [ 48%]
..ss.s.s.s.s..sss.s.ssss.s.........s.................................... [ 49%]
........................................................................ [ 51%]
........................................................................ [ 53%]
.........sssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss [ 55%]
sss........s..................ssssssssssss.............................. [ 57%]
...........................................s............................ [ 59%]
........................................................................ [ 60%]
.....................................................s.s.s.............. [ 62%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 97%]
........................................................................ [ 99%]
...........                                                              [100%]
3783 passed, 118 skipped in 199.41s (0:03:19)
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
INFO    -  Documentation built in 3.92 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

No repro: the failing test can only be shown against the code before the fix, which a reviewer cannot check out; the regression test is test_agent_conversation.py::test_a_reply_after_a_restart_that_failed_is_refused_naming_the_restart, and the worker recorded it failing with the check planted off (5 agent tests, 8 appender tests DID NOT RAISE).

Reviewed (not the worker): closed. Full scripts/check exit 0 (3783 passed, gates and docs ok), no files changed by it. AC#1 met: Appender refuses a replaced/removed/linked file (Replaced) and FileTranscript raises TranscriptReplaced naming /restart transcript, tested from the loop for /clear and /compact with a failed restart, both files left untouched. Nits only: Appender.__init__ now stats the disk on the caller's thread (event loop); decision-0009 (trajectory) is unrelated, the decision taken is the owner's, recorded in the plan. Known limits already filed as TASK-0152 and TASK-0153; no new drafts.
<!-- SECTION:NOTES:END -->
