---
id: DRAFT-0020
title: /restart ui or /restart jobs cancels itself and ends the session
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - commands
  - cordis
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03 (reproduced in memory): commands:jobs runs each restart in its own row's task (cordis_helpers.perform); jobs depends on output, which the ui row binds, so restarting ui or jobs reloads jobs and cancels the restart halfway. cordis's Loader.restart (libs/cordis/src/cordis/loader.py) unmounts then mounts with no cancellation guard. Seen: /restart jobs drops the jobs row from loader.status() and leaves operator inactive; /restart output never remounts output; in the app chat needs jobs and the session ends. GLOSSARY.md and commands' wiring say the ui never reloads; it does. Proposed: Loader.restart/apply finish once begun (shielded inner task, or mount in finally), and /restart refuses a row jobs depends on, or the queue lives at loader scope.
<!-- SECTION:DESCRIPTION:END -->
