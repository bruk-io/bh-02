---
id: TASK-0185
title: /restart ui or /restart jobs cancels itself and ends the session
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T13:44:00Z'
labels:
  - commands
  - cordis
  - size-3
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (reproduced in memory): commands:jobs runs each restart in its own row's task (cordis_helpers.perform); jobs depends on output, which the ui row binds, so restarting ui or jobs reloads jobs and cancels the restart halfway. cordis's Loader.restart (libs/cordis/src/cordis/loader.py) unmounts then mounts with no cancellation guard. Seen: /restart jobs drops the jobs row from loader.status() and leaves operator inactive; /restart output never remounts output; in the app chat needs jobs and the session ends. GLOSSARY.md and commands' wiring say the ui never reloads; it does. Proposed: Loader.restart/apply finish once begun (shielded inner task, or mount in finally), and /restart refuses a row jobs depends on, or the queue lives at loader scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A /restart either finishes with every row back up or refuses and says why; it never leaves rows unmounted; repro test: ui, jobs and operator rows, /restart ui then /restart jobs, and every row is active with output remounted
- [ ] #2 GLOSSARY.md and the commands wiring docstring say what /restart does to the ui and jobs
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
