---
id: TASK-0143
title: Two bh-02 processes can't write one session at once
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:15'
updated_date: '2026-10-18 14:18'
labels:
  - app
  - size-3
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Record-a-sessions-trajectory-as-timing-on-the-transcripts-entries-and-read-it-with-bh-02-trajectory.md
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found designing TASK-0136 (noted there, filed at the owner's word 2026-10-18). Nothing stops bh-02 --resume ID while another bh-02 still runs that session: both append to its transcript, rows.jsonl and the ui's history, interleaving two conversations in one file. The shell should hold the session for the run and refuse a second.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A running bh-02 holds its session directory exclusively (an advisory lock on a file in it, held for the run and released however the run ends, including a crash)
- [x] #2 bh-02 --resume of a session another process holds refuses before any row starts, with an error naming the session and the process that holds it and what to do; a test runs two and sees the second refused
- [x] #3 bh-02 sessions, bh-02 trajectory and bh-02 watch read a held session as before (they take no lock); scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order: (1) sessions.py: a pure-ish 'held' context manager that opens '<session dir>/running.lock' (O_RDWR|O_CREAT, 0600, non-inheritable), takes fcntl.flock(LOCK_EX|LOCK_NB), then writes this pid; on BlockingIOError reads the pid and raises Held(message: names the session and the process, says to leave the other bh-02 first). The kernel drops the flock with the process, so a crash releases it. (2) cli.py: main holds it in an ExitStack from before the session's layer is read or rewritten (resume) and right after create (new), through _run; refused as 'error: ...' exit 1 before any row starts; farewell/discard after release. sessions/trajectory/watch never import held. (3) Tests: a holder in another process (subprocess, the real flock) -> bh-02 --resume refused, session untouched, no row started; holder SIGKILLed -> resume works (crash releases); sessions/trajectory/watch read a held session; unit tests of held (second refused, released at exit of the with, pid named). Plant: remove the flock call and see the refusal test fail. (4) Docs: sessions.md, command-line.md, GLOSSARY, app README, sessions.py docstring; root pyproject impure budget entry for sessions:held. Proof: uv run pytest on app tests incl. test_real_launch, scripts/check bh-02/app, scripts/arch-check --no-fix.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: bh-02/app/src/bh_02/sessions.py (Held, held(): O_RDWR|O_CREAT 0600 running.lock in the session dir, fcntl.flock LOCK_EX|LOCK_NB, then the pid written; Held names the pid and says to leave the other bh-02 first; the pid-less fallback covers the window between locking and writing), cli.py (main holds the session in an ExitStack through _run; _session takes it for a new session right after create and for a resume BEFORE its layer is read or --model rewrites it; Held is printed as 'error: ...' exit 1; discard and the farewell run after release), root pyproject (impure budget: sessions:held), tests (new bh-02/app/tests/test_session_lock.py, one real-launch test in test_real_launch.py), docs (sessions.md, command-line.md, GLOSSARY, app README). sessions/trajectory/watch never import held. Evidence: AC1 - test_session_lock.py: held twice in one process is refused, free after the block; a holder process SIGKILLed with a child still alive leaves the session resumable (OS release, fd not inherited); the real-launch test kills a running bh-02 with SIGKILL and the next --resume comes up. AC2 - a holder in another process: bh-02 --resume ID --model claude/haiku --trace F exits 1 with 'error: session ID is held by bh-02 process PID ... Leave that bh-02 first', F never created (no row started), session.toml unchanged, no farewell, the session still listed; the real-launch test (first bh-02 running in a pty, second --resume refused naming its pid, nothing drawn). PLANTED: with the fcntl.flock call replaced by pass, 4 of the 5 lock tests fail (the fifth only checks the file), and the real run's exit_code is 0 instead of 1; with the hold moved after set_model in _session, the 'session.toml unchanged' assertion fails (layer rewritten). Both restored. AC3 - test_sessions_trajectory_and_watch_read_a_held_session_as_before: sessions, trajectory ID and watch ID NAME --once all exit 0 with their output while another process holds it, and the lock file still names the holder afterwards. Ran: uv run pytest bh-02/app/tests/test_session_lock.py (5 passed); test_real_launch.py::test_a_running_bh_02_holds... passed; scripts/check bh-02/app (with gates and docs): format, lint, types, tests 336 passed 1 skipped (bwrap), all five gates, docs build ok (tokens skipped: no bh-01). Left for the reviewer: the 'scripts/check passes' half of AC3, so #3 is unticked.

Correction to the evidence above: the planted violation (flock replaced by pass) was run against test_session_lock.py only, where the CLI refusal test failed with exit_code 0 != 1; the real-launch test was run unplanted (passed) and not seen failing. scripts/arch-check --no-fix also run after the root pyproject change: all five gates ok.

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
....s.s..ssss.s.ss..ss....s..ss..s..ss..ss..ss.s..sssss................. [ 49%]
........................................................................ [ 51%]
..........................................s............................. [ 53%]
.......................................s.sssssssssssssssssssssssssssssss [ 54%]
sssssssssssssssssssssssssssssssssss........................ssssssssssss. [ 56%]
......................................................................s. [ 58%]
........................................................................ [ 60%]
........................................................................ [ 62%]
..........sss........................................................... [ 64%]
........................................................................ [ 65%]
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
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 98%]
........................................                                 [100%]
3812 passed, 118 skipped in 199.16s (0:03:19)
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

Review (not the worker): every criterion met (AC3 ticked: full scripts/check exit 0, 3812 passed, gates and docs ok). Not closed: close-task refuses a bug without a recorded repro. The worker should record one from the pre-fix tree (e.g. at d30ae9c, record-check TASK-0143 --repro -- uv run pytest bh-02/app/tests/test_session_lock.py::test_resume_of_a_session_another_process_holds_is_refused_before_any_row_starts), or add a 'No repro:' note saying why; then it closes as is. Nits: running.lock opened with os.open, not host_paths' no-link opener (no realistic path: the state dir is outside the jail); the real-launch test was never seen failing under the plant.

Repro at ba936c8e2d62, test files: bh-02/app/tests/test_session_lock.py; command: `uv run pytest bh-02/app/tests/test_session_lock.py::test_resume_of_a_session_another_process_holds_is_refused_before_any_row_starts` exited 4

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
============================= test session starts ==============================
platform linux -- Python 3.15.0, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/user/bh-02
configfile: pyproject.toml
plugins: xdist-3.8.0, hypothesis-6.168.0, asyncio-1.4.0, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 0 items / 1 error

==================================== ERRORS ====================================
____________ ERROR collecting bh-02/app/tests/test_session_lock.py _____________
ImportError while importing test module '/home/user/bh-02/bh-02/app/tests/test_session_lock.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
bh-02/app/tests/test_session_lock.py:18: in <module>
    from bh_02.sessions import Held, Session, create, held
E   ImportError: cannot import name 'Held' from 'bh_02.sessions' (/home/user/bh-02/bh-02/app/src/bh_02/sessions.py)
=========================== short test summary info ============================
ERROR bh-02/app/tests/test_session_lock.py
=============================== 1 error in 0.19s ===============================
ERROR: found no collectors for /home/user/bh-02/bh-02/app/tests/test_session_lock.py::test_resume_of_a_session_another_process_holds_is_refused_before_any_row_starts
```

Check `uv run pytest bh-02/app/tests/test_session_lock.py::test_resume_of_a_session_another_process_holds_is_refused_before_any_row_starts` exited 1

(23 earlier lines omitted)
```text
        holding: Callable[[Path], _Holder],
    ) -> None:
        runner = CliRunner()
        patch = _ran(composition)
        assert runner.invoke(main, ["--no-jail", "--patch", str(patch)]).exit_code == 0
        (session,) = [path for path in state.iterdir() if path.is_dir()]
        layer = (session / "session.toml").read_text()
        other = holding(session)
    
        trace = tmp_path / "trace.log"
        refused = runner.invoke(
            main,
            ["--resume", session.name, "--model", "claude/haiku", "--patch", str(patch), "--trace", str(trace)],
        )
    
>       assert refused.exit_code == 1, refused.output
E       AssertionError: session 20261018-141827-1f55  (uv run bh-02 --resume to continue it)
E         
E       assert 0 == 1
E        +  where 0 = <Result okay>.exit_code

/home/user/bh-02/bh-02/app/tests/test_session_lock.py:153: AssertionError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_session_lock.py::test_resume_of_a_session_another_process_holds_is_refused_before_any_row_starts
============================== 1 failed in 2.52s ===============================
```

Round 2 (review finding 1: a bug closes with a repro recorded). No code changed; the only edits are these notes. Plan: run the committed test from this branch with the two source files the fix touched put back to their d30ae9c content (working tree only, never committed), record that failure, then restore them. Done:
1. Put bh-02/app/src/bh_02/cli.py and sessions.py back to 'git show d30ae9c:<path>' (git diff d30ae9c -- bh-02/app/src was empty), then ran 'record-check TASK-0143 --repro -- uv run pytest bh-02/app/tests/test_session_lock.py::test_resume_of_a_session_another_process_holds_is_refused_before_any_row_starts'. The repro is recorded above ('Repro at ba936c8e2d62, test files: bh-02/app/tests/test_session_lock.py'). ba936c8 is where the test file lives (the test arrived with the fix in 49c82ee, so no commit holds it beside the pre-fix source); the tree it ran on is that commit with only the two fix files at their d30ae9c content. To repeat: git show d30ae9c:bh-02/app/src/bh_02/cli.py > bh-02/app/src/bh_02/cli.py, the same for sessions.py, run the command, git checkout -- those two files. The failure on the pre-fix source is an ImportError at collection (cannot import name 'Held' from 'bh_02.sessions'): the test imports the new API, so on the old code it fails for want of it, not yet on behaviour (pytest exit 4: no collectors).
2. To show the bug itself, recorded the same test again with only cli.py at its d30ae9c content (sessions.held present, so a holder process really holds the session, but the command never takes it): 'Check ... exited 1' above, 'assert refused.exit_code == 1' fails with 0 == 1, and the output is 'session ... (uv run bh-02 --resume to continue it)': the second bh-02 resumed a session another process held, which is the bug. This is a plain record-check (not --repro), so it names no commit.
3. Restored both files (git checkout --); git status clean; test_session_lock.py with the fix: 5 passed (uv run pytest bh-02/app/tests/test_session_lock.py -q).
Not done, per the review: the two nits (running.lock opened with os.open rather than host_paths' no-link opener; test_real_launch.py's test never seen failing under the plant) stay as the reviewer left them, nothing filed.
<!-- SECTION:NOTES:END -->
