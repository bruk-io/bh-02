---
id: decision-0006
title: >-
  Tell the model of the functions the startup files define by progressive
  disclosure, with no decorator
date: '2026-10-16 01:51'
status: proposed
---
## Context

decision-0004 (accepted 2026-10-14, built by TASK-0100, worded by TASK-0105) marks a startup file's
functions with `@helper` (bound in the Python process's namespace; it sets `__bh_helper__`), lists
the marked ones by signature in the first input's output, counts the rest as hidden, and leaves the
docstring to `help(name)`.

The owner, 2026-10-15 and 16, after weighing it: drop the decorator and drop "helper" as an idea.
These are just functions the model has in its REPL, already defined when it starts. What matters is
that the model has details about them in context, disclosed progressively. The python tool must make
the model understand that a startup file's public functions are told to it, take up context, and how
they take it up, since the model writes the project's startup file and so decides what it costs.
And a docstring convention for examples, which a check enforces automatically, with no model, using
ruff and mypy where they can; and the files' typing enforced.

What does not change, and shapes the design:
- The system prompt is fixed for a conversation and built on the host, which cannot run the
  project's startup file (only the jailed Python process may). So the prompt can carry only the
  convention; what a file defines can only arrive from the REPL.
- The project's startup file (`.bh-02/startup.py`) is the model's to write; the person's
  (`$XDG_CONFIG_HOME/bh-02/startup.py`) is theirs, and the jail can't read it (the host hands the
  REPL its text).

Weighed and not taken:
- **A decorator, `@helper` or a renamed `@disclose`.** A bh-02 name in the file, a stand-in to run
  it elsewhere, and a forgotten decorator hides a function from the model with nothing to say so.
- **Each level written out as strings on the decorator.** A typed signature goes stale when the
  function changes and the model calls it wrongly; a second summary duplicates the docstring; a
  source string could differ from the code that runs.
- **Helpers as callable classes, an envelope protocol.** Authoring costs a class per function;
  `help()` and `inspect.getsource()` work badly on instances. The one gap it fills, a useful
  one-line `repr`, the listing gives without it.
- **A `helpers` module with search.** Structural, but a new file and a new word, and nothing to
  search for while every name is shown (point 2).
- **Extras on the decorator (examples, cost, side effects).** Examples belong in the docstring
  (point 4); the rest waits until a function needs it.
- **reST fields (`:param a:`, `:returns:`) as the convention.** They restate the types level 1
  already shows, and would fight a project written in Google or NumPy style. reST is kept where
  every style already uses it: the examples.
- **A docstring checker of bh-02's own for what ruff checks.** Ruff already checks a docstring's
  presence and summary line and calls public what point 1 tells; bh-02 writes only the rule ruff
  lacks (an example).
- **Ruff and mypy on the host, or with the project's config.** mypy imports a config's plugins
  and reads through links the model can make; and a config the model writes is a check the model
  can loosen.

## Decision

1. **Which functions are told.** The functions and classes a startup file defines itself (their
   code is that file: an import is not one) under a public name, with no leading underscore. When
   the file has `__all__`, exactly the callables it names instead, imported ones included: that is
   what `__all__` is for. Everything else the file binds works as before and is not told.
2. **Three levels, and the frame that points at them.**

   | | What | When | From |
   |---|---|---|---|
   | Frame | The convention, the cost (point 3) and the docstring convention (point 4), once | Every request: the python row's section of the system prompt, fixed and cached | bh-02's own text (`python.instructions_for`) |
   | 1 | `name(signature)` for each told function | Pushed once per REPL (a start, `/clear`, a restart, a resume), in the aside before the first input's output: signatures up to 1,500 characters, then the rest by name only, so nothing is hidden | The live object (`inspect.signature`), cleaned on the host as now: control and format characters stripped, each cut at 160 characters, a name that is not an identifier counted, never shown |
   | 2 | The docstring | Pulled only: `help(name)` | The live object, when asked (current after an edit and a reload) |
   | 3 | The source | Pulled only: `inspect.getsource(name)` | The project's file from disk in the jail; the person's from the text the host handed the REPL |

3. **The model is told what a function costs.** The frame says, in the model's terms: every public
   function in a startup file is listed by signature each time a REPL starts, so each costs its
   signature in context in every session; a leading underscore keeps a function working but
   untold; a docstring and the source cost nothing until asked for. So keep public only what is worth
   telling every session, keep its signature short and its defaults plain, and put what it needs to
   say in the docstring.
4. **The docstring convention.** A summary line; then what the signature doesn't already say, in
   the project's own field style (Google when it has none), never the types again, since level 1
   shows them; then examples in reST, which every style shares (Google and NumPy sections are reST
   once Sphinx's napoleon reads them, and the examples inside them are reST in all three):
   - a doctest block (`>>>` calls with their output, a blank line before and after) when the
     output is fixed: it says what a right call returns, and it is the form that can run;
   - a literal block (`::`, the code indented under it) when the output isn't fixed or the use
     takes setup, as for most startup functions (they run tests, call a server): a `>>>` with
     made-up output would be a false claim.

   `help(name)` prints a docstring as written, so the model reads both forms as plain text; Sphinx
   renders them for a project that builds docs. A docstring is pulled with level 2, so it costs
   nothing until asked for. Nothing runs the examples; the model can run the doctest ones with
   `doctest.run_docstring_examples`.
5. **Unchanged from decision-0004:** told at startup only (a function the model writes or edits
   later is its own knowledge; the person's mid-session edits arrive at the next REPL); unconfined
   (`--no-jail`), the aside names the file, the model runs it, and nothing is listed, so the frame's
   sentences must be true either way; a function's signature text is the Python process's, so it is
   cleaned on the host as any output it hands bh-02 to say.
6. **Removed:** `@helper`, the `helper` name in the namespace and `__bh_helper__`, and the word
   "helper" from the model-facing text, the glossary and the docs. TASK-0105's three kinds of
   function become the model's own, the startup files', and tools.
7. **The convention and the types are checked by tools, not left to the model.** The frame states
   point 4 and that the files are type-checked, but whether a function follows them is a check
   that runs the same way every time:
   - **Docstrings: ruff**, `--isolated --select D101,D103,D205,D415,D419`: a docstring on each
     public function and class, a summary line, none empty. Ruff calls public what point 1 tells:
     no leading underscore, and only the names in `__all__` when the file has one (measured
     2026-10-16 on ruff 0.16.7). Ruff has no rule for the rest of point 4, so a rule of bh-02's
     own, standard library only (`ast` and `doctest`'s parser), checks it: an example (a doctest
     block or a `::` literal block), and doctest blocks that parse, each with a blank line before
     it. The blank line after can't be checked: `doctest` reads everything up to it as the
     expected output. Not checked: the field style (the project's own), types repeated in it
     (that depends on the style), whether the examples pass (that runs the file's code).
   - **Types: mypy `--strict`**: every told function annotated (`no-untyped-def`) and the file
     type-checks, since a signature is what the model reads and calls by. A name the REPL
     provides, such as `tools`, is declared with a bare annotation (`tools: Any`), which binds
     nothing when the file runs, so the REPL's own stays, and satisfies mypy (both measured; a
     `__builtins__.pyi` stub on `MYPYPATH` does not: mypy ignores it). The frame tells the model
     so. An import mypy can't find is a finding: the REPL, under bh-02's interpreter, can't import
     it either.
   - **Where: in the jail.** The Python process runs both as programs under bh-02's interpreter,
     whose environment every jail reads, so ruff and mypy become dependencies of the python plugin.
     Never on the host: a project's mypy config can name plugins, which mypy imports, mypy follows
     imports and links through files the model can make, and the model writes the config. bh-02's
     flags only (`--isolated`, `--config-file=`), so the result doesn't depend on a file the model
     can loosen. Unconfined (`--no-jail`) nothing runs unasked (point 5), so neither do they: the
     frame gives the model the commands to run.
   - **When: at every REPL start**, after the files run: the aside names each told function that
     misses and the rule codes it breaks (`D103`, `example`, `no-untyped-def`), never a tool's
     message, which quotes the file; the model runs the tool for the detail. The person's file is
     checked from the text the host hands the REPL. mypy's cache (in the jail's writable roots)
     makes a repeat cheap: 0.2 s warm, 5.3 s cold on today's uncompiled mypy pin (measured).
   - **Without a session**: CI and a pre-commit hook run the same ruff and mypy lines, which bh-02
     documents, and bh-02's example rule as a command, exit status 1 on a finding. Its name and
     home are the build's to choose: `plugin-layering` keeps the app's CLI from importing the
     python plugin.
   - **Advisory in a session**: a finding never stops a file running or hides a function. The
     commands are where it is enforced, by whoever runs them.

## Consequences

- No bh-02 name in a startup file: it runs unchanged outside bh-02, and the model and the person
  read nothing bh-02-specific in it.
- More is told by default (every public function), bounded by the budget and names-only past it.
  A forgotten underscore costs one line; under decision-0004 a forgotten decorator hid a function.
- A startup file that still says `@helper` fails at startup with a NameError, which the startup
  line reports as it reports any failing file: nothing translates the old name (decision-0005's
  "a rename is clean"). The model fixes the project's own; the person, theirs.
- Kept from TASK-0100: the data line the input prints, the host's formatting and cleaning, the cut
  at 160, the identifier rule. Changed: which functions are told, the budget and names-only past
  it, the frame's text. TASK-0105's wording loses "helper".
- After `/compact` the signatures live only in the model's summary, as before; the frame tells it
  how to look again (`help`, `dir`, `inspect`).
- The aside grows by a few words per finding, until the file is fixed. A person's own file can't be
  fixed by the model (the jail can't read it): its findings are the person's, through the commands.
- bh-02 gains two runtime dependencies, about 40 MB (ruff 23 MB, mypy 16 MB). A REPL start in a
  project with no mypy cache yet waits for mypy's cold start until mypy 2.4 is on PyPI, compiled.
- A startup file that uses a name the REPL provides declares it (`tools: Any`): plain Python, not
  a bh-02 import, so the file still runs anywhere.
- Not decided here: a search over functions (not needed while every name is shown); envelopes for
  results (progressive disclosure of output, a design of its own).

## Acceptance

Proposed 2026-10-16 from the owner's choices in conversation: no decorator, no "helper", public
functions told, the model told what they cost and how, a docstring convention for examples (reST
examples, both forms, with the project's own field style), a check of the convention that needs
no model (ruff where it has rules, bh-02's own where it has none), and typing enforced with mypy.
Two parts are the orchestrator's, for the owner to confirm: the 1,500-character budget for
signatures at REPL start, and point 7's rule selection, flags and placement in the jail.
