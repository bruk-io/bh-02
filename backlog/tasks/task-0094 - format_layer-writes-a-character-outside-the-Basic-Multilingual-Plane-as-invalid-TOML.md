---
id: TASK-0094
title: >-
  format_layer writes a character outside the Basic Multilingual Plane as
  invalid TOML
status: To Do
assignee: []
created_date: '2026-10-14 09:53'
updated_date: '2026-10-14 10:09'
labels:
  - cordis
  - size-2
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cordis.composition.format_layer writes every string with json.dumps, which escapes a character above U+FFFF as a surrogate pair (\ud83e\udd99). TOML allows only Unicode scalar values in an escape, so tomllib refuses the layer (checked 2026-10-14: 'Escaped character is not a Unicode scalar value'). Any string a layer holds that came from outside, such as a model name /model writes into the session's layer (models_cordis_plugin.wiring.set_model) or a --model value (bh_02.sessions.create), can break the layer the loader reads next, and the session with it. TASK-0088 keeps discovered model ids to printable ASCII so a server's id cannot do it; a name typed by hand or passed to --model still can. Fix where the layer is written, by writing such a character as a TOML \UXXXXXXXX escape or literally, and say so in format_layer's docstring.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 format_layer round-trips through tomllib a string holding a character above U+FFFF, in a row id, use, config value and config key (a test of each, seen failing before the fix)
- [ ] #2 /model NAME and --model NAME with such a name write a layer the loader reads back as the same name (a test)
<!-- AC:END -->
