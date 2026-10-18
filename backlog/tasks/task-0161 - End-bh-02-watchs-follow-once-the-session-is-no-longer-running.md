---
id: TASK-0161
title: End bh-02 watch's follow once the session is no longer running
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 19:32'
updated_date: '2026-10-18 21:03'
labels:
  - app
  - subagents
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by Fable ruling TASK-0148 (2026-10-18). bh-02 watch SESSION AGENT follows a child's event log until its agent_end line. A log that stopped writing never gets one, nor does a session that ended without it (a crash), so the follow never ends and Ctrl-C is the only way out. TASK-0143 made a running bh-02 hold its session's running.lock; watch can end its follow once that lock is free (the session no longer runs) and say why.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 bh-02 watch ends its follow, saying the session is no longer running, once the session's running.lock is free, even with no agent_end in the log (a test with the lock released and no end line)
- [x] #2 A follow of a running session's child is unchanged; watch never takes the lock; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Decision: no flock probe. A starting bh-02 takes LOCK_EX|LOCK_NB (sessions.held); any lock held at that instant, a shared one for a microsecond too, makes it fail with Held and a refusal naming a stale pid, and AC2 and three docs say watch takes no lock. So watch READS what held() leaves: the pid in running.lock (written only after the lock is taken, never cleared, the OS drops the lock when that process dies). Order: (1) sessions.py: pure _holder(written)->int|None + impure running(root, session_id)->bool (read_beneath the lock file through no link, then os.kill(pid, 0)); a missing file or a dead pid = not running; a pid alive or unreadable-but-present = running (errs toward the old follow); budget entry bh_02.sessions:running in root pyproject. (2) watching.py watched(): per poll ask running() BEFORE reading the log, so lines written before the holder died are shown; when follow, no agent_end and not running: yield a line saying the session is no longer running and the log has no end, then stop. (3) Tests first, seen failing: test_session_lock.py with the real holder subprocess: follow goes on while held (several polls), the holder crashed mid-follow -> ends with the message and the last lines; holder exited cleanly; no end line + never-locked dir; pure _holder cases; watch took nothing (resume still works after, holder pid intact). test_watching.py existing follow test holds the session with held() (a running follow unchanged). (4) Docs: watch help in cli.py, sessions.py docstring, command-line.md, sessions.md, app README if it names watch, GLOSSARY. (5) scripts/check bh-02/app (gates, docs), scripts/arch-check --no-fix. Risk: pid namespace/reuse; says so in docs and notes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision: watch does NOT probe the flock. A starting bh-02 takes LOCK_EX|LOCK_NB in sessions.held; any lock held at that instant, a shared one tried and released at once too, makes that call fail with Held, so a resume starting in the same instant would be refused naming a stale pid. That is a probe that can block a starting bh-02, and AC2 plus sessions.py/sessions.md/command-line docs say watch takes no lock. So watch reads what sessions.py leaves: the pid in running.lock (written after the lock is taken, left when the block ends; the OS drops the lock with the process). New sessions.running(root, session_id) reads that file through host_paths.read_beneath (no link) and asks os.kill(pid, 0); False only for no lock file or a dead pid. Anything it cannot tell is True (empty or garbage file, not a plain file, EPERM), so the follow goes on as before. Limits, documented in command-line.md and the docstring: a bh-02 in another pid namespace looks gone (the follow ends early); a pid a crash left that another process has taken keeps the follow going until Ctrl-C; a run that released the lock but whose process lingers is seen until it exits. Changed: sessions.py (running, _holder, docstrings), watching.py (watched takes running: Callable[[], bool], required; asks it BEFORE each read so lines written before the holder died are shown; with no agent_end and not running yields a line on its own line saying the session is no longer running and the log has no end, then stops; --once never asks), cli.py (passes partial(sessions.running, root, session); help text), root pyproject (impure budget: sessions:running, seen needed: without it the gate reports os.kill), docs (command-line.md, sessions.md, app README, GLOSSARY). Tests: test_watching.py (loop with an injected running: ends and says so, shown-before-gone, an agent_end read wins, a running session is followed to poll 50, --once never asks) and test_session_lock.py (running by pid, no-pid files read as running, asking takes and writes nothing; with the real holder subprocess: follow goes on for 3 polls then the holder is SIGKILLed and the follow ends with the message; a run that ended cleanly with no end line ends at once without sleeping, and held() still works after; the CLI watch ends with exit 0 when the holder is killed by a timer). Planted, seen failing: gone = False in watched made the no-end test hang (timeout 20 exit 124: the original bug); gone = not done (ignore running) failed 4 tests (the running-follow ones); ProcessLookupError returning True in running failed the pid test; budget entry removed -> arch gate failed on os.kill. All restored. Ran: uv run pytest test_watching.py test_session_lock.py (44 passed); scripts/check bh-02/app exit 0 (363 passed, 1 skipped, gates, docs); scripts/arch-check --no-fix exit 0. Old files: none stop working (no stored format changed; a session dir with no running.lock now counts as not running, which only a hand-made or pre-TASK-0143 dir is). Filed TASK-0163: the TASK-0148 log-stopped note still says 'must be left with Ctrl-C' (subagents plugin text and tests, not touched here). Left for the reviewer: the 'scripts/check passes' half of AC2, so #2 is unticked.

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 32%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
...............................s..s....sss.s..ss..ss...sss..ss.s.s.s.s.. [ 49%]
ss.s..sss.s.........s................................................... [ 50%]
......................................................................s. [ 52%]
................................................................ssssssss [ 54%]
ssssssssssssssssssss.sssssssssssssssssssssssssssssssssssssss............ [ 56%]
...............ssss.sssssss.s........................................... [ 58%]
...........................s............................................ [ 60%]
........................................................................ [ 61%]
.......................................sss.............................. [ 63%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
.....................................................................    [100%]
3841 passed, 118 skipped in 204.69s (0:03:24)
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
INFO    -  Documentation built in 4.40 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

No repro: the fix is in HEAD, so the repro test (test_session_lock.py::test_a_follow_goes_on_while_the_session_is_held_and_ends_when_the_holder_has_crashed_with_no_end_line) passes here. The worker recorded it failing against the bug planted back (gone = False in watched: the follow hung until timeout 20 exit 124).
<!-- SECTION:NOTES:END -->
