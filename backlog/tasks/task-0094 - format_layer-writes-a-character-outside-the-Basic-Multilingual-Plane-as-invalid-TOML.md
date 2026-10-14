---
id: TASK-0094
title: >-
  format_layer writes a character outside the Basic Multilingual Plane as
  invalid TOML
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-14 09:53'
updated_date: '2026-10-14 14:06'
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
- [x] #1 format_layer round-trips through tomllib a string holding a character above U+FFFF, in a row id, use, config value and config key (a test of each, seen failing before the fix)
- [x] #2 /model NAME and --model NAME with such a name write a layer the loader reads back as the same name (a test)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
ORDER: (1) failing tests first: libs/cordis/tests/test_loader.py gets round-trip tests of a non-BMP char (U+1F999) in a row id, use, config value, value nested in a list and a table, and a config key; plus control characters staying escaped and a lone surrogate refused with a message; run them, see them fail (tomllib: Escaped character is not a Unicode scalar value). Then the models plugin test (/model local/<llama> through Switch + the real set_model, read back by read_layer) and the app test (create(model=...) and set_model(session, ...) read back), seen failing. (2) Fix in cordis/composition.py: one small pure function _toml_string(str) -> str that writes a TOML basic string: literal UTF-8 for printable characters (incl. non-BMP), backslash escapes for the TOML short escapes (quote, backslash, b t n f r), \\uXXXX for other control characters (C0, DEL; C1 and U+2028/9 stay literal-safe? decide: escape C0, DEL, C1), and ValueError (says what to do) for a lone surrogate, which no TOML string can hold; _toml uses it for str values and keys. format_layer's docstring says so. (3) Risks: error text uses json.dumps for display only (not written as TOML, left alone); output file is written with write_text (UTF-8 default? check the callers' encoding: a literal non-BMP char needs UTF-8, so prefer the \\UXXXXXXXX escape if any caller writes with a locale encoding). (4) Proof: the new tests fail before, pass after; uv run pytest libs/cordis -q, test_invariants, models plugin tests, bh-02/app/tests, scripts/arch-check, uv run mypy, scripts/check (root, no tini).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
WHAT CHANGED. libs/cordis/src/cordis/composition.py: format_layer wrote every string with json.dumps (a JSON string with ensure_ascii), which writes a character above U+FFFF as a surrogate pair that TOML refuses in an escape. Now one small pure function, _toml_string (with _written for one character), turns a str into a TOML basic string of printable ASCII: a quote, a backslash and a control character (C0, DEL, C1, U+2028) get their escape, every other character outside space..~ is \\uXXXX, and one above U+FFFF is one \\UXXXXXXXX. I chose escapes over literal UTF-8 so the layer text stays pure ASCII (as json.dumps made it) and the callers' write_text() calls, which pass no encoding, work under any locale; text for strings below U+10000 is byte-identical to before (lowercase hex), so existing layers rewrite unchanged. _toml uses it for every string value, and for config keys (nested too). A lone surrogate (half of a character; what argv bytes that are not UTF-8 decode to) can't be in any TOML string, so _toml_string raises ValueError saying what to do (previously it wrote an unreadable layer silently); format_layer's docstring now says all this and lists its Raises (TypeError, ValueError). json stays imported in composition.py only for error-message display text (_check_row, _toml_kind), which is not written as TOML.
TESTS. libs/cordis/tests/test_loader.py: test_format_layer_round_trips_a_character_above_u_ffff (7 cases: row id, use, config value, value in a list, value in a table, config key, key in a table in a list), test_format_layer_escapes_what_a_toml_string_may_not_hold_raw (every control char, DEL, C1, U+2028, quote, backslash, BMP, U+FFFF, U+10000, U+10FFFF; the text is ASCII only and reads back equal), test_format_layer_refuses_a_lone_surrogate_and_says_what_to_do (value and key). bh-02/plugins/models-cordis-plugin/tests/test_models_discovery.py: test_a_name_above_u_ffff_is_written_to_the_session_s_layer_and_read_back_as_typed (/model local/llama-U+1F999 through Switch with the real set_model, read back by read_layer, and resolved() gives the id; no request made). bh-02/app/tests/test_session_dirs.py: test_a_model_name_above_u_ffff_is_recorded_in_the_layer_and_read_back_as_typed (create(model=NAME) and sessions.set_model, the resume's --model path).
SEEN FAILING BEFORE THE FIX (new tests written first, source untouched): the 7 round-trip cases and the control-character test failed with tomllib.TOMLDecodeError: 'Escaped character is not a Unicode scalar value' (at the surrogate-pair escape), the two lone-surrogate cases with 'DID NOT RAISE ValueError' (10 failed in test_loader.py); the models plugin test and the app test each failed with the same TOMLDecodeError raised from read_layer. After the fix: test_loader.py 50 passed; the two bh-02 tests passed.
CHECKS (all as root without tini, one at a time, exit codes read directly): uv run pytest libs/cordis -q: 493 passed (exit 0); libs/cordis/tests/test_invariants.py: 360 passed (exit 0); uv run pytest bh-02/plugins/models-cordis-plugin -q: 314 passed, 2 skipped (exit 0); uv run pytest bh-02/app/tests -q: 223 passed, 1 skipped (exit 0); scripts/arch-check: exit 0; uv run mypy: 'Success: no issues found in 187 source files' (exit 0); scripts/check: exit 0 (format, lint, types, tests 2791 passed 31 skipped, gates, docs ok; tokens skipped: no ../bh-01/dist). Not run: scripts/linux-jail-check (nothing in brig or the jail changed).
FOLLOW-UP: TASK-0098 (size-1): bh-02 --model with a name that is not valid UTF-8 now raises format_layer's ValueError from sessions.create after the session directory and meta.json were made (checked: the directory holds meta.json only); before, it wrote an unreadable layer. The fix belongs where the name enters (the CLI), a different area from this task.
<!-- SECTION:NOTES:END -->
