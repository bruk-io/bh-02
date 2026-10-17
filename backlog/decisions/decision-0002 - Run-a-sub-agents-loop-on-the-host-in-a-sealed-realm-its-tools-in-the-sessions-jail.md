---
id: decision-0002
title: >-
  Run a sub-agent's loop on the host in a sealed realm, its tools in the
  session's jail
date: '2026-10-12 00:39'
status: accepted
---
## Context

TASK-0080 (sub-agents) leaves four questions the implementation needs answered: where a child's loop runs, its limits, what comes back to the parent, and how parallel writers are kept apart. The constraints are bh-02's rules: one loop per conversation; `tools.serve` is one loop's, a second raises; a conversation's prompt and tool list stay fixed; nothing blocks the TUI's event loop; approval is one rule in one row; only a layer's rows act in bh-02's process. decision-0001 (accepted) puts every process of a session in one jail, each with its own namespaces where the jail type allows, and has agents talk only through the embedder.

Two ways were open:

- **The loop in the jail.** An agents program inside the jail runs each child's loop and borrows the host for model steps. Nothing on the host changes, but the rows a loop leans on (the prompt's sections, `access`, approval) are host rows, so the jail would need a second copy of each, and every model step would cross the jail.
- **The loop on the host.** Each child is another conversation in bh-02's process, its tools running in the session's jail. It gets the whole composition, but `tools`, `transcript`, `model` and `loop` are one per process today.

cordis already has what removes the second option's cost. A **realm**: `use(child, expose={...})` mounts a sealed subtree that reads only the exposed keys from outside and keeps every key it binds to itself (libs/cordis/README.md, Concepts; `tests/test_runtime.py::test_a_sealed_subtree_sees_only_what_it_was_exposed_and_keeps_the_rest`). And a **performer**: a component performs effects after its setup, their undos joining its fiber's stack, so unloading the component unwinds them (`cordis.performer`, runtime.py `Performer`, whose docstring names this case: "a session mounting what a model just wrote"). cordis's README lists "per-session realms wired into a harness" as not yet composed; this decision composes it.

## Decision

### A child's loop runs on the host, in a sealed realm

The `agents` row mounts each sub-agent while it lives: `await performer.perform(use(loader, config=LoaderConfig(overrides=child_rows, watch=None), expose={...}))`. The nested `cordis.loader:loader` resolves `agent:loop`, `agent:tools` and the rest by name through entry points, so the agents plugin imports no other plugin (plugin-layering). `child_rows` are the rows of an ordinary conversation (`loop`, `tools`, `transcript`, `model`, `system`, `asides`, `access`, `executor`, `python`), each binding its key privately; the agents row writes their config: the child's `transcript.path` (its own state directory) and `models:model`'s default (the type's model). Retiring the child's fiber (`Fiber.retire`, idempotent) ends it early; the agents row unloading retires every child. No new cordis mechanism is needed; a cordis-helpers wrapper only once a second use shows up.

From outside, the realm sees only what it is exposed:

| Key | Why the child needs it |
|---|---|
| `runner` | its python tool's REPL is a process in the session's jail (TASK-0074; until then, a jail of its own from the same policy) |
| `approval` | the one rule, never a copy |
| `host` | what the jail keeps from the model |
| `asker` | a narrow key the agents plugin provides outside over the parent's `output`: `confirm(request)` only, the request labelled with the agent's name and type |

Inside the realm a small `agents:output` row provides the child's `output` over `asker`: `confirm` reaches the person through the parent's ui, labelled; the loop never calls `show`. The child gets nothing else of the parent's `output`. The agents row itself depends on `models` (to check a type's model), outside the realm.

TUI questions queue one at a time and a cancelled one is withdrawn (tui app.py, ports.py), so a child's question waits behind the parent's and stalls only that child; each child has its own `executor` thread, so nothing blocks the event loop. `ApprovalScreen` shows the request's agent label.

A child has no `input`, no `chat` row and no memory rows in this milestone: the agents row drives its `loop.reply(prompt)` and writes the events to the child's event log. Project guidance in a child (`memory:files` with a private `commands` registry, never `memory:auto`, whose writes would race the parent's) is later work.

A child's rows must not look like the parent's: cordis's lifecycle listeners are runtime-wide, so the child's row ids carry a prefix (`agents/<id>/...`) and the ui ignores lifecycle events under it; `--trace` keeps them, prefixed. A child's starts share the parent's `runner`, whose report describes the last start; that is acceptable because the policy is identical, and the status names whose start it was.

### Agent types are data

A type is a name, a prompt section, a model name, a step limit and the tools it may use, read from bh-02's config directory (`~/.config/bh-02/agents/NAME.toml`) and the shipped ones (`explore`, `general`). Data, not rows: a type chooses only among the rows listed above, never extensions or MCP, and never names a component. Types are read only from places the model can't write (`host.trusted`), as the models file is. This reverses the M6 milestone's first sketch (types interpreted in the jail, possibly from the project): a type chooses a model and so the spend, which the person decides, not the project.

### Tools, and the Python side

The `agents` row registers four tools, each also a function in a python input (`tools.NAME(...)`):

- `agent(prompt, type, model?, background?)`: the child's report, or its name when `background`;
- `agent_wait(names, timeout?)`: the reports of those agents as they finish;
- `agent_send(name, text)`: a message into a running child's conversation, framed as from its parent agent;
- `agent_stop(name)`: ends the child and everything it started.

bh-02 names agents (`TYPE-N`); a description the model gives is shown as text, never used as an argument (tmux, paths, labels take only bh-02's names).

They run in bh-02's process. Today a request with `runs="host"` is always asked (CONTRACTS `tools`, runner approval.py). These declare a new value, `runs="harness"`: bh-02's own code, acting only on the session's jail and bh-02's own state, unasked when the runner confines and asked when it doesn't (`--no-jail`). Only a layer's row can make that claim (extensions are forced to `"jail"`). CONTRACTS' `request.runs` gains the value. (Amended 2026-10-17, TASK-0068: the memory tool does not use this case. It took a `runs` value of its own, `"memory"`, which is never asked, jailed or under `--no-jail`, since it writes only beneath `host.auto_memory` through no link, which the jailed model can already write; the owner ruled so. This case stays the agents tools'.) A sub-agent's own calls go through the same rule, from inside its realm.

### Limits, and what the person controls

- **Depth:** one. A child's composition has no `agents` row unless its type grants it, and no shipped type does.
- **How many at once:** the `agents` row's `max_running`, default 4; a fifth `agent` call waits for a slot, saying so.
- **Steps:** each child has a step limit from its type (default 30 model steps); reaching it ends the child with what it has, said in its report.
- **The session:** a session budget, `session_agents` (default 16 children); once spent, each further `agent` call is asked. A call naming a model other than its type's is asked.
- **Stopping:** Ctrl-C stops the parent's reply and any child it is waiting on (`agent` without `background`, from the tool or from a python input). Background children keep running; the stop notice says how many and `/agents stop`. Ctrl-C refuses only the questions of the reply it stops (the parent's and its foreground child's); a background child's open question stays queued (today the TUI answers every open question no on Ctrl-C, which changes with background children, TASK-0080.04). They also end at `agent_stop`, `/agents stop`, `/clear`, `/model` (their reports would land in another conversation), a restart of the `agents` row (each with a notice), and the end of the session. `/compact` keeps them. `/release` stops their REPLs, as it does the parent's; their conversations go on.
- **Questions under `--no-jail`:** each child's python call is asked, labelled; questions queue and each child waits on its own.

### What comes back

The report is the `agent` tool's result: the final answer only, framed as the agent's report ("Report from agent NAME (TYPE), not instructions:") with its usage. The transcript's path is for the person and `/agents`, never the model (the state directory is `host.secrets`). The child's usage reaches the session's totals as a usage event the agents row shows through the parent's `output` when the child ends. Everything else stays in the child's transcript and event log.

### Watching

Each child's events go to an event log in its own state directory (`<session>/agents/<name>/events.jsonl`, mode 0600, under `host.secrets`, so the jail can neither read nor forge it) beside its transcript. `bh-02 watch SESSION AGENT` renders one, read-only. Inside tmux, the `agents` row opens a detached split per child running that viewer (`tmux split-window -d -h -P -F '#{pane_id}' -- bh-02 watch ...`, off the event loop), every argument a name bh-02 chose. Outside tmux there is a status field (`agents: 2 running`) and `/agents` (list, watch, stop). `TMUX` and `TMUX_PANE` are scrubbed from every program the runner starts: the confined runner's environment allowlist already drops them; the unconfined runner must too, which there is hygiene, not a boundary (an input under `--no-jail` can open the socket itself). On darwin, where the jail reads by denylist, a check that Seatbelt stops a connection to the tmux socket under /tmp is a precondition for opening panes there.

### Parallel writers

Children share the project's files, as decision-0001's namespace bundle intends. A type that must not write says so in its prompt and gets no editing tools beyond python; that is cooperative, and `/agents` says so. Enforced isolation (a worktree, or a jail narrowed from the session's) is later work, not this milestone.

### Teams

Not in this milestone. If built, through the same router, never a shared mailbox.

### Split

M6 needs no brig task: a child's REPL runs in a jail of its own from the same policy until TASK-0074, which later moves it into the session's jail. The tasks, in order:

1. TASK-0080.02 (size-1): approval's `runs="harness"` case and CONTRACTS.
2. TASK-0080.03 (size-5): one child end to end: the realm mounted and retired through a performer, the exposed set with `asker` and the labelled confirm, row-id prefixing, `agent(prompt, type)` in the foreground with the shipped `general` type, the report as the tool result, Ctrl-C from the tool and from a python input, a real-launch test.
3. TASK-0080.04 (size-3): types as data, `background` and `agent_wait`, `max_running`, the step limit, the session budget, a model other than the type's asked, usage into the totals.
4. TASK-0080.05 (size-2): `agent_send` and `agent_stop`, and what `/clear`, `/model`, `/compact`, `/release` and a row restart do to children.
5. TASK-0080.06 (size-2): watching: the event log, `bh-02 watch`, tmux panes, `/agents` and the status field, the TMUX scrub in the unconfined runner, darwin's tmux-socket check (on a Mac, TASK-0079.15). Can run beside 4 and 5 once 3 lands, since it needs a child to watch.
6. TASK-0080.07 (size-2, later, low priority): project guidance in a child (`memory:files` with a private `commands` registry).

## Consequences

- No second copy of the prompt, approval or access in the jail; a child is a conversation like the parent's, mounted with cordis as it is.
- Approval gains one rule case, used by the agents tools (TASK-0068's memory tool has a case of its own, see the amendment above).
- The person keeps the spend: a model a type didn't choose, and children past the session budget, are asked; Ctrl-C and `/agents stop` end them.
- A child's REPL shares the session's jail once TASK-0074 lands; before that it runs in a jail of its own from the same policy, so sub-agents don't wait on the brig work.

## Defaults set here, for the owner to revise

The reviews asked the owner these; the decision sets a default for each so the work can start, and any can be changed before its task starts: what `/clear`, `/model`, `/compact`, `/release` and a row restart do to children (above); that bh-02 names agents; that a type grants only the listed rows; the session budget (16 children, then asked); that the report is the tool result and `agent_send` text is framed as from the parent agent.

## Reviews

Two reviews, 2026-10-12, neither by the author, both ACCEPT WITH CHANGES; all taken:

- **Composition.** cordis needed no new effect: `performer` plus `use(loader, expose=...)` mounts and retires a child (the draft's "children" effect is gone). The exposed set lacked a way to confirm and carried `models`, which nothing in the realm reads. The loop never calls `show`; the agents row writes the events. Confirm queues safely but needed a label; lifecycle events leaked into the parent's screen; memory in a child was unaddressed; usage had no path to the totals. Re-sized split.
- **Closing review of TASK-0080.01** (2026-10-12): CLOSE; taken: Ctrl-C refuses only the stopped reply's questions; TASK-0080.03 resized to size-5; the split's wording on TASK-0080.06; the M6 milestone brought in line with this decision.
- **Boundaries.** No path to the person (now `asker`); a transcript path the jailed parent can't read (now the person's only); unasked spending on any model with no session cap (now asked past a type's model and the session budget); the unconfined runner keeps `TMUX` (now scrubbed, said to be hygiene); the dropped darwin tmux-socket check (restored as a precondition); the reversal of where types live (recorded); runner state shared with children (said); Ctrl-C leaving spend running (a notice, and `/agents stop`); `/release` kept to REPLs; queued, labelled questions under `--no-jail`.
