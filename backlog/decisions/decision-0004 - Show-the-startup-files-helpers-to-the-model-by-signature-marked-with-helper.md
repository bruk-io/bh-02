---
id: decision-0004
title: 'Show the startup files'' helpers to the model by signature, marked with @helper'
date: '2026-10-14 15:55'
status: accepted
---
## Context

The owner (2026-10-14) wants the functions in the startup files to cost little context: the
name and signature always in front of the model, the docstring only when it asks, and only for
the functions the file's author chooses.

How it works today (python plugin):

- A new, confined Python process runs each startup file as an input of its own (the person's,
  `$XDG_CONFIG_HOME/bh-02/kernel.py`, then the project's, `.bh-02/kernel.py`). The input is
  built on the host by `client._startup_input`; it prints, last, the public names the file bound,
  and the first input's output begins `(PATH ran first and defined: a, b, c)`.
- That is every public name, by name only: no signature, no docstring. The model sees more only
  by asking (`help(name)`, `inspect.getsource(name)`).
- bh-02's own tools already do the rest of the pattern: `worker._function` gives each
  `tools.NAME` a `__signature__` and `__doc__` from its spec, and the model is told the names
  once, with `help(tools.NAME)` for what one takes.
- The system prompt is fixed for a conversation and is built on the host, which cannot run the
  project's startup file (only the jailed Python process may). So a helper's signature can't be
  in the `python` section; it has to come from the Python process, in an input's output, as the
  names do now.

Kept simple on purpose: one marker, REPL-only. No slash commands from helpers (a row or an
extension registers a command), no directory of startup files, no change to which environment
the REPL runs in (a separate design), no tracking of helpers after startup.

## Decision

1. **`helper` is bound by the Python process.** The worker puts `helper` in the namespace when
   it starts, beside `tools`, before any startup file runs. `@helper` sets one attribute on what
   it decorates (`__bh_helper__ = True`) and returns it unchanged, so a decorated function is the
   same function, and a file run outside bh-02 can define a stand-in
   (`try: helper` / `except NameError: def helper(f): return f`). An input that binds `helper` to
   something of its own keeps it, as with `tools`; only bh-02's marker counts, since the listing
   reads the attribute, not the name.
2. **The startup line lists helpers by signature and counts the rest.** After each startup file,
   the input prints its helpers (the callables it bound that carry the attribute), each as
   `name(signature)` from `inspect.signature`, then how many other public names it bound:
   `(PATH ran first: helpers run_tests(path='.', *, quiet=True), changed(); 3 other names
   hidden)`. A file with no helpers says `no helpers; N names hidden`. Undecorated names are
   hidden: they exist and work, they are just not told.
3. **A signature is the Python process's text, so it is held like any output.** Control
   characters are stripped, each signature is cut at 160 characters (a default's `repr` can be
   anything, and the project's file is model-written), and one `inspect.signature` can't read is
   `name(...)`.
4. **The docstring is on request, by Python's own `help(name)`.** Nothing new: it already works.
5. **The `python` section says the convention once**, in `_keep`: "`@helper` on a function in a
   startup file lists it with its signature when the REPL starts; `help(name)` shows its
   docstring; a startup file's other names are not listed." The prompt stays fixed; the
   signatures arrive with the first input's output, never in the prompt.
6. **Told at startup only.** A REPL started again runs the startup files again and tells them
   again. A helper the model defines or redefines in a later input is not announced: the model
   wrote it.
7. **Unconfined (`--no-jail`) stays as today**: the aside names the file and the model runs it
   with `exec(open(PATH).read())`, which lists nothing. The person reads every input there
   anyway, and a long listing input to approve would be more than was asked.

Where it lands: `worker.py` (binds `helper`), `client.py` (`_startup_input` and the startup
aside's text), `python.py` (`_keep`'s sentence), the plugin README,
`docs/bh-02/how-it-works/python-tool.md`, and GLOSSARY.md (`helper`).

## Consequences

- Context: a startup file of twenty functions with three marked costs three signatures and a
  count, not twenty names.
- Existing startup files lose their listing until their author marks functions: their names
  are then only counted. This is visible (the count) and intended (the owner chose hidden by
  default).
- The worker stays standard library only (`inspect` is), and the gate's `worker-stdlib-only`
  holds.
- A helper the model writes in the project's startup file is listed the same way, so the model
  can grow its own toolbox and see it next session.
- After `/compact` the signatures live only in the model's summary (the python row is kept
  across it, and `/compact` already asks the model to name what the namespace holds); `/clear`
  and a new run tell them again. Accepted as a limit, not built around.
- The 160-character cut is the one point beyond the owner's ask, kept: it keeps the line cheap
  when a default's `repr` is long, which is the point of the feature.
- Not decided here, each its own work: a directory of startup files; the environment the REPL
  runs in (owner, 2026-10-14: a `.venv` per project); naming (the startup files are still
  `kernel.py`, an older name the naming work may change, which this decision does not depend on).

## Accepted

2026-10-14, by Fable standing in for the owner (he delegated these decisions): accepted with two
changes, both applied above: unconfined stays as today (was: the model runs the listing input),
and the `/compact` limit is written down. Built by TASK-0100, after TASK-0099.02 renames the
startup files and the python row's class.
