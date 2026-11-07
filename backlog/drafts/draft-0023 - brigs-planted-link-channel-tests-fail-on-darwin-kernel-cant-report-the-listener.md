---
id: DRAFT-0023
title: >-
  brig's planted-link channel tests fail on darwin: kernel can't report the
  listener
status: Draft
assignee: []
created_date: '2026-11-07 06:53'
labels:
  - brig
  - tests
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In TASK-0201's full check (2026-11-07, macOS 27): libs/brig/tests/integration/test_channel_planted_link.py::test_a_listener_that_left_after_listening_is_refused and ::test_a_link_planted_with_the_empty_stack_is_refused_by_readiness_and_connect fail with EndpointRefused '... the kernel could not report who listens there ([Errno 57] Socket is not connected)' from brig/run/dial.py:219. Unrelated to TASK-0201's change; keeps scripts/check red on the Mac.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Both tests pass on macOS and Linux, still asserting the refusal they were written to, or the cause is in the notes if the product is wrong
<!-- AC:END -->
