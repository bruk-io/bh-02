---
id: TASK-0186
title: >-
  test_real_launch's keyed-model --no-jail launch exits 1 on quit, once, under
  the full check
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T03:39:00Z'
updated_date: '2026-11-04T13:57:00Z'
labels:
  - tests
  - size-1
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen once in the reviewer's full scripts/check for TASK-0179 (2026-11-03, on 1e0b11b): test_a_keyed_model_s_key_never_reaches_an_input_s_environment asserted app.exit_code() == 0 and got 1 after Ctrl-Q. Passes alone and in later full runs; not reproduced. The cause is unknown and could involve the Unjailed stop path that TASK-0179 changed (it now removes the socket directory on stop). The assertion shows nothing of why.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 When the launch's exit code is not 0, the failure shows the app's last screen and stderr (app.text())
- [x] #2 If it recurs, the cause is named and fixed, or the test's flake is explained in its notes
- [x] #3 Every exit_code() mismatch in test_real_launch.py shows app.text() in its failure; a planted non-zero exit shows it
- [x] #4 The notes record whether the keyed-model launch failure recurred over a stated number of full runs
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).

Changed: all 43 exit_code() mismatches in bh-02/app/tests/test_real_launch.py (each 'assert X.exit_code(..) == N') now carry f"exit code was not N; the screen said:\n{X.text()[-3000:]}" (same shape as the existing wait_for/exit_code messages). Showing it works: planted '== 7' on the keyed-model launch (line 980); the failure printed 'assert 0 == 7' plus the whole last screen (session line, 'the input said: False False'); plant removed (diff is only the 43 message additions). Recurrence: scripts/check bh-02/app run 3 times (member check, not the whole-repo scripts/check; it includes test_real_launch), all exit 0, first lines were uv's UV_NATIVE_TLS deprecation warning; the keyed-model --no-jail launch failure did NOT recur in 3 runs. No repro: the original failure was seen once (reviewer's full run for TASK-0179 on 1e0b11b) and could not be reproduced on demand; a planted failure is not a repro. Criterion #2 left unticked: no recurrence, so cause is unknown; the new message will show the screen if it recurs. Criteria left unticked for the reviewer; AC#3 includes planted-failure evidence above.

Check `scripts/check` exited 1

(70 earlier lines omitted)
```text
E       AssertionError: assert 'denied' not in '           ...            '
E         
E         'denied' is contained here:
E              
E              ⎿ denied: the person said no to this call, so it did not run; ask them what they want instead                        
E         ?      ++++++
E                                                                                                                                   
E            the input said: denied: the person said no to this call, so it did not run; ask them what they want instead                                                                                                                                    ...
E         
E         ...Full output truncated (36 lines hidden), use '-vv' to show

bh-02/app/tests/test_real_launch.py:514: AssertionError
_______ test_a_call_whose_question_the_stop_withdrew_has_the_time_alone ________
[gw3] linux -- Python 3.15.0 /home/user/bh-02-small/.venv/bin/python

    async def test_a_call_whose_question_the_stop_withdrew_has_the_time_alone() -> None:
        stepped = Stepped()
        transcript = MemoryTranscript()
    
        class Waiting:
            async def approve(self, question: Json) -> Answer:
                stepped.advance(1.0)
                await asyncio.Event().wait()
                return Answer.YES  # pragma: no cover
    
        model = Timing(stepped, transcript, steps((0.5, text("on it")), (0.0, slow("c1", 0))))
        task = asyncio.create_task(
            reply(LoopModel(model, slow_tools(stepped, []), transcript, Waiting(), clock=stepped.clock), "go")
        )
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
>       (result,) = entries(transcript, "tool")
        ^^^^^^^^^
E       ValueError: not enough values to unpack (expected 1, got 0)

bh-02/plugins/agent-cordis-plugin/tests/test_agent_records.py:565: ValueError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_real_launch.py::test_keys_typed_as_the_modal_comes_up_do_not_answer_it
FAILED bh-02/plugins/agent-cordis-plugin/tests/test_agent_records.py::test_a_call_whose_question_the_stop_withdrew_has_the_time_alone
2 failed, 2593 passed, 6 skipped, 1 xfailed in 236.49s (0:03:56)
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
INFO    -  Building documentation to directory: /home/user/bh-02-small/site
INFO    -  Documentation built in 6.20 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

No repro: the failure was seen once (the TASK-0179 full run on 1e0b11b). It did not recur in 3 member runs or in the reviewer's full run, and it can't be triggered on demand. The new message shows the screen if it recurs.
<!-- SECTION:NOTES:END -->
