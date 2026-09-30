---
id: task-0030
title: >-
  A jail record written just before a crash never leads the sweep to remove the
  person's directories
status: To Do
assignee: []
created_date: '2026-09-30 14:48'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0024. A Linux jail writes its record (the placeholders it will make) before bubblewrap starts, and marks each placeholder only once the jail is up. If bh-02 crashes between the two, the record holds paths without marks, and the next sweep removes any empty directory at those paths, which could be one the person created in the meantime.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The sweep removes a directory only when it can prove the jail made it; a record with unmarked paths removes nothing it can't prove
- [ ] #2 A test writes such a record, has the person create an empty directory at one of its paths, and shows the sweep leaves it
- [ ] #3 A crash in that window still leaves nothing behind that stays forever, or the notes say what remains and why that's acceptable
- [ ] #4 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->
