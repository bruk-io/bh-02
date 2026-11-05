---
id: TASK-0193
title: >-
  Keys typed before the approval prompt appeared can answer it when the app
  stalls
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-04T16:59:00Z'
updated_date: '2026-11-05T04:56:00Z'
labels:
  - tui
  - approval
  - size-2
dependencies: []
modified_files:
  - bh-02/plugins/tui-cordis-plugin/src/tui_cordis_plugin/widgets/approval.py
  - bh-02/plugins/tui-cordis-plugin/src/tui_cordis_plugin/widgets/choice.py
  - bh-02/plugins/tui-cordis-plugin/README.md
  - bh-02/CONTRACTS.md
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0191's worker, 2026-11-04 (test_keys_typed_as_the_modal_comes_up_do_not_answer_it failed 3 of 8 runs under 12 CPU burners). The tui's ApprovalScreen arms on a 0.4 s wall-clock timer from mount, and its y/n/Escape bindings are judged when the key is processed, not when it was typed. When the app stalls, the grace timer can expire while keys typed before the modal came up are still queued, and they then answer it: a stray y typed ahead can approve a call the person never saw. The grace period exists to stop exactly that. Fix: judge each key by when it arrived (Textual's key event time, or a stamp taken where keys are read), against when the modal became visible.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A key that arrived before the approval modal was visible plus its grace period never answers it, however late it is processed; a test that holds the event loop while keys are queued, then releases it, shows the modal unanswered; repro recorded failing before the fix
- [ ] #2 A key that arrived after the grace period still answers at once
- [ ] #3 test_keys_typed_as_the_modal_comes_up_do_not_answer_it passes 50 of 50 under the load that failed it (12 CPU burners)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Judge each key by when it arrived, not when it is processed. Textual 8.2.8's Linux driver builds each `Key` in its input thread (linux_driver.py `_run_input_thread`), so `Message.time` (`textual._time.get_time`, monotonic) is the arrival time even while the event loop is stalled.

### Order of work

1. Repro first (AC1). In bh-02/plugins/tui-cordis-plugin/tests, write a test that pushes an `ApprovalScreen`, queues `y` while the modal is up but unarmed, then holds the event loop past `GRACE` (a blocking call scheduled ahead of the queued key: `time.sleep` in a `call_later`, or the equivalent the existing tests use). After the loop is released the modal must still be unanswered. Run it against the current code and record the failure on the task before changing anything. Add the same for `ChoiceScreen`.
2. widgets/approval.py: the modal stamps when it became visible, with `get_time()` in a `call_after_refresh` from `on_mount`, so the stamp is taken after the first paint and not when the screen object was made. A key answers only when `event.time >= shown + grace`. A pure function, `answers(arrived, shown, grace) -> bool`, holds the rule. The y/n/Escape `BINDINGS` give way to an `on_key` that maps the key to its answer and judges `event.time`; actions can't see the event, and `ChoiceScreen.on_key` already works this way, so the two share the judgement. Every judged key is stopped (`event.stop()`, `prevent_default()`), answered or not, so it never reaches the composer, as now. The `-arming` class on the keys line still comes off by a timer at `grace` after the stamp. That's display only, and no longer what decides.
3. widgets/choice.py: use the same judgement through the shared base (no copy).
4. Keep the `armed` property only if something outside the module still needs it, and make it read the same rule.
5. Docs: the module docstrings, plus the tui plugin README and CONTRACTS.md where they describe the grace period ("from when it was shown, by when each key arrived").

### Risks

- A key made in a test with Pilot is stamped when the test creates it, not when a person typed it. That's fine, since the tests control when they create them, but a test that creates keys after a sleep isn't testing the stall.
- If the first paint is delayed by a stall, keys typed during that stall arrive before the stamp and are dropped. That's intended: the person couldn't see the modal.
- Ctrl-C is the app's priority binding and must still withdraw the modal at once. A test pins this.

### Proof

- The repro, recorded failing before the fix and passing after.
- A key that arrives after the grace period answers at once.
- `test_keys_typed_as_the_modal_comes_up_do_not_answer_it` 50 of 50 under 12 CPU burners (`stress-ng` if it's installed, otherwise 12 `python -c 'while 1: pass'`), recorded on the task with the command and the count.
- scripts/check; scripts/linux-jail-check in both modes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Plan note: AC3's test is test_keys_typed_as_the_modal_comes_up_do_not_answer_it in bh-02/app/tests/test_real_launch.py (real_launch: the real app in a pty, so its keys come through the driver's input thread, as a person's do).

Repro at e121e6f758af, test files: bh-02/plugins/tui-cordis-plugin/tests/test_tui_key_time.py; command: `uv run pytest bh-02/plugins/tui-cordis-plugin/tests/test_tui_key_time.py -q` exited 1

(94 earlier lines omitted)
```text
╭───────────────────── Traceback (most recent call last) ──────────────────────╮
│ /home/user/bh-02/.claude/worktrees/agent-a09be7ed4005c7078/bh-02/plugins/tui │
│ -cordis-plugin/src/tui_cordis_plugin/widgets/choice.py:52 in on_key          │
│                                                                              │
│   49 │   │   │   self.action_answer(str(self.question.get("escape", "")))    │
│   50 │   │   elif key in self._values:                                       │
│   51 │   │   │   event.stop()                                                │
│ ❱ 52 │   │   │   self.action_answer(self._values[key])                       │
│   53                                                                         │
│                                                                              │
│ ╭───────────────────────────── locals ─────────────────────────────╮         │
│ │ event = Key(key='n', character='n', name='n', is_printable=True) │         │
│ │   key = 'n'                                                      │         │
│ │  self = ChoiceScreen()                                           │         │
│ ╰──────────────────────────────────────────────────────────────────╯         │
│                                                                              │
│ /home/user/bh-02/.claude/worktrees/agent-a09be7ed4005c7078/bh-02/plugins/tui │
│ -cordis-plugin/src/tui_cordis_plugin/widgets/approval.py:142 in              │
│ action_answer                                                                │
│                                                                              │
│   139 │   def action_answer(self, answer: T) -> None:                        │
│   140 │   │   """Answer, unless the modal was shown too recently for the key │
│   141 │   │   if self._armed:                                                │
│ ❱ 142 │   │   │   self.dismiss(answer)                                       │
│   143                                                                        │
│                                                                              │
│ ╭──────── locals ─────────╮                                                  │
│ │ answer = 'no'           │                                                  │
│ │   self = ChoiceScreen() │                                                  │
│ ╰─────────────────────────╯                                                  │
│                                                                              │
│ /home/user/bh-02/.claude/worktrees/agent-a09be7ed4005c7078/.venv/lib/python3 │
│ .15/site-packages/textual/app.py:3105 in pop_screen                          │
│                                                                              │
│   3102 │   │                                                                 │
│   3103 │   │   screen_stack = self._screen_stack                             │
│   3104 │   │   if len(screen_stack) <= 1:                                    │
│ ❱ 3105 │   │   │   raise ScreenStackError(                                   │
│   3106 │   │   │   │   "Can't pop screen; there must be at least one screen  │
│   3107 │   │   │   )                                                         │
│   3108                                                                       │
│                                                                              │
│ ╭──────────────────────────── locals ─────────────────────────────╮          │
│ │ screen_stack = [Screen(id='_default')]                          │          │
│ │         self = BhApp(                                           │          │
│ │                │   title='bh-02',                               │          │
│ │                │   classes={                                    │          │
│ │                │   │   '-theme-bh-01-dark',                     │          │
│ │                │   │   '-dark-mode'                             │          │
│ │                │   },                                           │          │
│ │                │   pseudo_classes={'focus', 'dark'}             │          │
│ │                )                                                │          │
│ ╰─────────────────────────────────────────────────────────────────╯          │
╰──────────────────────────────────────────────────────────────────────────────╯
ScreenStackError: Can't pop screen; there must be at least one screen on the 
stack
=========================== short test summary info ============================
FAILED bh-02/plugins/tui-cordis-plugin/tests/test_tui_key_time.py::test_keys_queued_before_the_grace_ended_do_not_answer_the_approval_when_read_late
FAILED bh-02/plugins/tui-cordis-plugin/tests/test_tui_key_time.py::test_keys_queued_before_the_grace_ended_do_not_answer_the_choice_when_read_late
2 failed in 1.94s
```

Check `scripts/check bh-02/plugins/tui-cordis-plugin` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== format
48 files already formatted
   ok
== lint
line-too-long: Line too long (153 > 110)
  --> bh-02/plugins/tui-cordis-plugin/src/tui_cordis_plugin/widgets/choice.py:23:111
   |
21 | …'s key answers its `value`, and
22 | …after the grace period (as
23 | …ore are dropped. Ctrl-C withdraws it, and the answer is then '' (nothing was chosen)."""
   |                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
24 | …
25 | …at = GRACE) -> None:
   |

Found 1 error.
   FAILED: lint
== types
Success: no issues found in 23 source files
   ok
== tests
bringing up nodes...
bringing up nodes...

........................................................................ [ 20%]
........................................................................ [ 40%]
........................................................................ [ 60%]
........................................................................ [ 80%]
.......................................................................  [100%]
359 passed in 36.17s
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
INFO    -  Building documentation to directory: /home/user/bh-02/.claude/worktrees/agent-a09be7ed4005c7078/site
INFO    -  Documentation built in 2.06 seconds
   ok
== tokens
   skipped: no /home/user/bh-02/.claude/worktrees/bh-01/dist (bh-01, built, beside this repository)
```

Check `scripts/check bh-02/plugins/tui-cordis-plugin` exited 0

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== format
48 files already formatted
   ok
== lint
All checks passed!
   ok
== types
Success: no issues found in 23 source files
   ok
== tests
bringing up nodes...
bringing up nodes...

........................................................................ [ 20%]
........................................................................ [ 40%]
........................................................................ [ 60%]
........................................................................ [ 80%]
.......................................................................  [100%]
359 passed in 36.11s
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
INFO    -  Building documentation to directory: /home/user/bh-02/.claude/worktrees/agent-a09be7ed4005c7078/site
INFO    -  Documentation built in 2.31 seconds
   ok
== tokens
   skipped: no /home/user/bh-02/.claude/worktrees/bh-01/dist (bh-01, built, beside this repository)
```

Check `scripts/linux-jail-check --ca /root/.ccr/ca-bundle.crt` exited 0

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
Installed 1 package in 1ms
== image bh-02-linux-jail (ubuntu 24.04, bubblewrap, uv, Python 3.15)
sha256:6b4985a834c4dc43a67dba8a671ce8cffc1c435c0c537a1a30dac45b2e50353b
== uv run --locked pytest -q -p no:cacheprovider bh-02/plugins/runner-cordis-plugin bh-02/plugins/python-cordis-plugin bh-02/plugins/extensions-cordis-plugin bh-02/app/tests/test_python_repl.py
bubblewrap 0.9.0
uv 0.13.7 (x86_64-unknown-linux-gnu)
Python 3.15.2 (main, Oct 26 2026, 14:06:56) [Clang 23.1.3 ]
........................................................................ [ 13%]
...............................x........................................ [ 26%]
........................................................................ [ 40%]
........................................................................ [ 53%]
........................................................................ [ 67%]
........................................................................ [ 80%]
........................................................................ [ 93%]
..............s..................                                        [100%]
535 passed, 1 skipped, 1 xfailed in 120.57s (0:02:00)
```

Check `scripts/linux-jail-check --as-root --ca /root/.ccr/ca-bundle.crt` exited 0

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== image bh-02-linux-jail (ubuntu 24.04, bubblewrap, uv, Python 3.15)
sha256:a944d242c9ab5429d81fd8d54176df386d350564249c2422a11d1523eb993b8f
== uv run --locked pytest -q -p no:cacheprovider bh-02/plugins/runner-cordis-plugin bh-02/plugins/python-cordis-plugin bh-02/plugins/extensions-cordis-plugin bh-02/app/tests/test_python_repl.py
bubblewrap 0.9.0
uv 0.13.7 (x86_64-unknown-linux-gnu)
Python 3.15.2 (main, Oct 26 2026, 14:06:56) [Clang 23.1.3 ]
........................................................................ [ 13%]
...............................x........................................ [ 26%]
........................................................................ [ 40%]
........................................................................ [ 53%]
........................................................................ [ 67%]
........................................................................ [ 80%]
........................................................................ [ 93%]
..............s..................                                        [100%]
535 passed, 1 skipped, 1 xfailed in 122.04s (0:02:02)
```

Repro: bh-02/plugins/tui-cordis-plugin/tests/test_tui_key_time.py (keys made before a time.sleep stall past the grace, posted after; ApprovalScreen and ChoiceScreen). Recorded failing at the repro commit (both tests failed: the modal was answered). Fix: ApprovalScreen.on_key judges event.time against a stamp taken in call_after_refresh from on_mount (_answers(arrived, shown, grace)); ChoiceScreen supplies only _key_answer; y/n/Escape BINDINGS removed; armed reads the same rule; a second queued answer key no longer dismisses twice. AC3: 12 background 'python3 -c "while True: pass"' burners (stress-ng not installed, 4 CPUs), 50 runs of test_keys_typed_as_the_modal_comes_up_do_not_answer_it, 50 passed 0 failed; burners killed, pgrep -f 'while True' empty. Checks recorded: scripts/check bh-02/plugins/tui-cordis-plugin (an earlier run failed on one line-too-long, fixed; then exit 0, 359 passed), linux-jail-check default and --as-root both exit 0. ACs left unticked for the reviewer.

Check `scripts/check` exited 0

(13 earlier lines omitted)
```text

........................................................................ [  2%]
........................................................................ [  5%]
..............s......................................................... [  7%]
..............................x......................................... [ 10%]
........................................................................ [ 12%]
........................................................................ [ 15%]
........................................................................ [ 18%]
................s....................................................... [ 20%]
........................................................................ [ 23%]
........................................................................ [ 25%]
........................................................................ [ 28%]
........................................................................ [ 30%]
........................................................................ [ 33%]
..................................s........s............................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 46%]
........................................................................ [ 48%]
........................................................................ [ 51%]
........................................................................ [ 54%]
........................................................................ [ 56%]
........................................................................ [ 59%]
........................................................................ [ 61%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 87%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 95%]
........................................................................ [ 97%]
...............................................................          [100%]
2794 passed, 6 skipped, 1 xfailed in 134.51s (0:02:14)
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
INFO    -  Building documentation to directory: /home/user/bh-02/.claude/worktrees/agent-a09be7ed4005c7078/site
INFO    -  Documentation built in 2.76 seconds
   ok
== tokens
   skipped: no /home/user/bh-02/.claude/worktrees/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
