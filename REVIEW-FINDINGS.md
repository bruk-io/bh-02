# Open review findings for TASK-0043 (not yet addressed)

From the workflow's two review lenses (acceptance, cordis). Delete this file once each is fixed or answered.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/prompt.py

`edits` splits the reading exactly at every "\n\n" and keeps the empty paragraphs that a run of blank lines produces. It then matches them with SequenceMatcher(autojunk=False), which is quadratic in duplicates. `changes` drops empty paragraphs (`_parts`), so it never paid this cost. `_told` calls `edits` on the event loop after the worker thread returns (loop.py:259), so a prompt with a long run of blank lines inside a section freezes the TUI each time the prompt changes. You need unusual input to hit this: thousands of consecutive newlines in a context file or an extension's section. Realistic prompts take milliseconds.

Evidence: Probe run with `uv run python -c ...` in the worktree. The input is 'head' + N empty paragraphs + 'tail', with 'head' changed to 'HEAD'. 500 empty paragraphs (1,010 chars): edits 0.019s, changes 0.0001s. 1,000 (2,010 chars): edits 0.114s. 3,000 (6,010 chars): edits 0.970s, changes 0.0003s. 10,000: edits 11.6s, changes 0.001s. For comparison, the realistic chain of `bh-02/CLAUDE.md` plus 9 branch switches came to 909 bytes of edits. Replaying 1,000 edits with `latest` takes 0.024s.

Suggested: Optional. Compute the edits in the worker thread together with `_prompt`, or match runs of empty paragraphs as junk (for example, diff over the paragraphs with `isjunk` for '' while keeping the exact split for replay). Alternatively, accept the cost and leave a note, since the 20,000-char cap on context files bounds the worst case.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/prompt.py

If a stored `edits` entry is malformed, `latest` raises a bare KeyError, TypeError or ValueError. `LoopModel._told` calls `latest` again whenever the system-entry count changes (loop.py:255), so in a fresh loop or after a resume every message in that session fails, and the error doesn't say what is wrong or what to do. Before this change a damaged system entry could not raise at all. Only the loop writes these entries, and the implementer chose not to validate them, so this only bites on a hand-edited or damaged transcript.

Evidence: prompt.py:88 `entry["edits"]`, :100-102 `int(step["at"])`, `step["add"]`, `int(step["drop"])`. Probe: `latest([{'role':'system','content':'a\n\nb'},{'role':'system','edits':[{'at':0}]}])` -> `KeyError 'add'`; `edits: None` -> `TypeError 'NoneType' object is not iterable`; `at: 'x'` -> `ValueError invalid literal for int()`. The first two never mention the transcript file or say how to recover, and the third doesn't say what to do.

Suggested: Optional: wrap the replay so the error names the session's transcript.jsonl entry that can't be read and says what to do (remove that line, or start with /clear). Or skip an unreadable edits entry and fall back to the last reading that can be rebuilt.

## [minor] bh-02/CONTRACTS.md

The new `system entry` shape says "`latest` applies a transcript's entries in turn to what the model was last told". That reads as if `latest` takes the last-told reading as its input. In fact it replays the entries, starting from the first whole one, and returns the last-told reading.

Evidence: CONTRACTS.md:189 vs prompt.py:80-91: `latest(entries)` starts from None, takes each whole `content`, applies each `edits` to the reading before it, and returns the result.

Suggested: Reword to: "`latest` applies a transcript's entries in turn, giving what the model was last told".
