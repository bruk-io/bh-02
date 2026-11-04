---
id: TASK-0189
title: >-
  subagents child.py still names memory:files, memory:auto and commands:registry
  by use
status: Done
assignee:
  - '@claude'
created_date: '2026-11-04T14:14:00Z'
updated_date: '2026-11-04T14:55:00Z'
labels:
  - subagents
  - size-2
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0187 moved the row list to bh-02.toml and listed the cross-plugin config fields, but child.py still hard-codes three component names: _MEMORY_USE and _COMMANDS_USE (a child with a memory row gets a commands registry of its own) and _AUTO_USE (the refusal of auto memory). Derive the first from the component injecting commands (wiring.py walk, cordis metadata) and name the registry and the refused uses in the agents row's config.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 child.py names no other plugin's component
- [x] #2 a child whose row injects commands gets a registry of its own, derived in wiring.py
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
child.py names no other plugin's component: AgentsConfig gains commands_row and refused (bh-02.toml names them); wiring.py derives which rows inject commands from cordis's resolve(use).inject and passes the predicate to Agents; child_rows copies the parent's commands row's component for a child with such a row. Proof: plugin and app tests, scripts/check on both members.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
child.py no longer has _MEMORY_USE, _AUTO_USE or _COMMANDS_USE (grep for 'memory:' and 'commands:' in child.py finds none). AgentsConfig gained commands_row (default commands) and refused (default none; bh-02.toml names memory:auto); wiring._injects_commands reads cordis.loader.resolve(use).inject and is handed to Agents, which hands it to child_rows. A child's row that injects commands (any, not only memory:files) now gets a registry copying the parent's commands row's component. The auto-memory error now reads 'a child must not have memory:auto (decision-0002...)'. Tests: full bh-02 pytest run 2004 passed before the last app-test fix; test_child_boot and the plugin tests updated, wiring test for the probe row now asserts it is given its own registry. scripts/check bh-02/plugins/subagents-cordis-plugin exit 0 (gates and docs included); scripts/check bh-02/app --no-gates --no-docs exit 0. Criteria left unticked.

Review (reviewer, not the worker): NOT closed, though both criteria are met and ticked. Check: the full tier ran once on this tree (HEAD 63d6f38) and was recorded on TASK-0190: exit 0, 2601 passed. #1: child.py names no memory: or commands: component. #2: wiring._injects_commands reads cordis.loader.resolve(use).inject, and child_rows adds a registry of the parent's commands row's component. The changed wiring test is the intended behaviour, not a weakened check: it still asserts the parent's value never reaches the child (seen[0] is not parent), which is what the old 'stays unmounted' test guarded. Blocking finding (high): decision-0002 regression. refused defaults to (), so a child is kept from auto memory only while the active config repeats refused = ["memory:auto"]. A patch's config replaces the row's whole, and TASK-0190's message tells people to copy bh-02.toml's rows, so a config that copies rows without refused lets a child mount memory-auto with no error. The plugin tests added refused explicitly, so no test pins a safe default. Filed as the draft 'A child can get auto memory again unless the agents row's config lists it in refused'. Recommended default: refused = ("memory:auto",) in AgentsConfig (agents.py), or a metadata flag on the auto memory component that wiring.py reads. Minor: the refusal message lists every refused component, not the one the offending row uses. Closes once that draft's fix lands here, or the owner accepts the regression.

Lead, 2026-11-04, on the review's high finding: fixed in d957d98. Auto memory is ALWAYS_REFUSED in the agents plugin, a floor joined to the config's refused (deduplicated), not a default a layer can drop; bh-02.toml no longer names it. A new test (refused unset, and refused empty) fails without the change. The review's DRAFT-0028 is archived.

Check `scripts/check` exited 1

(52 earlier lines omitted)
```text
__ test_a_step_that_failed_or_was_stopped_has_a_record_of_what_came_before_it __
[gw3] linux -- Python 3.15.0 /home/user/bh-02-sub/.venv/bin/python

    async def test_a_step_that_failed_or_was_stopped_has_a_record_of_what_came_before_it() -> None:
        class Failing(Timing):
            async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
                self.stepped.advance(0.5)
                yield text("Hel")
                self.stepped.advance(0.25)
                raise RuntimeError("429")
    
        stepped, transcript = Stepped(), MemoryTranscript()
        with pytest.raises(RuntimeError):
            await reply(loop(Failing(stepped, transcript), transcript, stepped), "hi")
        (answer,) = entries(transcript, "assistant")
        assert answer["content"].endswith(FAILED)
        assert answer["step"] == {
            "at": START,
            "first_chunk": 0.5,
            "took": 0.5,
        }  # up to the last chunk, not the error
    
        class Silent(Timing):
            async def complete(self, messages: Sequence[Json], tools: Sequence[Json]) -> AsyncIterator[Json]:
                await asyncio.Event().wait()
                yield text("never")  # pragma: no cover
    
        stepped, transcript = Stepped(), MemoryTranscript()
        task = asyncio.create_task(reply(loop(Silent(stepped, transcript), transcript, stepped), "hi"))
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        (answer,) = entries(transcript, "assistant")
>       assert answer["content"] == STOPPED and answer["step"] == {"at": START}  # no chunk came
                                                ^^^^^^^^^^^^^^
E       KeyError: 'step'

bh-02/plugins/agent-cordis-plugin/tests/test_agent_records.py:281: KeyError
=========================== short test summary info ============================
FAILED bh-02/plugins/agent-cordis-plugin/tests/test_agent_records.py::test_a_step_that_failed_or_was_stopped_has_a_record_of_what_came_before_it
1 failed, 2602 passed, 6 skipped, 1 xfailed in 209.09s (0:03:29)
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
INFO    -  Building documentation to directory: /home/user/bh-02-sub/site
INFO    -  Documentation built in 5.88 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Re-review (reviewer): closed. The decision-0002 regression is fixed in d957d98: ALWAYS_REFUSED = ('memory:auto',) in agents.py is joined to the config's refused, so no layer can drop it. The new parametrized wiring test (refused unset, refused empty) refuses the call and mounts no child. DRAFT-0028 was archived by the lead. Criteria #1 and #2 are met; child.py still names no other plugin's component, since the floor lives in agents.py. Full check at HEAD 2a306af: first line is uv's UV_NATIVE_TLS deprecation warning; 2602 passed and 1 failed. The one failure is an unrelated timing flake in agent-cordis-plugin (test_agent_records, sleep(0.01) before cancel); it passed 13 reruns and was filed as a draft. Open minor point, no task: the refusal message lists every refused component, not the one the offending row uses.
<!-- SECTION:NOTES:END -->
