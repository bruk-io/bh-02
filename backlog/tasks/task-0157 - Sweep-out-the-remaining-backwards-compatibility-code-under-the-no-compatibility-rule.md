---
id: TASK-0157
title: >-
  Sweep out the remaining backwards-compatibility code under the
  no-compatibility rule
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 14:39'
updated_date: '2026-10-18 17:33'
labels:
  - agent
  - app
  - size-3
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner's rule (root CLAUDE.md, Conventions, 2026-10-18): no backwards compatibility before a supported release. Code from before the rule still reads or translates old forms, for example the claude-code provider's records that replay a session from before the provider (models-cordis-plugin claude_code/records.py, the mcp__bh__ prefix), and the prompt's handling of a transcript from before the loop kept edits (agent plugin, test_agent_prompt.py). List every such path across bh-02/ and libs/ first, then remove them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The notes list every path found that reads, translates or tests an old stored format or name (grep for from before, old, legacy, earlier, compat, and the bh-02 CLAUDE.md naming rule's cases), each with what it kept working
- [x] #2 Each listed path and the tests pinning it are removed, or the notes say why one is not compatibility (a guard against a name a layer still names, say)
- [x] #3 The notes say which old files stop working; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Inventory (grep for from before, older, earlier, legacy, compat, replays, renamed and each file kind incl. scripts/model-friction). Paths to remove, each with its tests and docs: (a) memory touch.py reading a tool entry without asides by searching its text (_before texts, _told_in, _ENDS), its README and tests; (b) agent prompt.latest taking every whole system entry as the reading (a transcript from before edits), loop.py/prompt.py/CONTRACTS/README/test_agent_prompt/test_loop; (c) CONTRACTS+README 'tool entry without asides is from before'; (d) models claude_code/records.py _prefixed (mcp__bh__ for a provider block of the Messages-API era), README, tests; (e) loop.py _unanswered_calls 'user entry follows' branch for an older bh-02, README, test; (f) sessions.py stack comment, GLOSSARY, docs sessions.md ('an earlier bh-02 claude/ollama'); (g) tui History.record's emptied-underneath carried entry (+ _count/_used/_counted), module docstring, README, two tests; (h) runner jail.py a placeholder recorded by path alone (None, older record): types tightened to str, recorded() skips an entry with no proof, tests; (i) scripts/model-friction _result fallback (_SHELL_HINT, _TOUCHED) for entries without asides; (j) doc-only: toolset.begun/_undated docstrings and test_agent_tools test (a /compact seed has no tools entry or date, which is real today: relabel, keep), test_agent_transcript docstring. Left, not compatibility: OpenAI legacy function_call; test_booting jail row id; test_session_dirs --ollama flag gone; @helper NameError test (clean-rename); models-file endpoint table with id refusal (rejects, reads nothing); .bak backups; brig (refuses older dicts by design); arch-check older pypeeker output guard. 2. Proof: for each removal first show the old-form test fails with the path removed (planted), then delete the test. 3. Checks: scripts/check for agent, memory, models, tui, runner plugins and bh-02/app (first with gates+docs, others --no-gates --no-docs), scripts/arch-check --no-fix once (scripts/model-friction and root files).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
FOUND AND REMOVED (path: what it kept working):
1. memory touch.py (_before's text list, _told_in, _ENDS), README, test_memory_touch.py: a `tool` entry with no `asides` (from before the loop kept them, or when it called them `notes`) was searched for an aside told whole, so a resumed old session was not told a rule again. Now only the `asides` list counts. Test for the old form replaced by one on `asides` entries (quoted, printed, cut short, changed text; read once; afresh after /clear). Seen failing: the old two tests run against the new code fail (2 failed).
2. agent prompt.py `latest` (+ loop.py via it, CONTRACTS.md system entry, agent README, test_agent_prompt.py, test_loop.py): every `system` entry without `edits` was taken as the reading, so a transcript that kept each prompt whole resumed as it was (old `Today:` line and all). Now the first entry is the reading and each later one holds edits. Removed test_a_transcript_that_kept_each_prompt_whole_still_loads_and_resumes; test_agent_prompt's latest test rewritten. Seen: two whole entries now give the first, not the second.
3. CONTRACTS.md (asides, system entry, tools entry), agent README: "a tool entry without asides is from before", "a transcript from before the loop kept edits / tools" sentences dropped. loop.py _undated and toolset.begun said "begun before the loop told dates / kept its tools": that case is real today (what /compact leaves has no date, no system and no tools entry), so the code stays, its docstrings now say /compact; test_agent_tools' test is relabelled onto a seed-shaped transcript.
4. models claude_code/records.py `_prefixed` (+ README, test_claude_code_records.py, test_claude_code_model.py, test_models_step_facts.py): a `provider` tool_use block with no mcp__ prefix (a session from the Messages-API provider) got `mcp__bh__` on a rebuild. Now a provider block is replayed as received; calls of a step with no Claude Code `provider` message (an OpenAI model's, rebuilt from text and calls) still get the prefix. Test data that used the old unprefixed block now uses Claude Code's name or an OpenAI-shaped step. Seen: the old records test fails against the new code.
5. agent loop.py _unanswered_calls (+ README, test_agent_unanswered_calls.py): a `user` entry after the last step ended the search, because an older bh-02 had resumed such a step as it was. The loop answers a crash's calls before appending the person's message, so that shape no longer arises. Removed the branch and test_a_step_an_older_bh_02_resumed_with_its_call_unanswered_is_left_as_it_was. Seen failing against the new code before deletion.
6. bh_02 sessions.py Session.stack comment, GLOSSARY.md stack, docs sessions.md: "an earlier bh-02's session says claude or ollama". Only prose: the stack is a free string and no code matched those values.
7. tui history.py (History.record's "emptied underneath" carried entry, and _count/_used/_counted that fed it), module docstring, tui README, test_history.py (test_emptied_underneath_the_next_entry_lands_at_the_new_end, test_clear_forgets_the_entries_but_not_the_session_s_usage): an older bh-02's `forget` emptied events.jsonl under the app and the next write put a `carried` entry first. Nothing empties it now (/clear writes a `cleared` event, covered by the replay test). Both tests failed against the new code before deletion. Also dropped "(once the operator's forget)" from the agent README, and "written now"/"a file from before the rename is not read, TASK-0137" from test_chat_view.py's reply_end test.
8. runner jail.py record_text/recorded/still_made/remove_placeholders/_Jailed._made/_clear_up (+ README, test_runner_confined.py): a placeholder recorded by path alone (None: an older bh-02's record from before placeholders were marked) was kept, never removed. The jail only writes `mark:ID` or an identity, so the types are now `str`, and `recorded` leaves out an entry with no way to know it (a damaged record), which keeps the safety property (nothing unproven is removed) and the sweep from raising. Tests: the None entries became marks; new assertion on a damaged record, seen failing with the filter removed. test_a_record_with_unmarked_paths_removes_nothing_it_can_t_prove (needs bwrap, skipped here, not run) now records the paths by mark, which is what a crash before marking leaves today.
9. scripts/model-friction `_result` (+ _SHELL_HINT, _TOUCHED): cut asides out of the text of a `tool` entry without `asides`. Now such an entry's text is taken as it is.
10. test_agent_transcript.py docstring "(an older session's, 0644)": the 0600-over-any-mode guard stays, the old-session wording is gone.

NOT COMPATIBILITY (left): the OpenAI wire's legacy `function_call` (the server's protocol); test_booting.py's `jail` row id check and the `--ollama` flag test in test_session_dirs.py ("No such option": a name that is gone, the clean-rename rule); test_python_tool's @helper NameError test and the docs line on it (same); the models file's refusal of an endpoint table with its own `id` (named.py _endpoint_problem, six test files): it reads nothing and translates nothing, the table fails either way and the message says what to write; if the owner wants the bespoke message gone too, the generic "is not a setting of an endpoint" error would take over and the fixtures in test_models_discovery/_broken_file/_named_models/_discover_names/test_session_dirs need another broken table (reworded the docs sentence so it no longer calls it "from before"); `.bak`/`.torn` kept files, "the old file" of /clear and /compact; arch-check's guard against a pypeeker that prints no residual findings (a tool's output, not our files); GLOSSARY "worker: an older word" (vocabulary); toolset._described reading `parameters` or `input_schema` (a spec shape, not found to be an earlier stored form); libs/brig (refuses older dicts by design, "no migration framework"), libs/cordis, cordis-helpers, host-paths, examples/warden: nothing found.

OLD FILES THAT STOP WORKING (none is read by an error; each is just no longer treated as a supported form): (a) a transcript whose `tool` entries have no `asides`: a memory rule it told is told again on first touch after a resume; (b) a transcript that kept each changed prompt as a whole `system` entry: the request still begins with its first prompt, but what the model was last told is now that first prompt, so the next message tells a diff against it (the date line and every change since), and later whole entries are passed over; (c) a transcript whose last assistant step has calls and a `user` entry after them: the calls are now answered with "interrupted: ..." after the person's message (the entries already written are never changed); (d) a Claude Code session from the Messages-API provider (provider tool_use blocks named `python`): rebuilt with the bare name, which Claude Code does not know as a declared tool; /clear starts a clean one; (e) an events.jsonl a pre-`cleared` bh-02 emptied: a resume's usage totals count what the file holds; (f) a jail record (state dir jails/*.json) with a path and no mark: swept as before (record deleted, nothing removed). (g) scripts/model-friction run over old sessions no longer strips the shell hint and old guidance asides from results, so an old session may show a few more or fewer signals.

CHECKS: scripts/check bh-02/plugins/agent-cordis-plugin (gates, docs) exit 0, 191 passed 1 skipped; --no-gates --no-docs: memory 149 passed, models 363 passed 2 skipped, tui 344 passed, runner 88 passed 1 skipped, bh-02/app 347 passed 1 skipped, all exit 0 (memory and models after one reformat/fix each: my scripted edits bypassed the format hook, and a models test used an unprefixed provider block); scripts/arch-check --no-fix exit 0. Not run: the full scripts/check (AC3 "scripts/check passes" is the reviewer's, unticked), scripts/linux-jail-check, the e2e tests.

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 32%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
........s.s...ssss.s.s.s.s..ss..ss.s..s..sss....ss.s.s..ssss.......s.... [ 49%]
........................................................................ [ 51%]
........................................................................ [ 53%]
............................................ssssssssssssssssssssssssssss [ 54%]
ssssssssssssssssssssssssssssssssssssss.s.......................sssssssss [ 56%]
sss..................................................................... [ 58%]
..s..................................................................... [ 60%]
........................................................................ [ 62%]
................sss..................................................... [ 64%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 98%]
............................................                             [100%]
3816 passed, 118 skipped in 212.01s (0:03:32)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 5.69 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
