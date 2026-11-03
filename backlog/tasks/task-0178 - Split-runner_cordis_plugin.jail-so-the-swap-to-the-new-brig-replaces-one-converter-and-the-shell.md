---
id: TASK-0178
title: >-
  Split runner_cordis_plugin.jail so the swap to the new brig replaces one
  converter and the shell
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T17:24:00Z'
updated_date: '2026-11-03T02:44:00Z'
labels:
  - runner
  - size-5
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the architecture review of the bh-02/brig seam, 2026-11-02 (TASK-0176). jail.py is about 1,400 lines with 33 exports, and its pure policy functions take and return the old brig's Spec and FsPolicy (spec_for returns a Spec; allowlisted, held and tripwired work on one), so the swap would rewrite nearly every signature. It also re-exports the old brig's group_alive, which app/tests/test_python_repl.py imports, and has two symlink walkers (_links_on_the_way and _linked_dirs) that return different sets for one interpreter.

Proposed, as a no-behaviour change against the old brig (like TASK-0176.06): policy.py, bh-02's own frozen Policy intent type with spec_for, the two lists, link_directories, readable_roots, told_reads and git_author, all pure and importing no brig; a bwrap-translation module (uncovered, mountable, held, tripwired); placeholders.py; a host-facts module (one link walk, the absent sets, the git identity); and the shell (BrigJail, _Jailed). One function converts Policy to the old brig's Spec, so the swap replaces that converter and the shell. Also: move the jail lock (/tmp/bh-02-jails-<uid>.lock) out of shared /tmp to under state_home, where another local user cannot create the name first (reasoned, not measured).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 spec_for returns bh-02's own Policy type, and exactly one function turns it into the old brig's Spec
- [x] #2 No module but the shell and that converter imports brig
- [ ] #3 No behaviour changes: the runner's tests pass unchanged but for imports, and scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Split jail.py into policy (Policy + pure fns), mounts, placeholders, facts, brig_spec (one converter), jail (shell); move lock to state_home; budgets moved; tests adapted to Policy field names.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal ("go through all of these tasks ... until we finish the entire migration; backwards compatible code should be removed and not kept").

Split jail.py (1396 lines) into: policy.py (Policy frozen intent + ReadModel, BrigConfig, spec_for, allowlisted, link_directories, readable_roots, told_reads, git_author, self_modify_denied; no brig), mounts.py (mountable, uncovered, held, tripwired, notice_for, graded, released_for; no brig), placeholders.py (MARK, records, place/clear_up/remove_placeholders, lock_path/open_lock; no brig), facts.py (one link walk, absent sets, git identity, present, interpreter_files; no brig), brig_spec.py (to_brig_spec: the one Policy -> old brig Spec function), jail.py (shell: BrigJail, _Jailed, launch, stack_for, supervisor_interpreter, host_interpreters; the module tests monkeypatch host_executable/base_prefix/prefix/SYSTEM_READABLE there, so they stay). Only jail.py and brig_spec.py import brig (grep). AC1 and AC2 ticked. AC3 NOT ticked: it names scripts/check, the reviewer's. Evidence: scripts/check bh-02/plugins/runner-cordis-plugin (format, lint, mypy, 115 passed 1 skipped, gates, docs) and scripts/arch-check --no-fix all ok; app tests test_python_repl/test_xdist_groups/test_host_values 47 passed. Policy field names differ from brig's (writable, write_denies, masks, readable, env_allow, env_set, channel), so test assertions on spec_for/allowlisted results changed names, plus imports; Policy canonicalises paths as brig's FsPolicy did (sorted, deduped, roots as antichain), so those assertions kept their values. Link walks: _linked_dirs and _links_on_the_way merged into facts.links_on_the_way returning _Link(entry, through); through=False marks a link the lookup ends at, which _linked_dirs excluded; the policy takes all entries, the Linux jail the through ones of each argv path (abspath first). Only difference: _linked_dirs resolved a '..' after a link lexically, the walk does it as the kernel does. Lock: now jails.lock beside the records in state_home/bh-02 (placeholders.lock_path), directory made 0700; seen failing with lock_path planted back to /tmp (2 new tests failed), passing after. conftest.py jail-lock text and the xdist test docstring updated; no code reads the old path; a /tmp/bh-02-jails-<uid>.lock left from before is just ignored. group_alive: re-export kept in runner_cordis_plugin: removing it changes no runtime behaviour but bh-02/app/tests/test_python_repl.py imports it and may not import brig (brig-one-adapter); the swap must replace it. Budgets: no-impure-functions entries: removed jail:remove_placeholders, jail:_lives (stale, named nothing), jail:_place, jail:_clear_up, jail:_links_on_the_way (5+_launch); added placeholders:remove_placeholders, place, clear_up, open_lock and facts:* (the module reads the host by purpose; the BrigJail methods that did that were covered by BrigJail.*). Net entries 6 -> 6 (incl. _launch). No over-exposed allow entries changed.
<!-- SECTION:NOTES:END -->
