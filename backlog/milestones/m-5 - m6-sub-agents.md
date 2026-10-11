---
id: m-5
title: "M6 Sub-agents"
---

## Description

Sub-agents the main agent can start from a tool call or from code in a python input, each one visible to the person, none able to reach anything its parent couldn't.

## What Claude Code does

Read from the CLI bundled with claude-agent-sdk 0.2.159 (2.1.281) and its tool definitions. Its Agent tool takes a prompt, an agent type, a model, `run_in_background` and optional isolation in a git worktree; the child runs in-process with a fresh context and only its final message comes back; a background one notifies when it ends, and SendMessage continues one. Agent types are `.claude/agents/*.md` (prompt, tools, model, limits). Agent teams: `teammateMode` is `auto`, `tmux`, `iterm2` or `in-process`; with tmux each teammate is a separate `claude` process in a split pane (`tmux split-window -d -h -l 70% -P -F '#{pane_id}' -- claude --agent-id ... --parent-session-id ...`), and teammates message each other through a mailbox directory.

## Design so far (with the owner, 2026-10-10)

- A sub-agent lives in its parent's jail, so it can reach nothing the parent couldn't, and starting one starts no jail. Its python tool is another REPL process in the same jail.
- A jail holds more than one process: a session has one jail, started once, that all its programs run in (the main REPL, the extensions process, sub-agents' REPLs). Today each program is a jail of its own, one launch each, which also fits Docker/OCI (in brig's stated purpose) badly, since a container is something you exec into. First pieces: TASK-0073 (brig) and TASK-0074 (the runner).
- Model steps stay on the host: the credential, the network and Claude Code never enter the jail. The host checks the model a child asks for and enforces its budget.
- The interface is tools: `agent(prompt, type, model?, background?)`, `agent_wait(ids)`, `agent_send(id, text)`, `agent_stop(id)`. Every registered tool is a function in a python input, so fan-out and fan-in are code: `tools.agent(..., background=True)` in a loop, then `tools.agent_wait(ids=...)`.
- Agent types are data (a prompt, a tool subset, a model name), interpreted inside the jail, so they may live in the project, as Claude Code's do.
- Watching: each agent shows in a tmux pane running a host-side viewer of its events (inside tmux, a detached split; outside it, a detached session to attach to; without tmux, a status field, `/agents` and a viewer command). The child never runs in a pane itself, so the jail never reaches the tmux socket; typing in a pane reaches the child through the host.
- Rules:
  - a child is never less confined than its parent;
  - model text never reaches a command line or a tmux argument, only plain names (tmux formats can run commands, `#(...)`);
  - a child's result is data, framed as its report, never instructions;
  - a child's approval questions go to the person, never to the parent model, labelled with the agent;
  - `agent_send` is marked as the parent agent's words, not the person's;
  - children end with their parent and with the jail;
  - the jail never reaches the tmux server's socket: scrub `TMUX` and `TMUX_PANE` under `--no-jail` too, and check that Seatbelt stops a connection to the socket in /tmp.
- Agents talk only through bh-02, never to each other directly: a message from one agent to another (a prompt, `agent_send`, a result) is a call over the sender's own socket to bh-02, which routes it to the receiver's conversation (decision-0001, "Between processes and between agents"). bh-02, the router, decides:
  - who may message whom: parent and child now, teams later;
  - framing: a result is "the agent's report", an `agent_send` is "the parent agent's words", never the person's;
  - provenance: which process sent a message, known by the socket it came over, never by a field the sender writes (brig's law 6);
  - authority: a message carries none; anything that needs approval goes to the person;
  - visibility: every message lands in a transcript the person can watch in tmux.
- Shared within one jail (decision-0001's per-process namespace bundle on bwrap): sibling agents share the project's files, `.bh-02/kernel.py` among them, and nothing else: each sees only its own socket, scratch directory, processes and IPC. Where a jail type can't give that (Seatbelt, or nested user namespaces blocked), the rest is shared too, counted as shared media and said. A stricter child (read-only, or writing only in a worktree) is opt-in per type, in a jail of its own compiled from `parent_spec.narrowed_to(type_spec)`, brig's pointwise meet, a subset of both.

## Open questions

- [ ] Where a child's loop runs: in the jail (an agents program runs it; the host's prompt sections and asides need a second copy there) or on the host (it gets the whole composition; `tools.serve`, `transcript` and `model` become per conversation).
- [ ] Limits: depth (a child gets `agent` only if its type grants it), how many at once, a budget per agent, and whether Ctrl-C in the parent stops a foreground child.
- [ ] What comes back: the final answer only, with the child's transcript for detail and its usage added to the session's.
- [ ] Parallel writers: worktrees inside the parent's writable roots, or narrowed jails.
- [ ] Teams (agents messaging each other): later, or never. If later, through the same router, never a shared mailbox (a sender's "from" would be its own claim).
