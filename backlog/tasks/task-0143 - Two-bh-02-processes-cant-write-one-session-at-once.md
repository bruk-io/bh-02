---
id: TASK-0143
title: Two bh-02 processes can't write one session at once
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:15'
updated_date: '2026-10-18 14:12'
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
- [ ] #3 bh-02 sessions, bh-02 trajectory and bh-02 watch read a held session as before (they take no lock); scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order: (1) sessions.py: a pure-ish 'held' context manager that opens '<session dir>/running.lock' (O_RDWR|O_CREAT, 0600, non-inheritable), takes fcntl.flock(LOCK_EX|LOCK_NB), then writes this pid; on BlockingIOError reads the pid and raises Held(message: names the session and the process, says to leave the other bh-02 first). The kernel drops the flock with the process, so a crash releases it. (2) cli.py: main holds it in an ExitStack from before the session's layer is read or rewritten (resume) and right after create (new), through _run; refused as 'error: ...' exit 1 before any row starts; farewell/discard after release. sessions/trajectory/watch never import held. (3) Tests: a holder in another process (subprocess, the real flock) -> bh-02 --resume refused, session untouched, no row started; holder SIGKILLed -> resume works (crash releases); sessions/trajectory/watch read a held session; unit tests of held (second refused, released at exit of the with, pid named). Plant: remove the flock call and see the refusal test fail. (4) Docs: sessions.md, command-line.md, GLOSSARY, app README, sessions.py docstring; root pyproject impure budget entry for sessions:held. Proof: uv run pytest on app tests incl. test_real_launch, scripts/check bh-02/app, scripts/arch-check --no-fix.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: bh-02/app/src/bh_02/sessions.py (Held, held(): O_RDWR|O_CREAT 0600 running.lock in the session dir, fcntl.flock LOCK_EX|LOCK_NB, then the pid written; Held names the pid and says to leave the other bh-02 first; the pid-less fallback covers the window between locking and writing), cli.py (main holds the session in an ExitStack through _run; _session takes it for a new session right after create and for a resume BEFORE its layer is read or --model rewrites it; Held is printed as 'error: ...' exit 1; discard and the farewell run after release), root pyproject (impure budget: sessions:held), tests (new bh-02/app/tests/test_session_lock.py, one real-launch test in test_real_launch.py), docs (sessions.md, command-line.md, GLOSSARY, app README). sessions/trajectory/watch never import held. Evidence: AC1 - test_session_lock.py: held twice in one process is refused, free after the block; a holder process SIGKILLed with a child still alive leaves the session resumable (OS release, fd not inherited); the real-launch test kills a running bh-02 with SIGKILL and the next --resume comes up. AC2 - a holder in another process: bh-02 --resume ID --model claude/haiku --trace F exits 1 with 'error: session ID is held by bh-02 process PID ... Leave that bh-02 first', F never created (no row started), session.toml unchanged, no farewell, the session still listed; the real-launch test (first bh-02 running in a pty, second --resume refused naming its pid, nothing drawn). PLANTED: with the fcntl.flock call replaced by pass, 4 of the 5 lock tests fail (the fifth only checks the file), and the real run's exit_code is 0 instead of 1; with the hold moved after set_model in _session, the 'session.toml unchanged' assertion fails (layer rewritten). Both restored. AC3 - test_sessions_trajectory_and_watch_read_a_held_session_as_before: sessions, trajectory ID and watch ID NAME --once all exit 0 with their output while another process holds it, and the lock file still names the holder afterwards. Ran: uv run pytest bh-02/app/tests/test_session_lock.py (5 passed); test_real_launch.py::test_a_running_bh_02_holds... passed; scripts/check bh-02/app (with gates and docs): format, lint, types, tests 336 passed 1 skipped (bwrap), all five gates, docs build ok (tokens skipped: no bh-01). Left for the reviewer: the 'scripts/check passes' half of AC3, so #3 is unticked.

Correction to the evidence above: the planted violation (flock replaced by pass) was run against test_session_lock.py only, where the CLI refusal test failed with exit_code 0 != 1; the real-launch test was run unplanted (passed) and not seen failing. scripts/arch-check --no-fix also run after the root pyproject change: all five gates ok.
<!-- SECTION:NOTES:END -->
