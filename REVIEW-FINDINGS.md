# Open review findings for TASK-0050 (not yet addressed)

From the workflow's two review lenses (acceptance, cordis). Delete this file once each is fixed or answered.

## [major] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/loop.py

Readings can still pile up when the loop reloads between stops, and the docs claim a limit that doesn't hold. The in-flight call is kept per LoopModel (loop.py:258-259, `self._working = None`). `agent:loop` builds a new LoopModel every time its row loads (wiring.py:56), and /clear and /model both reload it. `system` (context:project) is not reloaded, so the same lock-free ContextFiles caches are shared across loops. Each 'Ctrl-C, /clear (or /model), send again' cycle therefore starts one more reading beside the earlier ones, with no upper limit. This is the deviation 3 the implementer disclosed, but the cost it states is wrong, and these docs now say something false: (a) the `_off_loop` docstring, loop.py:264-266, says 'the context plugin's caches are never used by two threads at once'; (b) the Memory Protocol docstring, loop.py:87-88, says memory runs 'never beside a reading of the prompt'; (c) the context_file.py:140-144 comment says 'The one overlap is such a call beside the first of a loop that reloaded meanwhile'; (d) the agent README.md:87-88 says the new loop's first reading 'may run beside one the last loop left'. In practice four readings ran at once on one ContextFiles. Shutdown is still fine, because every thread is a daemon.

Evidence: I wrote an end-to-end pty probe (scratchpad wf-review/drive_clear.py). It starts the real `.venv/bin/bh-02 --no-jail --model fake` with a `--patch` that replaces the `system` row by a ProjectContext wrapper whose text() sleeps 40 s and logs each reading. The probe repeats 'type message, Ctrl-C, /clear' four times, then presses Ctrl-Q. The fixed code logged:
  begin #1 running=1 thread=bh-02 agent:loop daemon=True
  begin #2 running=2 ...
  begin #3 running=3 ...
  begin #4 running=4 ...
so four readings ran at once. The same probe without /clear (drive.py) logged only `begin #1 running=1`, so pure Ctrl-C is bounded. The screen showed 'loop reloaded' after each /clear.

Suggested: Keep the in-flight call somewhere that outlives a loop reload. One option is a small row of its own that depends on nothing, as `memory` does. It would provide a one-at-a-time daemon runner that `agent:loop` takes as a dependency, so /clear and /model keep it. If per-LoopModel is kept on purpose, correct (a) to (d) instead: say that each reload can add one more reading on the shared caches, with no limit across reloads, and drop the 'never two threads at once' and 'never beside a reading' claims.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/loop.py

When a reading left behind by a stopped reply later fails, asyncio now logs it at ERROR. It's reported to the event loop's exception handler as 'OSError exception in shielded future'. Deviation 1 says awaiting through `asyncio.shield` means asyncio logs nothing ('no exception never retrieved'), but on Python 3.15 shield adds `_log_on_exception` to the inner future once the outer is cancelled. The old `asyncio.to_thread` path dropped such a failure silently, because the cancelled asyncio future ignores the concurrent future's late result. Inside the TUI, Textual redirects stderr so nobody sees it, but the new test itself emits the error, and it reaches the terminal if the failure lands after Textual restores stderr at exit.

Evidence: `pytest bh-02/plugins/agent-cordis-plugin/tests/test_loop.py -k fails_costs -o log_cli=true --log-cli-level=ERROR` prints
  ERROR    asyncio:base_events.py:1897 OSError exception in shielded future
  future: <Future finished exception=OSError('the project went away')>
  ... PASSED
In CPython 3.15.0rc3, asyncio/tasks.py:1019-1024 (`_outer_done_callback`) does `inner.add_done_callback(_log_on_exception)`, which calls `loop.call_exception_handler(...)`. The call site is loop.py:280: `return await asyncio.shield(working)`.

Suggested: Don't await the call through shield. Add a done-callback on `working` that reads its exception (`f.cancelled() or f.exception()`), then use `await asyncio.wait([working]); return working.result()`. A cancelled wait leaves `working` untouched and logs nothing. Or keep shield and correct the claim.

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/loop.py

Deviation 1 says the shield on a call's own awaiter stops asyncio from logging anything about a stopped reply's left-behind call that raises. That is wrong on the Python 3.15 this repo runs. When the outer future is cancelled, asyncio.shield attaches `_log_on_exception` to the inner future, so a failing left-behind reading goes to the loop's exception handler as an ERROR with its full traceback. The old `asyncio.to_thread` path said nothing in this case: `_copy_future_state` returns early when the destination was cancelled. bh-02 sets no exception handler, so under Textual the error goes to the captured stderr. If the failure lands after the TUI has torn down but before the loop closes, it prints to the real terminal. test_a_stopped_reply_s_reading_that_fails_costs_the_next_reply_nothing does not check for this log.

Evidence: A scratch probe (scratchpad/probe/probe.py, run with the worktree's .venv, Python 3.15.0rc3): a LoopModel whose system.text() raises OSError on the first reading; that reply is cancelled while the reading is held, then released. Output:
`ERROR:asyncio:OSError exception in shielded future
future: <Future finished exception=OSError('gone')>
Traceback ... loop.py, line 164, in _settle ... OSError: gone
second: ['text', 'stop']`.
asyncio/tasks.py:939 `_log_on_exception` calls `call_exception_handler({'message': f'{exc.__class__.__name__} exception in shielded future', ...})`; shield's `_outer_done_callback` adds it to the inner future at tasks.py:1023-1024. loop.py:280 is `return await asyncio.shield(working)`.

Suggested: Have the loop take a left-behind call's outcome quietly. One way: a done-callback on `working` that calls `f.exception()` when the future is not cancelled. Then wait with `await asyncio.wait([working]); return working.result()` instead of shield (asyncio.wait never cancels the inner future and adds no logging callback). Assert in the failing-reading test that nothing is logged at ERROR, using caplog.

## [minor] bh-02/plugins/context-cordis-plugin/README.md

Some docs still say, with no exception, that calls run one at a time and that the caches are used by one thread at a time. The code now has a known overlap: the in-flight handle `_working` belongs to each LoopModel, so after a loop reload the new loop's first reading can run beside one the old loop left. The updated context_file.py comment and the agent README say so; these places don't. context-cordis-plugin/README.md:41 says "The loop awaits each before the next, so the one set of caches ... is used by one thread at a time and takes no lock". The Memory Protocol docstring at loop.py:88 says calls are "never beside a reading of the prompt". bh-02/CLAUDE.md:123-128 says "Ctrl-C after Ctrl-C leaves at most one in flight" and does not mention reloads.

Evidence: loop.py:259 sets `self._working = None` in `__init__`. wiring.py:56 builds a new `LoopModel(...)` each time the loop row loads, and that row depends on model, kernel, transcript, system, approval and memory. agent README (new text): "A loop that reloads (`/model`, `/clear`) starts with none in flight, so its first reading may run beside one the last loop left." context_file.py:140-144 (new): "The one overlap is such a call beside the first of a loop that reloaded meanwhile". context README:41 still states the guarantee with no exception.

Suggested: Add the reload exception to context-cordis-plugin/README.md:41 (or point it at the ContextFiles comment, as project.py:86-90 does). Soften the Memory docstring's "never beside a reading of the prompt" to "one at a time within a loop".

## [minor] bh-02/plugins/agent-cordis-plugin/src/agent_cordis_plugin/loop.py

The guard against the pile-up lives on the `loop` value, but what it protects (the `system` value's ContextFiles caches, and the state each `memory` contributor keeps) belongs to rows that outlive a loop reload. So the bound resets every time the loop row reloads: on /model, /clear, /restart, a new ui (through approval), or a kernel or system reload. Repeating "Ctrl-C during a slow reading, then /clear (or /model), then a message" still leaves one more reading thread per round. AC1 is met for plain repeated stops, and the implementer documented this as deviation 3. Recorded here because a user stuck on a slow reading is likely to try /clear or /model between stops.

Evidence: loop.py:259 `self._working: asyncio.Future[Any] | None = None` (per instance). loop.py:272-279 waits only on `self._working`. wiring.py:56 constructs a fresh LoopModel on each load of the loop row. The test that reproduces the pile-up uses one LoopModel throughout (test_loop.py, test_replies_stopped_over_and_over_...).

Suggested: Optional. Keep the in-flight handle somewhere that outlives the loop and is shared by every caller of `system`/`memory` (for example a small lock or single-flight held by the system value), or hand the old loop's in-flight future to the new one. Otherwise leave it as the documented limit.
