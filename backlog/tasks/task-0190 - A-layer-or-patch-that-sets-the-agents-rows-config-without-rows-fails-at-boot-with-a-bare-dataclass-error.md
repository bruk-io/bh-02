---
id: TASK-0190
title: >-
  A layer or patch that sets the agents row's config without rows fails at boot
  with a bare dataclass error
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-04T14:18:00Z'
updated_date: '2026-11-04T14:40:00Z'
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
- [x] #1 A layer naming subagents:parent without rows fails with a message that says to list the child's rows in the agents row's config and points to bh-02.toml's list
- [x] #2 A test pins that message
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

Fix: wiring.py builds AgentsConfig itself (config annotated Mapping | AgentsConfig, so cordis passes the payload through) and raises a TypeError saying to list the child's rows in the agents row's rows, with bh-02.toml's agents row as the shipped list. The repro test (commit 4057a84, recorded) failed before and passes after. pytest on the plugin: 139 passed; mypy clean; scripts/check bh-02/plugins/subagents-cordis-plugin exit 0 (first line is the uv NATIVE_TLS deprecation warning; the '== format' section follows). Criteria left unticked for the reviewer.

Check `scripts/check` exited 0

(11 earlier lines omitted)
```text
bringing up nodes...
bringing up nodes...

........................................................................ [  2%]
........................................................................ [  5%]
..s..................................................................... [  8%]
.............x.......................................................... [ 11%]
........................................................................ [ 13%]
........................................................................ [ 16%]
........................................................................ [ 19%]
..............................s......................................... [ 22%]
........................................................................ [ 24%]
........................................................................ [ 27%]
........................................................................ [ 30%]
........................................................................ [ 33%]
........................................................................ [ 35%]
..............................s.s....................................... [ 38%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 49%]
........................................................................ [ 52%]
........................................................................ [ 55%]
........................................................................ [ 58%]
........................................................................ [ 60%]
........................................................................ [ 63%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 85%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 96%]
........................................................................ [ 99%]
..............                                                           [100%]
2601 passed, 6 skipped, 1 xfailed in 187.91s (0:03:07)
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
INFO    -  Building documentation to directory: /home/user/bh-02-sub/site
INFO    -  Documentation built in 5.09 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (reviewer, not the worker): every criterion met and ticked; close-task refused. scripts/check full tier exit 0 (2601 passed; first line is uv's UV_NATIVE_TLS deprecation warning, then '== format', nothing reformatted). #1: _agents_config raises at the generator's first line, before any effect, so the row fails and /explain carries the message; the repro test asserts both phrases in loader.explain('agents'). #2: that test. The Mapping | AgentsConfig annotation does not weaken the contract: cordis's configure() only builds the dataclass, which _agents_config now does (unknown keys still refused, still before any effect; Row.config defaults to {}). Criteria clean: #1 and #2 only. close-task refusal: 'the repro test file changed since 4057a84'. The repro test itself is unchanged from 4057a84 through 3cff21d; the file changed only in 63d6f38 (TASK-0189, another test in the same file). Status left In Progress for the lead: close by hand-off once the script accepts, or record a new repro on HEAD.
<!-- SECTION:NOTES:END -->
