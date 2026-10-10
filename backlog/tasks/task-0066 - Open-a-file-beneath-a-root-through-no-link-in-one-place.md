---
id: TASK-0066
title: 'Open a file beneath a root through no link, in one place'
status: Done
assignee: []
created_date: '2026-10-09 03:08'
updated_date: '2026-10-09 18:31'
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
- [x] #1 The strictest flags are agreed first and written in this task's notes (every directory `O_DIRECTORY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, the file `O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, a regular file with one name, a size cap the caller gives), with why each one
- [x] #2 host_paths has one opener: the file a sequence of names reaches beneath a root's descriptor, its bytes (or what a final link points to, for the caller to decide), raising OSError that says which part was a link, not a directory, or not a regular file with one name, or over the cap
- [x] #3 memory, agent's `.git/HEAD` reader and the extensions host use it, each with its own cap and decoding; their tests still pass in what they assert
- [x] #4 host-paths' tests hold the opener to a table: a link at each depth, a hard link, a pipe, a directory, a file over the cap, a file gone between the walk and the read
- [x] #5 The opener is named in host-paths' purity budget, and the three callers' entries in the root budget shrink where they no longer open files themselves
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The flags agreed (host_paths.beneath's docstring says the same):
- Every name: O_NOFOLLOW (a link the model made, on the way or at the end, could lead to a file the jail hides; one on the way stops the walk, Linked; one at the end is answered as Link(target) for the caller), O_NONBLOCK (a FIFO left in a file's place is never waited on; on a directory it costs nothing and holds on a system that opens before checking O_DIRECTORY), O_CLOEXEC (no program started meanwhile inherits a descriptor).
- Every name but the last: O_DIRECTORY (a file on the way is not walked through; NotADirectoryError).
- The file: O_NOCTTY besides (a terminal device opened never becomes bh-02's controlling terminal; stricter than the list the task named, at no cost).
- Then judged by the descriptor only: a regular file with one name (st_nlink == 1: a hard link has two, a file removed since it was opened has none), NotOneFile with its mode and names; no larger than the caller's cap, by fstat and by reading at most cap + 1 bytes, so a file that grew since is refused too (TooLarge), never cut short.
- Each name is one step: '', '.', '..' and a name with '/' are a ValueError (a '/' would walk the steps it joins following links; '..' would leave the root).
- The root is the caller's to trust, opened as named (a path, or a directory descriptor, dup'd and left open).

Callers' caps and decoding: memory 4 MiB (Claude Code's), decoded with replacement; agent's .git/HEAD 4,096 bytes (refused over it now, where it was cut short: a HEAD that long names no branch), decoded with replacement; the extensions host 256 KiB, decoded strictly (a source must be UTF-8). The extensions cap came with a fix: the worker read lines with asyncio's 64 KiB default, so an extension over about 64 KiB ended the worker and every extension with it; its server now reads lines of up to 2 MiB (256 KiB escaped as JSON), and a test loads a 200 KiB one through the real worker and refuses one over the cap (it fails without the limit).

Root budget: agent_cordis_plugin.system:_head and memory_cordis_plugin.reading:_opened left it; host_paths' budget names directory_beneath, read_beneath and _stopped.
<!-- SECTION:NOTES:END -->
