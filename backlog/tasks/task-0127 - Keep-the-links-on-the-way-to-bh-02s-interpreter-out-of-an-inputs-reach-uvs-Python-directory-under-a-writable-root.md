---
id: TASK-0127
title: >-
  Keep the links on the way to bh-02's interpreter out of an input's reach (uv's
  Python directory under a writable root)
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 22:27'
updated_date: '2026-10-16 23:20'
labels:
  - runner
  - security
  - size-2
dependencies: []
modified_files:
  - bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/jail.py
  - bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/__init__.py
  - bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py
  - bh-02/plugins/runner-cordis-plugin/README.md
  - docs/bh-02/using/jail.md
  - pyproject.toml
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0126's worker, measured in bwrap. TASK-0126 denies writing the interpreter files bh-02 runs on, but a read-only mount on a file cannot hold the links on the way to it. In bh-02's venv layout with the project root holding uv's Python (a project opened at the home directory), .venv/bin/python leads through uv's ~/.local/share/uv/python/cpython-3.15-<platform> link to the versioned directory; with only the file denied, an input can mv that link away and plant its own tree at its name, and the next `uv run` on the host executes it. Closing it needs a policy decision (the owner's): deny the directories that hold each link on the way to the interpreter when they lie under a writable root (for uv, ~/.local/share/uv/python), or refuse a confined session whose writable roots contain bh-02's own interpreter or installation, or another rule.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The owner's chosen rule is written in the runner README's host section and decided by a pure function beside spec_for
- [x] #2 In a real bwrap jail, in the layout above, an input can neither replace nor rename any link on the way from sys.executable to the interpreter file, and a test plants it; seen failing before the fix
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Tests first, seen failing: the pure link_directories(links, writable) and spec_for(links=); a compile of a planted uv layout (walk, own venv left alone, supervisor); a real bwrap jail as tester under tini refusing every change to a link on the way (seen failing with the deny removed).
2. Fix in runner jail.py: pure link_directories beside spec_for, a pure _stepped and the shell _links_on_the_way (component by component, physical holder, 40-link limit), BrigJail.compile hands it sys.executable and <base_prefix>/bin/python3.
3. README writes bullet states the owner's rule, replaces 'Not held', updates the supervisor paragraph; jail.md; update the TASK-0124/0126 test that asserted the link is not held.
4. Probe the common layouts (own checkout, uv tool install, project = home, plain project with its own venv) and record what each denies.
### Risks
A deny equal to a root is not made (strictly under, as host/trusted/code: it would make the project read-only); a holder that contains the jail dir is refused by brig (fail closed); the purity gate on the walker; load-sensitive bwrap tests (re-run alone).
### Proof
Runner tests + bh-02/app/tests/test_python_repl.py as tester under tini; scripts/check bh-02/plugins/runner-cordis-plugin once at the end; scripts/arch-check --no-fix once (root pyproject and docs are outside the member).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner's decision, 2026-10-16 (in conversation): deny each link's directory. For every link on the way from sys.executable (and <sys.base_prefix>/bin/python3) to the interpreter file, deny writing the directory that holds that link when it lies under a root the jail may write (for uv: ~/.local/share/uv/python). Generic across uv, pyenv and other layouts; a project opened at the home directory keeps working confined.

What changed (bh-02/plugins/runner-cordis-plugin, plus docs/bh-02/using/jail.md and one budget line in the root pyproject.toml). The owner's rule: for every link on the way from sys.executable (and <sys.base_prefix>/bin/python3) to the interpreter file, deny writing the directory that holds that link when it lies strictly under a root the jail may write. Decided by the pure link_directories(links, writable) beside spec_for (public, re-exported); spec_for(..., links=) adds its result to write_denies. The shell is _links_on_the_way(names): it walks each name one path component at a time (a pure _stepped does each step: enter, leave on .., or replace a link by what it leads to, absolute from / and relative from the directory that holds it), so a link is found in the directory that physically holds it, including a link to a directory in the middle of a path (uv's cpython-3.15-<platform>) and a relative link with ..; the kernel's 40-link limit ends a loop. BrigJail.compile hands spec_for the chain for the same two names it already gave _interpreter_files. README (writes bullet, the host part) states the rule, what it denies by layout, the root case and the tests; the supervisor paragraph and supervisor_interpreter's docstring now say the base's bin/python3 link IS held (its directory is read-only), so the supervisor may run under it; jail.md says it in one clause. Budget: one name added to no-impure-functions.exclude (_links_on_the_way: readlink), after the decide split into _stepped.

What it denies in the common layouts (a probe on real symlink layouts built like uv's, not committed; the project = the root named):
1. bh-02 on its own checkout (uv run bh-02), project = the checkout: nothing new. .venv/bin holds the python link but .venv is sys.prefix, denied already; uv's Python directory is not under the checkout.
2. uv tool install (venv under ~/.local/share/uv/tools/bh-02), project a plain project elsewhere: nothing (none of the chain is under it).
3. Project = the home directory (tool venv or checkout venv, and uv's Python, all under it): ~/.local/share/uv/python (it holds the cpython-3.15-linux-x86_64-gnu link and the versioned directory with it) and the venv's bin where it is bh-02's (denied already with the venv). The rest of the home stays writable. Run in a REAL jail with project = /root (the real home) and the worker on the real uv Python 3.15.0b4: the worker started and ran, a file created in /root/.local/share/uv/python failed with Read-only file system, files beside it were written (probe, files removed).
4. A plain project with a .venv of its own (bin/python on uv's Python): NOT denied (writable: .venv/bin/pip, site-packages), because that venv is not on the way from bh-02's interpreter to its file.
5. A denied directory that is a writable root itself (project = uv's Python directory, or a venv's bin): not denied, as host/trusted/code are not: a root that is also a deny is a read-only project and every write of the session would fail; the person opened the project there to let the model write it. What stays: an input can rename that link in that one directory (probe: only the versioned directory's bin was added; the project root, which holds the cpython-3.15-linux link, was not). A judgement for the owner to confirm: the alternative is a read-only project (fail closed).

Evidence AC1: README text above; test_the_directory_of_each_link_on_the_way_to_the_interpreter_is_denied_where_it_is_writable (the pure decision: order, once each, outside every root, a root itself, a sibling name, spec_for puts them in write_denies, the usual project has none).
Evidence AC2: test_a_linux_jail_refuses_an_input_that_changes_a_link_on_the_way_to_the_interpreter_bh_02_runs_on, a real bwrap jail, planted uv layout under the project (venv python3 -> python -> uv/python/cpython-3.15-linux (a directory link) /bin/python3 -> python3.15; 4 links), as tester under tini (runuser -u tester -- env HOME=/home/tester tini -s -- .venv/bin/python -m pytest -p no:cacheprovider): the worker tries to replace each link by one planted beside it, rename it, remove it, and writes beside them. PASSED (not skipped) with the fix; FAILED with the *holders line commented out of spec_for's denies (AssertionError {'0 replace': 'done', '0 rename': 'done', '0 remove': 'No such file or directory', '1 replace': 'done', ...}: the links were replaced and renamed); PASSED again restored (cmp identical). Seen failing, as tester. Two more planted checks: the compile test (test_a_jail_denies_the_directory_of_each_link_from_the_interpreter_bh_02_runs_on_to_its_file: the walk alone holds the venv's bin when the venv is not sys.prefix; a project's own venv is left alone; the supervisor may run under the held python3 link) failed too with the deny removed (4 failed in all); and the walker test (relative links, .., a loop) failed with the .. handling removed and hung (terminated) with the 40-link limit removed.
TASK-0124/0126 tests updated, not weakened: test_a_jail_denies_the_interpreter_bh_02_runs_on_when_it_lies_in_the_project asserted the base's python3 link is not PID 1's Python; it now is the supervisor's (its directory is held), and the file is checked through _denied (its own deny is covered by the directory's, which uncovered drops). test_a_jail_does_not_run_its_supervisor_under_a_python_in_its_project_unless_a_deny_holds_it is unchanged and passes (a link not on bh-02's way is still skipped).

Checks: runner tests + bh-02/app/tests/test_python_repl.py as tester under tini (-n 2 --dist loadgroup): 126 passed, 2 skipped (seatbelt, darwin's), exit 0 (was 122 + 2; +4 tests). scripts/check bh-02/plugins/runner-cordis-plugin under tini, exit 0 read directly: format, lint, types, tests 86 passed 1 skipped, every gate, docs; tokens skipped (no bh-01 dist). The first run failed one gate (no-impure-functions on _links_on_the_way): fixed by the budget entry. scripts/arch-check --no-fix under tini exit 0 (root pyproject and docs are outside the member). The machine was shared with one other worker; no timing claimed. Not done: the full scripts/check (the reviewer's).

No repro: the failing plant needs the fix's deny commented out of spec_for, which a reviewer may not edit; the worker's run with it removed (links replaced and renamed) is recorded above.

Review: CLOSE. AC1 and AC2 met (tester run 126 passed, 2 skipped). Decide split done. Root-is-holder exception accepted, README states it. Should-fix filed as draft: ancestor-directory rename above a deny mount (unprobed).
<!-- SECTION:NOTES:END -->
