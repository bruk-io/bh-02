---
id: decision-0009
title: >-
  Record a session's trajectory as timing on the transcript's entries, and read
  it with bh-02 trajectory
date: '2026-10-18 03:47'
status: accepted
---
## Context

DRAFT-0004 (the trajectory intent) asks to see what happened in a session, step by step, with its timing: model steps, tool calls, approvals, context changes, sub-agents and row reloads, browsable while a reply runs and after the session ends, written off the event loop, at 0600, where the jail can't reach it. Its open questions were where the record lives, whether raw requests are recorded, and how it is shown.

DeepSeek Harness (dsh) answers with a session log: a typed, append-only record that is the source of the context the model sees ("model-visible ⟺ logged"), with the trajectory as a pure projection of it. A first draft proposed the same for bh-02: a new session log, written by any plugin through `append(kind, data)`, replacing the transcript. Four lens reviews (cordis fit, what dsh learned, failures and security, simplicity) and an adversarial second round, against the code, showed bh-02 already has most of it:

- **The transcript already holds what the loop hands a provider, and only the loop appends to it** (the person's messages with their date and asides as sent, each step's assistant entry with the provider's own message, each call's result with its asides as sent, every prompt reading as `system` entries and every tool list as `tools` entries). `/clear` and `/compact` write the next conversation's file.
- **Each request is already a pure selection of the transcript** (`request_for`, `loop.py`). The tools offered are `begun` or `listed` (`toolset.py`), as the model's `tool_changes` says.
- **Every conversation is already kept:** `rewrite` keeps the old file as `transcript.jsonl.bak`, `.bak.2`, ...
- **Neither provider sends a key it does not read** (OpenAI's `replayed`, claude-code's `records`). The claude-code digest covers whole entries but stays stable, since an entry is appended once and never changed.

What it lacks is time, and the facts that never reach it: who answered a call's question and how long that took, which model answered a step and what it cost, the model settings, which sub-agent a call started, and row reloads. Two of the intent's must-not-breaks also fail today: the transcript is written on the event loop the TUI shares (`FileTranscript.append`), and it, its backups and the session directory take the umask's mode.

The owner chose (2026-10-18): practical timestamps; model settings recorded only when the model loads or changes; the terms below; row reloads kept; the three robustness defects noted on the intent, not on the board yet.

## Decision

### Terms

One word, one thing. These go in GLOSSARY.md:

- **conversation**: what the model is sent, from the session's start, `/clear` or `/compact` until the next one; one transcript file.
- **entry** (a transcript's): one line of it, a message (`user`, `assistant`, `tool`) or a record of the prompt (`system`) or the tool list (`tools`).
- **reply**: everything the loop does to answer one message, until the model answers. "Turn" is retired: it meant a reply in GLOSSARY and a step in `loop.py`.
- **step**: one request to the model and the answer it streams back.
- **request**: what one step hands the model: the conversation's first prompt, its messages, and the tools offered.
- **question**: a call the approval rule doesn't let run unasked, put to the person. Today's approval `request` (CONTRACTS.md's shape, `confirm(request)`, `unasked(request)`) is renamed to it.
- **answer** (a call's): what approval made of it, `unasked`, `yes` or `no`. **approval** stays the rule.
- **nested call**: a call an input makes through `tools.NAME(...)`.
- **history** is the ui's file only. The transcript is never called history.
- **chat view**: the TUI widget that shows the conversation, today's `Transcript` widget, renamed so "transcript" names only the conversation's file and row.
- **trajectory**: a session laid out in time, its conversations, replies, steps, calls, questions, sub-agents and row reloads with timing and usage. It is computed from the session's files and never stored.

### The rule

What the loop hands the model's `complete` for a step is exactly `request_for(entries before the step)` plus the tools that step offered. A test pins it with a fake model. What a provider does past `complete` is the provider's, and the transcript does not claim to hold it: claude-code's tool-name line before the prompt, its `CONTINUE` after a rebuild, a steer pushed ahead of results, OpenAI's settings. The settings are recorded when they change (below).

### The records

Each entry is appended once and never changed. A field is left out only where there is nothing to record (a call refused before approval has no `answer`, a step that got no chunk has no `first_chunk`, the answer to a message the model was never asked has no `step`). A transcript written before these records is promised nothing: no code reads or translates it (see Amended). Each record is a closed TypedDict in the agent plugin, listed in CONTRACTS.md (transcript).

**Time is data.** `at` is UTC ISO-8601 to the millisecond with `Z` (`2026-10-18T03:47:12.345Z`), so it sorts as text. Durations are seconds from a monotonic clock, rounded to the millisecond. The loop takes one clock value with `now()` (aware UTC) and `monotonic()`. Today's date derives from `now()`, replacing the loop's `today` function, and tests give a fake clock.

| Entry | Gains |
|---|---|
| a person's message (`user`, including `feedback` and an unanswered message) | `at` |
| a step (`assistant`, including `STOPPED` and `FAILED`) | `step: {at, first_chunk, took, model, usage, settings?, tool_changes?}` |
| a call (`tool`) | `call: {at, answer?, waited?, took?, child?, nested?}` |
| `system`, `tools` | nothing: where they sit between entries dates them, and `edits[].at` is already a paragraph index |
| the seed of a compacted conversation (its `user` entry) | `at`, `seed: {keep}` |

A step:

- `at`: when the request was handed to `complete`.
- `first_chunk`: seconds to the first chunk. It includes a Claude Code start or rebuild and the provider's own retry.
- `took`: seconds to the last chunk.
- `model`: the id the model answered with. The provider reports it as `model` on its `usage` chunk: claude-code from `message_start`, OpenAI from the response. It is absent when the provider reported none.
- `usage`: the step's `usage` chunks summed, `cost_usd` included, with the one function the agent plugin already uses for `/compact`'s total.
- `settings`: on the first step of a conversation, and on any step whose settings differ from the last ones recorded in it. It holds the model row's named model (`ENDPOINT/MODEL`), its provider, and the `max_tokens` and `temperature` it sends. The model value exposes them as an optional `settings` attribute (CONTRACTS.md: model), read as `tool_changes` is.
- `tool_changes`: only when it is `listed`. Absent means `fixed`.

A call:

- `at`: when the call reached approval, or was refused before it.
- `answer`: an `Answer` StrEnum (`unasked`, `yes`, `no`), which `Asked.approve` returns in place of the bool. Every use is a `match` ending in `assert_never`, since the member `no` is truthy. `no` also covers a question that Ctrl-C or a closed app withdrew. It is absent when the call was refused before approval or never reached it (`_NOT_RUN`).
- `waited`: seconds from the question being put to its answer, including time queued behind another question, since the ui shows one at a time. It is absent for `unasked`.
- `took`: seconds the tool ran. A question a tool puts during its own run stays inside `took` and is not recorded on its own (a sub-agent start past the session budget, an extension load).
- `child`: the sub-agent the call started. The `agent` tool's result gains `child: NAME` beside `content`, and the loop keeps it as it keeps `touched`.
- `nested`: the calls an input made through `tools`, each a `call` record with its tool's name, in order.

`_Turn` becomes `_Step` and builds the `step` record. A `_Call` collector builds the `call` record. `self._nested` becomes one list of records that carry their asides.

### Writing

- **One appender for the family.** `host_paths` gains the chained writer `eventlog.py` has today: one file per writer, opened for append with `O_NOFOLLOW`, created at 0600, each write done on a thread after the one before it, and `flush()` waiting for the last.
- **The transcript and the event log use it.** `FileTranscript.append` stays synchronous: it commits in memory and queues the write, so no consumer's Protocol changes. The loop flushes at the end of every reply. `/clear` and `/compact` never read or replace a file with a write pending.
- **Permissions.** `rewrite` creates its new file and its backup at 0600, and the session directory is made 0700.

### Conversations

- **Order.** A session's conversations are its transcript files: the live `transcript.jsonl` last, the backups before it ordered by their first `at`, else by mtime. A backup is copied at the rewrite, so its mtime is when its conversation ended.
- **The seed.** `/compact` begins the next conversation with its seed. The seed's `user` entry carries `seed: {keep}`, the text the person asked to keep (`""` for none), so no reader matches the seed's wording. Its `assistant` entry, the summary, carries the summary step's `step` record. That step's request is the old conversation, so the trajectory shows it as the boundary with its time and cost.
- **Known gap.** A `/compact` whose step fails spends tokens and leaves no entry.
- **`/clear`** starts an empty file. A conversation that begins without a seed was cleared or is the session's first.

### Row reloads

The shell already hears every lifecycle event (`bootstrap.py`). It keeps `reload`, `restart` and `failed` in the session, through the appender: `<session>/rows.jsonl`, one `{at, kind, row, error?}` a line, sub-agent rows (`agents/NAME/...`) included. `--trace FILE` stays as it is.

### Reading

`bh-02 trajectory [ID]` (the id as `--resume` takes it; the directory's newest by default) prints a session's trajectory.

- **Code.** A pure `trajectory(conversations, rows) -> Trajectory` (frozen dataclasses) in `bh_02`, beside `bh-02 sessions` and `bh-02 watch`. It types the entries it reads with TypedDicts of its own, since it imports no plugin.
- **What it prints:**
  - each reply, with its message and its time;
  - each step, with its model, time to first chunk, generation time, output tokens per second, usage and cost, and its settings when they changed;
  - each call, with its tool, answer and wait, run time and nested calls;
  - each sub-agent, under the call that started it;
  - each conversation boundary, with the summary step's time and cost;
  - each row reload.
- **Sub-agents.** A child's transcripts are under `<session>/agents/NAME/`. The reader checks `child` against the name pattern `bh-02 watch` accepts before it builds a path. It places a child by its own times (a background agent included), and lists a child with no linking call by its own times.
- **Live.** `--follow` re-reads the files by path every second, so a file `/clear` or `/compact` replaced is simply new, and prints what is new.
- **Safety.** Files are read through `host_paths`, beneath the sessions' state, through no link. Control characters are stripped from all printed text. A torn last line is skipped, and a call with no result shows "no result recorded".
- **Not yet.** The raw request is not shown. Rebuilding it needs `request_for`, `begun`, `listed` and `prompt.latest`, which are the agent plugin's, and `bh_02` may import no plugin. Showing it is a later piece of work that first moves those pure functions into a library both may import. Raw requests are never stored. A TUI trajectory screen is later still, and needs the same move.

### Stays as it is

The ui's history (`events.jsonl`); the event log, which only changes its writer; `--trace`; telemetry (out of scope); extensions, which get no transcript key, pinned by a behaviour test (as `test_extensions_host.py` pins the others), not through the private `_OFFERED`.

## Consequences

- No new log, row, key or file beside the transcript, except `rows.jsonl`. A session written before these records stops working with the code that reads them: `/compact` knows a seed by its `seed` field alone, and `bh-02 trajectory` has no case for a transcript that has no times (see Amended). No migration and no format header.
- The loop gains a clock and two collectors. `Asked.approve` returns `Answer`, and the four test fakes that return a bool change with it. Both providers add `model` to their `usage` chunk and expose `settings`. The `agent` tool's result gains `child`.
- `host_paths` gains an appender that the transcript, the event log and the shell share. The transcript's writes leave the event loop.
- `/compact` keeps what the person asked to keep, and records its step.
- The trajectory's reader is plain code over JSON files in `bh_02`, testable without a session.
- Rejected, with the reason:
  - **A new session log beside or instead of the transcript:** it would duplicate the transcript.
  - **`append(kind, data)` for every plugin, with namespaced kinds and listeners:** every fact the trajectory needs reaches the loop through a chunk, `Asked` or a result. More writers raise cordis questions (who depends on the log, what reloads with it) with no consumer.
  - **Two rows, a log and a transcript view:** the transcript's restart on `/clear` and `/compact` stays, and `memory:on_touch` and `memory:auto` rely on it.
  - **A full request envelope per step:** settings are recorded when they change, as dsh records a request header. The rest rebuilds from the entries.
  - **A timed token stream per step:** first-chunk and end times give the timings asked for.
  - **A format header and refusal rules:** there is no old form to tell from the new one (see Amended).
  - **Changing what `/compact` offers** (`begun` instead of `tools.specs()`): possibly worth doing, but not this decision's.
- Noted on the intent, not on the board (the owner's call):
  - a torn last line stops a resume;
  - a process that dies mid-call leaves the call unanswered;
  - two processes can append to one session.

## Amended

2026-10-18 (TASK-0156), by the owner's rule, root CLAUDE.md, Conventions, "No backwards compatibility before a supported release": until there is a release the owner plans to support, a change to a stored format breaks what came before: no code reads the old form or translates it, and no test pins it. This decision had promised that old sessions read unchanged: the records' "every new field is optional: a transcript from before this reads as it did, and its trajectory shows no times", and Consequences' "old sessions read unchanged". That promise is withdrawn. A field is still absent where the record above says it is (a call refused before approval has no `answer`; the answer to a message the model was never asked has no `step`), and the reader of the files still leaves out a field that is missing or of the wrong type, since the files are the person's and a hand-edited or half-written one must not stop the view. What no longer works is a session written before the records: `/compact` no longer knows a seed by its wording, so a conversation compacted before the `seed` field is compacted again like any other, summarising the summary; and `bh-02 trajectory` has no code or test for a transcript with no `at`, so one prints as the reader finds it, with whatever times it lacks left out.
