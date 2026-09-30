---
id: task-0029
title: 'A Linux jail whose bh-02 was killed is ended, not left running'
status: To Do
assignee: []
created_date: '2026-09-30 14:48'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0024. If bh-02 is killed (SIGKILL, crash) while a cell's background program runs, its bubblewrap jail keeps running with its mounts. The next session's sweep correctly leaves it and its placeholders alone, but nothing ever ends it, so a program the person thought stopped with bh-02 keeps running with project write access.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A jail's processes end when the bh-02 that started them dies, however it dies; a real-bwrap test kills bh-02 with SIGKILL while a cell's background program runs and shows the program gone
- [ ] #2 After that, the next session's sweep removes the dead jail's placeholders and record
- [ ] #3 darwin gets the same guarantee (a real seatbelt test), or the notes say why it already holds
- [ ] #4 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->
