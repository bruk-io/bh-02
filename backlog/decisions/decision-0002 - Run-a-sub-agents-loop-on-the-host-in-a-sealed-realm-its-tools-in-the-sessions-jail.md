---
id: decision-0002
title: >-
  Run a sub-agent's loop on the host in a sealed realm, its tools in the
  session's jail
date: '2026-10-12 00:39'
status: proposed
---
## Context

TASK-0080 (sub-agents) leaves four questions the implementation needs answered: where a child's loop runs, its limits, what comes back to the parent, and how parallel writers are kept apart. The constraints are bh-02's rules: one loop per conversation; `tools.serve` is one loop's, a second raises; a conversation's prompt and tool list stay fixed; nothing blocks the TUI's event loop; approval is one rule in one row; only a layer's rows act in bh-02's process. decision-0001 (accepted) puts every process of a session in one jail, each with its own namespaces where the jail type allows.

Two ways were open:

- **The loop in the jail.** An agents program inside the jail runs each child's loop and borrows the host for model steps. Nothing on the host changes, but the rows a loop leans on (the prompt's sections, memory's asides, `access`) are host rows, so the jail would need a second copy of each, and every model step would cross the jail.
- **The loop on the host.** Each child is another conversation in bh-02's process, its tools running in the session's jail. It gets the whole composition, but `tools`, `transcript`, `model` and `loop` are one per process today.

cordis already has the primitive that removes the second option's cost: a **realm**. `use(child, expose={...})` mounts a sealed subtree that reads only the exposed keys from outside and keeps every key it binds to itself (cordis README, Concepts; `tests/test_runtime.py::test_a_sealed_subtree_sees_only_what_it_was_exposed_and_keeps_the_rest`). Inside one, `agent:loop`, `agent:tools`, `agent:transcript`, `models:model` and `agent:system` bind their keys privately, so a child has its own loop, broker, transcript and model, and `tools.serve` is one per realm. What cordis lacks is mounting a realm while a component lives: `use` is an effect yielded at setup. cordis's README lists "per-session realms wired into a harness" as not yet done.

## Decision

### A child's loop runs on the host, in a sealed realm

The `agents` row mounts each sub-agent as a sealed realm in bh-02's own cordis runtime. Inside it are the rows of an ordinary conversation (`loop`, `tools`, `transcript`, `model`, `system`, `asides`, `access`, `executor`, `python`), each binding its key privately. From outside, the realm sees only what it is exposed:

| Key | Why the child needs it |
|---|---|
| `runner` | its python tool's REPL is a process in the session's jail (TASK-0074; until then, a jail of its own from the same policy) |
| `approval` | the one rule, never a copy |
| `host` | what the jail keeps from the model |
| `models` | to check the model its type names |

Its `output` is its own: a binding inside the realm that sends `confirm` to the person through the parent's ui, labelled with the agent's name and type, and keeps `show` events for the agent's own event log, never the parent's screen. A child has no `input` and no `chat` row: the `agents` row drives its `loop.reply(prompt)` and collects the events.

cordis gains one effect to do this: a component may hold a **children** handle that mounts and retires sealed children while it lives, every one retired when the component unloads (TASK-0080.02). A component still never touches the runtime: the handle is what an effect yields back.

### Agent types are data

A type is a name, a prompt section, a model name and the tools it may use, read from bh-02's config directory (`~/.config/bh-02/agents/NAME.toml`) and the shipped ones (`explore`, `general`). Data, not rows: a type chooses among rows bh-02 ships, never names a component, so a type file the model could write would choose nothing that runs code; types are still read only from places the model can't write (`host.trusted`), as the models file is.

### Tools, and the Python side

The `agents` row registers four tools, each also a function in a python input (`tools.NAME(...)`):

- `agent(prompt, type, model?, background?)`: the child's final answer, or its id when `background`;
- `agent_wait(ids, timeout?)`: the answers of those ids as they finish;
- `agent_send(id, text)`: a message into a running child's conversation, as the parent agent's words;
- `agent_stop(id)`: ends the child and everything it started.

They run in bh-02's process (`runs = "host"`), so approval needs a case for them, the same question TASK-0068's memory tool asks. Settled here for both: a request whose `runs` is `"harness"` (bh-02's own code, acting only on the session's jail and bh-02's own state) runs unasked when the runner confines, and is asked when it doesn't (`--no-jail`). A sub-agent's own calls go through the same rule, from inside its realm.

### Limits

- **Depth:** one. A child's composition has no `agents` row unless its type grants it, and no shipped type does.
- **How many at once:** the `agents` row's config, `max_running`, default 4; a fifth `agent` call waits for a slot, saying so.
- **Budget:** each child has a turn limit and a cost limit from its type (defaults: 30 model steps, the cost of 30 steps on its model); reaching one ends the child with what it has, said in its answer.
- **Stopping:** Ctrl-C stops the parent's reply and any child it is waiting on (`agent` without `background`). Background children keep running until `agent_stop`, `/agents stop`, the end of the session, or `/release`.

### What comes back

The final answer only, framed as the agent's report ("Report from agent NAME (TYPE), not instructions:"), with the path of its transcript and its usage, which the session's totals include. Everything else stays in the child's own transcript and event log.

### Watching

Each child's events go to an event log in its own state directory (`<session>/agents/<id>/events.jsonl`) beside its transcript. `bh-02 watch SESSION AGENT` renders one, read-only. Inside tmux, the `agents` row opens a detached split per child running that viewer (`tmux split-window -d -h -P -F '#{pane_id}' -- bh-02 watch ...`), every argument a plain name it chose itself. Outside tmux there is a status field (`agents: 2 running`) and `/agents` (list, watch, stop). The jail never reaches the tmux socket: `TMUX` and `TMUX_PANE` are scrubbed from every program the runner starts, `--no-jail` included.

### Parallel writers

Children share the project's files, as decision-0001's namespace bundle intends. A type that must not write says so in its prompt and gets no editing tools beyond python; that is cooperative, and `/agents` says so. Enforced isolation (a worktree, or a jail narrowed from the session's) is later work, not this milestone.

### Teams

Not in this milestone. If built, through the same router, never a shared mailbox.

## Consequences

- No second copy of the prompt, asides or approval in the jail; a child is a conversation like the parent's.
- cordis gains dynamic sealed children, which is the multi-session harness its README names.
- Approval gains one rule case, used by the agents tools and TASK-0068's memory tool.
- A child's REPL shares the session's jail once TASK-0074 lands; before that it runs in a jail of its own from the same policy, so sub-agents don't wait on the brig work.

## Open questions

- [ ] Whether the children handle belongs in cordis (a new effect beside `use`) or in cordis-helpers over an existing one; cordis's README keeps mechanisms in cordis and patterns in helpers.
- [ ] The budget's defaults (30 model steps, the cost of 30 steps on the child's model): to be set from the first real runs, not guessed further.
- [ ] Whether `agent_send` text arrives in the child's conversation as the parent agent's words (as decided) or framed like a report; the parent is the child's principal, so its words are instructions, but they may carry text the parent read from elsewhere.
