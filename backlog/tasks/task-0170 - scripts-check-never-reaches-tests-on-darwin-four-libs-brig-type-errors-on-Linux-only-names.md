---
id: TASK-0170
title: >-
  scripts/check never reaches tests on darwin: four libs/brig type errors on
  Linux-only names
status: In Progress
assignee: []
created_date: '2026-10-25 21:02'
updated_date: '2026-11-07 06:55'
labels:
  - size-2
dependencies:
  - TASK-0202
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`scripts/check` (the one definition of green) fails at its types step on macOS, before tests, gates or docs run, so no reviewer on darwin can get a full-tier check to pass. Four mypy errors, all in libs/brig and all from names that exist only on Linux:

- libs/brig/src/brig/runtime/_oci_agent.py:201 - Module has no attribute "SO_PEERCRED" [attr-defined]
- libs/brig/src/brig/run/dial.py:113 - Module has no attribute "pidfd_send_signal" [attr-defined]
- libs/brig/src/brig/run/host.py:476 - Module has no attribute "memfd_create" [attr-defined]
- libs/brig/src/brig/run/host.py:485 - Returning Any from function declared to return "int" [no-any-return]

Evidence: recorded on TASK-0169.02 (reviewer's --tier full, 2026-10-25, Darwin 27.0.0, exit after 'FAILED: types'); the same four appear in TASK-0169.01's recorded check; TASK-0169.03's worker also hit them and called them pre-existing. The last commit touching the three files is e2393a1 (TASK-0164), so this is not one task's regression but a standing condition of the repo on macOS.

Cost: every worker and reviewer on macOS either scopes the check to one member (which the gates and cross-member types do not cover) or reports a red full check they then have to explain away, which is how a real failure gets mistaken for this one. Fix is a design choice for the owner - a platform guard mypy understands (sys.platform narrowing), a per-module override in libs/brig's mypy settings, or typing the three uses behind a getattr seam - not a decision this review should make.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scripts/check on macOS reaches its tests, gates and docs steps and reports them, with no type error from a Linux-only name in libs/brig
- [x] #2 The chosen fix keeps the Linux behaviour type-checked rather than silencing the modules wholesale, and a note says which approach was taken and why
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Approach: an explicit `sys.platform != "linux"` guard at the three Linux-only call sites (commit 3ee5f3e), not a mypy `platform` setting and not a per-module override. `brig/run/host.py:_source_fd` raises OSError (its docstring already said it raises when not on Linux), `brig/run/dial.py:_pidfd_alive` answers False (a pidfd is Linux's, so elsewhere no process is held), `brig/runtime/_oci_agent.py:accept_hello` raises AgentStartFailed. This keeps the Linux path fully type-checked on Linux (mypy analyses it there) and the code matches its own docstring; a `platform = "linux"` setting would have stopped mypy looking at the darwin branches, and a module override would have silenced three modules wholesale.

Evidence: `uv run mypy` -> Success on 208 files (host platform, darwin); `uv run mypy --platform linux` -> Success on 208 files; brig unit tests for dial, peer, pidfd, accept_hello pass; `scripts/arch-check --no-fix` ok for every gate. Pre-existing and unrelated: `libs/brig/tests/unit/test_process_namespaces_pure.py` fails to collect on darwin (`signal.SIGRTMIN`).

Correction to the draft's premise, from the TASK-0169.01 review: `scripts/check` starts every step at once and reports in order, so a types failure does not stop tests, gates and docs; the earlier runs never reached them because stray test runs held the jail lock. AC #1 is therefore a question about a full run on a quiet machine; one is running now and its result goes here.

Orchestrator, 2026-11-06 (macOS 27.0.1, HEAD ba798c43): scripts/check's types step passes on darwin (Success: no issues found in 208 source files), and format and lint pass. Its tests step never reported: with pytest -n auto (28 workers) the run hung for 28 minutes; filed as TASK-0202. Criterion #1 (the check reaches and reports tests, gates and docs) therefore waits on TASK-0202. The SIGRTMIN collection error noted above is in TASK-0198.

Check `scripts/check` exited 1

(322 earlier lines omitted)
```text

libs/brig/src/brig/run/dial.py:219: EndpointRefused
___ test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts ___
[gw3] darwin -- Python 3.15.0 /Users/brukhabtu/Documents/src/github.com/bruk-io/bh-02/.venv/bin/python

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

pilot = <Pilot app=BhApp(title='bh-02', classes={'-theme-bh-01-dark', '-dark-mode'}, pseudo_classes={'focus', 'dark'})>
done = <function test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts.<locals>.<lambda> at 0x1115b3ab0>
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
FAILED libs/brig/tests/integration/test_channel_planted_link.py::test_a_peer_the_kernel_cannot_report_is_refused_not_waited_out
FAILED bh-02/plugins/tui-cordis-plugin/tests/test_tui_working.py::test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts
3 failed, 3850 passed, 231 skipped in 70.68s (0:01:10)
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
INFO    -  Documentation built in 1.26 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```
<!-- SECTION:NOTES:END -->
