---
id: DRAFT-0001
title: Report Backlog.md's project_name quote stripping upstream
status: Draft
assignee: []
created_date: '2026-10-10 12:14'
labels:
  - backlog
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Backlog.md 1.53.0 reads `project_name` with `replace(/['"]/g, "")`, which strips every quote character in the value rather than the quotes around it (its own `zq` helper strips only those), so "Bruk Habtu's Harness" reads as "Bruk Habtus Harness", and any rewrite of config.yml saves it so. Worked around in e063b68 with a typographic apostrophe, which the reader leaves alone. Reporting it is a post outside this repository, so it is the owner's to send or drop. A draft until it is accepted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An issue on Backlog.md describes the bug, with the line that strips the quotes and a minimal config, or the owner decides not to report it
<!-- AC:END -->
