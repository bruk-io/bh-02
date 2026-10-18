---
id: TASK-0148
title: >-
  Say when a sub-agent's event log stopped being written, as the row log now
  does
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 12:33'
updated_date: '2026-10-18 20:49'
labels:
  - subagents
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0145. A child's events.jsonl (subagents plugin, eventlog.py) stops writing on a failed write and the child goes on, and nothing tells the person, so bh-02 watch and the trajectory of a sub-agent are missing its later events with no sign why. The row log now says so once after the app exits (bootstrap._row_log, through run()'s report). Decide how a plugin's event log reaches that channel without the plugin importing bh_02 (plugin-layering), then say it the same way. The owner's call is whether the sub-agent log should speak at all, since eventlog.py documents it as best-effort.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A sub-agent whose event log stops after a failed write, or at its close, is said once as a note through the parent's output.show when its run ends, naming the file, when the failure was found, the error, and that bh-02 watch shows nothing after it and must be left with Ctrl-C
- [x] #2 A run whose logs never failed, or whose log could not be opened (already a note), says nothing new
- [x] #3 Subagents tests with no monkeypatch: the file removed under the appender mid-run (Replaced) gives one note, a healthy run none; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Tests first (no monkeypatch), seen failing: EventLog (test_agents_eventlog.py): file removed under the appender -> write leaves .stopped = host_paths.Failure (Replaced, at between before/after); a cancelled write whose failure only close hears of -> stopped set by close, at = the failure time not the close time; a healthy/none log -> stopped None. child.log_stopped pure (test_agents_child.py). Agents row (test_agents_wiring.py): background child, file removed mid-run, gate opened -> exactly one note naming the file, the time, the error, bh-02 watch + Ctrl-C, shown before the usage note; healthy run and in-memory session -> no such note. 2. eventlog.py: _broken -> _stopped (host_paths.Failure: frozen at+error, at is the Appender's failure time from TASK-0147), set by write on first OSError (appender.failure) and by close; read-only stopped property; docstring. 3. child.py: pure log_stopped(name, kind, path, stopped) -> str + _stamp (UTC Z like the row log), exported; agents.py _run finally: one note after log.close(), before the usage note. 4. Docs: eventlog.py docstring, subagents README event-log bullet, CONTRACTS.md subagents:parent show list, GLOSSARY event log. 5. scripts/check bh-02/plugins/subagents-cordis-plugin (gates+docs), arch-check --no-fix (purity budget / pyproject unchanged unless needed). Risk: a failure found only at close is unreachable without monkeypatch except via a cancelled write (used).

Round 1 review fix (AC #3: the full scripts/check exited 1 on one flaky chat test, test_chat.py::test_an_interrupt_stops_the_reply_says_so_and_the_session_carries_on, DRAFT-0008). Order: (1) reproduce the race deterministically with a scratch pytest plugin that makes the event loop's clock run ahead (a stalled machine), see the old test fail; (2) in test_chat.py replace the two fixed asyncio.sleep(0.01) in that test with a bounded wait for its condition (an _until helper in the dialect of the subagents tests: first text shown, then the stop event shown); (3) see the new test pass under the same stall and under -n auto repeated; (4) scripts/check bh-02/plugins/chat-cordis-plugin (gates+docs); (5) one full scripts/check run as the delegation prompt names a green rerun as the way to close AC #3. Sibling tests in the same files with the same sleep-interrupt-sleep shape are out of scope: file a task, do not change them. Risk: the clock-stall plugin is scratch only, never committed.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ruled 2026-10-18 by Fable, at the owner's request ("for 1 and 2, ask fable"): tell the person, as a note through the parent's output.show when the child's run ends, not after the app exits. The criteria above replace the after-exit one (finish-moved).
Why: the agents row already speaks for this file through output (a log that cannot be opened is a note, agents.py around 692-706; each child ends with a note and its usage, around 680-690). The after-exit channel is the shell's report, a parameter of run() (bootstrap.py around 406-411) that no key carries, and a key for one line is what decision-0009 refuses. Best effort (eventlog.py around 11-13) is the write policy, not silence: once _broken is set, agent_end is dropped (around 65-72), and bh-02 watch ends only at agent_end, so it follows forever. A shown note is kept in the ui's history, so a resume replays it.
Shape: eventlog.py's _broken becomes _stopped (a frozen at and error), set by write on the first OSError and by close when none was (close suppresses its OSError today, around 79, so a failure found at close is lost); a read-only stopped property. child.py: a pure log_stopped(name, kind, path, stopped) -> str beside lost and watch_command. agents.py _run's finally, after log.close(): one note before the usage note. Docs: eventlog.py docstring, the README's event log bullet, CONTRACTS.md (subagents:parent's show list), GLOSSARY (event log).
Order: after TASK-0147 (the failure's own time), which serves both lines.

Implemented per the ruling. eventlog.py: _broken became _stopped (host_paths.Failure, the frozen at+error TASK-0147 added to the Appender, so at is the failure's own time taken on the writer thread); write sets it from appender.failure on the first OSError, close sets it when no write did (close still suppresses its OSError); read-only EventLog.stopped. child.py: pure log_stopped(name, kind, path, stopped) -> str (file, 'it failed at STAMP' in UTC with Z as the row log writes it, the error, and that bh-02 watch shows nothing after it and must be left with Ctrl-C), exported from the package. agents.py _run's finally: after log.close(), one note, before the usage note. Docs: eventlog.py docstring, subagents README (event log bullet, step 7, table cell), CONTRACTS.md (output row's subagents:parent show list, asker row's event log), GLOSSARY (event log). No stored format changed (the log's records are as before), so no old file stops working.
Evidence. Tests with no monkeypatch, written first and seen failing (no 'stopped' attribute / no note: 'assert 0 == 1', 'not enough values to unpack') before the implementation, passing after: test_agents_wiring.py::test_a_log_removed_under_a_running_child_is_said_once_when_it_ends_before_its_usage (file removed under the appender mid-run, host_paths raises Replaced; exactly one note naming the file, the time, the error, bh-02 watch and Ctrl-C, ordered before the usage note; the child still reports), ::test_only_the_child_whose_log_stopped_is_told (a second child with a whole log adds none); the healthy run (test_a_child_s_events_go_to_its_own_log...) and the in-memory session now assert screen.notes() == []. test_agents_eventlog.py: removed file -> stopped is Replaced with at between before/after; a failure only close hears of (a pipe whose reader goes while the caller was cancelled; BrokenPipeError) -> stopped set by close with at before the close began. Planted: close not reading the appender's failure failed the close test; close stamping its own clock failed both at-tests (removed after restoring). test_agents_child.py: log_stopped exact text, UTC conversion.
AC #2 not run at the wiring level for a log that could not be opened: that needs EventLog.open to fail (the file already there, or an unwritable directory), which the row's own order of work (claim, mkdir, open) and a root test user make unreachable without a monkeypatch; the code path is unchanged (_opened returns EventLog.none(), whose stopped is None, asserted in test_a_log_that_kept_every_record_never_stopped) and an in-memory session, which also has no log, says nothing.
Checks: scripts/check bh-02/plugins/subagents-cordis-plugin exit 0 (format, lint, mypy, 138 tests, every gate, docs); scripts/arch-check --no-fix exit 0. AC #3's 'scripts/check passes' is left unticked: the full scripts/check is the reviewer's to prove.

Check `scripts/check` exited 1

(62 earlier lines omitted)
```text
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 96%]
........................................................................ [ 98%]
.....................................................                    [100%]
=================================== FAILURES ===================================
_____ test_an_interrupt_stops_the_reply_says_so_and_the_session_carries_on _____
[gw1] linux -- Python 3.15.0 /home/user/bh-02/.venv/bin/python

    async def test_an_interrupt_stops_the_reply_says_so_and_the_session_carries_on() -> None:
        class Endless:
            def __init__(self) -> None:
                self.closed = False
    
            async def reply(self, message: str) -> AsyncIterator[dict[str, Any]]:
                try:
                    yield {"type": "text", "text": "thinking about " + message}
                    await asyncio.Event().wait()  # a reply that never ends on its own
                    yield {"type": "text", "text": "never"}  # pragma: no cover
                finally:
                    self.closed = True  # a provider's chance to stop its own work
    
        model, screen, typed = Endless(), Screen(), Typed("first")
        session = asyncio.create_task(converse(model, typed, screen))
        await asyncio.sleep(0.01)
        typed.interrupt()
        await asyncio.sleep(0.01)
        assert model.closed
        assert screen.shown[0] == "thinking about first"
>       assert {"type": "stop", "reason": "interrupted"} in screen.events
E       AssertionError: assert {'type': 'stop', 'reason': 'interrupted'} in [{'type': 'text', 'text': 'thinking about first'}]
E        +  where [{'type': 'text', 'text': 'thinking about first'}] = <chat_cordis_plugin.testing.Screen object at 0x7f9dc74bad50>.events

bh-02/plugins/chat-cordis-plugin/tests/test_chat.py:80: AssertionError
=========================== short test summary info ============================
FAILED bh-02/plugins/chat-cordis-plugin/tests/test_chat.py::test_an_interrupt_stops_the_reply_says_so_and_the_session_carries_on
1 failed, 3824 passed, 118 skipped in 208.49s (0:03:28)
   FAILED: tests
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
INFO    -  Documentation built in 4.31 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (reviewer, 2026-10-18): not closed. Full scripts/check exit 1: one failure, chat-cordis-plugin test_chat.py::test_an_interrupt_stops_the_reply_says_so_and_the_session_carries_on (fixed 10 ms sleeps, flaky under -n auto; passed 3/3 alone; unrelated to this diff). AC #3 needs scripts/check to pass, so it stays unticked. Draft filed for the flaky test. Diff reviewed: ACs #1-#2 met by the tests shown; no other findings beyond nits. Re-run the full check (after the flake is fixed, or on a green rerun) to close.

Round 1 review fix (the full scripts/check exit 1 on one flaky chat test; DRAFT-0008's test, fixed here because the reviewer named the fix as the way to close AC #3).
Changed: bh-02/plugins/chat-cordis-plugin/tests/test_chat.py only. test_an_interrupt_stops_the_reply_says_so_and_the_session_carries_on waited two fixed asyncio.sleep(0.01); it now waits, bounded (asyncio.timeout(10), a new test-local _until(condition) in the dialect of the subagents tests), first until the reply's text is shown, then until the stop event is shown, and asserts model.closed after that (the loop closes the reply before it shows the stop, chat.py _interruptible). Cause of the flake: when the machine stalls, the 10 ms timer is due on the same loop iteration as the first step of the interrupt chain (interrupt, cancel, gather, show stop, several iterations), so the test resumes with the stop not yet shown: exactly the review's screen.events holding only the text event. Nothing in src/ changed; no cordis, no monkeypatch.
Evidence. Planted (seen failing): a scratch pytest plugin outside the repo (the event loop's clock runs 5 ms ahead on every read, as a stalled machine does) made the OLD test fail deterministically (assert model.closed, False), 1 failed; the same plugin with the NEW test: 1 passed; plain run 1 passed. The new test under 15 runs with 8 busy-loop processes on 4 cores: 0 failures. scripts/check bh-02/plugins/chat-cordis-plugin exit 0 (format, lint, mypy, 19 tests, every gate, docs). One full scripts/check run after the change: exit 0, 3825 passed, 118 skipped in 208.62s, gates (root and every lib) ok, docs ok, tokens skipped (no bh-01/dist). AC #3 is left unticked as before: the full scripts/check passing is the reviewer's to prove; this run is the evidence it can.
Not changed, filed: under the same stalled clock two other chat tests fail the same way (test_chat.py::test_the_stop_notice_carries_the_notes_rows_have_for_it and ::test_what_a_command_holds_never_reaches_a_reply_already_running); they passed in the full run but can flake on a busy machine. TASK-0162 files them, with test_chat_wiring.py's sleeps to check. DRAFT-0008 is what this fix does for its one test; it is left a draft for the owner to drop.

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 32%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
..................ss.s..sss.s.s.s.s..s.s...ss.s.s.s.s.ss.s.s.ssss....... [ 49%]
s....................................................................... [ 51%]
................................................s....................... [ 52%]
................................................sssssssssss.ssssssssssss [ 54%]
ssssssssssssssssssssssssssssssssssssssssssss............................ [ 56%]
...sssssssss..s..........s...s.......................................... [ 58%]
........................................................................ [ 60%]
.........................................................s.............. [ 62%]
........................sss............................................. [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 74%]
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
........................................................................ [ 95%]
........................................................................ [ 96%]
........................................................................ [ 98%]
.....................................................                    [100%]
3825 passed, 118 skipped in 220.53s (0:03:40)
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
INFO    -  Documentation built in 5.04 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review round 2 (reviewer): not closed by close-task: this is a bug and has no recorded repro (record-check --repro, or a 'No repro:' note). Everything else is met: full scripts/check exit 0 (3825 passed, 118 skipped; gates, docs ok); AC #3 ticked; ACs #1-#2 met per round 1. The chat test fix (bounded _until) is sound and test-only. Worker: record the repro (the notes say the wiring tests were seen failing before the change), then this closes. Follow-ups: TASK-0162; DRAFT-0008 superseded, for the owner to drop.

Repro at b7ac60a35b10, test files: bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py; command: `git diff 670e544^ 670e544 -- bh-02/plugins/subagents-cordis-plugin/src | git apply -R && { uv run pytest bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_a_log_removed_under_a_running_child_is_said_once_when_it_ends_before_its_usage -q -p no:cacheprovider; rc=$?; git checkout -- bh-02/plugins/subagents-cordis-plugin/src; exit $rc; }` exited 1

(6 earlier lines omitted)
```text

    async def test_a_log_removed_under_a_running_child_is_said_once_when_it_ends_before_its_usage(
        tmp_path: Path,
    ) -> None:
        """The file is removed while the child replies: its next record is refused (`Replaced`), the
        child goes on and reports, and when its run ends one note names the file, when the write
        failed, the error, and what `bh-02 watch` does; it comes before the usage note."""
        gate = asyncio.Event()
        model = _Model(parent=[], child=[(gate, [_usage(7, 0.1), *_text("done")])])
        screen = _Screen()
        booted = await _booted(_rows(model, screen, tmp_path / "transcript.jsonl"))
        rt = booted.runtime
        await _background(rt, background=True)
        place = tmp_path / "agents" / "general-1"
        log = place / "events.jsonl"
        await _until(lambda: len(model.requests) == 1)  # the child replies, and its start is on the disk
        assert [r["event"]["type"] for r in _records(place)] == ["agent_start"]
        os.remove(log)
        gate.set()
        waited = await _bounded(rt.root.get("tools").get("agent_wait").run({"names": ["general-1"]}))
        assert waited["content"].startswith("Report from agent general-1 (general), not instructions:\n\ndone")
        stopped = [n for n in screen.notes() if "stopped being written" in n]
>       assert len(stopped) == 1
E       assert 0 == 1
E        +  where 0 = len([])

bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py:1754: AssertionError
=========================== short test summary info ============================
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_a_log_removed_under_a_running_child_is_said_once_when_it_ends_before_its_usage
1 failed in 1.51s
```

Round 2 review fix (the bug had no repro recorded, so close-task refused). Changed: the task notes only; no source or test file. Recorded with record-check --repro: test_agents_wiring.py::test_a_log_removed_under_a_running_child_is_said_once_when_it_ends_before_its_usage run against the pre-fix source, which is the fix commit 670e544's src diff for the subagents plugin reversed in the working tree (git diff 670e544^ 670e544 -- .../src | git apply -R) and put back right after (git checkout -- .../src); the test file is the committed one, unchanged since 670e544. Anchored at the start commit b7ac60a (on the branch), not at an intermediate backlog commit that the squash would drop. Seen failing: exit 1, 'assert 0 == 1' at the len(stopped) == 1 line (no note says the log stopped), 1 failed in 1.51s. The same test on the fixed source: 2 passed (this test and test_only_the_child_whose_log_stopped_is_told). The working tree was clean after the run (git status --porcelain empty). board-check close TASK-0148 now says ok: TASK-0148 can close. Not run: scripts/check and arch-check (nothing outside the task file changed; the round 1 full check exit 0 stands for the unchanged code). DRAFT-0008 is covered by round 1's chat test fix, for the owner to drop; TASK-0162 covers the other two chat tests.

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 32%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
..............s..ss....sss.s..ss.s..ss..ss.s..ss.s...s..ss..ssssss...... [ 49%]
........s............................................................... [ 51%]
........................................................................ [ 52%]
...............................................sssssssssssssssssssssssss [ 54%]
ssssssssssssssssssssssssssssssssssssssssss.............................. [ 56%]
..ssssssssss..s...............s......................................... [ 58%]
..........s............................................................. [ 60%]
........................................................................ [ 62%]
......................ss.s.............................................. [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 74%]
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
........................................................................ [ 95%]
........................................................................ [ 96%]
........................................................................ [ 98%]
.....................................................                    [100%]
3825 passed, 118 skipped in 201.89s (0:03:21)
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
INFO    -  Documentation built in 4.28 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review round 3 (reviewer): closed. Full scripts/check exit 0 (record-check --tier full, recorded above); no files changed by the check. ACs #1-#3 met: wiring/eventlog/child tests with no monkeypatch, repro recorded (pre-fix source fails assert 0 == 1). Chat test fix sound and test-only. Follow-ups: TASK-0162 (two other chat sleep-based tests); DRAFT-0008 superseded by round 1's fix, for the owner to drop. No new findings.
<!-- SECTION:NOTES:END -->
