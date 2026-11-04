---
id: TASK-0190
title: >-
  A layer or patch that sets the agents row's config without rows fails at boot
  with a bare dataclass error
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-04T14:18:00Z'
updated_date: '2026-11-04T14:24:00Z'
labels:
  - subagents
  - size-1
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0187 made AgentsConfig.rows required. A patch's config replaces the layer's whole, so a user patch such as config = { start = 60 } on the agents row now fails at boot with cordis's generic 'agents: invalid config for AgentsConfig: __init__() missing 1 required keyword-only argument: rows' (component.py:140). That names the field but not what to write or where the shipped list is, against CLAUDE.md's rule that an error says what to do.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A layer naming subagents:parent without rows fails with a message that says to list the child's rows in the agents row's config and points to bh-02.toml's list
- [ ] #2 A test pins that message
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Cordis builds a dataclass config before the component runs, so annotate the parent's config as Mapping | AgentsConfig (cordis passes it through) and build AgentsConfig in wiring.py, turning the missing-rows TypeError into a message saying what to write and where bh-02.toml's list is. Proof: the committed repro fails before, passes after; the existing AgentsConfig() test stays.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
finish-moved: the lead asked for the acceptance criteria after promotion (the task had none when the worker began).

Correction: the task already carried criteria #1 and #2 when the worker began (the lead's brief said none); the worker added two duplicates, then removed them. The finish-moved label stays only because the lead asked for it.

Repro at 4057a84f2d0d, test files: bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py; command: `uv run pytest bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py -q -k names_no_rows` exited 1

```text
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
F                                                                        [100%]
=================================== FAILURES ===================================
_ test_an_agents_row_whose_config_names_no_rows_is_refused_saying_where_the_list_is _

    async def test_an_agents_row_whose_config_names_no_rows_is_refused_saying_where_the_list_is() -> None:
        """A patch's config replaces the row's whole, so `{ start = 60 }` drops the shipped `rows`: the
        row fails at boot, and `/explain agents` says to list the child's rows in the row's `rows` and
        where the shipped list is (bh-02.toml's agents row), not only which keyword is missing."""
        rows = _rows(_Model(parent=[]), _Screen(), agents=Row("agents", "subagents:parent", {"start": 60}))
        booted = await _bounded(boot((), rows, watch=None))
        await _bounded(booted.runtime.settle())
        assert booted.loader.status()["agents"] != "active"
        said = booted.loader.explain("agents")
>       assert "list the child's rows in the agents row's `rows`" in said
E       assert "list the child's rows in the agents row's `rows`" in 'agents#15: failed\n  error: TypeError("parent: invalid config for AgentsConfig: AgentsConfig.__init__() missing 1 req...nfig.__init__() missing 1 required positional argument: \'rows\'")\n  unloading agents#15\n  failed-inactive agents#15'

bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py:1889: AssertionError
=========================== short test summary info ============================
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_an_agents_row_whose_config_names_no_rows_is_refused_saying_where_the_list_is
1 failed, 57 deselected in 0.32s
```
<!-- SECTION:NOTES:END -->
