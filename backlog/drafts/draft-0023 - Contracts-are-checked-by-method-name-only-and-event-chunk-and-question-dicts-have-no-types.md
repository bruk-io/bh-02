---
id: DRAFT-0023
title: >-
  Contracts are checked by method name only, and event, chunk and question dicts
  have no types
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - contracts
dependencies: []
type: design
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: cordis's check_contract is isinstance against a runtime_checkable Protocol (method names only, no signatures, keywords or async); 95 consumer Protocols, mostly private, and no provider is ever type-checked against one. 'Data crosses as dicts, typed by its reader' mostly does not hold: 16 TypedDicts, none for event, chunk, question, message or tool result; about 270 Mapping[str, Any]. CONTRACTS.md rows run 2.2k to 3.6k characters of prose. Proposed: one app test module assigning each shipped provider to each consumer Protocol so mypy checks every pairing (needs those Protocols public or an allow entry); TypedDicts where chat, tui and the loop match on type.
<!-- SECTION:DESCRIPTION:END -->
