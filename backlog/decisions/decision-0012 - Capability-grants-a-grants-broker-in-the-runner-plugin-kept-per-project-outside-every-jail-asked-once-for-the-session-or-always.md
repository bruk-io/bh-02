---
id: decision-0012
title: >-
  Capability grants: a grants broker in the runner plugin, kept per project
  outside every jail, asked once, for the session or always
date: '2026-11-04T12:41:00Z'
status: proposed
---
## Context

TASK-0181, in the owner's words: let other plugins request whatever they need, let the person
approve once or always, shape brig's policy per project from that, with the runner managing it.
Network is approved per hostname and/or IP address, plus the port.

What exists:
- **Policy:** the jail's policy is `spec_for`, plus the runner row's hand-edited `allow`. The
  environment allow-list is `runner.toml` (decision-0010).
- **Approval:** one rule, `runner:approval`, which keeps no memory of an answer.
  `output.confirm(question) -> bool` is the only way to ask.
- **bruk-io/brig:**
  - It fixes a jail's paths and environment when the jail is created.
  - Its egress (its decision-0009) allows destinations per host and port through a proxy. It
    changes them live (`allow_egress`, `revoke_egress`), and hands back refusals as data
    (`egress_decisions`).
  - On brig main, `network` reads best_effort whenever the jail sees any root, and violated when a
    root shows `/run`, `/tmp` and the like (its TASK-0043).
- **bh-02's pin:** bh-02 pins brig 1c7c8d4, which predates egress.

## Decision

1. **A grant is a capability with a reason.**
   - **Kinds:** `read` (an absolute path), `write` (an absolute path), `env` (a variable name), or
     `net` (brig's `Destination`: an exact hostname, `*.suffix` or an IP literal, always with a
     port).
   - **Who asks:** a row, an input, an extension or a sub-agent. The person always sees who.
2. **The answers are once, always or no.**
   - **once:** for the rest of this session, held in memory.
   - **always:** for this project, from now and at every later start.
   - **no:** kept for the session, so the same request is not asked again.

   Ctrl-C withdraws the question and records nothing. "Once" never means "this one call": a path
   grant would then need a jail of its own, which breaks CodeAct's namespace.
3. **Where "always" lives.** `$XDG_STATE_HOME/bh-02/projects/<project>/grants/grants.toml`:
   - It is keyed as auto memory is (`project_of(cwd)`), and it sits beside `memory/`, not in it.
   - It is a new `host.grants` field. The bootstrap creates the directory at 0700 before any jail
     starts, because a deny on an absent path would make brig hold a placeholder there.
   - It is read and written only through `host_paths` (`read_beneath`, `write_beneath`, 0600).
   - `spec_for` masks it and denies writing it, which matters when bh-02 runs from the home
     directory.
4. **Taking effect.**
   - **Egress:** live. `allow_egress` and `revoke_egress` on every running jail of the runner. A
     revoke does not cut a connection already open.
   - **A path or env grant mid-session:** restarts the program it is for before its next input.
     The extensions process restarts at once. The Python process restarts before the next input,
     losing its variables, and the person and the model are told.
   - **A row's standing need:** requested before the first start, so it costs nothing.
5. **What is never asked, and what is never grantable.**
   - **Unasked:**
     - a request already inside the current policy, answered "standing";
     - a grant written in a layer's runner `config`, which is the person's own composition, as
       `write` and `env` are today.
   - **Asked:** everything else, from a plugin at runtime, an input, an extension or a sub-agent.
   - **Never grantable, refused with the reason:**
     - `host.secrets`, the grants directory and `CREDENTIALS`;
     - layer files, `code`, `trusted`, interpreters and the link directories on the way to them;
     - a variable a model key reads (the fresh set TASK-0184 provides);
     - the proxy variables.
6. **Network refusals become prompts.**
   - The runner drains `egress_decisions` for each running jail, without blocking.
   - **Not granted:** the refused destination is asked while the call still runs. The program
     has its 403 already; on a yes, an aside tells the model the destination is now allowed and
     it may retry.
   - **A name pointing at a private address:** the prompt offers only an IP-literal grant, with a
     warning.
   - **Unresolvable names and unreadable requests:** not asked; the model is told.
   - **Wildcards:** a prompt from a refusal never offers one. A plugin's request or `/grants` may
     name `*.suffix`.
7. **The broker.** `grants`, bound by a new `runner:grants` row that depends on nothing:
   - `need(request)` (acquired, leaving with the row);
   - `ask(request)`;
   - `granted()` (a frozen value the runner reads at each start);
   - `on_change(fn)`;
   - `serve(prompt)`;
   - `list()`;
   - `revoke(id)`.

   A row `runner:grant_prompt` (depending on `grants`, `output`, `asides` and `commands`) asks
   through a new `output.choose(question) -> str`, with `confirm` kept for yes/no. It registers
   `/grants` (list and revoke), and `bh-02 grants` does the same outside a session. `approval`
   depends on neither `grants` nor the requesters, so a grant never reloads it.
8. **The prompt shows four things before "always":** what, who asks and why, when it applies, and
   what it does to the grades. A path that would make `network` violated, such as a socket
   directory, says so: approval would then stop counting the jail as confined.
9. **Moving to brig main, and the network grade.**
   - **Every start passes an `EgressPolicy`.** It is empty when nothing is granted, so egress is
     always enforced and live grants work.
   - **What approval counts as confined:** `network: best_effort` when the start had an egress
     policy. The remaining gap is a socket the host puts under a visible root, which the pinned
     brig already had while grading it enforced. `violated` never counts.
   - **Roots under a socket directory are refused at start.** A project, a `write` root, scratch
     or memory under `/tmp`, `/var/tmp` or `/run`, or under `$XDG_RUNTIME_DIR`, is refused with a
     message saying why. bh-02's own jail tests move their projects off `/tmp`.
10. **`allow` goes.**
    - Writing CLAUDE.md and AGENTS.md becomes the policy's default.
    - Any other self-modifying path (`.git/hooks`, `.envrc`) is a `write` grant on that exact
      path. It is always asked, and its prompt warns that it can run code outside the jail later.
    - `runner.toml` stays the person's standing environment allow-list across projects.
    - `access` is unchanged: it is a check before a file is opened, not the wall.

## Consequences

- **Build tasks, in order:**
  1. **Move the brig pin (size 5).** Item 9, stdio as pipes, the new errors, roots under socket
     directories refused, jail tests off `/tmp`.
  2. **The grant values and store (size 3).** Pure `grants.py`: the values, validation and the
     never-grantable floor. Then the store, `host.grants`, the bootstrap mkdir, and the mask and
     deny. Runs beside task 1.
  3. **`spec_for` and `to_brig` take grants (size 3).** `allow` removed. Needs tasks 1 and 2.
  4. **The broker and its contracts (size 3).** `runner:grants`, CONTRACTS.md, the sub-agent
     realm's key, `/grants` and `bh-02 grants`.
  5. **The prompt (size 5).** `output.choose`, the tui modal's once, always and no keys,
     subagents forwarding, and `runner:grant_prompt`.
  6. **Live egress (size 3).** `allow_egress` and `revoke_egress`, and the refusal poller.
  7. **Requesters (size 5).** A `grant(...)` the model's Python can call, the restart before the
     next input, the python plugin's own needs, and extension requests.
  8. **Docs and the jail battery (size 2).**

  Tasks 4, 5 and 6 follow task 3; task 7 comes last.
- **Prerequisites:**
  - TASK-0183: no "jailed" where nothing jails.
  - TASK-0184: the fresh key-variable set.
- **What stops working:** a layer naming `allow` fails at boot with the loader's error.
- **Asks of brig:** export `SOCKET_DIRECTORIES`, or a pure `ceilings_for(FsPolicy, egress)`, so the
  prompt can predict a grade without copying brig's list.
- **What the owner accepts with this:**
  - "once" is the session;
  - the Python process restarts for a path or env grant;
  - `network: best_effort` counts as confined with egress enforced.
