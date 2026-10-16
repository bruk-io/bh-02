---
id: TASK-0126
title: The jail must not let an input write the Python bh-02 itself runs on
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 22:06'
updated_date: '2026-10-16 22:29'
labels:
  - runner
  - security
  - size-1
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0124's worker (2026-10-16), probing spec_for in bh-02's own venv layout with the project root holding the uv-managed Python (a project opened at the home directory): <sys.base_prefix>/bin/python3 is not in the Spec's write_denies (the base standard library directories are), so an input can write the interpreter bh-02 itself runs on, and the next bh-02 start on the host runs what it wrote, outside any jail. With no venv (prefix == base_prefix) it is denied. bh-02/CLAUDE.md's rule: what the host trusts, the jail keeps from the model (a file the host reads and trusts, or code it imports, is in host and runner:confined denies writing it); the interpreter the host executes is the plainest case of that. TASK-0124 only stopped the supervisor from choosing such an interpreter as the jail's PID 1; this is the host side.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 spec_for denies writing the interpreter bh-02 runs on (sys.executable, <sys.base_prefix>/bin/python3 and each one's resolved target) whenever it lies under a root the jail may write, in a venv layout and without one
- [x] #2 A test plants the layout (the base interpreter under the project root, in a venv layout) and shows the write denied; seen failing before the fix
- [x] #3 Shown in a real bwrap jail: an input's write to that interpreter path is refused
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Finding (re-probed, scratch): with root=/root (uv Python under it) and host = sys.path + the venv prefix, none of sys.executable's target nor <base_prefix>/bin/python3's target is in write_denies (stdlib dirs are). Measured in bwrap (root, scratch): a --ro-bind of a LINK lands on the file it leads to, so a write through the link and a write to the file are both EROFS, but the link's own entry can be renamed (mv rc 0), and a link that dangles in the jail fails the launch. So a deny must name the FILE to hold anything.
Plan: 1. Tests first, seen failing: (a) pure spec_for test: base interpreter under a home root in a venv layout (host = stdlib dirs + venv prefix) and without a venv; the interpreter files are denied, a sibling name and one outside every writable root are not. (b) compile-level test: venv layout planted under tmp_path (module facts executable, base_prefix, prefix, import_path patched), Spec denies the resolved base interpreter, and the supervisor is not run under the base python3 link. (c) real bwrap jail: an input's write/rename/unlink of the planted interpreter file and of its python3 link is refused, a neighbour file writes. 2. Fix: spec_for(..., interpreters=()) denies each interpreter file strictly under a write root (pure; a root itself and paths outside stay); BrigJail.compile hands it the resolved files of sys.executable and <sys.base_prefix>/bin/python3 (module-level private helper, skips an empty name). 3. README (host and supervisor paragraphs) and docstrings say it; the supervisor paragraph's claim that spec_for does not deny bin/python3 is updated (the link entry is still not held, the file is). Risks: a deny on a link is the file's (brig resolves), so only files are listed; a launch must not fail on a dangling name; denying a root itself would make the project read-only (strictly under only, as host). Proof: new tests planted (fix removed) fail; runner tests + bh-02/app/tests/test_python_repl.py as tester under tini; scripts/check bh-02/plugins/runner-cordis-plugin once.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
What changed (bh-02/plugins/runner-cordis-plugin): spec_for(..., interpreters=()) denies each interpreter file strictly under a writable root (the pure decision, next to host/trusted/code; a root itself and a path outside every root stay as they were; the socket directory counts as a root too). BrigJail.compile hands it _interpreter_files((sys.executable, <sys.base_prefix>/bin/python3)): where each name leads with every link followed (an empty name, an embedded interpreter, is skipped). README (writes bullet, supervisor paragraph), jail.py docstrings and docs/bh-02/using/jail.md say it. brig unchanged.
DEVIATION to judge (AC1 wording): the Spec lists the interpreter's FILES (resolved), not a link's own spelling. Measured in bwrap (scratch, root): a --ro-bind of a link lands on the file it leads to, so a write to the file and one through the link are both refused (EROFS), but the link's own entry can still be renamed (mv rc 0); and a deny on a link that dangles in the jail fails the launch (bwrap: Can't create file at ...). brig resolves a write deny to its realpath on bwrap and seatbelt alike, so a link spelling adds nothing the file does not hold, and would make the final write_denies claim a hold the jail does not have (supervisor_interpreter reads them: a base python3 link would have become an accepted PID 1 Python that an input can replace; TASK-0124's guarantee stays because the link is not in the denies; the compile test asserts it). Every name (sys.executable, python3, the venv's python links) is refused for writing in the real jail through the file; shown below.
Finding re-probed: root=/root (uv Python under it), host = sys.path + venv prefix: neither sys.executable's target nor <base_prefix>/bin/python3's target was in write_denies (the stdlib dirs were), as TASK-0124 said. After the fix a real compile with the project at /root (probe, not committed) lists /root/.local/share/uv/python/cpython-3.15.0b4-linux-x86_64-gnu/bin/python3.15 in write_denies.
Tests (tests/test_runner_confined.py): test_the_interpreter_bh_02_runs_on_is_denied_where_an_input_could_write_it (pure, venv layout and none, sibling name, outside every root, project = its directory, a root itself); test_a_jail_denies_the_interpreter_bh_02_runs_on_when_it_lies_in_the_project (compile of a venv layout planted under tmp_path with sys facts patched: the base file denied beside the stdlib, the python3 link not, the supervisor not run under the link, run under the held file); test_a_linux_jail_refuses_an_input_that_writes_the_interpreter_bh_02_runs_on (real bwrap jail, planted file + link under the project: write, write through the link, rename and remove are refused, a file beside it is written, the file's bytes unchanged).
Evidence AC2 (seen failing): with the fix's line removed (*interpreter dropped from the denies) the three new tests FAILED (3 failed), the real-jail one with {'write': 'done', 'write through the link': 'done', 'rename': 'done', ...}: the input wrote and renamed the planted interpreter; restored (cmp identical), 3 passed. The pure test fails with TypeError before the parameter exists.
Evidence AC3: real bwrap jail, as tester under tini (runuser -u tester -- env HOME=/home/tester tini -s -- .venv/bin/python -m pytest -p no:cacheprovider): test_a_linux_jail_refuses_an_input_that_writes_the_interpreter_bh_02_runs_on PASSED (not skipped), and FAILED with the line removed (above).
Checks: runner tests + bh-02/app/tests/test_python_repl.py as tester under tini (-n 2 --dist loadgroup): 122 passed, 2 skipped, 58 s (was 119+2 before; +3 tests), the machine shared with two other workers, no timing claimed. scripts/check bh-02/plugins/runner-cordis-plugin under tini exit 0: format, lint, types (7 source files), tests 82 passed 1 skipped, every gate (root, brig, cordis, cordis-helpers, host-paths), docs; tokens skipped (no bh-01 dist). scripts/arch-check --no-fix under tini exit 0 (docs/bh-02/using/jail.md is outside a member).
NOT held, found while measuring, not fixed (a policy call, needs the link's directory denied, which a mount of the file cannot do): the entry of a link in a writable directory, and a link directory on the way to the file. In the incident layout the venv's python leads through uv's cpython-3.15-linux-x86_64-gnu (a link to the versioned directory) under ~/.local/share/uv/python: measured in bwrap with only the file denied, an input could mv that link away and plant a tree of its own at its name (rc 0), and the next uv run / .venv/bin/python would execute it. Closing it means denying ~/.local/share/uv/python (or each link's directory) when under a writable root. README says so under the writes bullet.

Orchestrator ruling, 2026-10-16: criterion 1 is met by denying the interpreter files (each name followed to the file it leads to), not the link names. Measured by the worker in bwrap: a read-only bind on a link lands on its target, brig resolves write denies to the realpath on bwrap and seatbelt alike, and a link spelling in the denies would make TASK-0124's supervisor_interpreter accept a replaceable link as PID 1's Python. Every write to the interpreter, through any of its names, is refused in a real jail. The links on the way to it (a link's own entry, uv's cpython-3.15-<platform> link to the versioned directory) are not held by a file mount: filed separately as a policy question for the owner.

No repro: the fixed tree has no failing test to record; the worker's plant (the interpreter deny removed, three new tests failing, the real-jail one showing the write and rename done) is recorded above.
<!-- SECTION:NOTES:END -->
