---
id: TASK-0095
title: >-
  Refuse an ENDPOINT/ID name when its endpoint table has a problem, and tidy
  discovery's edges
status: To Do
assignee: []
created_date: '2026-10-14 10:40'
labels:
  - models
  - size-2
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Filed from TASK-0088's close review (should-fix and nits, not blocking). Should-fix: named.find (named.py ~704-717) and not_a_model (~720) derive a model for ENDPOINT/ID even when the endpoint's table has a problem (e.g. both id and discover = true, or a bad include): problem(host) reports it and listed/endpoints skip the table, yet --model, /model and a layer's default resolve through it. No network or trust impact; the person just gets a model from a table bh-02 calls broken. Fix: find/derived check problem(host) and the resolution says the table's problem with what to write. Nits: discovery.py ~89-94 checks the 1 MiB limit after appending a chunk (up to one chunk more is held); discovery.py ~96-101 lets an exception outside the caught set (UnicodeEncodeError from a non-ASCII key value in local.env, put in a header) out of refresh into /model, against its docstring's 'never raises for a server'; listing.py ~278 counts entries that are not dicts or have no id as 'ids not listed'.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 --model, /model and a layer default naming ENDPOINT/ID on an endpoint table with a problem are refused with that problem and what to write (models-file house style), and bh-02 still starts; a test, seen failing before the fix
- [ ] #2 A key line in local.env that cannot go in a header gives one line under /model's list, not an exception out of /model; a test
- [ ] #3 The body limit stops before holding more than 1 MiB, and the not-listed count says what it counts; scripts/check passes
<!-- AC:END -->
