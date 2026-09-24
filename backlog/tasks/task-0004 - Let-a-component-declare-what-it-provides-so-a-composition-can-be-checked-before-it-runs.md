---
id: task-0004
title: >-
  Let a component declare what it provides, so a composition can be checked
  before it runs
status: Done
assignee:
  - Claude
created_date: '2026-09-16 17:51'
updated_date: '2026-09-18 14:17'
labels:
  - cordis
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while restructuring bhh (task-0003). A component's dependencies are static (`Component.inject`, read from its signature) but what it provides is known only after it runs (`Fiber.bound`, filled by `bind_step`). So a layer that fills the wrong role, e.g. `id = "llm", use = "bhh-terminal:console"`, mounts fine and the mode waits forever on `Model`; `explain` diagnoses it after the fact, nothing refuses it.

Smallest change, in two steps: (a) `@component(provides=(Model,))` recorded on the Component, and a pure rule in `decisions.py` applied at activation in `_lifetime` that fails a fiber which declared a key and did not bind it, making the README's "what it provides is what it binds" a checked property; (b) a pure `unsatisfiable(components)` over declared provides vs injects that `boot` reports before any effect runs ("mode needs Model; no row provides it"). Do not make the row `id` a role; it is a diagnostic name and a patch target.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A `@component(provides=(...))` records declared provides on the Component
- [x] #2 A pure rule in decisions.py, applied at activation in _lifetime, fails a fiber that declared a key it did not bind
- [x] #3 A pure `unsatisfiable(components)` checks declared provides vs injects across a composition
- [x] #4 `boot` reports unsatisfiable compositions before any effect runs, with an actionable error message (e.g. "mode needs Model; no row provides it")
- [x] #5 Row `id` is not treated as a role/type — only declared `provides` types are checked
- [x] #6 New pure rules have a no-runtime test in cordis/tests/test_decisions.py
- [x] #7 cordis/tests/test_invariants.py passes
- [x] #8 scripts/arch-check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Keys are strings (Key = str); existing components bind under string keys (bind("llm", ...)), so `provides` is a frozenset[Key] on Component, parallel to `inject` — string keys, confirmed with user (not type-based matching).

Step (a):
- Add `provides: frozenset[Key] = frozenset()` to `Component` (component.py).
- Thread `provides` through `derive`/`_read`: accept it as an explicit decorator arg (no signature position implies it, unlike inject).
- Add `provides=` to the `@component` overloads and implementation in authoring.py.
- Add a pure rule in decisions.py: `check_provided(owner: str, declared: frozenset[Key], bound: Set[Key]) -> None` (naming may adjust), raising when `declared - bound` is nonempty, with an actionable message.
- Call it in `_lifetime` (runtime.py) at fiber activation, alongside the existing `_check_contracts` call — this is the imperative half.

Step (b):
- Add a pure `unsatisfiable(components: Iterable[Component]) -> ...` in decisions.py: declared provides vs declared injects across a composition, returning what's missing.
- Wire into `boot` (locate exact call site — bhh bootstrap or cordis composition/loader) so it reports before any effect runs, with message style like "mode needs Model; no row provides it".
- Row `id` stays a diagnostic name / patch target, never a role — only declared `provides` keys are checked.

Tests:
- Pure rule tests with no runtime in cordis/tests/test_decisions.py.
- Run cordis/tests/test_invariants.py after touching runtime.py.
- Run scripts/arch-check (new public names need over-exposed-module-symbol allow entries if unused elsewhere; check import-boundaries if any new module).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Step (a) done: Component.provides (frozenset[Key]) threaded through component.py/authoring.py; decisions.py has UnboundProvide/check_provided (declared-bound raises, called from _lifetime only when unchanged() so a mid-setup target retarget doesn't spuriously fail) and Declared/unsatisfiable (pure, no Component import to keep decisions.py's effects-only boundary). Tests in test_decisions.py. Full suite (520), invariants (360), mypy, arch-check all green. Now wiring unsatisfiable into Loader.apply for step (b).

Step (b) done: unsatisfiable(components: Iterable[Declared]) in decisions.py (pure); Loader._entries/_unsatisfiable_rows in loader.py resolve entries and call it; boot() calls report() per unsatisfiable row before rt.mount (the first effect) when report is set. Message: '<row id> needs <keys>; no row provides it'.

Scope change (confirmed with user via AskUserQuestion): retrofitted every shipped plugin's binding components with provides= so the check doesn't false-positive on undeclared-but-correct rows: tools-cordis-plugin.registry, ollama-cordis-plugin.completion, claude-agent-sdk-cordis-plugin.model/agent, agent-cordis-plugin.transcript/loop, terminal-cordis-plugin.console. Also updated test-fixture components in bhh/tests/conftest.py and cordis/tests/conftest.py (echo_model, angry_model, held_model, silent_ui, subprocess, git, git_tools) for the same reason — they're components too and were producing false-positive reports that broke bhh's CLI test assertions. fs-cordis-plugin.filesystem, terminal-cordis-plugin.approver, chat-cordis-plugin.session/ask bind nothing (acquire/background only) so provides stays empty by default — correct, not an oversight.

New test: test_boot_reports_a_row_whose_inject_nothing_declares_provides_for in cordis/tests/test_loader.py.

Final verification: full suite 527 passed, test_invariants 360 passed, mypy clean, scripts/arch-check clean, ruff format/check clean. Task complete.

Post-review fixes (advisor caught these before commit): (1) decisions.py docstring said unsatisfiable -> Loader.apply, corrected to -> boot (where it's actually wired). (2) unsatisfiable() previously let a row's own declared provides satisfy its own inject — fixed to exclude self, since a fiber can only activate once its deps are already bound, so self-injection is always a deadlock; updated/added tests in test_decisions.py accordingly. (3) Added two defensive tests in test_runtime.py confirming check_provided does NOT mask a real setup failure (component raises after partial binds — the original exception surfaces, not UnboundProvide) — confirmed already correct by the existing try/except structure, now pinned by a test. (4) Documented provides=/check_provided/unsatisfiable in cordis/README.md (The rule, Binding concept, capability example) and CONTRACTS.md (note that the Bound-by table is backed by checked provides= declarations). bhh/README.md's plugin table already matched the retrofit, no change needed. Full suite 530 passed, invariants 360 passed, mypy/arch-check/ruff clean.
<!-- SECTION:NOTES:END -->
