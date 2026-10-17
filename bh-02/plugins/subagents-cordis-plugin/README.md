# subagents-cordis-plugin

Sub-agents: the `agent`, `agent_wait`, `agent_send` and `agent_stop` tools and `/agents`, each `agent` call a child conversation of its
own, of a type that is data, mounted in a sealed cordis realm while it runs, its questions put to
the person labelled with its name and type, and its last answer handed back as its report, in the
foreground or, with `background`, to `agent_wait`. The design is decision-0002
(`backlog/decisions`).

| Row | Binds | Consumes |
|---|---|---|
| `subagents:parent` | `asker`: `confirm(request)` over the parent's `output`, only for a request labelled with an agent; `roster`: how many children run and a way to hear it change (read-only); registers the `agent`, `agent_wait`, `agent_send` and `agent_stop` tools (`runs="harness"`), the command `/agents` (list, `stop [NAME]`, `watch NAME`) and a note for the stop notice and the `system` section `agents` (naming the types there are); config: `rows` (the parent's rows a child is made of, by id: `loop`, `tools`, `transcript`, `model`, `system`, `asides`, `access`, `memory`, `on-touch`, `executor`, `python`; never auto memory), `tools` (those of `rows` a type may grant, `["python"]`; every other row each child has), `transcript_row` (`transcript`), `model_row` (`model`), `start` (seconds a child has to come up, 30), `max_running` (children at once, 4), `session_agents` (children started before each further start is asked, 16) | `tools` (`register`), `commands` (`register`, `on_stop`), `model` (its lifetime alone), `system` (`add`), `output` (`confirm`: behind `asker`, and a start it asks about; `show`: a note, and each child's usage), `loader` (`rows`), `host` (`trusted`: where type files are read) |
| `subagents:status` | the status bar's `agents` field: `agents: N running` while a sub-agent runs, absent at none; config: none | `roster` (`running`, `watch`), `frame` (`status`) |
| `subagents:output` | a child's `output`, inside its realm: `confirm(request)` through `asker`, the request labelled `agent: {name, type}`; nothing else; config: `name`, `type` | `asker` |
| `subagents:child` | nothing: a child's own row, inside its realm: its type's section of the prompt (`agent`) and its `loop` passed to the call that mounted it; config: `hand`, `section` | `loop`, `system`, `asides` (`add`: what `agent_send` left) |

The shipped layer fills them as the rows `agents` (`subagents:parent`) and `agents-status`
(`subagents:status`); the two inner rows are written by the agents row into each child's realm, so a
layer names only `subagents:parent` and `subagents:status`. The plugin is `subagents` so that no
plugin's name is a letter from `agent`, the conversation loop's; the row id stays `agents`, the word
the person types (`/agents`, `agents: N running`) and a layer's `clear` and `rows` name. An installed
bh-02 needs `uv tool install --editable ./bh-02/app --reinstall` after the pull that renamed the
plugin.

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
model = "claude/haiku"                                # optional: the session's model
steps = 30                                            # optional: model steps it may take
tools = ["python"]                                    # optional: every row in the agents row's `tools`
```

They are read afresh for each call (off the event loop), and for the `system` section as a
conversation begins. A type chooses a model and so the spend, which is the person's, so a type is
read only from where the model can't write: bh-02's config directories, and never a file whose
reading passes through the project (bh-02 run from a directory that holds its config, or a link
into the project: `host_paths.passes`, as the models file is judged), which the call answers is
not read and why. One that passes is read through no link at all (`host_paths.read_beneath`, from
the descriptor it was opened as, so no link can be swapped in between the check and the read): not
the file, nor the `agents` directory it is in, nor a file with a second name, and at most 64 KiB of
UTF-8; each is answered as not read, with what to do (keep the file itself in the config
directory). A malformed type is refused when a call names it, the error naming the file,
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
   A model a yes chose is the child's alone: its model row's `default`, in its realm. A start is
   counted as it is admitted, before the child's directory is made (on a thread), so two calls
   made together cannot both pass the last of the budget unasked; one that fails before a child
   exists (its directory can't be made, a layer gives it the agents row, the call is cancelled
   while the directory is waited for) is given back with its name, and one that was admitted but
   never comes up has spent its start.

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
   its type grants. The project's guidance is among them (`memory` and `on-touch`, below), with a
   `commands:registry` of the child's own beside it; no auto memory, no `chat`, no `input`, no
   `agents` row: a child can't start one of its own (depth one). A layer whose `rows` names the
   agents row (by its id, or any row using `subagents:parent`) gets an error from the call saying
   so, not a child with one (decision-0002); one that names the auto memory row (any row using
   `memory:auto`) gets the same, below. Then `subagents:output` and `subagents:child`.
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
6. **Its reply**: once `subagents:child` has passed its loop (`Hand`), the run drives
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
row gave no background agent. A report is kept: waiting again returns it again. `background`
is a boolean and `timeout` a number of seconds: the loop's schema check refuses anything else
before the tool runs, and the tool answers it with text of its own when it is run bare
(`background` such as `"true"` starts nothing; a `timeout` that is NaN or infinite is refused
and nothing is waited for).

## Questions, and nothing else of the parent's output

A child's loop asks through its `output`, which is `subagents:output`'s: `confirm` alone, every
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
  one is up is withdrawn, and the child is retired
  (`test_ctrl_c_withdraws_the_open_question_of_the_foreground_child_it_stops` drives a real child's
  open question through it).
- **Retired from outside** while it replies (its realm's fiber), the call ends with no report:
  `gave no report: it was stopped before it answered`.
- **Background children** keep running through Ctrl-C (and an `agent_wait` it stops); the stop notice says how many.
- **The agents row unloading** (a restart, a layer that drops it, the session ending) cancels
  every background run and retires every child it still holds: each mount is an effect
  performed on its fiber, whose undo is the child's retirement.

## What the person sees of a child

cordis's lifecycle listeners are runtime-wide, so a child's rows would read as the parent's;
they run under `agents/NAME/...` instead, and the ui shows none of their lifecycle. `--trace`
keeps every one, prefixed. The runner's status field describes its last start, which may be a
child's: the policy is the same.

## Talking to a child, and ending it

- **`agent_send(name, text)`** (`tools.agent_send(name=..., text=...)` in an input) leaves `text`
  in a running child's mailbox (`Hand`). The child reads it as an *aside* (`subagents:child` adds
  one to its `asides`, which the loop asks after every call, on the executor): the text rides
  with its next call's result, framed `Message from your parent agent (the agent that started
  you), not from the person:` (`parent_message`, decision-0002's default, the owner's to revise).
  A child that answers before another call is made reads what is left as a message of its own:
  the run replies again with it, and the report is then the last turn's. Once the reply has ended
  with the mailbox empty it takes no more: the call answers that the agent has just finished. A
  name that is no running child is answered `error: no sub-agent named ... is running; the
  running ones are ...`. The mailbox is the parent's only way to a child; the child's text never
  reaches the parent but as its report.
- **`agent_stop(name)`** (`tools.agent_stop(name=...)`) retires the child's realm (`Fiber.retire`),
  and with it its python row, whose program the runner stops: the run's report is `gave no
  report: it was stopped before it answered`, and a child still waiting for a slot never mounts.
  Same error for a name that is not running. Foreground children are the parent's reply's: only
  a background one can be stopped from the parent's own tool, and `/agents stop` reaches the
  rest once the reply has ended.
- **`/agents`** lists the running children (name, type, foreground or background, what each is
  doing: waiting to start, starting, calling a tool, thinking, answering, and the path of its
  transcript, for the person). **`/agents stop [NAME]`** ends one or all (a child that ends on its own while an earlier one is
  being stopped is skipped, and the answer names only those it stopped).

### What other commands do to children

Children are the agents row's, so what ends them is the row reloading:

| | children |
|---|---|
| `/clear` | end, each with a note. The shipped `conversation` row's `clear` names `agents` beside `loop`, `transcript` and `python`, so a new conversation restarts this row; a layer replacing that row's config must keep it to keep this. |
| `/model NAME` | end, each with a note: the row consumes `model` (for its lifetime alone), which a switch reloads; their reports would land in another conversation. |
| a restart of the row (`/restart agents`, a layer that changes it) | end, each with a note. |
| `/compact` | keep running: nothing it restarts (`loop`, `transcript`) is a row this one depends on. |
| `/release` | stops their python programs only: each child's python row registers its stop with the runner as the parent's does. Their conversations go on, and the next input starts a program again. |

The note for a child ended this way is `agent NAME (TYPE) was ended before it answered: the agents
row restarted ...` (shown by the run as it ends, whatever ended it from outside), and a restart
counts the session's budget and names afresh. Unloading waits (5 seconds) for the runs of retired
children to say so before cancelling the rest.

After Ctrl-C the chat row shows the notes rows have for a stop (`commands.stop_notes`): this
row's is `2 background agents still run; /agents stop ends them`, none when no background child
runs.

## Watching a child

- **Its event log.** Each child's events go to `<session>/agents/NAME/events.jsonl` (`eventlog.py`),
  beside its transcript and under the same state directory, which `host.secrets` keeps from every
  jail: an input can neither read it nor append a forged record (`test_a_jailed_input_can_neither_read_nor_forge_a_sub_agent_s_event_log`).
  The file is made by the agents row alone, in one `open` with `O_CREAT | O_EXCL | O_NOFOLLOW` and mode
  0600 (not the umask's: a test runs with umask 0), so there is no moment it is wider. A line is
  `{"at": TIME, "event": ...}`: first `agent_start` (name, type, prompt, background), then every
  event of the child's reply as it came, then `agent_end` with the report (or why it gave none),
  whatever ended the child. Writes run on a thread, so the event loop never waits on a disk, one
  after the other: a record waits for the write before it, even one a cancelled child's caller left
  to finish, so the end record never overtakes or mixes with it, and closing waits for the last; one
  that fails (a full disk) stops the log and the child goes on. A session kept in memory has no log;
  a log that can't be made is said in a note, and the child runs without one.
- **`bh-02 watch SESSION AGENT`** (the app's, `bh_02.watching`) renders one log read-only, follows it
  until `agent_end` (`--once` stops after what is there), and refuses names bh-02 did not make before
  it builds a path: it reads through `host_paths.read_beneath` (no link, a descriptor opened
  read-only). Terminal control characters and bidirectional overrides in what the model wrote are dropped.
- **The status field.** `subagents:status` shows `agents: N running` while any child runs and takes the
  field down at none, following the agents row's `roster`. A layer with no ui has no `frame`, and so
  no field.
- **`/agents watch NAME`** answers with the command to run in another terminal, `bh-02 watch SESSION NAME`,
  for any child this row has started in this run, running or ended (its log is kept). That is the
  choice for showing a child's log: the TUI does not render it itself; it works the same inside tmux
  or outside it. A child of a session kept in memory is answered as having no log.
- **No tmux panes yet.** Opening a pane per child, and darwin's check that Seatbelt stops a connection
  to the tmux socket, are TASK-0080.10. `TMUX` and `TMUX_PANE` are in the environment of no program
  the runner starts (`runner-cordis-plugin`).

## The project's guidance in a child

A child's prompt has the project's guidance as the parent's has it, and its python inputs are
told what loads on demand: its `rows` (by default) include the parent's `memory` row
(`memory:files`: the CLAUDE.md and AGENTS.md files, imports and rules, a section of its
`system` prompt, read fresh before each message the child reads) and `on-touch` row
(`memory:on_touch`: a subdirectory's CLAUDE.md or a rule for the files an input opened, an aside to
that input's result, once in the child's conversation), each copied with the parent's config (the
project, the person's home, the excludes) like every other row. A child's conversation is its
own, so it is told afresh what the parent was told; its `access` row refuses its first write to a
file whose instructions it has not been told, as the parent's does. A layer with no memory rows
gives a child none.

`memory:files` registers `/memory` with `commands`, which the sealed realm does not read from
outside. So the agents row writes a `commands:registry` into each child's realm beside the memory
row (`agents/NAME/commands`, unless the layer's `rows` already gave it one): the child's own
value, which nobody runs a line through (a child has no `chat`), so the parent's registry never
holds the child's `/memory` and the child never reaches the parent's `/agents`. The exposed set is
still `runner`, `approval`, `host` and `asker`.

**No auto memory in a child.** N children writing one auto memory directory would race the
parent (decision-0002), and the child is a task's worker, not a conversation the person has with
the model. A `rows` that names a row using `memory:auto` is refused as one naming the agents row
is: the call answers `a child has no auto memory ...; take it out of `rows``, and mounts nothing
(`test_no_child_composition_includes_auto_memory_though_the_parent_has_it`,
`test_a_layer_naming_the_auto_memory_row_among_the_child_s_rows_fails_the_call_and_mounts_no_child`).
The jail still lets a child's python input write the directory the parent's `host` names
(`auto_memory`), as it lets the parent's; the child is not told it is there.
