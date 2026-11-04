---
id: TASK-0183
title: On darwin runner:confined reports itself jailed until the first input fails
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T12:41:00Z'
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
- [ ] #1 Off Linux, or with no bwrap on PATH, runner:confined's report is not confined: approval.confined is false and the status bar never shows jailed, before or after a start; repro test: Approval(Runner(BrigJail(BrigConfig(), Host(), platform='darwin'))).confined is False
- [ ] #2 The person is told before the first input that runner:confined cannot jail here and what to use instead (runner:unconfined, --no-jail)
- [ ] #3 The darwin skip conditions in test_runner_tmux.py and test_runner_allowlist.py say what they now mean
<!-- AC:END -->

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
<!-- SECTION:NOTES:END -->
