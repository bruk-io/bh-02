---
id: DRAFT-0028
title: >-
  A write grant on a path that is gone fails every start instead of being left
  out
status: Draft
assignee: []
created_date: '2026-11-04T18:15:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0181.04. policy.admitted leaves out a read grant whose path is missing (told in Policy.refused), but not a write grant: spec_for adds it to writable, and brig's create_bwrap_jail raises PolicyRootAbsent for a writable root that does not exist. An always-grant in the store on a directory later removed (a deleted worktree, a cleaned build dir) therefore fails every jailed start until the person edits the grants file by hand, with brig's wording rather than bh-02's. The same applies to a grant under a config.hide path (brig PolicyMaskHides). Evidence: bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/policy.py admitted() checks exists() only for Kind.READ; brig domain/policy/paths.py refusal() returns RootAbsent and MaskHides.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A write grant whose path is not there is left out of the policy and its reason is in Policy.refused, told in the start's notice
- [ ] #2 A read or write grant under a hide path is left out with its reason rather than failing the start
- [ ] #3 A unit test covers each
<!-- AC:END -->
