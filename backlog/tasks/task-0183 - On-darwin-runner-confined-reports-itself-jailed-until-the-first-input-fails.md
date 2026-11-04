---
id: TASK-0183
title: On darwin runner:confined reports itself jailed until the first input fails
status: Done
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T13:07:00Z'
labels:
  - runner
  - size-1
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: BrigJail.report() returns PLANNED on every platform and the darwin refusal (and the missing-bwrap check) happens only at start, so before an input approval.confined is true, the status bar says jailed and the model is told its inputs are confined. Nothing escapes; what the person sees is wrong. Proposed: refuse in the confined component when the platform has no jail type or bwrap is missing (said before a row starts), or report UNENFORCED off Linux.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Off Linux, or with no bwrap on PATH, runner:confined's report is not confined: approval.confined is false and the status bar never shows jailed, before or after a start; repro test: Approval(Runner(BrigJail(BrigConfig(), Host(), platform='darwin'))).confined is False
- [x] #2 The person is told before the first input that runner:confined cannot jail here and what to use instead (runner:unconfined, --no-jail)
- [x] #3 The darwin skip conditions in test_runner_tmux.py and test_runner_allowlist.py say what they now mean
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Repro test first; decide unjailable (platform, bwrap) once in BrigJail.__init__, report UNENFORCED then; Runner.notice() before a start = mechanism's notice; tui:grades row says it as a note at bind; fix skips; docs.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).

Repro at 31574ee4960c, test files: bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py; command: `uv run pytest bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
.........F                                                               [100%]
=================================== FAILURES ===================================
_ test_a_confined_runner_that_cannot_jail_here_is_not_confined_before_any_start _

    def test_a_confined_runner_that_cannot_jail_here_is_not_confined_before_any_start() -> None:
        """On darwin every start of `runner:confined` refuses, so nothing is ever jailed: the report
        that decides `confined` (and the status bar's `jailed`) says so before an input, not after one fails."""
>       runner = Runner(BrigJail(BrigConfig(), Host(), platform="darwin"))
                                               ^^^^^^

bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py:119: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <runner_cordis_plugin.jail.Host object at 0x7f940ba2dd30>, args = ()
kwargs = {}

    def _no_init_or_replace_init(self, *args, **kwargs):
        cls = type(self)
    
        if cls._is_protocol:
>           raise TypeError('Protocols cannot be instantiated')
E           TypeError: Protocols cannot be instantiated

/root/.local/share/uv/python/cpython-3.15.0b4-linux-x86_64-gnu/lib/python3.15/typing.py:1903: TypeError
=========================== short test summary info ============================
FAILED bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py::test_a_confined_runner_that_cannot_jail_here_is_not_confined_before_any_start
1 failed, 9 passed in 0.81s
```

Repro at cf903e132189, test files: bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py; command: `uv run pytest bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
.........F                                                               [100%]
=================================== FAILURES ===================================
_ test_a_confined_runner_that_cannot_jail_here_is_not_confined_before_any_start _

    def test_a_confined_runner_that_cannot_jail_here_is_not_confined_before_any_start() -> None:
        """On darwin every start of `runner:confined` refuses, so nothing is ever jailed: the report
        that decides `confined` (and the status bar's `jailed`) says so before an input, not after one fails."""
        runner = Runner(BrigJail(BrigConfig(), _Host(), platform="darwin"))
>       assert Approval(runner).confined is False
E       assert True is False
E        +  where True = Approval(runner=<runner_cordis_plugin.runner.Runner object at 0x7fb94228a270>).confined
E        +    where Approval(runner=<runner_cordis_plugin.runner.Runner object at 0x7fb94228a270>) = Approval(<runner_cordis_plugin.runner.Runner object at 0x7fb94228a270>)

bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py:131: AssertionError
=========================== short test summary info ============================
FAILED bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py::test_a_confined_runner_that_cannot_jail_here_is_not_confined_before_any_start
1 failed, 9 passed in 2.48s
```

Repro: Approval(Runner(BrigJail(BrigConfig(), host, platform='darwin'))).confined was True; recorded failing with record-check --repro (test_runner_approval.py; the task's Host() is a Protocol, so the test uses a small host dataclass). Fix: jail._why_unjailable(platform, shutil.which('bwrap')) decided once in BrigJail.__init__ (bind time); report() is UNENFORCED when non-empty, PLANNED otherwise, before and after (no start can succeed); start() raises the same text. Notice: chose the runner's notice, shown by the tui:grades row at bind as a note in the conversation, because notice() already is the channel for 'what the person should know of the jail' and the grades row already shows it; Mechanism gained notice() (Unjailed returns ''), Runner.notice() returns the mechanism's before any start; the text says to use runner:unconfined or --no-jail. Skips: test_runner_tmux.py (2) and test_runner_allowlist.py (1) now skip unless Linux with /usr/bin/bwrap. README/CONTRACTS updated. Tests added: test_runner_confined (platforms, no bwrap, ready), test_tui_wiring (note before any start). Results: scripts/check bh-02/plugins/runner-cordis-plugin exit 0 (all steps ok), scripts/check tui-cordis-plugin --no-gates --no-docs exit 0, scripts/arch-check --no-fix exit 0. scripts/linux-jail-check NOT run: 'docker is not answering' - the Docker daemon is not running in this sandbox (docker info: cannot connect to /var/run/docker.sock). scripts/check (full) left to the reviewer.

Check `scripts/check` exited 1

(35 earlier lines omitted)
```text
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 80%]
........................................................................ [ 83%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 94%]
........................................................................ [ 97%]
........................................................................ [ 99%]
..                                                                       [100%]
=================================== FAILURES ===================================
____________ test_every_test_file_that_starts_a_jail_is_in_a_group _____________
[gw1] linux -- Python 3.15.0 /home/user/bh-02/.venv/bin/python3

    def test_every_test_file_that_starts_a_jail_is_in_a_group() -> None:
        """A test that starts a jail of bh-02's own measures how long it takes to end, which a worker
        loaded with other jails flakes (the `jails` group): a file that starts one belongs in a
        group of the repository's `conftest.py`, with a reason there."""
        conftest = _conftest()
        files = [
            path.relative_to(_ROOT).as_posix()
            for tree in ("bh-02", "examples")
            for path in sorted((_ROOT / tree).glob("**/tests/**/test_*.py"))
            if path != Path(__file__).resolve() and _STARTS_A_JAIL.search(path.read_text())  # not this pattern
        ]
        assert files, "no test file starts a jail: the pattern no longer finds what it is for"
        ungrouped = [path for path in files if conftest.group_of(path) is None]
>       assert not ungrouped, f"these start a jail but are in no group of conftest.py (jails?): {ungrouped}"
E       AssertionError: these start a jail but are in no group of conftest.py (jails?): ['bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py']
E       assert not ['bh-02/plugins/runner-cordis-plugin/tests/test_runner_approval.py']

bh-02/app/tests/test_xdist_groups.py:49: AssertionError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_xdist_groups.py::test_every_test_file_that_starts_a_jail_is_in_a_group
1 failed, 2588 passed, 6 skipped, 1 xfailed in 136.89s (0:02:16)
   FAILED: tests
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
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
INFO    -  Documentation built in 2.98 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (reviewer, 2026-11-04): NOT CLOSED. Blocker: scripts/check (full) exited 1 on bh-02/app/tests/test_xdist_groups.py::test_every_test_file_that_starts_a_jail_is_in_a_group - the new repro makes test_runner_approval.py match BrigJail( but it is in no group of the root conftest.py; add it to the jails group (with a reason) and re-run scripts/check. Everything else holds: the second repro fails for the right reason (confined True is False); off Linux report() is UNENFORCED before and after a refused start, and the status bar's jailed follows approval.confined only; the grades row queues the runner's notice at bind, before any input; scripts/linux-jail-check passed with and without --as-root (366 passed, 1 skipped, 1 xfailed each), so a ready Linux host is unchanged. Findings for the lead: the criteria were ticked by the worker in 799b449, not by a reviewer; 799b449 also carries unrelated board files (decision-0012, task-0181.01). No drafts filed: the blocker is this task's own.

Check `scripts/check` exited 0

(11 earlier lines omitted)
```text
bringing up nodes...
bringing up nodes...

........................................................................ [  2%]
........................................................................ [  5%]
....s................................................................... [  8%]
...........x............................................................ [ 11%]
........................................................................ [ 13%]
........................................................................ [ 16%]
........................................................................ [ 19%]
....................................s................................... [ 22%]
........................................................................ [ 24%]
........................................................................ [ 27%]
........................................................................ [ 30%]
........................................................................ [ 33%]
........................................................................ [ 36%]
........................ss.............................................. [ 38%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 47%]
........................................................................ [ 49%]
........................................................................ [ 52%]
........................................................................ [ 55%]
........................................................................ [ 58%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 80%]
........................................................................ [ 83%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 94%]
........................................................................ [ 97%]
........................................................................ [ 99%]
..                                                                       [100%]
2589 passed, 6 skipped, 1 xfailed in 140.25s (0:02:20)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
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
INFO    -  Documentation built in 3.06 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Closed by reviewer 2026-11-04. Full check (scripts/check) at 3409d29 exited 0: 2589 passed, 6 skipped, 1 xfailed. The earlier blocker (test_runner_approval.py in no xdist jails group) is fixed in 3409d29. Repro fails for the right reason (confined True is False). Off Linux or without bwrap, report() is UNENFORCED before and after a refused start; jailed is drawn only from approval.confined. The grades row shows the notice at bind, before any input. linux-jail-check passed with and without --as-root (366 passed, 1 skipped, 1 xfailed each), so a ready Linux host is unchanged. Findings: the worker ticked the criteria itself (I verified each against this evidence); the unrelated board files were a stale-checkout artefact, resolved by the rebase. No drafts.
<!-- SECTION:NOTES:END -->
