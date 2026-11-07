---
id: TASK-0132
title: >-
  Save and delete auto memories under a lock, so two sessions never lose a
  MEMORY.md line
status: Done
assignee:
  - '@claude'
created_date: '2026-10-17 14:00'
updated_date: '2026-11-07 07:16'
labels:
  - memory
  - size-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0068 (2026-10-17). The memory tool's save and delete read MEMORY.md, change their own line and write it back by a temporary file renamed over it (memory_cordis_plugin/directory.py, host_paths.write_beneath). The rename keeps a reader from seeing a torn file, but two sessions on one project (or two worktrees) saving at once both read the old index, and the last rename wins: the other's line is lost until that memory is saved again. Owner, 2026-10-17: use the platform's file lock. flock is advisory, which is enough here since every writer that matters is bh-02's own tool (a write the model makes through Python is not checked, the owner's earlier call). Lock the memory directory, opened through no link with host_paths.directory_beneath, not MEMORY.md, which the rename replaces; the lock goes with the descriptor, so a crashed session holds nothing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A save and a delete hold an exclusive flock on the memory directory (opened through no link) for the whole read, change and write of MEMORY.md
- [x] #2 Two saves of different memories started at once, from two processes, both have their line in MEMORY.md afterwards; the test is seen failing without the lock
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Fix round after review: record the pre-fix repro via record-check --repro instead of prose. 1) Save fixed directory.py aside, restore pre-fix version via 'git show 8bed0533~1:...directory.py' into the working tree only (test file stays committed/clean). 2) Run testlock record-check TASK-0132 --repro -- uv run pytest '...test_two_saves_started_at_once_from_two_processes_both_keep_their_line' -q; confirm it fails and is appended to notes. 3) git checkout the fixed directory.py back, confirm git status shows no code diff. 4) Append notes summarizing, leave ACs as already ticked (unchanged), do not touch anything else. Risk: record-check requires the test file itself be clean in git status, which it is since only directory.py is swapped.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented. bh-02/plugins/memory-cordis-plugin/src/memory_cordis_plugin/directory.py: new private _locked(directory) contextmanager opens the memory directory through no link (host_paths.directory_beneath(directory, [])) and takes an exclusive fcntl.flock(at, LOCK_EX) on its descriptor; _saved and _deleted now run their whole read of MEMORY.md, their write of the topic file, and their write/removal in MEMORY.md inside with _locked(directory) as at:, passing at (the locked fd) as the root to _index/write_beneath/remove_beneath instead of the Path, so the lock covers the whole read-change-write. _index simplified to take the fd (directory existence is already proven by the open succeeding). The lock is released when directory_beneath closes the descriptor on leaving the with block (normal return or exception), so a crashed session holds nothing. _read is untouched (unaffected by the race: rename already makes it atomic). Updated the module docstring and README.md's auto-memory bullet list to describe the lock.

Evidence for AC#1: see directory.py's _locked/_saved/_deleted; _saved and _deleted each wrap their entire body in 'with _locked(directory) as at:' before any read, write or removal of MEMORY.md or the topic file.

Evidence for AC#2, with the planted failure: added test_two_saves_started_at_once_from_two_processes_both_keep_their_line in tests/test_memory_directory.py. It starts two real subprocess.Popen children against one memory directory, each importing memory_cordis_plugin.keep, printing 'ready', then busy-polling for a shared go-file before calling Save with a distinct name; the parent waits for both 'ready' lines, then touches the go file once, so both children reach the save at nearly the same instant. Looped 5 times with fresh names each round.

Checked out the pre-fix directory.py (git show HEAD:...) and re-ran: FAILED, e.g. 'round 0: race-b-0's line is missing: ...MEMORY.md held only race-a-0's line, race-b-0's write was clobbered by the later rename' (AssertionError: assert '(race-b-0.md)' in '- [race-a-0](race-a-0.md): line for race-a-0\n'). Restored the fixed directory.py and re-ran: PASSED (1 passed). A standalone 10-trial version of the same race (scratchpad script) also showed 10/10 failures before the lock and 0/10 after.

Commands run: uv sync --all-packages (ok); testlock uv run pytest bh-02/plugins/memory-cordis-plugin -q -> 150 passed; uv run mypy -> Success: no issues found in 208 source files; uv run ruff check . -> All checks passed; uv run ruff format --check . -> 851 files already formatted; testlock scripts/check bh-02/plugins/memory-cordis-plugin -> format/lint/types/tests/gates/docs all ok (150 passed). scripts/check (whole repo) was not run -- left for the reviewer per standing rules. scripts/arch-check was not run separately since nothing outside this one member changed; the member's own gate ran clean as part of scripts/check.

Follow-up fix found by review: _deleted's second write_beneath (the index rewrite after remove_beneath) had lost its own except OSError branch when the lock was added, so a failure there (e.g. ENOSPC) fell through to the outer handler and wrongly reported 'bh-02 did not delete the memory' even though the topic file was already removed. Restored the original two-phase handling (distinct 'deleted, but MEMORY.md could not be updated' message) inside the lock, matching _saved's shape; moved the _unknown(name) early return back inside the with block too. Verified by monkeypatching write_beneath to raise only for MEMORY.md after a real delete: before the fix it said 'bh-02 did not delete the memory', after the fix it correctly says 'the memory was deleted, but MEMORY.md could not be updated, so its line is still there: ...'. Also hardened the new race test (test_two_saves_started_at_once_from_two_processes_both_keep_their_line) with a try/finally that always touches the go file and kills any still-running child, so a failed assertion never leaves a busy-polling process behind. Re-ran after these changes: testlock uv run pytest bh-02/plugins/memory-cordis-plugin -q -> 150 passed; uv run mypy -> no issues (208 files); uv run ruff check/format -> clean; testlock scripts/check bh-02/plugins/memory-cordis-plugin -> format/lint/types/tests/gates/docs all ok.

Check `scripts/check` exited 1

(128 earlier lines omitted)
```text
E         Use -v to get more diff

bh-02/app/tests/test_python_repl.py:980: AssertionError
___ test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts ___
[gw6] darwin -- Python 3.15.0 /Users/brukhabtu/Documents/src/github.com/bruk-io/bh-02/.venv/bin/python

    async def test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts() -> None:
        """The defaults, undriven: about once a second, so nothing for the first moments, then
        the seconds."""
        app = BhApp()
        async with app.run_test(size=_SIZE) as pilot:
            app.post_message(ReplyStarted())
            await pilot.pause(0.4)
            assert _line(app) is None
            await _until(pilot, lambda: _line(app) is not None, within=3.0)
            assert re.fullmatch(r"Working · [12]s", _line(app) or "")
>           await _until(pilot, lambda: _line(app) == "Working · 2s", within=3.0)

bh-02/plugins/tui-cordis-plugin/tests/test_tui_working.py:320: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

pilot = <Pilot app=BhApp(title='bh-02', classes={'-dark-mode', '-theme-bh-01-dark'}, pseudo_classes={'focus', 'dark'})>
done = <function test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts.<locals>.<lambda> at 0x111971f30>
within = 3.0

    async def _until(pilot: Pilot[None], done: Callable[[], bool], *, within: float = 3.0) -> None:
        """Let the app run until `done()`, polling in short pauses."""
        for _ in range(round(within / 0.02)):
            if done():
                return
            await pilot.pause(0.02)
>       raise AssertionError("what the test waited for never happened")
E       AssertionError: what the test waited for never happened

bh-02/plugins/tui-cordis-plugin/tests/test_tui_working.py:59: AssertionError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_python_repl.py::test_a_session_run_from_home_can_t_choose_what_a_later_session_reads_as_the_person_s@jail-lock
FAILED bh-02/plugins/tui-cordis-plugin/tests/test_tui_working.py::test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts
2 failed, 3852 passed, 231 skipped in 71.00s (0:01:10)
   FAILED: tests
== gates
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
INFO    -  Building documentation to directory: /Users/brukhabtu/src/github.com/bruk-io/bh-02/site
INFO    -  Documentation built in 1.28 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```

Review (reviewer agent): not closed. Both criteria are met and ticked: _saved/_deleted hold an exclusive flock on the directory_beneath descriptor for the whole read-change-write, and the two-subprocess race test is recorded failing pre-fix and passing after. Full check: format, lint, types, gates, docs ok; tests 2 failed of 3854, neither in this member (test_python_repl later_session_reads_as_the_person_s is the known darwin hole TASK-0197; test_tui_working real-clock test passed alone, a load flake). Blocking: close-task refuses a bug without a recorded repro. The pre-fix failure is described in prose only; the worker should record it with record-check TASK-0132 --repro -- uv run pytest 'bh-02/plugins/memory-cordis-plugin/tests/test_memory_directory.py::test_two_saves_started_at_once_from_two_processes_both_keep_their_line' -q against the pre-fix directory.py (git show 8bed0533~1:...), then restore and hand back for close. The reviewer cannot change files to do it.

Owner stand-in (Opus), 2026-11-06: Approved as the reviewer proposes, no waiver. The close-task rule that a bug needs a recorded repro stays; prose in the notes doesn't count. Send TASK-0132 back to its worker to record the repro: put the pre-fix directory.py (git show 8bed0533~1:bh-02/plugins/memory-cordis-plugin/src/memory_cordis_plugin/directory.py) in the working tree only, run record-check TASK-0132 --repro -- uv run pytest 'bh-02/plugins/memory-cordis-plugin/tests/test_memory_directory.py::test_two_saves_started_at_once_from_two_processes_both_keep_their_line' -q, then restore the fixed file with git checkout, confirm git status shows no code change, and hand it back for review. That revert is local and temporary, the old code is never committed, and it's the smallest step that satisfies the gate. The two failures in the full check don't block this task. test_python_repl is TASK-0197. The test_tui_working real-clock failure is a load flake outside this member; if it shows up again, file it as its own bug rather than holding this task.

Repro at 6a91269bce42, test files: bh-02/plugins/memory-cordis-plugin/tests/test_memory_directory.py; command: `uv run pytest bh-02/plugins/memory-cordis-plugin/tests/test_memory_directory.py::test_two_saves_started_at_once_from_two_processes_both_keep_their_line -q` exited 1

```text
F                                                                        [100%]
=================================== FAILURES ===================================
____ test_two_saves_started_at_once_from_two_processes_both_keep_their_line ____

memory = PosixPath('/private/var/folders/rf/f34xmczn4659gm98hrsprydc0000gn/T/pytest-of-brukhabtu/pytest-999/test_two_saves_started_at_once0/state/memory')
tmp_path = PosixPath('/private/var/folders/rf/f34xmczn4659gm98hrsprydc0000gn/T/pytest-of-brukhabtu/pytest-999/test_two_saves_started_at_once0')

    def test_two_saves_started_at_once_from_two_processes_both_keep_their_line(
        memory: Path, tmp_path: Path
    ) -> None:
        """Two processes (two sessions on the same project, or two worktrees) saving different
        memories at the same moment: the lock on the directory serialises their read, change and
        write of MEMORY.md, so neither save's line is lost to the other's rename. Seen failing
        without the lock on `_saved` (`host_paths.directory_beneath`/`fcntl.flock` taken out):
        MEMORY.md held only the line of whichever process's rename landed last."""
        for round_ in range(5):
            go = tmp_path / f"go-{round_}"
            names = [f"race-a-{round_}", f"race-b-{round_}"]
            processes: list[subprocess.Popen[str]] = []
            try:
                for name in names:
                    processes.append(_racing_save(memory, name, go))
                go.touch()
                for started in processes:
                    assert started.wait(timeout=10) == 0
                    assert started.stdout is not None and started.stdout.readline().startswith("saved")
            finally:
                go.touch()  # unblock a child still polling, even when a sibling or an assert failed
                for started in processes:
                    if started.poll() is None:
                        started.kill()
            index = (memory / "MEMORY.md").read_text()
            for name in names:
>               assert f"({name}.md)" in index, f"round {round_}: {name!r}'s line is missing: {index!r}"
E               AssertionError: round 0: 'race-a-0''s line is missing: '- [race-b-0](race-b-0.md): line for race-b-0\n'
E               assert '(race-a-0.md)' in '- [race-b-0](race-b-0.md): line for race-b-0\n'

bh-02/plugins/memory-cordis-plugin/tests/test_memory_directory.py:285: AssertionError
=========================== short test summary info ============================
FAILED bh-02/plugins/memory-cordis-plugin/tests/test_memory_directory.py::test_two_saves_started_at_once_from_two_processes_both_keep_their_line
1 failed in 0.75s
```

Fix round after review (blocking finding: close-task needs a recorded repro, not prose). Restored the pre-fix directory.py (git show 8bed0533~1:bh-02/plugins/memory-cordis-plugin/src/memory_cordis_plugin/directory.py) into the working tree only (test file left untouched/clean), then ran testlock python3 record-check TASK-0132 --repro -- uv run pytest 'bh-02/plugins/memory-cordis-plugin/tests/test_memory_directory.py::test_two_saves_started_at_once_from_two_processes_both_keep_their_line' -q: the command failed (1 failed) as recorded above ('Repro at 6a91269bce42...exited 1'), and record-check itself exited 0, confirming the failure was recorded. Then ran 'git checkout -- bh-02/plugins/memory-cordis-plugin/src/memory_cordis_plugin/directory.py' and confirmed 'git status --porcelain' and 'git diff --stat HEAD -- <file>' were both empty, so the fixed code is unchanged and the old code was never committed. No code or test files were edited in this round; sending back for review/close.

Review (reviewer agent): closed. Both criteria met and ticked: _saved/_deleted hold an exclusive flock on the directory descriptor across read-change-write, and the two-process race test is recorded failing against the pre-fix directory.py (repro at 6a91269bce42, record-check exit 1) and passing after. No source changed since the full check recorded last round (only the task file), so that check stands: format, lint, types, gates, docs ok; the two test failures are outside this member (TASK-0197 darwin hole; test_tui_working real-clock load flake, which per the owner stand-in gets its own bug only if it recurs). The blocking finding (repro only in prose) is resolved. No drafts filed.
<!-- SECTION:NOTES:END -->
