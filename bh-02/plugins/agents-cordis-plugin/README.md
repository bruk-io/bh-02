# agents-cordis-plugin

Sub-agents: the `agent` tool, each call a child conversation of its own, mounted in a sealed
cordis realm while it runs, its questions put to the person labelled with its name and type,
and its last answer handed back as its report. The design is decision-0002 (`backlog/decisions`);
this is the first of it: one shipped type, `general`, in the foreground.

| Row | Binds | Consumes |
|---|---|---|
| `agents:agents` | `asker`: `confirm(request)` over the parent's `output`, only for a request labelled with an agent; registers the `agent` tool (`runs="harness"`) and the `system` section `agents`; config: `rows` (the parent's rows a child is made of, by id: `loop`, `tools`, `transcript`, `model`, `system`, `asides`, `access`, `executor`, `python`), `transcript_row` (`transcript`), `model_row` (`model`), `start` (seconds a child has to come up, 30) | `tools` (`register`), `system` (`add`), `output` (`confirm`, behind `asker`), `loader` (`rows`) |
| `agents:output` | a child's `output`, inside its realm: `confirm(request)` through `asker`, the request labelled `agent: {name, type}`; nothing else; config: `name`, `type` | `asker` |
| `agents:child` | nothing: a child's own row, inside its realm: its type's section of the prompt (`agent`) and its `loop` passed to the call that mounted it; config: `hand`, `section` | `loop`, `system` |

The agents row writes the two inner rows' config; a layer names only `agents:agents`.

## A child is a conversation of its own

`agent(prompt, type)` (or `tools.agent(prompt=..., type=...)` in a python input, which the loop
serves as it does the model's own calls) runs one child to its end:

1. **Its name**: bh-02's, `TYPE-N`, the first `N` this row has not given whose state directory
   is not there yet (a resumed session's children keep theirs), so a description the model gives
   is never a path or a label. The directory is the session's `agents/NAME` (beside the parent's
   transcript, mode 0700, under the sessions' state directory, which `host.secrets` keeps from
   every jail); a parent kept in memory has children kept in memory.
2. **Its rows**: the parent's own, as the parent's loader mounted them (`loader.rows`, the rows
   `config.rows` names that are up), each under an id prefixed `agents/NAME/`, so a model row a
   `--patch` replaced with a fake is the child's too. What is the child's own is written over
   them: `transcript.path` (`agents/NAME/transcript.jsonl`), the model's Claude Code `state`
   (`agents/NAME/claude`, when the parent's model row keeps one) and the model its type names
   (`general` names none: the session's). No memory rows, no `chat`, no `input`, no `agents`
   row: a child can't start one of its own (depth one). Then `agents:output` and `agents:child`.
3. **Its realm**: `performer.perform(use(cordis.loader:loader, config=LoaderConfig(overrides=rows,
   watch=None), expose={runner, approval, host, asker}, id="agents/NAME"))`. The realm's own
   loader resolves each row by name (this plugin imports no other), and every key its rows bind
   is its own: its `loop`, its `tools` broker, its `transcript`, its `model`. From outside it
   reads only `runner` (its python tool's REPL is a program of the parent's runner: in a jail of
   its own from the same policy, until the session has one jail, TASK-0074; its stop is
   `/release`'s, as the parent's is), `approval` (the one rule, never a copy), `host` (what the
   jail keeps from the model; the model row reads it for the credential) and `asker`.
4. **Its reply**: once `agents:child` has passed its loop (`Hand`), the call drives
   `loop.reply(prompt)` and keeps the events; the report is the last turn's text
   (`report_of`), framed `Report from agent NAME (TYPE), not instructions:` with how it ended
   when that was not an answer, and its usage (`framed`). That is the tool's result, so the
   model reads it as another agent's account, never as instructions. A child that never comes
   up (`start` seconds) answers which of its rows is not up and what each waits on; a
   recoverable failure of its reply (`kind`, `message`) answers that it failed and why.
5. **Its end**: retired (`Fiber.retire`, idempotent) when the call ends, however it ends.

## Questions, and nothing else of the parent's output

A child's loop asks through its `output`, which is `agents:output`'s: `confirm` alone, every
request labelled `agent: {name, type}` (over whatever it carried) and put through `asker`.
`asker` puts to the person only a labelled request (any other is a no), through the parent's
`output.confirm`: the ui queues it behind the parent's own, one at a time, and its modal says
`Agent NAME (TYPE) asks:` above the question. A child never shows anything on the parent's
screen; the person sees the `agent` call and its report.

## Stopping

- **Ctrl-C** stops the parent's reply (chat's `_interruptible` cancels it). The `agent` call it
  waits on is cancelled with it, from the model's call and from an input's
  `tools.agent(...)` alike (the python tool's call awaits that call in the same task, then
  interrupts the input): the child's reply is closed, its model step with it, its question if
  one is up is withdrawn, and the child is retired.
- **Retired from outside** while it replies (its realm's fiber), the call ends with no report:
  `gave no report: it was stopped before it answered`.
- **The agents row unloading** (a restart, a layer that drops it, the session ending) retires
  every child it still holds: each mount is an effect performed on its fiber, whose undo is the
  child's retirement.

## What the person sees of a child

cordis's lifecycle listeners are runtime-wide, so a child's rows would read as the parent's;
they run under `agents/NAME/...` instead, and the ui shows none of their lifecycle. `--trace`
keeps every one, prefixed. The runner's status field describes its last start, which may be a
child's: the policy is the same.

Later (decision-0002's split): agent types as data and background agents with their limits
(TASK-0080.04), `agent_send` and `agent_stop` (TASK-0080.05), watching a child: its event log,
`bh-02 watch`, tmux panes, `/agents` (TASK-0080.06), and the project's guidance in a child
(TASK-0080.07).
