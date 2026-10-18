---
id: DRAFT-0008
title: 'Make chat''s interrupt test wait for its condition, not 10 ms'
status: Draft
assignee: []
created_date: '2026-10-18 20:31'
labels:
  - chat
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bh-02/plugins/chat-cordis-plugin/tests/test_chat.py:60-82 (test_an_interrupt_stops_the_reply_says_so_and_the_session_carries_on) waits asyncio.sleep(0.01) for the stop event; under scripts/check's pytest -n auto it failed during TASK-0148's review (screen.events held only the text event), and passed 3/3 run alone. It stops scripts/check being green for unrelated work.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The test waits for the stop event (bounded) instead of a fixed sleep, and passes under pytest -n auto --dist loadgroup repeatedly
<!-- AC:END -->
