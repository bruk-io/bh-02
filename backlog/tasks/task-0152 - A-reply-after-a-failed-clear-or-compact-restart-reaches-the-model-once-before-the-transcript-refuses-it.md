---
id: TASK-0152
title: >-
  A reply after a failed /clear or /compact restart reaches the model once
  before the transcript refuses it
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 13:24'
updated_date: '2026-10-18 21:17'
labels:
  - agent
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0139 made a transcript whose file was replaced under it refuse every entry, as TranscriptReplaced naming /restart transcript. The check runs on the appender's writing thread, so the refusal surfaces at the first append made after the thread has run it: in a reply that is the step's entry, after the model step (the person's message and the model's answer from the old conversation are shown first, then the notice). Only that first message after the failed restart gets this; every later append is refused at once. Find the cheapest way to refuse it before the model is asked (for example the loop awaiting the transcript's health at the start of a reply without a disk wait, or a check the transcript can make without a stat on the event loop), without a flush per entry.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A reply begun after a /clear or /compact whose restart failed is refused before the model is asked: the scripted model sees no request, and the error is the TranscriptReplaced that names /restart transcript
- [x] #2 A reply over a transcript whose file was not replaced costs the event loop no wait on a disk, and the flush-count tests in test_loop.py still hold or change for a stated reason
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Decision: the loop awaits the transcript's check at the start of a reply, before it appends anything (not 'has the writer failed yet': after a failed restart nothing was queued since the rename, so the thread has not looked at the file and the failure is not there to read; and not a flush: the transcript cannot know a restart failed, and a flush per reply is a disk wait).
1. host_paths.Appender.check(): queues a no-write job on the writing thread (the same lstat/samestat the thread makes before each write), awaits it; a replaced file is kept as the failure like a failed write (nothing after it written, append/flush/close raise it). The stat runs on the thread, never on the event loop; no write is waited for. ValueError once closed, as append.
2. FileTranscript.check(): Appender.check through _refusing (TranscriptReplaced naming /restart transcript).
3. Loop: optional capability (_Checkable Protocol, like _Flushable; MemoryTranscript and the flush-count doubles have none) awaited first in _reply, before _answer_the_unanswered and any append, so a refused reply keeps nothing and the model is never asked.
4. Tests: appender check tests (host-paths); test_agent_conversation failed-restart test asserts the scripted model saw no request and the error is TranscriptReplaced naming /restart transcript, entries untouched; test_loop: check runs once first before any append on a transcript double and flush counts stay as they are; a FileTranscript reply stats the file only on the writer thread (none on the event loop).
5. Docs: appender docstring, host-paths README/CLAUDE.md, transcript.py/loop.py/conversation.py docstrings, agent README (drop the known limit), CONTRACTS.md transcript row, docs loop page.
Proof: plant the violation (loop does not call check) and see the new conversation tests fail; scripts/check host-paths and agent plugin (first with gates+docs), arch-check --no-fix.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision: the loop awaits the transcript's check first in a reply, before it appends anything (loop.py _checked, an optional capability _Checkable like _Flushable; FileTranscript.check -> host_paths.Appender.check). Why not 'has the writer failed yet' read without waiting: after a failed restart nothing has been queued since the rename, so the writing thread has never looked at the file and there is no failure to read; only a look the reply asks for can find it. Why not a flush: the transcript cannot know a restart failed, so it would be a flush (a wait for a disk write) on every reply. The check queues the thread's own pre-write stat (os.stat, samestat) with no write, behind nothing at a reply's start (the reply before flushed), and is awaited with the event loop free; a replaced file is kept as a failed write is (nothing after it written, append/flush/close raise it; the row's leaving still raises it). Honest cost: one thread hop and one lstat per reply, on the writer thread; the event loop makes no stat and waits on no write or flush.
Changed: libs/host-paths/src/host_paths/appender.py (check, _look, docstring), agent plugin loop.py (_Checkable, _checked, first line of _reply, docstrings), transcript.py (FileTranscript.check, docstrings), conversation.py docstring; docs: host-paths README + CLAUDE.md, agent README (the known limit is gone), CONTRACTS.md transcript row, docs/bh-02/how-it-works/loop.md.
AC#1: test_agent_conversation.py::test_a_reply_after_a_restart_that_failed_is_refused_naming_the_restart (/clear and /compact x file held open / nothing written yet) now asserts the scripted model saw no request (model.requests == []), the error is TranscriptReplaced with kind transcript_replaced and /restart transcript in its message, and the transcript kept nothing of the message in memory. Planted violation seen failing: with loop.py's await self._checked() removed, all 4 parametrizations fail at model.requests == [] (the model was asked once); restored, they pass.
AC#2: test_loop.py::test_a_reply_costs_the_event_loop_no_stat_of_the_file_either (a real FileTranscript over an existing file: every os.stat of the file is on the writer thread, none on the event loop's; seen failing with Appender.check changed to look on the caller's thread); test_a_reply_asks_the_transcript_to_check_its_file_first_and_flushes_it_once (a double with check and flush: checked == [0] before anything appended, flushed == [n], one flush per reply across two replies); test_a_transcript_that_refuses_at_the_check_is_never_asked_a_model_step_or_an_entry (both new loop tests seen failing with the check call removed). The existing flush-count tests in test_loop.py (_Flushing, no check method) are unchanged and pass: the check is no flush, so a flush is still one per reply, at its end. Appender tests (libs/host-paths/tests/test_host_paths_appender.py, 6 new): check finds renamed over / removed / linked, held and not yet opened, with nothing queued, keeps it, neither file touched; no file made for a never-made file; stat on the writer thread and nothing written; queued behind a held write; raises an earlier failure; closed -> ValueError (8 fail with _look made a no-op, planted). test_agent_transcript.py: FileTranscript.check refuses naming /restart transcript.
Commands: scripts/check libs/host-paths (exit 0: format, lint, types, 80 tests, all gates ok, docs ok); scripts/check bh-02/plugins/agent-cordis-plugin --no-gates --no-docs (exit 0, 195 passed, 1 skipped); scripts/arch-check --no-fix (exit 0); uv run pytest bh-02 -n auto --dist loadgroup (1906 passed, 5 skipped).
Known limits: a Ctrl-C landing in the check's window (microseconds, before anything is kept) keeps neither the message nor any entry; nothing was in the conversation to lose, but the ui's history shows the message. The check waits behind writes still queued from an abandoned flush (a slow disk), none in the normal case. Appender.__init__ still stats on the caller's thread (the reviewer's nit on TASK-0139), not touched. The full scripts/check is the reviewer's.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
......................................s...ssss.s...s..s.ss..s.ss.s.s.s.s [ 48%]
..ss..ss..sssss..........s.............................................. [ 50%]
....................................................................s... [ 52%]
...................................................................sssss [ 54%]
ssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss.......... [ 56%]
...................ssssssssssss......................................... [ 58%]
........................................................................ [ 59%]
........................................................................ [ 61%]
..........................................sss........................... [ 63%]
........................................................................ [ 65%]
....................s................................................... [ 67%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 97%]
........................................................................ [ 99%]
............                                                             [100%]
3856 passed, 118 skipped in 207.31s (0:03:27)
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
INFO    -  Documentation built in 4.75 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
