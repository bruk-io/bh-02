# Open review findings for TASK-0045 (not yet addressed)

From the workflow's two review lenses (acceptance, cordis). Delete this file once each is fixed or answered.

## [major] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/compact.py

If the person quits (Ctrl-Q, /exit, a closed terminal) while the model is writing the summary, bh-02 does not exit until the summary step finishes, which can take up to `timeout` (300 s) plus the provider's drain. After the person has quit, the compaction still goes ahead: transcript.jsonl is rewritten, but the ui never records `cleared` or the note in events.jsonl. On `bh-02 --resume` the screen then replays the old conversation while the model only receives the seed and the summary. Before this change no command ran long in the chat row's task, so quitting always ended bh-02 promptly. A normal turn is cancelled when the app ends, because `_interruptible` hears `interrupted()`. A command is not.

Evidence: Probe /tmp/claude-0/-home-user-bh-02/4dc0d93e-ad1a-579e-8549-da59b471193d/scratchpad/wf-review/race/probe_quit.py. It boots the shipped layers with the real tui `Bridge` and `TuiOutput`, and a model whose summary takes 6 s. It submits 'hello', then '/compact', and calls `bridge.end()` 0.5 s later, which is what Ctrl-Q does through `_until_ended`. Output: `run() returned 5.5s after the app ended (summary takes 6.0s)` and `transcript rewritten after quitting: True`. Code path: chat.py:94-95 awaits `commands.run(message)` and does not race it against the input ending. compact.py:241 awaits `summarise` for up to `config.timeout`, then writes the file at compact.py:243. Once the bridge has ended, `TuiOutput.show` posts nothing (ports.py:390 and :407), so `cleared` never reaches the app's history `_record`. The ui row stays up after the app exits (the `running` context in wiring.py), and `bootstrap._await_chat` waits on the chat row's `done`, so the process keeps running.

Suggested: Let the app ending cancel the summary step. Two options: chat runs a command raced against `input.interrupted()`, which returns at once when the app ends and on Ctrl-C (cancelling before the rewrite is safe, because `summarise` closes the step and nothing has been written yet); or the compact row checks that its answer can still be shown before calling `rewrite`. Add a test that ends the input during the summary and asserts that `run()` returns promptly and the transcript is untouched.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/compact.py

The restart is queued (compact.py:255) before the chat row shows the answer. The restart's own work then retires the loop and cancels the chat row while it is still showing the answer. Putting the summary step's usage events ahead of `cleared` (compact.py:212) uses up most of the margin /clear has. Once a provider sends 4 usage events, `restarting` is lost; at 5, `cleared` and the note carrying the summary are lost too. The person never sees the summary, the screen is not cleared, and a resume's replay does not start at the compaction. The `_answer` docstring says 'the note is what must not be lost', but the ordering does not guarantee that. Shipped providers send 1 (openai) or 2 (claude-code; 3 on a restarted stream) usage events, so this passes today by about 2 events.

Evidence: Probe /tmp/claude-0/-home-user-bh-02/4dc0d93e-ad1a-579e-8549-da59b471193d/scratchpad/wf-review/race/probe_tui.py uses the shipped layers and the real `Bridge` and `TuiOutput` (only the Textual app is replaced by a post callback that marks each batch drawn). Events shown per number of usage events N: N=3 ['text','stop','usage','usage','usage','cleared','note','restarting','text','stop']; N=4 [...,'usage','cleared','note','text','stop'], with `restarting` lost; N=5 [...,'usage','usage','usage','usage','usage','text','stop'], with `cleared` and the note lost. A lifecycle trace (probe_trace2.py) shows `unloading loop#3` right after `EVENT cleared` and `unloading chat#11` before `EVENT restarting`. The real-launch test's fake model sends no usage events, so this path is untested.

Suggested: Do not start the restart until the answer has been shown. For example, put the usage events after the note and before `restarting`, so that the note always comes right after `cleared`. Better still, have the queued job wait for a signal that the chat row sets once `output.show` has returned, or wait for the chat row to read again.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/compact.py

Running a second /compact before any new message (easy to do, since nothing shows while the first is running) summarises the seed and summary with no system prompt at all. `request_for` takes the first `system` entry, and the seed has none. The second run also overwrites transcript.jsonl.bak with the one-summary transcript, so the backup of the original conversation is gone. With claude-code, a request without the system prompt also restarts Claude Code, and the next real message restarts it again.

Evidence: Probe /tmp/claude-0/-home-user-bh-02/4dc0d93e-ad1a-579e-8549-da59b471193d/scratchpad/wf-review/race/probe_double.py, script ['hello','/compact','/compact'], prints: `request 2: ['user', 'assistant', 'user']` (no system entry) and `.bak still holds the original 'hello'? False`. compact.py:239 only refuses a conversation with no non-system messages, and the seed always has two. transcript.py:61 copies over any existing `.bak`.

Suggested: Treat a conversation that is only the seed (no system entry, nothing after the summary) as nothing to compact, and/or keep earlier backups (a numbered or timestamped `.bak`) instead of replacing them.

## [minor] bh-02/plugins/chat-cordis-plugin/src/chat_cordis_plugin/chat.py

Nothing tells the person that /compact is working. For up to 300 s the screen shows only the typed '/compact'. Ctrl-C does nothing and says nothing. /help says 'Ctrl-C stops a reply', so the person has no feedback and is likely to retype /compact (see the double-compact finding) or quit (see the quit finding).

Evidence: `TurnStarted` is posted only when `output.show` begins (ports.py:390), and chat.py:95 calls it only after `commands.run` returns. While a command runs, `Bridge.interrupt()` holds the Ctrl-C and returns True (ports.py:245), so `action_interrupt` shows no note. The next `line()` drops the held Ctrl-C (ports.py:216). This held-and-dropped Ctrl-C was harmless for instant commands; /compact is the first long one.

Suggested: Show a note before the summary step (for example, let a command answer an async iterator of events that the chat row streams, with 'compacting… (the model is writing a summary)' first), or make /compact interruptible as suggested for the quit finding.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/compact.py

Usage from a failed summary step is dropped. When the step times out, calls python, is truncated, is silent or refuses, `summarise` raises `Unsummarised` and the collected `usage` list is thrown away. The tokens and cost of a failed /compact (a truncated one may have generated a full output budget) never reach the session's usage totals. This contradicts the stated reason for putting usage first in the answer, 'so the summary's cost counts in the session's totals'.

Evidence: compact.py:181 appends usage chunks to a local list; compact.py:202 `raise Unsummarised(why)` (and the timeout and model-error raises above it) leave that list behind; compact_conversation only uses `usage` on success (compact.py:241, 212).

Suggested: Attach the usage to `Unsummarised` and have `compact_conversation` answer a failure as events: the usage, then a note saying why nothing changed.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/compact.py

The seed message is kept in transcript.jsonl for good, and it says the namespace still holds what the earlier inputs defined. After `bh-02 --resume` the kernel starts empty, but the model still reads that statement (and the summary's list of variables) at the start of the conversation, which contradicts the kernel instructions in the system prompt.

Evidence: compact.py:67-71 `_SEEDED` says '...Your Python namespace is as the earlier conversation left it: what its inputs defined is still there.' kernel_cordis_plugin/python.py:52 tells the model the namespace starts empty 'when bh-02 starts (a resumed session too: the conversation comes back, the variables do not)'.

Suggested: Word the seed so it stays true after a resume, for example 'the Python namespace was kept when this conversation was compacted; a later restart or resume empties it, as the instructions say'.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/compact.py

`_answer` (lines 206-216) puts every usage event from the summary step before `cleared` and the note. The `_answer` docstring says the note "is what must not be lost", but the queued restart races the chat row while it is still showing the answer. Each usage event placed in front of the note brings it closer to the point where the restart cancels the chat row before the note is read.

Evidence: Experiment in a scratch copy, not the worktree. I booted the shipped layers through `bh_02.bootstrap.run` with `fragile:compacting_model` and `scripted_ui`, the same setup as test_compacting.py. I gave `Record.show` an `await asyncio.sleep(0)` after each event, as the TUI's `Output.show` does (tui_cordis_plugin/ports.py, the loop ending in `await asyncio.sleep(0)`), and made the summary step yield N usage chunks. Results: the compact note was shown for N = 0, 1, 2, 3, 4 and lost for N = 5, 6, 7, 8 and 16. The claude-code provider sends at most 2 usage chunks per step (claude_code/stream.py:124 and :251), so nothing breaks today, but the safety margin is about 3 events.

Suggested: Send at most one usage event in front of `cleared`, by summing the step's usage chunks into one event. Or put the usage after the note, just before `restarting`. Either way the note's position no longer depends on how many usage chunks a provider sends.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/wiring.py

The compact row's `failures` list (lines 97-99) is never read, so a restart job that fails is never reported. By the time the job runs, `compact_conversation` has already replaced the transcript file. If `loader.restart` raises, or the row reloads before its queued job runs, the live transcript row keeps the old conversation in memory and keeps appending to the new file. The model is then sent the old conversation while a resume reads the new one, and nobody is told.

Evidence: wiring.py:97-99: `failures: list[str] = []`, `yield background(perform(jobs, failures.append))`, and nothing reads `failures` afterwards. compact.py:243 rewrites the file before line 255 queues the restart. cordis loader.py:181-184: `restart` raises LookupError for a row that has gone. The operator has the same unread list, but there a lost job loses nothing that was already written.

Suggested: Report a failed job to the person: for example, have the row depend on `output` and call `notice`, or keep the failure and show it with the next /compact answer. Alternatively, rewrite the file inside the job, just before the restart, so the file and the rows change together.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/compact.py

`kept_in(loader.entries(), ...)` (lines 127-133 and 232) re-reads every layer file from disk instead of looking at the transcript row that is actually mounted. As a result: (1) if any layer cannot be read right now, for example a `--patch` file deleted or half-saved mid-session, /compact fails with a raw parse or OSError message even though the conversation is fine; (2) the path can differ from the file the live row is writing until the watcher reloads; (3) it ignores the entry's `use` and `disabled`, so a transcript row filled by another component, or a disabled one, that has a `path` would have that file overwritten in agent:transcript's JSONL format.

Evidence: cordis loader.py:161-162 `def entries(self): return _entries(self.config)`, and :65-67 `_entries` calls `read_layer(p)` for every layer, which is `Path(path).read_text()` (loader.py:34-36). By contrast, `restart` uses the mounted entries (`self.rows[rid].entry`, loader.py:185). `kept_in` checks only `getattr(e, 'id')` and `config.get('path')`.

Suggested: Find the path from the mounted row, for example a Protocol member that returns the live entry, or check `entry.use == 'agent:transcript'` and `not entry.disabled`. Catch a layer that cannot be read and give a message that says what to do.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/transcript.py

Each /compact replaces the single `.bak` (lines 49-68: `shutil.copyfile(file, backup)`). After a second /compact, the conversation from before the first one is gone. The docstring mentions this ("an earlier one replaced"), but the user-facing docs do not: bh-02/app/README.md says "the old transcript is kept as the session's `transcript.jsonl.bak`" and GLOSSARY.md says "the old transcript kept as `transcript.jsonl.bak`". A person counting on the .bak to recover the full history loses it without warning.

Evidence: transcript.py:56-63 builds `backup = file.with_name(f"{file.name}.bak")` and copies over it unconditionally. git diff of bh-02/app/README.md and bh-02/GLOSSARY.md shows the wording quoted above.

Suggested: Either keep numbered backups (`.bak`, `.bak.1`, ...) or say in the README and GLOSSARY that the .bak holds only the conversation before the latest /compact.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/compact.py

/compact is the first command that waits on a model, for up to `timeout` = 300 s plus the provider's drain, and the person gets no feedback while it does. The screen shows only `› /compact`. Ctrl-C prints nothing: `interrupt()` returns True, so the app neither withdraws anything nor prints the "Nothing is running" note, and the held interrupt is silently dropped at the next read. A long summary looks like a hang. Also, the REFUSED message ("the model declined to summarise the conversation, so nothing changed", line 87) does not say what to do next, against the repo's error-message convention.

Evidence: chat.py:94-96 awaits `commands.run` with no output until it returns. tui app.py:327-334: with `stopped` True and no open questions, nothing is shown. ports.py:233-246 sets `_interrupt_held`, and ports.py:215 drops it in `line()`. grep finds no busy indicator in tui_cordis_plugin.

Suggested: Tell the person before the step starts, for example through a `frame` status field or an `output.notice` like "asking the model for a summary (up to 300 s; this can't be stopped)". Give REFUSED a next step, for example "try /compact WHAT TO KEEP, or /clear to start afresh without a summary".
