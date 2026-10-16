---
id: TASK-0122
title: Make the docs' strict build fail on a link to an anchor that is not there
status: To Do
assignee: []
created_date: '2026-10-16 13:35'
labels:
  - docs
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0104.02: a planted link to a missing anchor in a README (`[old](#detached-and-on-the-subscription-only)`) left `mkdocs build --strict` at exit 0 with only an INFO line, because mkdocs.yml sets no `validation.links.anchors` and mkdocs 1.6 defaults it to info. So scripts/check's docs step, the one definition of green, passes a broken anchor. Setting `validation: links: anchors: warn` makes --strict fail on it; first see what the existing docs would fail on, and fix those in the same change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scripts/check's docs step fails on a link to a missing anchor, shown by a planted link seen failing and then removed
- [ ] #2 The docs as they are build clean under that setting, any broken anchors it finds fixed in the same change
<!-- AC:END -->
