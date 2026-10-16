---
id: TASK-0124
title: Never choose a supervisor interpreter under a root the jail may write
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 13:48'
updated_date: '2026-10-16 22:06'
labels:
  - runner
  - security
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0084.02's close review. supervisor_interpreter(found, mounted) takes the first candidate (/usr/bin/python3, then <sys.base_prefix>/bin/python3) whose spelling and resolved target are under the Spec's read_allows, and read_allows include the project and the jail's other writable roots. If bh-02's base interpreter ever lay under one of them (a project opened at a directory that holds the uv-managed Python, such as the home directory), the jail's PID 1 would run an interpreter the model can write. Check first whether the runner's spec_for already denies writing it (bh-02/CLAUDE.md: what the host trusts, the jail keeps from the model); if it does, record that and add the test; if not, exclude candidates under a write root.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 supervisor_interpreter never returns a candidate whose spelling or resolved target is under a root the jail may write unless that path is denied to writes, shown by a test with the base interpreter under a writable root
- [x] #2 The decision stays one pure function; the runner's existing tests pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Finding first (probe in scratch, not committed): spec_for does NOT deny the base interpreter's binary when the project root holds base_prefix. Venv layout (bh-02's uv run, prefix = the venv): host holds base's stdlib dirs (sys.path, under the root, so denied) but not <base_prefix>/bin/python3, so the binary is not in write_denies (checked with root=/root, the uv Python under it). No-venv layout (prefix == base_prefix, in host): the whole base tree is denied, binary included. So AC1 needs the supervisor_interpreter change, not a spec_for change.
Plan: 1. supervisor_interpreter(found, mounted, *, writable=(), denied=()): a candidate's spelling and target count when each is under a mounted root and, if under a writable root, under a write deny (one pure function; defaults keep the existing test's two-argument calls). compile passes the final spec's write_allows and write_denies. 2. Tests: a pure test (base under a writable home, target check, deny holds it, sibling name not) and a compile-level test: the base-like link under the project is not the PID 1 unless the policy's own deny holds it (BrigConfig(deny=)). 3. Docstrings and the runner README's supervisor paragraph say the rule. Planted: remove the writable check, the compile test must fail (the link chosen). Proof: runner tests and test_python_repl.py as tester under tini; scripts/check bh-02/plugins/runner-cordis-plugin once at the end, scripts/check bh-02/app --no-gates --no-docs. Risk: a candidate excluded by writability falls to /usr/bin/python3, which brig refuses with the TASK-0123 message if absent; the message is then accurate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Finding (probe in the scratchpad, not committed): spec_for does NOT deny bh-02's base interpreter's binary when the project root holds it. Probe with root=/root (the uv Python under it), host = sys.path plus the venv's prefix (bh-02's uv run layout): the base stdlib directories are denied (they are sys.path entries under the root), <base_prefix>/bin/python3 is not in write_denies. With no venv (prefix == base_prefix, in host) the binary is denied. So the fix is in the choice, not in spec_for.
What changed (bh-02/plugins/runner-cordis-plugin): supervisor_interpreter(found, mounted, *, writable=(), denied=()) is still the one pure function (two inner helpers, no I/O). A candidate's spelling and its target each count when under a mounted root and, if under a writable root, under a write deny. BrigJail.compile passes the Spec's write_allows and its final write_denies. Docstrings and the README's supervisor paragraph say so. The existing two-argument test is unchanged.
Tests: test_the_supervisor_never_runs_under_a_python_an_input_can_write_unless_a_deny_holds_it (pure: base under a writable home, a deny holds it, a sibling deny does not, a target into the writable tree is refused); test_a_jail_does_not_run_its_supervisor_under_a_python_in_its_project_unless_a_deny_holds_it (compile: a Python in the project is PID 1 only with BrigConfig(deny=) holding it).
Evidence AC1: planted, the writable check removed from whole() (candidate under mounted only): both new tests FAILED (2 failed, 6 passed); restored, 8 passed.
Evidence AC2: the existing test_the_supervisor_runs_under_the_first_interpreter_the_jail_holds_whole passes unchanged. runner tests + bh-02/app/tests/test_python_repl.py as tester under tini (-n 2 --dist loadgroup): 119 passed, 2 skipped, 67 s, the machine shared with two other workers, no timing claimed.
Checks (root, under tini): scripts/check bh-02/plugins/runner-cordis-plugin exit 0: format (13 files formatted), lint, types (7 source files), tests 79 passed 1 skipped, every gate, docs. scripts/check bh-02/app --no-gates --no-docs exit 0: format, lint, types, 238 passed 1 skipped, tokens skipped. scripts/arch-check not run: nothing outside a member changed. brig unchanged (git diff d552a08 -- libs/brig is empty).
Observation, not filed: in bh-02's own venv layout with the project at the home directory, spec_for leaves <base_prefix>/bin/python3 writable by an input, and the host runs bh-02 on that interpreter; a later host start could run what an input wrote there. TASK-0124 closes only the PID 1 path. spec_for would need to deny the base binary too (a policy decision, to be sized by the owner).
<!-- SECTION:NOTES:END -->
