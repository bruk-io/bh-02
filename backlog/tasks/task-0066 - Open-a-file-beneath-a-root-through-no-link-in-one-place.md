---
id: TASK-0066
title: 'Open a file beneath a root through no link, in one place'
status: To Do
assignee: []
created_date: '2026-10-09 03:08'
updated_date: '2026-10-09 03:08'
labels:
  - memory
  - agent
  - extensions
  - security
dependencies:
  - TASK-0052
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Three packages open a file the model may have written by walking to it from a root a name at a time with `O_NOFOLLOW`, then reading it only when the descriptor says it is a regular file: memory's `reading._opened` (memory files in the project), agent's `system._head` (the project's `.git/HEAD`) and the extensions host (`.bh-02/plugins/*.py` and status.json). The copies have drifted: `O_NONBLOCK` on the directories in the extensions host only, `O_CLOEXEC` there only, a size cap of 4 MiB in memory (refused over it), a read of the first 4,096 bytes in agent and no cap in extensions, and decoding with replacement in two and strict in the third. All three already require a regular file with one name (`st_nlink == 1`). This is what keeps the host from reading a file the jail hides through a link the model made, so it belongs with the link walk in host-paths (TASK-0052), as one opener with the strictest flags. Found by the review against cordis of 2026-10-09 (the separation, duplicates and docs review).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The strictest flags are agreed first and written in this task's notes (every directory `O_DIRECTORY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, the file `O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, a regular file with one name, a size cap the caller gives), with why each one
- [ ] #2 host_paths has one opener: the file a sequence of names reaches beneath a root's descriptor, its bytes (or what a final link points to, for the caller to decide), raising OSError that says which part was a link, not a directory, or not a regular file with one name, or over the cap
- [ ] #3 memory, agent's `.git/HEAD` reader and the extensions host use it, each with its own cap and decoding; their tests still pass in what they assert
- [ ] #4 host-paths' tests hold the opener to a table: a link at each depth, a hard link, a pipe, a directory, a file over the cap, a file gone between the walk and the read
- [ ] #5 The opener is named in host-paths' purity budget, and the three callers' entries in the root budget shrink where they no longer open files themselves
<!-- AC:END -->
