---
id: TASK-0185
title: /restart ui or /restart jobs cancels itself and ends the session
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T13:50:00Z'
labels:
  - commands
  - cordis
  - size-3
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (reproduced in memory): commands:jobs runs each restart in its own row's task (cordis_helpers.perform); jobs depends on output, which the ui row binds, so restarting ui or jobs reloads jobs and cancels the restart halfway. cordis's Loader.restart (libs/cordis/src/cordis/loader.py) unmounts then mounts with no cancellation guard. Seen: /restart jobs drops the jobs row from loader.status() and leaves operator inactive; /restart output never remounts output; in the app chat needs jobs and the session ends. GLOSSARY.md and commands' wiring say the ui never reloads; it does. Proposed: Loader.restart/apply finish once begun (shielded inner task, or mount in finally), and /restart refuses a row jobs depends on, or the queue lives at loader scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A /restart either finishes with every row back up or refuses and says why; it never leaves rows unmounted; repro test: ui, jobs and operator rows, /restart ui then /restart jobs, and every row is active with output remounted
- [ ] #2 GLOSSARY.md and the commands wiring docstring say what /restart does to the ui and jobs
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).

Repro at 2aa4b7d8ad24, test files: bh-02/plugins/commands-cordis-plugin/tests/test_restart.py; command: `uv run pytest bh-02/plugins/commands-cordis-plugin/tests/test_restart.py -q` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
F                                                                        [100%]
=================================== FAILURES ===================================
_________ test_restarting_the_ui_or_jobs_never_leaves_a_row_unmounted __________

    async def test_restarting_the_ui_or_jobs_never_leaves_a_row_unmounted() -> None:
        booted = await boot(
            [],
            overrides=[
                Row("commands", "commands_cordis_plugin.wiring:registry"),
                Row("ui", f"{__name__}:_ui"),
                Row("jobs", "commands_cordis_plugin.wiring:jobs"),
                Row("operator", "commands_cordis_plugin.wiring:operator"),
            ],
            watch=None,
        )
        rt, loader = booted.runtime, booted.loader
        every_row_up = {rid: "active" for rid in ("commands", "ui", "jobs", "operator")}
        assert await _settled(loader.status, every_row_up) == every_row_up
        for line in ("/restart ui", "/restart jobs"):
            await rt.root.get("commands").run(line)
            await asyncio.sleep(0.2)
>           assert await _settled(loader.status, every_row_up) == every_row_up, line
E           AssertionError: /restart ui
E           assert {'commands': ...': 'inactive'} == {'commands': ...or': 'active'}
E             
E             Omitting 1 identical items, use -vv to show
E             Differing items:
E             {'jobs': 'inactive'} != {'jobs': 'active'}
E             {'operator': 'inactive'} != {'operator': 'active'}
E             Right contains 1 more item:
E             {'ui': 'active'}
E             Use -v to get more diff

bh-02/plugins/commands-cordis-plugin/tests/test_restart.py:52: AssertionError
=========================== short test summary info ============================
FAILED bh-02/plugins/commands-cordis-plugin/tests/test_restart.py::test_restarting_the_ui_or_jobs_never_leaves_a_row_unmounted
1 failed in 9.40s
```

Fix (a), no cordis change: Operator.restart refuses the jobs row and every row it depends on, directly or transitively (computed from each entry's component inject/provides, resolved in wiring.py), with a message naming the row and why. Repro test bh-02/plugins/commands-cordis-plugin/tests/test_restart.py (real boot: commands, ui, jobs, operator rows) recorded failing before the fix (jobs and operator inactive, ui gone after /restart ui; commit 2aa4b7d); passes after, and /restart operator still restarts. scripts/check bh-02/plugins/commands-cordis-plugin exit 0. Docs: GLOSSARY ui and jobs entries, jobs wiring docstring, commands README, docs/bh-02 rows-and-layers. Criteria left unticked for the reviewer. Not fixed: Loader.restart still has no cancellation guard in cordis (any other caller running inside a dependent row's task would hit it); that is a cordis design question for the owner.
<!-- SECTION:NOTES:END -->
