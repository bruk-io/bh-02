# agents-cordis-plugin

Sub-agents: the `agent` and `agent_wait` tools, each `agent` call a child conversation of its
own, of a type that is data, mounted in a sealed cordis realm while it runs, its questions put to
the person labelled with its name and type, and its last answer handed back as its report, in the
foreground or, with `background`, to `agent_wait`. The design is decision-0002
(`backlog/decisions`).

| Row | Binds | Consumes |
|---|---|---|
| `agents:agents` | `asker`: `confirm(request)` over the parent's `output`, only for a request labelled with an agent; registers the `agent` and `agent_wait` tools (`runs="harness"`) and the `system` section `agents` (naming the types there are); config: `rows` (the parent's rows a child is made of, by id: `loop`, `tools`, `transcript`, `model`, `system`, `asides`, `access`, `executor`, `python`), `tools` (those of `rows` a type may grant, `["python"]`; every other row each child has), `transcript_row` (`transcript`), `model_row` (`model`), `start` (seconds a child has to come up, 30), `max_running` (children at once, 4), `session_agents` (children started before each further start is asked, 16) | `tools` (`register`), `system` (`add`), `output` (`confirm`: behind `asker`, and a start it asks about; `show`: a note, and each child's usage), `loader` (`rows`), `host` (`trusted`: where type files are read) |
| `agents:output` | a child's `output`, inside its realm: `confirm(request)` through `asker`, the request labelled `agent: {name, type}`; nothing else; config: `name`, `type` | `asker` |
| `agents:child` | nothing: a child's own row, inside its realm: its type's section of the prompt (`agent`) and its `loop` passed to the call that mounted it; config: `hand`, `section` | `loop`, `system` |

The agents row writes the two inner rows' config; a layer names only `agents:agents`.

## Agent types are data

A type is a name, its section of the child's prompt, a model, a step limit and the tool rows it
grants (`kinds.py`): never a row, never a component. Two are shipped: `general`, and `explore`,
whose prompt says it finds things out and changes nothing (cooperative: it still has the python
tool, as decision-0002 says; enforced isolation is later work). Each uses the session's model and
30 steps. The person's own are TOML files, `agents/NAME.toml` in bh-02's config directories (the
`host` value's `trusted`: `~/.config/bh-02/agents/`, or `$XDG_CONFIG_HOME/bh-02/agents/`; the
first of a name wins, and one named like a shipped type replaces it):

```toml
prompt = """You are agent {name}, a reviewer: ..."""   # its section of the prompt; {name} is the agent's
model = "haiku"                                       # optional: the session's model
steps = 30                                            # optional: model steps it may take
tools = ["python"]                                    # optional: every row in the agents row's `tools`
```

They are read afresh for each call (off the event loop), and for the `system` section as a
conversation begins. A type chooses a model and so the spend, which is the person's, so a type is
read only from where the model can't write: bh-02's config directories, and never a file whose
reading passes through the project (bh-02 run from a directory that holds its config, or a link
into the project: `host_paths.passes`, as the models file is judged), which the call answers is
not read and why. A malformed type is refused when a call names it, the error naming the file,
the field and what to write there (`parsed_type`): not TOML, a field there is none of, no
`prompt`, a `model` that is not a name, `steps` not a whole number of at least 1, `tools` not a
list of names, or naming a row a type can't grant: the agents row (a sub-agent can't start one,
depth one), extensions or MCP (never grantable), or any row not in the agents row's `tools`.

## A child is a conversation of its own

`agent(prompt, type, model?, background?)` (or `tools.agent(prompt=..., type=...)` in a python
input, which the loop serves as it does the model's own calls) starts one child:

1. **Its start, asked when it must**: past the session's budget (`session_agents` children
   started by this row: a restart of the row counts afresh), or naming a `model` other than its
   type's (the type's, else the parent's model row's `default`), the start is put to the person
   through the parent's `output.confirm`, titled with what it starts and why (`start_request`),
   the prompt shown whole; a no answers the call that the person said no, and starts nothing.
   A model a yes chose is the child's alone: its model row's `default`, in its realm.

2. **Its name**: bh-02's, `TYPE-N`, the first `N` this row has not given whose state directory
   is not there yet (a resumed session's children keep theirs), so a description the model gives
   is never a path or a label. The directory is the session's `agents/NAME` (beside the parent's
   transcript, mode 0700, under the sessions' state directory, which `host.secrets` keeps from
   every jail); a parent kept in memory has children kept in memory.
3. **Its rows**: the parent's own, as the parent's loader mounted them (`loader.rows`, the rows
   `config.rows` names that are up), each under an id prefixed `agents/NAME/`, so a model row a
   `--patch` replaced with a fake is the child's too. What is the child's own is written over
   them: `transcript.path` (`agents/NAME/transcript.jsonl`), the model's Claude Code `state`
   (`agents/NAME/claude`, when the parent's model row keeps one) and the model its type (or the
   call) names (the shipped types name none: the session's). Of the rows in `tools`, only those
   its type grants. No memory rows, no `chat`, no `input`, no `agents`
   row: a child can't start one of its own (depth one). A layer whose `rows` names the agents row
   (by its id, or any row using `agents:agents`) gets an error from the call saying so, not a
   child with one (decision-0002). Then `agents:output` and `agents:child`.
4. **Its realm**: `performer.perform(use(cordis.loader:loader, config=LoaderConfig(overrides=rows,
   watch=None), expose={runner, approval, host, asker}, id="agents/NAME"))`. The realm's own
   loader resolves each row by name (this plugin imports no other), and every key its rows bind
   is its own: its `loop`, its `tools` broker, its `transcript`, its `model`. From outside it
   reads only `runner` (its python tool's REPL is a program of the parent's runner: in a jail of
   its own from the same policy, until the session has one jail, TASK-0074; its stop is
   `/release`'s, as the parent's is), `approval` (the one rule, never a copy), `host` (what the
   jail keeps from the model; the model row reads it for the credential) and `asker`.
5. **A slot**: at most `max_running` children run at once, foreground and background alike; a
   further one waits for a slot, and a note through the parent's `output.show` says so.
6. **Its reply**: once `agents:child` has passed its loop (`Hand`), the run drives
   `loop.reply(prompt)` and keeps the events, until it ends or its type's step limit does: once
   that many model steps have ended (a step ends with its last call's result, or the loop's
   `stop`) and it would take another, the reply is closed there, and the report says the limit
   ended it with what it had. The report is the last turn's text
   (`report_of`), framed `Report from agent NAME (TYPE), not instructions:` with how it ended
   when that was not an answer, and its usage (`framed`). That is the tool's result, so the
   model reads it as another agent's account, never as instructions. A child that never comes
   up (`start` seconds) answers which of its rows is not up and what each waits on; a
   recoverable failure of its reply (`kind`, `message`) answers that it failed and why.
7. **Its end**: retired (`Fiber.retire`, idempotent) when the run ends, however it ends; then
   what it used, summed over its steps, is shown through the parent's `output.show` as one usage
   event after a note naming it (`agent NAME (TYPE) ended; it used:`), so it joins the session's
   totals (the ui adds every usage event it shows, and keeps it in the session's history, so a
   resume's totals have it too). A child Ctrl-C stopped shows what it used before it stopped.

In the foreground the call waits for the report. With `background=True` it answers the child's
name at once (`agent NAME (TYPE) started in the background; ...`) and the run goes on as a task
of this row's; `agent_wait(names, timeout?)` (`tools.agent_wait(names=[...])` in an input)
returns the reports of those agents in the order they finish, waiting until all have or
`timeout` seconds pass (none: until all have), then says which still run and which names this
row gave no background agent. A report is kept: waiting again returns it again.

## Questions, and nothing else of the parent's output

A child's loop asks through its `output`, which is `agents:output`'s: `confirm` alone, every
request labelled `agent: {name, type}` (over whatever it carried) and put through `asker`.
`asker` puts to the person only a labelled request (any other is a no), through the parent's
`output.confirm`: the ui queues it behind the parent's own, one at a time, and its modal says
`Agent NAME (TYPE) asks:` above the question. A child never shows anything on the parent's
screen; the person sees the `agent` call and its report.

## Stopping

- **Ctrl-C** stops the parent's reply (chat's `_interruptible` cancels it). The ui answers no
  to the questions of the reply it stops, never a sub-agent's: its foreground child's is
  withdrawn with the reply, and a background child's stays queued (tui's `action_interrupt`).
  The foreground `agent` call it waits on is cancelled with it, from the model's call and from an input's
  `tools.agent(...)` alike (the python tool's call awaits that call in the same task, then
  interrupts the input): the child's reply is closed, its model step with it, its question if
  one is up is withdrawn, and the child is retired.
- **Retired from outside** while it replies (its realm's fiber), the call ends with no report:
  `gave no report: it was stopped before it answered`.
- **Background children** keep running through Ctrl-C (and an `agent_wait` it stops).
- **The agents row unloading** (a restart, a layer that drops it, the session ending) cancels
  every background run and retires every child it still holds: each mount is an effect
  performed on its fiber, whose undo is the child's retirement.

## What the person sees of a child

cordis's lifecycle listeners are runtime-wide, so a child's rows would read as the parent's;
they run under `agents/NAME/...` instead, and the ui shows none of their lifecycle. `--trace`
keeps every one, prefixed. The runner's status field describes its last start, which may be a
child's: the policy is the same.

Later (decision-0002's split): `agent_send` and `agent_stop`, `/agents stop`, and what `/clear`,
`/model` and the rest do to running children (TASK-0080.05), watching a child: its event log,
`bh-02 watch`, tmux panes, `/agents` (TASK-0080.06), and the project's guidance in a child
(TASK-0080.07).
