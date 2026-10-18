---
id: TASK-0153
title: >-
  A transcript write failure (a full disk) ends bh-02 with a traceback instead
  of a recoverable failure
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 13:24'
updated_date: '2026-10-18 21:41'
labels:
  - agent
  - chat
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
FileTranscript raises the writer's OSError from append, flush and the row's leaving. chat:converse shows only an exception with kind and message (Recoverable) and re-raises the rest; bootstrap._await_chat propagates it and cli.py re-raises a non-Recoverable one. Read from the code, not run: a full disk during a reply therefore ends bh-02 with a traceback and the conversation in memory lost, where a TranscriptReplaced (TASK-0139) is shown and the chat carries on. Make a failed transcript write a recoverable failure that says which file, what failed, and what the person can do (free space, then /restart transcript), keeping the writer's rule that nothing after a failed write is written.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A transcript write that fails (a full disk) is shown to the person as a recoverable failure (kind and message) naming the file and /restart transcript, and the chat carries on
- [x] #2 Tested from the loop with a failing write: the reply's error has kind and message, and nothing after the failed line reaches the file
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. transcript.py: add TranscriptWriteFailed(OSError) with kind transcript_write_failed and message naming the file, the OS error, and the remedy (free space / fix, then /restart transcript); FileTranscript._refusing keeps Replaced -> TranscriptReplaced and now says any other OSError from the Appender (append/check/flush/leaving) as TranscriptWriteFailed. The Appender is untouched, so nothing after a failed write is written. 2. export it from __init__. 3. Tests: transcript level (ENOSPC via os.write, existing monkeypatched test extended with kind/message) and from the loop with a failing write that needs no monkeypatch (a directory where the file should be: os.open fails with EISDIR on the thread), reply error has kind/message/file/restart, the notice a chat:converse-shaped Recoverable check, nothing after the failed line reaches the file; test fails first with the guard (wrapper) removed. 4. Docs: transcript.py docstring, agent README, CONTRACTS.md transcript row + docs/bh-02/how-it-works/loop.md. Proof: uv run pytest on agent tests, scripts/check bh-02/plugins/agent-cordis-plugin, arch-check --no-fix.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added TranscriptWriteFailed (OSError, kind transcript_write_failed, message naming the file, the OS error, 'free some space' and /restart transcript) in agent_cordis_plugin/transcript.py; FileTranscript._refusing keeps Replaced -> TranscriptReplaced and now says any other OSError from the Appender (append, check, flush, the row's leaving) as TranscriptWriteFailed. The Appender is untouched, so its rule stands: the failed write and everything queued after it are dropped, later appends are refused before they are kept. Exported from the package. Docs: transcript.py docstring, plugin README, CONTRACTS.md transcript row, docs/bh-02/how-it-works/loop.md. Tests: test_loop.py (replaced the monkeypatched ENOSPC loop test by two with no os function replaced: a directory swapped for a file mid-reply so the writer's stat fails with ENOTDIR, file inspected: lines before the failure present, none after, next message refused before the model is asked, same message; and a directory where the file should be, EISDIR at the first write); test_agent_transcript.py (ENOSPC test now asserts kind/message/cause/leaving; a /dev/full test, a real full disk, skipped where there is no /dev/full); test_agent_conversation.py (/restart transcript works: row retire after the failure, new row starts from the lines the file held). Planted check: with the new 'except OSError' branch of _refusing removed, both new loop tests fail (bare NotADirectoryError / IsADirectoryError, not Recoverable); restored, they pass. Ran: uv run pytest bh-02/plugins/agent-cordis-plugin -n auto --dist loadgroup (6 runs, 197-198 passed, 1 skipped = existing), scripts/check bh-02/plugins/agent-cordis-plugin (exit 0: format, lint, types, tests, gates, docs), scripts/arch-check --no-fix (exit 0). chat:converse and bootstrap unchanged (they already show any exception with kind and message). Not verified: the TUI showing the notice (converse's notice path is the one TranscriptReplaced already uses). Old files: none stop working.

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
....................................s.....s...ss.ssss..sss...s..s.s.s.s. [ 48%]
s.s..ss.s.s.ssss...s.....s.............................................. [ 50%]
........................................................................ [ 52%]
......................................................................ss [ 54%]
ssssss.ssssssssssssssssssssssssssssssssssssssssssssssssssssssssss......s [ 56%]
........................ssssssssss.......s..............s............... [ 57%]
..................................s..................................... [ 59%]
........................................................................ [ 61%]
..............................................sss....................... [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
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
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 97%]
........................................................................ [ 99%]
...............                                                          [100%]
3859 passed, 118 skipped in 202.34s (0:03:22)
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
INFO    -  Documentation built in 4.32 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review: not closed. Full scripts/check exit 0 and both criteria met, but close-task refuses: a bug needs its repro recorded (record-check TASK-0153 --repro -- <loop test that failed without the fix>). The worker's planted check is described in prose only. No code findings.

Repro at dff00254afd7, test files: bh-02/plugins/agent-cordis-plugin/tests/test_loop.py; command: `uv run pytest bh-02/plugins/agent-cordis-plugin/tests/test_loop.py::test_a_reply_whose_entries_could_not_be_written_is_a_recoverable_failure_with_nothing_after_it bh-02/plugins/agent-cordis-plugin/tests/test_loop.py::test_a_reply_over_a_file_that_is_a_directory_ends_with_the_failure_the_person_is_shown -q -p no:cacheprovider` exited 1

(45 earlier lines omitted)
```text
        `append` the thread had already failed before or at the flush at its end, whichever the thread
        was first to; the file is named and so is the error of the open."""
        path = tmp_path / "transcript.jsonl"
        path.mkdir()
        transcript = FileTranscript(str(path))
        scripted = Scripted([text("hi")], [text("never asked")])
        loop = LoopModel(scripted, as_tool(Shouting()), transcript, Confined())
        with pytest.raises(TranscriptWriteFailed, match="Is a directory") as failed:
>           await _collect(loop, "go")

bh-02/plugins/agent-cordis-plugin/tests/test_loop.py:1422: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
bh-02/plugins/agent-cordis-plugin/tests/test_loop.py:167: in _collect
    return "".join([str(e["text"]) async for e in model.reply(message) if e["type"] == "text"])
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/loop.py:745: in reply
    await self._flushed()
bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/loop.py:755: in _flushed
    await self._transcript.flush()
bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/transcript.py:254: in flush
    await self._appender.flush()
libs/host-paths/src/host_paths/appender.py:132: in flush
    self._raise()
libs/host-paths/src/host_paths/appender.py:171: in _raise
    raise self._failed.error
bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/loop.py:742: in reply
    async for event in events:
bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/loop.py:777: in _reply
    self._transcript.append(_asked(message, dated, aside, at))
bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/transcript.py:229: in append
    self._appender.append(f"{json.dumps(message)}\n".encode())
libs/host-paths/src/host_paths/appender.py:118: in append
    self._raise()
libs/host-paths/src/host_paths/appender.py:171: in _raise
    raise self._failed.error
libs/host-paths/src/host_paths/appender.py:191: in _write
    self._fd = self._hold()
               ^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <host_paths.appender.Appender object at 0x7f149a51ae90>

    def _hold(self) -> int:
        """Open the file, on the calling thread, and make it the one this appender means (the file
        found at the path when it was made, if there was one, else the one opened, made if need
        be).
    
        Raises:
            Replaced: the file opened is not the one found when the appender was made.
        """
>       fd = os.open(self._path, _APPEND | (os.O_EXCL if self._new else 0), _MODE)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       IsADirectoryError: [Errno 21] Is a directory: '/tmp/pytest-of-root/pytest-2615/test_a_reply_over_a_file_that_0/transcript.jsonl'
E       appending to /tmp/pytest-of-root/pytest-2615/test_a_reply_over_a_file_that_0/transcript.jsonl failed: this write and every one queued after it were dropped, so the file ends before them

libs/host-paths/src/host_paths/appender.py:215: IsADirectoryError
=========================== short test summary info ============================
FAILED bh-02/plugins/agent-cordis-plugin/tests/test_loop.py::test_a_reply_whose_entries_could_not_be_written_is_a_recoverable_failure_with_nothing_after_it
FAILED bh-02/plugins/agent-cordis-plugin/tests/test_loop.py::test_a_reply_over_a_file_that_is_a_directory_ends_with_the_failure_the_person_is_shown
2 failed in 0.39s
```

Review round 1 (blocking: no repro recorded). Fixed by recording it, no code or test changed (git diff dff0025 over bh-02/ and libs/ is empty). With the 'except OSError' branch of FileTranscript._refusing planted out (replaced by 'except ZeroDivisionError', source edited and uncommitted, test files clean), ran record-check TASK-0153 --repro -- uv run pytest test_loop.py::<the reply whose entries could not be written> test_loop.py::<the reply over a file that is a directory>: both FAILED (bare NotADirectoryError / IsADirectoryError, not Recoverable), exit 1, recorded above at dff00254afd7 (the commit this round started from, still an ancestor of the squashed commit, so close-task can diff the test file against it). The source was then restored with git checkout; the tree held only the task file as the auto-commit. With the guard restored: uv run pytest test_loop.py test_agent_transcript.py test_agent_conversation.py: 119 passed, 1 skipped (the existing /dev/full skip), exit 0. board-check close TASK-0153: 'ok: TASK-0153 can close'. The TUI nit (no test drives the TUI to show the notice) stands, as the reviewer left it. scripts/check not re-run: no code changed since its exit 0 above.

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
....................................s......s..ssss..s.s.s..s.ss.s.s..ss. [ 48%]
s.s.s.s.s..sssss.s.........s............................................ [ 50%]
........................................................................ [ 52%]
......................................................................ss [ 54%]
sssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss....... [ 56%]
.......................sssssssssss....s................................. [ 57%]
........................................................................ [ 59%]
........................................................................ [ 61%]
.............................................sss........................ [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
...................................s.................................... [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 97%]
........................................................................ [ 99%]
...............                                                          [100%]
3859 passed, 118 skipped in 201.21s (0:03:21)
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
INFO    -  Documentation built in 4.16 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
