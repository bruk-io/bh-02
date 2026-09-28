---
id: task-0021
title: >-
  A reply that streamed only thinking before Claude Code retried its stream is
  not cut short
status: To Do
assignee: []
created_date: '2026-09-28 13:16'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing task-0020, by reading Claude Code's CLI (2.1.282): after a stream that showed only thinking, the CLI emits a made-up message_stop and then retries the stream. The provider would read that as a finished step with nothing said, cut it, and drop the real reply that follows, so the person sees an empty or failed turn. Not yet seen live; confirm it and handle it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Whether the CLI emits that order is confirmed from its code or a live log, with the evidence recorded in the notes
- [ ] #2 If it does: a test with the fake Claude Code reproduces the order and fails first, and afterwards the reply that follows the retried stream is what the loop receives
- [ ] #3 If it does not: the notes say why, and nothing changes
- [ ] #4 Existing provider tests and scripts/check pass
<!-- AC:END -->
